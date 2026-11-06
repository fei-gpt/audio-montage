"""Local whole-clip batch proposal pilot; never creates audio timings or renders."""
import random
from collections import Counter
from workbench.duration_planner import ascending,compact_number_run


def propose(candidates, count=10, clips_per_video=3, seed='pilot', limit=3):
    rng = random.Random(seed)
    uses, heads, tails, pairs = Counter(), Counter(), Counter(), Counter()
    plans = []
    for _ in range(count):
        choices = []
        available = [c for c in candidates if c.get('usage_count', 0) + uses[c['asset_sha256']] < limit]
        for _ in range(200):
            if len(available) < clips_per_video:
                break
            parts = rng.sample(available, clips_per_video)
            if compact_number_run(c['name'] for c in parts):continue
            hashes = [c['asset_sha256'] for c in parts]
            if len(set(hashes)) < len(hashes) or any(ascending(a['name'], b['name']) for a,b in zip(parts, parts[1:])):
                continue
            if any(hashes == [c['asset_sha256'] for c in old] for old in plans):
                continue
            overlap = max((len(set(hashes) & {c['asset_sha256'] for c in old}) / clips_per_video for old in plans), default=0)
            score = (overlap, heads[hashes[0]] + tails[hashes[-1]],
                     sum(pairs[x] for x in zip(hashes, hashes[1:])), sum(uses[h] for h in hashes))
            choices.append((score, parts))
        if not choices:
            break
        _, best = min(choices, key=lambda x: x[0])
        plans.append(best)
        hashes = [c['asset_sha256'] for c in best]
        uses.update(hashes); heads[hashes[0]] += 1; tails[hashes[-1]] += 1
        pairs.update(zip(hashes, hashes[1:]))
    return {'requested': count, 'proposed': len(plans), 'plans': plans,
            'usage_reservations': dict(uses), 'rendered': False,
            'note': '实验选材组合，无配音时间轴、不输出成片、不计正式引用、不表示人工核验。'}
