"""Opt-in local visual matching pilot using ImageHash; no model calls."""
import json
import subprocess
import sys
from pathlib import Path
from montage import fingerprint, probe, portrait_geometry, media_duration, save

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.dedup-runtime'))
VERSION = 'imagehash-phash-color-2fps-v1'


def signature(path, cache):
    import imagehash
    from PIL import Image, ImageStat
    sha = fingerprint(path)
    dest = Path(cache) / (sha + '.json')
    if dest.exists():
        value = json.loads(dest.read_text(encoding='utf-8'))
        if value.get('version') == VERSION:
            return value
    info = probe(path)
    portrait_geometry(info)
    duration = media_duration(info, 'video')
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-an', '-vf',
               'fps=2,scale=64:64', '-frames:v', '120', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-']
    raw = subprocess.run(command, capture_output=True, check=True, timeout=120).stdout
    size = 64 * 64 * 3
    frames = []
    for i in range(len(raw) // size):
        image = Image.frombytes('RGB', (64, 64), raw[i * size:(i + 1) * size])
        stats = ImageStat.Stat(image)
        # Flat backgrounds can generate deceptively identical structural hashes.
        if max(ImageStat.Stat(image.convert('L')).stddev) < 8:
            continue
        frames.append({'time': i / 2, 'hash': str(imagehash.phash(image)), 'rgb': stats.mean})
    value = {'version': VERSION, 'source_sha256': sha, 'duration': duration,
             'sampled_seconds': min(duration, 60), 'partial': duration > 60, 'frames': frames}
    save(dest, value)
    return value


def compare(a, b):
    if a['source_sha256'] == b['source_sha256']:
        return {'score': 1, 'candidate_duplicate': True, 'basis': 'exact_bytes'}
    fa, fb = a['frames'], b['frames']
    if len(fa) < 3 or len(fb) < 3:
        return {'score': None, 'candidate_duplicate': False, 'basis': 'insufficient_detail'}
    pairs = []
    for i, x in enumerate(fa):
        for j, y in enumerate(fb):
            distance = (int(x['hash'], 16) ^ int(y['hash'], 16)).bit_count()
            if distance <= 8 and max(abs(u-v) for u,v in zip(x['rgb'], y['rgb'])) <= 30:
                pairs.append((i, j, round((y['time'] - x['time']) * 2)))
    best = (0, 0)
    evidence = []
    for offset in {p[2] for p in pairs}:
        # Matching frames must agree on temporal offset, not just share a background.
        coherent = [p for p in pairs if abs(p[2] - offset) <= 1]
        matched_a = len({p[0] for p in coherent}) / len(fa)
        matched_b = len({p[1] for p in coherent}) / len(fb)
        if min(matched_a, matched_b) > min(best):
            best = matched_a, matched_b
            evidence = [{'a_seconds': fa[i]['time'], 'b_seconds': fb[j]['time']} for i,j,_ in coherent[:6]]
    score = round(min(best), 4)
    return {'score': score, 'matched_a': round(best[0], 4), 'matched_b': round(best[1], 4),
            'candidate_duplicate': score >= .9 and not a.get('partial') and not b.get('partial'),
            'basis': 'sampled_perceptual_candidate_only', 'content_verified': False, 'evidence': evidence}
