"""Incremental shot index and local lexical retrieval, no model API calls."""
import argparse
import json
import math
import re
import sqlite3
import unicodedata
import hashlib
from pathlib import Path

from montage import fingerprint, probe, read, run, save, media_duration, portrait_geometry

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS assets(
          hash TEXT PRIMARY KEY, paths TEXT NOT NULL, duration REAL NOT NULL,
          settings TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clips(
          id TEXT PRIMARY KEY, asset_hash TEXT NOT NULL,
          start REAL NOT NULL, end REAL NOT NULL, frames TEXT NOT NULL,
          labels TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0);
    ''')
    return db


def index_library(args):
    library = Path(args.library).resolve()
    if not library.is_dir():
        raise ValueError('素材库目录不存在')
    if args.window <= 0 or not math.isfinite(args.window) or not 0 < args.scene < 1:
        raise ValueError('window 必须大于零，scene 必须在 0 和 1 之间')
    db_path = Path(args.database).resolve()
    db = connect(db_path)
    frames_root = db_path.parent / (db_path.stem + '-frames')
    settings = json.dumps({'window': args.window, 'scene': args.scene, 'version': 1}, sort_keys=True)
    stats = {'indexed_files': 0, 'cached_files': 0, 'clips_created': 0, 'repaired_frames': 0,
             'excluded': [], 'failed': []}
    for path in sorted(library.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        try:
            info = probe(path)
            try:
                portrait_geometry(info)
            except ValueError as exc:
                stats['excluded'].append({'path': str(path), 'reason': str(exc)})
                continue
            digest = fingerprint(path)
            old = db.execute('SELECT * FROM assets WHERE hash=?', (digest,)).fetchone()
            if old and old['settings'] == settings:
                for clip in db.execute('SELECT * FROM clips WHERE asset_hash=?', (digest,)):
                    for dest, fraction in zip(json.loads(clip['frames']), [0.1, 0.5, 0.9]):
                        dest = Path(dest)
                        if not dest.exists() or dest.stat().st_size == 0:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss',
                                 clip['start'] + (clip['end'] - clip['start']) * fraction,
                                 '-i', path, '-frames:v', '1', '-vf', 'scale=360:-2', dest])
                            if not dest.is_file() or not dest.stat().st_size:
                                raise ValueError('缓存抽帧修复失败')
                            stats['repaired_frames'] += 1
                paths = json.loads(old['paths'])
                if str(path) not in paths:
                    paths.append(str(path))
                db.execute('UPDATE assets SET paths=? WHERE hash=?', (json.dumps(paths), digest))
                db.commit()
                stats['cached_files'] += 1
                continue
            if old:
                raise ValueError('该文件已用另一切分配置建库；请使用新的数据库保留旧标注')
            if not any(s['codec_type'] == 'video' for s in info['streams']):
                raise ValueError('没有视频轨道')
            duration = media_duration(info, 'video')
            # Scene detection gives proposals, not semantic action boundaries.
            import subprocess
            detection = subprocess.run(['ffmpeg', '-v', 'info', '-nostdin', '-i', str(path),
                '-vf', f"select='gt(scene,{args.scene})',showinfo", '-an', '-f', 'null', '-'],
                capture_output=True, text=True)
            if detection.returncode:
                raise ValueError(detection.stderr[-1000:])
            cuts = sorted(set([0.0, duration] + [float(x) for x in re.findall(r'pts_time:([\d.]+)', detection.stderr)
                                               if 0 < float(x) < duration]))
            intervals = []
            for start, end in zip(cuts, cuts[1:]):
                count = max(1, math.ceil((end - start) / args.window))
                for i in range(count):
                    a = start + (end - start) * i / count
                    b = start + (end - start) * (i + 1) / count
                    if b - a >= 0.1:
                        intervals.append((a, b))
            rows = []
            folder = frames_root / digest[:20]
            folder.mkdir(parents=True, exist_ok=True)
            for start, end in intervals:
                cid = f'{digest[:20]}-{round(start * 1e6)}-{round(end * 1e6)}'
                frames = []
                for i, fraction in enumerate([0.1, 0.5, 0.9]):
                    dest = folder / f'{cid}-{i}.jpg'
                    if not dest.exists():
                        run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', start + (end - start) * fraction,
                             '-i', path, '-frames:v', '1', '-vf', 'scale=360:-2', dest])
                    if not dest.exists():
                        raise ValueError('无法抽取关键帧')
                    frames.append(str(dest))
                labels = {'description': '', 'subject': '', 'action': '', 'scene': '',
                          'descriptions': {'en': '', 'es': ''}, 'aliases': [],
                          'tags': [], 'hint_only': str(path.relative_to(library)), 'source': 'unlabeled'}
                rows.append((cid, digest, start, end, json.dumps(frames), json.dumps(labels, ensure_ascii=False)))
            db.execute('INSERT INTO assets VALUES(?,?,?,?)', (digest, json.dumps([str(path)]), duration, settings))
            db.executemany('INSERT INTO clips(id,asset_hash,start,end,frames,labels) VALUES(?,?,?,?,?,?)', rows)
            db.commit()
            stats['indexed_files'] += 1
            stats['clips_created'] += len(rows)
        except (OSError, ValueError, KeyError) as exc:
            db.rollback()
            stats['failed'].append({'path': str(path), 'error': str(exc)})
    # Queue includes existing labels, so repeat indexing never erases annotation.
    queue = []
    for row in db.execute('SELECT * FROM clips ORDER BY asset_hash,start'):
        queue.append({'id': row['id'], 'start': row['start'], 'end': row['end'],
                      'frames': json.loads(row['frames']), 'labels': json.loads(row['labels']),
                      'reviewed': bool(row['reviewed'])})
    queue_file = db_path.with_suffix('.label-queue.json')
    queue_data = {'clips': queue}
    if queue_file.exists() and read(queue_file) != queue_data:
        n = 2
        while db_path.with_suffix(f'.label-queue-{n}.json').exists():
            n += 1
        queue_file = db_path.with_suffix(f'.label-queue-{n}.json')
    save(queue_file, queue_data)
    stats['label_queue'] = str(queue_file)
    save(db_path.with_suffix('.index-report.json'), stats)
    db.close()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats['failed']:
        raise ValueError('部分素材索引失败，见 index-report.json；已完成素材可以复用')


def import_labels(args):
    db = connect(args.database)
    incoming = read(args.labels)['clips']
    # Validate all entries first: a bad batch must not partially change labels.
    seen, updates = set(), []
    for entry in incoming:
        cid = entry['id']
        if cid in seen:
            raise ValueError(f'重复片段 ID：{cid}')
        seen.add(cid)
        row = db.execute('SELECT * FROM clips WHERE id=?', (cid,)).fetchone()
        if not row:
            raise ValueError(f'未知片段：{cid}')
        labels = entry['labels']
        for key in ['description', 'subject', 'action', 'scene']:
            if not isinstance(labels.get(key, ''), str):
                raise ValueError(f'{cid}: {key} 必须是字符串')
        for key in ['tags', 'aliases']:
            if not isinstance(labels.get(key, []), list) or not all(isinstance(t, str) for t in labels.get(key, [])):
                raise ValueError(f'{cid}: {key} 必须是字符串列表')
        descriptions = labels.get('descriptions', {})
        if not isinstance(descriptions, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in descriptions.items()):
            raise ValueError(f'{cid}: descriptions 必须为语言代码到描述的映射')
        reviewed = entry.get('reviewed', False)
        if type(reviewed) is not bool:
            raise ValueError('reviewed 必须是布尔值')
        if reviewed and not labels.get('description', '').strip():
            raise ValueError(f'{cid}: 已复核片段必须有画面描述')
        for key in ['shot_size', 'screen_direction']:
            if not isinstance(labels.get(key, ''), str):
                raise ValueError(f'{cid}: {key} 必须是字符串')
        from planner import usable_ranges
        usable_ranges(labels, row['start'], row['end'])
        updates.append((json.dumps(labels, ensure_ascii=False), int(reviewed), cid))
    with db:
        db.executemany('UPDATE clips SET labels=?,reviewed=? WHERE id=?', updates)
    db.close()
    print(f'已导入 {len(updates)} 条标注')


def normalize(text):
    # Accent-insensitive lookup, but preserve ñ (año and ano are different).
    decomposed = unicodedata.normalize('NFD', text.casefold().replace('’', "'"))
    return unicodedata.normalize('NFC', ''.join(c for c in decomposed if not unicodedata.combining(c) or c == '\u0303'))


STOPWORDS = set('a an the of to and in on with for is are this that it your then el la los las un una unos unas de del al y o en con para por es son este esta ahora tu tus'.split())


def tokens(text):
    text = normalize(text)
    latin = re.sub(r'[\u3400-\u9fff]+', ' ', text)
    result = set(re.findall(r"[^\W_]+(?:'[^\W_]+)*", latin, flags=re.UNICODE)) - STOPWORDS
    for chunk in re.findall(r'[\u3400-\u9fff]+', text):
        result.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
        if len(chunk) == 1:
            result.add(chunk)
    return result


def label_text(labels):
    return normalize(' '.join([labels.get(k, '') for k in ['description', 'subject', 'action', 'scene']]
                  + labels.get('tags', []) + labels.get('aliases', []) + list(labels.get('descriptions', {}).values())))


def contains(text, term):
    term = normalize(term.strip())
    if not term:
        raise ValueError('必须/排除条件不能是空字符串')
    if re.search(r'[\u3400-\u9fff]', term):
        return term in text
    return re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text) is not None


def digest_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def request_signature(shot):
    return digest_json({k: shot.get(k) for k in ['start', 'end', 'text', 'query', 'required', 'forbidden']})


def search(database, query, minimum=0, required=(), forbidden=(), limit=5, path_cache=None):
    if not math.isfinite(minimum) or minimum < 0 or type(limit) is not int or limit < 1:
        raise ValueError('min-duration 必须非负，limit 必须为正整数')
    query_tokens = tokens(query)
    if not query_tokens:
        return []
    db = connect(database)
    results, valid_paths = [], path_cache if path_cache is not None else {}
    for row in db.execute('SELECT clips.*,assets.paths FROM clips JOIN assets ON clips.asset_hash=assets.hash WHERE reviewed=1'):
        if row['end'] - row['start'] < minimum - 0.001:
            continue
        labels = json.loads(row['labels'])
        # Directory and filename are excluded from content ranking.
        text = label_text(labels)
        if any(not contains(text, t) for t in required) or any(contains(text, t) for t in forbidden):
            continue
        overlap = query_tokens & tokens(text)
        if not overlap:
            continue
        if row['asset_hash'] not in valid_paths:
            valid_paths[row['asset_hash']] = next((p for p in json.loads(row['paths'])
                if Path(p).is_file() and fingerprint(p) == row['asset_hash']), None)
            if valid_paths[row['asset_hash']]:
                try:
                    portrait_geometry(probe(valid_paths[row['asset_hash']]))
                except (ValueError, OSError):
                    valid_paths[row['asset_hash']] = None
        path = valid_paths[row['asset_hash']]
        if not path:
            continue
        score = len(overlap) / len(query_tokens)
        from planner import usable_ranges
        results.append({'clip_id': row['id'], 'path': path, 'source_start': row['start'],
                        'source_end': row['end'], 'rank_score': round(score, 4),
                        'asset_hash': row['asset_hash'],
                        'usable_ranges': usable_ranges(labels, row['start'], row['end']),
                        'visual': {k: labels.get(k, '') for k in ['subject', 'scene', 'shot_size', 'screen_direction']},
                        'matched_terms': sorted(overlap), 'description': labels.get('description', ''),
                        'labels_sha256': digest_json(labels),
                        'frames': json.loads(row['frames']),
                        'note': '本地文本排序分数，不是匹配概率；需要检查动作起止和语义。'})
    db.close()
    return sorted(results, key=lambda r: (-r['rank_score'], r['clip_id']))[:limit]


def search_command(args):
    print(json.dumps(search(args.database, args.query, args.min_duration, args.required,
                            args.forbidden, args.limit), ensure_ascii=False, indent=2))


def candidates(args):
    root = Path(args.project).resolve()
    shots = read(root / 'plans/edit.json')['shots']
    output = root / 'plans/candidates.json'
    if output.exists():
        raise ValueError('candidates.json 已存在，请先备份移走')
    rows, path_cache = [], {}
    for shot in shots:
        query = shot.get('query') or shot.get('text') or ''
        found = search(args.database, query, shot['end'] - shot['start'],
                       shot.get('required', []), shot.get('forbidden', []), args.limit, path_cache)
        rows.append({'shot_id': shot['id'], 'query': query, 'candidates': found,
                     'request_sha256': request_signature(shot),
                     'status': 'needs_review' if found else 'missing_material'})
    save(output, {'shots': rows, 'note': '未修改 edit.json，也未自动确认候选。'})
    print(output)


def choose(args):
    root = Path(args.project).resolve()
    path = root / 'plans/edit.json'
    data = read(path)
    shot = next((s for s in data['shots'] if s['id'] == args.shot), None)
    if not shot:
        raise ValueError('镜头 ID 不存在')
    candidates_data = read(root / 'plans/candidates.json')
    group = next((s for s in candidates_data['shots'] if s['shot_id'] == args.shot), None)
    if not group or group.get('request_sha256') != request_signature(shot):
        raise ValueError('镜头文案、时长或检索条件已改变，请重新生成候选')
    candidate = next((c for c in (group or {}).get('candidates', []) if c['clip_id'] == args.clip), None)
    if not candidate:
        raise ValueError('该片段不在当前镜头候选中')
    db = connect(args.database)
    clip = db.execute('SELECT clips.*,assets.paths FROM clips JOIN assets ON clips.asset_hash=assets.hash WHERE clips.id=?',
                      (args.clip,)).fetchone()
    db.close()
    if not clip or not clip['reviewed']:
        raise ValueError('索引片段不存在或未完成标注')
    source = Path(candidate['path'])
    if not source.is_file() or fingerprint(source) != clip['asset_hash']:
        raise ValueError('候选素材已移动或修改，请重新检索')
    portrait_geometry(probe(source))
    if shot['end'] - shot['start'] > clip['end'] - clip['start'] + 0.001:
        raise ValueError('镜头时长已改变，候选片段不够长')
    labels = json.loads(clip['labels'])
    if candidate.get('labels_sha256') != digest_json(labels):
        raise ValueError('素材标注已改变，请重新生成候选')
    text = label_text(labels)
    if any(not contains(text, t) for t in shot.get('required', [])) or any(contains(text, t) for t in shot.get('forbidden', [])):
        raise ValueError('候选不再满足当前限制，请重新检索')
    # Preserve previous choices in a local backup before changing the plan.
    n = 1
    backup = path.with_name(f'edit.backup-{n}.json')
    while backup.exists():
        n += 1
        backup = path.with_name(f'edit.backup-{n}.json')
    save(backup, data)
    from planner import usable_ranges, trim_window
    candidate = dict(candidate, asset_hash=clip['asset_hash'])
    options = [(region.get('priority', 0), trim_window(candidate, region, shot['end'] - shot['start']))
               for region in usable_ranges(labels, clip['start'], clip['end'])]
    options = [(priority, option) for priority, option in options if option]
    if not options:
        raise ValueError('没有能保留完整动作的裁切区间；请换素材或调整分镜时长')
    _, chosen = max(options, key=lambda item: item[0])
    shot['selection'] = {k: v for k, v in chosen.items() if k != 'duration'}
    shot['reviewed'] = False
    save(path, data)
    print('已写入选片并保留备份；仍需检查动作边界和音画语义。')


def register(sub):
    p = sub.add_parser('index-library'); p.add_argument('--library', required=True); p.add_argument('--database', required=True)
    p.add_argument('--window', type=float, default=6); p.add_argument('--scene', type=float, default=0.3); p.set_defaults(func=index_library)
    p = sub.add_parser('import-labels'); p.add_argument('--database', required=True); p.add_argument('labels'); p.set_defaults(func=import_labels)
    p = sub.add_parser('search'); p.add_argument('--database', required=True); p.add_argument('--query', required=True)
    p.add_argument('--min-duration', type=float, default=0); p.add_argument('--required', nargs='*', default=[])
    p.add_argument('--forbidden', nargs='*', default=[]); p.add_argument('--limit', type=int, default=5); p.set_defaults(func=search_command)
    p = sub.add_parser('candidates'); p.add_argument('project'); p.add_argument('--database', required=True)
    p.add_argument('--limit', type=int, default=5); p.set_defaults(func=candidates)
    p = sub.add_parser('choose'); p.add_argument('project'); p.add_argument('--database', required=True)
    p.add_argument('--shot', required=True); p.add_argument('--clip', required=True); p.set_defaults(func=choose)
