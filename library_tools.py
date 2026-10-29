"""Local evidence browser, feedback and conservative similarity hints."""
import html
import json
import subprocess
from pathlib import Path

import asset_index as ix
from montage import read, save, run


def policy(labels, model=None):
    product = labels.get('product', {})
    rights = labels.get('rights', {})
    issues = []
    if rights.get('usage') != 'allowed':
        issues.append('素材使用权限未确认或禁止使用')
    if product.get('restrictions') and product.get('restrictions_reviewed') is not True:
        issues.append('产品使用限制尚未复核')
    if model and product.get('restrictions_reviewed') is True and product.get('restrictions'):
        if model not in product.get('approved_models', []):
            issues.append('当前型号未列入限制复核后的允许名单')
    return issues


def feedback(args):
    db = ix.connect(args.database)
    try:
        row = db.execute('SELECT labels FROM clips WHERE id=?', (args.clip,)).fetchone()
        if not row:
            raise ValueError('片段不存在')
        path = Path(args.database).resolve().with_suffix('.feedback.json')
        data = read(path) if path.exists() else {'events': []}
        from datetime import datetime, timezone
        data['events'].append({'clip_id': args.clip, 'labels_sha256': ix.digest_json(json.loads(row['labels'])),
                               'project': str(Path(args.project).resolve()), 'decision': args.decision,
                               'reason': args.reason, 'time': datetime.now(timezone.utc).isoformat()})
        save(path, data)
    finally:
        db.close()
    print(path)


def contact(args):
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    db = ix.connect(args.database)
    cards = []
    try:
        for row in db.execute('SELECT * FROM clips ORDER BY asset_hash,start'):
            labels = json.loads(row['labels'])
            images = []
            for frame in json.loads(row['frames']):
                path = Path(frame)
                if path.is_file():
                    images.append('<img loading="lazy" src="' + html.escape(path.resolve().as_uri(), quote=True) + '">')
            title = f"{row['id']} | {row['start']:.3f}—{row['end']:.3f}s"
            text = title + ' ' + labels.get('description', '')
            cards.append('<article data-search="' + html.escape(text.lower(), quote=True) + '"><h2>' + html.escape(title) +
                         '</h2><p>' + html.escape(labels.get('description', '待理解')) + '</p><div>' + ''.join(images) +
                         '</div><p>' + html.escape('；'.join(policy(labels))) + '</p></article>')
    finally:
        db.close()
    output = root / 'contact.html'
    output.write_text('''<!doctype html><meta charset="utf-8"><title>素材联系表</title>
<style>body{font:16px system-ui;margin:32px;background:#f4f4f4}article{background:white;padding:20px;margin:20px 0}h2{font-size:16px;overflow-wrap:anywhere}img{width:180px;max-height:320px;object-fit:contain;margin:4px}input{padding:12px;width:80%}</style>
<h1>素材联系表</h1><p>本地只读浏览。区间为原视频秒数；图片抽样不能证明完整动作。</p>
<input placeholder="搜索描述或片段 ID" oninput="document.querySelectorAll('article').forEach(x=>x.hidden=!x.dataset.search.includes(this.value.toLowerCase()))">''' + ''.join(cards), encoding='utf-8')
    print(output)


def visual_hash(path, time):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(time), '-i', path,
                             '-frames:v', '1', '-vf', 'scale=9:8,format=gray',
                             '-f', 'rawvideo', '-'], capture_output=True, check=False)
    if result.returncode or len(result.stdout) != 72:
        raise ValueError('相似检测抽帧失败')
    pixels = result.stdout
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return value


def similar(args):
    if not 0 <= args.distance <= 64:
        raise ValueError('distance 应在 0—64 之间')
    db = ix.connect(args.database)
    entries, pairs, failures = [], [], []
    from understanding import source
    try:
        for row in db.execute('SELECT * FROM assets ORDER BY hash'):
            try:
                path, duration = source({'paths': json.loads(row['paths']), 'asset_hash': row['hash']})
                hashes = [visual_hash(path, duration * f) for f in [0.1, 0.5, 0.9]]
                for previous in entries:
                    distances = [(a ^ b).bit_count() for a, b in zip(hashes, previous['hashes'])]
                    if max(distances) <= args.distance:
                        pairs.append({'left': previous['asset_hash'], 'right': row['hash'], 'distances': distances,
                                      'status': 'needs_review'})
                entries.append({'asset_hash': row['hash'], 'hashes': hashes})
            except (ValueError, OSError) as exc:
                failures.append({'asset_hash': row['hash'], 'error': str(exc)})
    finally:
        db.close()
    output = Path(args.database).resolve().with_suffix('.similar.json')
    save(output, {'pairs': pairs, 'failed': failures,
                  'note': '三处采样的感知哈希提示，仅发现部分近似内容；不自动合并、删除或转移审核。'})
    print(output)


def register(sub):
    p = sub.add_parser('contact-sheet'); p.add_argument('--database', required=True)
    p.add_argument('--output', required=True); p.set_defaults(func=contact)
    p = sub.add_parser('similar-media'); p.add_argument('--database', required=True)
    p.add_argument('--distance', type=int, default=6); p.set_defaults(func=similar)
    p = sub.add_parser('selection-feedback'); p.add_argument('--database', required=True)
    p.add_argument('--clip', required=True); p.add_argument('--project', required=True)
    p.add_argument('--decision', choices=['selected', 'rejected'], required=True)
    p.add_argument('--reason', required=True); p.set_defaults(func=feedback)
