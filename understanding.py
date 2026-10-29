"""Evidence preparation and reviewed semantic ingestion; no model API execution."""
import json
from pathlib import Path

import asset_index as ix
from montage import read, save, fingerprint, probe, portrait_geometry, media_duration, number, run


def template(asset):
    return {
        'asset_hash': asset['hash'], 'paths': json.loads(asset['paths']),
        'duration': asset['duration'],
        'product': {'brand': None, 'model': None, 'source': 'unknown',
                    'reuse_scope': 'unknown', 'restrictions': []},
        'rights': {'source': None, 'usage': 'unknown'},
        'overview': '', 'unknowns': [],
        'review': {'overview': False, 'product_identity': False,
                   'action_boundaries': False},
        'segments': [],
        'segment_template': {
            'id': '', 'start': None, 'end': None,
            'facts': {'description': '', 'subject': '', 'action': '', 'scene': '',
                      'descriptions': {}, 'aliases': [], 'tags': []},
            'usable_ranges': [],
            'interpretation': {'suitable_for': [], 'does_not_prove': []},
            'quality': {'issues': [], 'shot_size': '', 'screen_direction': ''},
            'evidence': [],
            'review': {'facts': False, 'action_boundaries': False},
        },
    }


def prepare(args):
    folder = Path(args.output).resolve()
    db = ix.connect(args.database)
    try:
        assets = [dict(row) for row in db.execute('SELECT * FROM assets ORDER BY hash')]
    finally:
        db.close()
    created = existing = 0
    for asset in assets:
        path = folder / 'assets' / (asset['hash'] + '.json')
        if path.exists():
            existing += 1
            continue
        save(path, {'schema_version': 1, 'status': 'pending_analysis',
                    'asset': template(asset)})
        created += 1
    print(f'已创建 {created} 份待理解记录，保留 {existing} 份已有记录；未执行视觉分析。')


def status(args):
    folder = Path(args.output).resolve()
    counts = {}
    for path in sorted((folder / 'assets').glob('*.json')):
        record = read(path)
        state = record.get('status', 'unknown')
        counts[state] = counts.get(state, 0) + 1
    print(json.dumps({'records': sum(counts.values()), 'status': counts},
                                 ensure_ascii=False, indent=2))


def source(asset):
    path = next((p for p in asset['paths'] if Path(p).is_file()
                 and fingerprint(p) == asset['asset_hash']), None)
    if not path:
        raise ValueError('原素材缺失或内容已改变')
    info = probe(path)
    portrait_geometry(info)
    return path, media_duration(info, 'video')


def observe(args):
    """Prepare timed evidence for Codex; never invent observations."""
    record_path = Path(args.record).resolve()
    record = read(record_path)
    asset = record['asset']
    path, duration = source(asset)
    start = args.start
    end = duration if args.end is None else args.end
    if not all(number(v) for v in [start, end, args.every]) or not 0 <= start < end <= duration or args.every <= 0:
        raise ValueError('观察区间或抽帧间隔无效')
    folder = record_path.parent.parent / 'evidence' / asset['asset_hash']
    folder.mkdir(parents=True, exist_ok=True)
    evidence = []
    t = start
    while t < end:
        dest = folder / f'{t:.6f}.jpg'
        if not dest.exists():
            run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', t, '-i', path,
                 '-frames:v', '1', '-vf', 'scale=720:-2', dest])
        evidence.append({'time': t, 'path': str(dest)})
        t += args.every
    manifest = folder / f'observation-{start:.6f}-{end:.6f}-{args.every:.6f}.json'
    save(manifest, {'asset_hash': asset['asset_hash'], 'source': path,
                    'start': start, 'end': end, 'evidence': evidence,
                    'instruction': '由 Codex 查看图片并按动作加密观察；抽帧不代表完成语义理解。'})
    print(manifest)


def import_understanding(args):
    record = read(args.record)
    asset = record['asset']
    path, duration = source(asset)
    from planner import usable_ranges
    if record.get('status') != 'reviewed':
        raise ValueError('理解记录尚未复核')
    product = asset['product']
    scope = product.get('reuse_scope')
    if scope not in {'unknown', 'product_specific', 'generic_context'}:
        raise ValueError('产品复用范围无效')
    if scope != 'unknown' and asset.get('review', {}).get('product_identity') is not True:
        raise ValueError('声明产品复用范围前需要核对产品身份')
    if asset.get('rights', {}).get('usage', 'unknown') not in {'unknown', 'allowed', 'prohibited'}:
        raise ValueError('rights.usage 必须为 unknown/allowed/prohibited')
    updates, ids = [], set()
    for segment in asset['segments']:
        sid = segment['id']
        a, b = segment['start'], segment['end']
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('语义片段 ID 为空或重复')
        ids.add(sid)
        if not number(a) or not number(b) or not 0 <= a < b <= duration:
            raise ValueError('语义片段必须位于原视频范围内')
        review = segment.get('review', {})
        if review.get('facts') is not True or review.get('action_boundaries') is not True:
            raise ValueError('语义片段的事实和边界必须实际复核')
        evidence = segment.get('evidence', [])
        if not evidence or any(not number(e.get('time')) or not a <= e['time'] <= b
                               or not Path(e.get('path', '')).is_file() for e in evidence):
            raise ValueError('需要片段范围内可读取的时间证据')
        labels = dict(segment['facts'])
        if not isinstance(labels.get('description'), str) or not labels['description'].strip():
            raise ValueError('需要非空的画面事实描述')
        ranges = segment.get('usable_ranges', [])
        if not ranges:
            raise ValueError('需要明确标注可用区间')
        usable_ranges({'usable_ranges': ranges}, a, b)
        labels.update(segment.get('quality', {}))
        labels.update(usable_ranges=ranges, product=product, rights=asset.get('rights', {}),
                      interpretation=segment.get('interpretation', {}), evidence=evidence,
                      source='codex-reviewed')
        ix.label_text(labels)
        cid = 'semantic:' + asset['asset_hash'] + ':' + sid
        updates.append((cid, asset['asset_hash'], a, b,
                        json.dumps([e['path'] for e in evidence]),
                        json.dumps(labels, ensure_ascii=False)))
    db = ix.connect(args.database)
    try:
        if not db.execute('SELECT 1 FROM assets WHERE hash=?', (asset['asset_hash'],)).fetchone():
            raise ValueError('请先在此数据库索引原视频')
        old = [dict(r) for r in db.execute(
            'SELECT * FROM clips WHERE asset_hash=? AND id LIKE ?',
            (asset['asset_hash'], 'semantic:%'))]
        history = Path(args.record).resolve().parent.parent / 'imports' / (asset['asset_hash'] + '.json')
        from workflow import archive
        archive(history)
        save(history, {'record': record, 'previous_clips': old})
        with db:
            db.execute('DELETE FROM clips WHERE asset_hash=? AND id LIKE ?',
                       (asset['asset_hash'], 'semantic:%'))
            db.executemany('INSERT INTO clips(id,asset_hash,start,end,frames,labels,reviewed) VALUES(?,?,?,?,?,?,1)', updates)
            db.execute('UPDATE assets SET paths=? WHERE hash=?',
                       (json.dumps(list(dict.fromkeys([path] + asset['paths']))), asset['asset_hash']))
    finally:
        db.close()
    print(f'已导入 {len(updates)} 个语义片段，可用于 search/candidates/auto-plan；选片仍需项目复核。')


def register(sub):
    p = sub.add_parser('prepare-understanding', help='创建长期素材理解记录，不调用模型')
    p.add_argument('--database', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(func=prepare)
    p = sub.add_parser('understanding-status', help='查看素材理解记录状态')
    p.add_argument('--output', required=True)
    p.set_defaults(func=status)

    p = sub.add_parser('observe-media', help='为 Codex 准备带时间码的观察证据')
    p.add_argument('record'); p.add_argument('--start', type=float, default=0)
    p.add_argument('--end', type=float); p.add_argument('--every', type=float, default=2)
    p.set_defaults(func=observe)
    p = sub.add_parser('import-understanding', help='将已复核语义片段接入检索和规划')
    p.add_argument('record'); p.add_argument('--database', required=True)
    p.set_defaults(func=import_understanding)
