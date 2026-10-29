"""Bounded local selection planning from reviewed labels, no model calls."""
import copy
import json
import math
from pathlib import Path

import asset_index as ix
from montage import read, save, expand_shots, fingerprint, number


def usable_ranges(labels, start, end):
    ranges = labels.get('usable_ranges')
    if ranges is None:
        return [{'start': start, 'end': end, 'kind': 'unknown', 'priority': 0,
                 'reason': '尚无精确动作边界，采用居中候选，必须看画面复核'}]
    if not isinstance(ranges, list):
        raise ValueError('usable_ranges 必须是列表')
    output = []
    for item in ranges:
        a, b = item.get('start'), item.get('end')
        if not number(a) or not number(b) or a < start - 0.001 or b > end + 0.001 or b <= a:
            raise ValueError('可用区间必须位于索引片段内，使用原视频绝对秒数')
        kind = item.get('kind', 'static')
        if kind not in {'action', 'static'}:
            raise ValueError('可用区间 kind 必须为 action/static')
        priority = item.get('priority', 0)
        if not number(priority) or not 0 <= priority <= 1:
            raise ValueError('区间 priority 必须在 0 和 1 之间')
        result = dict(item, kind=kind, priority=priority)
        if kind == 'action':
            x, y = item.get('action_start', a), item.get('action_end', b)
            if not number(x) or not number(y) or x < a or y > b or y <= x:
                raise ValueError('完整动作边界必须位于可用区间内')
            result.update(action_start=x, action_end=y)
        output.append(result)
    return output


def trim_window(candidate, region, duration):
    a, b = region['start'], region['end']
    if duration <= 0 or duration > b - a + 0.000001:
        return None
    low, high = a, b - duration
    if region['kind'] == 'action':
        x, y = region['action_start'], region['action_end']
        if y - x > duration + 0.000001:
            return None  # Never truncate a labeled complete action.
        low, high = max(low, y - duration), min(high, x)
        if low > high + 0.000001:
            return None
        preferred = (x + y - duration) / 2
        method = 'complete_action'
    else:
        preferred = (a + b - duration) / 2
        method = 'reviewed_range' if region['kind'] == 'static' else 'center_fallback'
    source_start = min(max(preferred, low), max(low, high))
    result = {'path': candidate['path'], 'clip_id': candidate['clip_id'],
            'asset_hash': candidate['asset_hash'], 'labels_sha256': candidate['labels_sha256'],
            'product': candidate.get('product', {}), 'rights': candidate.get('rights', {}),
            'source_start': source_start, 'duration': duration,
            'allowed_start': a, 'allowed_end': b, 'trim_method': method,
            'reason': region.get('reason') or candidate.get('description', '')}
    if region['kind'] == 'action':
        result.update(action_start=region['action_start'], action_end=region['action_end'])
    result['visual'] = candidate.get('visual', {})
    return result


def trim_options(candidate, region, duration):
    best = trim_window(candidate, region, duration)
    if not best:
        return []
    output = [best]
    for start in [region['start'], region['end'] - duration]:
        if abs(start - best['source_start']) < 1e-6:
            continue
        if region['kind'] == 'action' and (start > region['action_start'] + 1e-6 or start + duration < region['action_end'] - 1e-6):
            continue
        output.append(dict(best, source_start=start))
    return output


def overlaps(part, used):
    return any(h == part['asset_hash'] and min(part['source_start'] + part['duration'], b) - max(part['source_start'], a) > 0.001
               for h, a, b in used)


def identity(part):
    return (part['asset_hash'], part['source_start'], part['source_start'] + part['duration'])


def transition_score(previous, current):
    if not previous:
        return 0, []
    score, notes = 0, []
    for key, bonus in [('subject', 0.12), ('scene', 0.06)]:
        if previous.get(key) and ix.normalize(previous[key]) == ix.normalize(current.get(key, '')):
            score += bonus
            notes.append(f'{key} 标签衔接一致')
    if previous.get('shot_size') and current.get('shot_size'):
        score += 0.03 if previous['shot_size'] != current['shot_size'] else -0.03
    if previous.get('screen_direction') and current.get('screen_direction') and previous['screen_direction'] != current['screen_direction']:
        notes.append('运动方向标签发生变化，需看衔接是否自然')
    return score, notes


def select_chain(candidates, duration, used, previous=None, max_parts=4, min_part=0.8):
    """Beam search; complete coverage or no selection, never partial filler."""
    states = [{'parts': [], 'used': list(used), 'remaining': duration,
               'score': 0.0, 'previous': previous, 'notes': []}]
    complete = []
    for depth in range(max_parts):
        next_states = []
        for state in states:
            remaining = state['remaining']
            for candidate in candidates:
                for region in candidate['usable_ranges']:
                    capacity = region['end'] - region['start']
                    sizes = {min(capacity, remaining)}
                    if remaining >= 2 * min_part:
                        sizes.update([min(capacity, remaining / 2), min(capacity, remaining - min_part)])
                    for size in sorted(sizes, reverse=True):
                        if size < min_part - 1e-6 and (depth or remaining > min_part):
                            continue
                        left = remaining - size
                        if 1e-6 < left < min_part - 1e-6:
                            continue
                        for position, part in enumerate(trim_options(candidate, region, size)):
                            if overlaps(part, state['used']):
                                continue
                            bonus, notes = transition_score(state['previous'], candidate['visual'])
                            if state['used'] and state['used'][-1][0] == part['asset_hash']:
                                bonus -= 0.08
                            score = state['score'] + size * (candidate['rank_score'] + 0.1 * region['priority'] + bonus) - 0.06 - position * 0.001
                            item = {'parts': state['parts'] + [part], 'used': state['used'] + [identity(part)],
                                    'remaining': max(0, left), 'score': score,
                                    'previous': candidate['visual'], 'notes': state['notes'] + notes}
                            if left <= 1e-6:
                                complete.append(item)
                            else:
                                next_states.append(item)
        # Retain bounded alternatives, favoring covered duration as well as rank.
        states = sorted(next_states, key=lambda x: x['score'] - x['remaining'] * 0.1, reverse=True)[:48]
        if not states:
            break
    if not complete:
        return None
    best = max(complete, key=lambda x: (-len(x['parts']), x['score']))
    # Remove floating-point remainder without changing any meaningful boundary.
    best['parts'][-1]['duration'] += duration - sum(p['duration'] for p in best['parts'])
    return best


def auto_plan(args):
    root = Path(args.project).resolve()
    source_path = root / 'plans/edit.json'
    original = read(source_path)
    output = root / 'plans/proposal.json'
    from workflow import archive
    archive(output)
    if not 1 <= args.max_parts <= 8 or not math.isfinite(args.min_part) or args.min_part <= 0 or not 0 < args.min_score <= 1:
        raise ValueError('max-parts 应为 1—8，min-part 必须大于零，min-score 应在 0—1 之间')
    proposed = copy.deepcopy(original)
    shots = proposed['shots']
    fps = read(root / 'project.json')['fps']
    # Reserve all preexisting choices so new proposals cannot reuse them.
    used = []
    for shot in expand_shots([s for s in shots if s.get('selection')]):
        selection = shot['selection']
        used.append((fingerprint(selection['path']), selection['source_start'],
                     selection['source_start'] + shot['end'] - shot['start']))
    report, previous, cache = [], None, {}
    for index, shot in enumerate(shots):
        if shot.get('selection'):
            report.append({'shot_id': shot['id'], 'status': 'kept_existing'})
            last = expand_shots([shot])[-1]['selection']
            previous = last.get('visual')
            continue
        if round(shot['end'] * fps) - round(shot['start'] * fps) < 1:
            report.append({'shot_id': shot['id'], 'status': 'needs_timeline_adjustment',
                           'reason': '该画面不足一帧，需要合并到相邻分镜'})
            continue
        request = shot
        if not (shot.get('query') or shot.get('text')):
            neighbors = sorted(range(len(shots)), key=lambda n: (abs(n - index), n))
            request = next((shots[n] for n in neighbors if shots[n].get('query') or shots[n].get('text')), shot)
        from workflow import effective_shot
        target = effective_shot(root, shot)
        query = shot.get('query') or request.get('query') or request.get('text') or ''
        required = shot.get('required') or request.get('required', [])
        forbidden = shot.get('forbidden') or request.get('forbidden', [])
        found = ix.search(args.database, query, 0, required, forbidden, 24, cache, target.get('product_model'))
        found = [c for c in found if c['rank_score'] >= args.min_score]
        chain = select_chain(found, shot['end'] - shot['start'], used, previous,
                             args.max_parts, args.min_part)
        if chain:
            shot['selection'] = {'parts': chain['parts']}
            shot['reviewed'] = False
            if not shot.get('purpose'):
                shot['purpose'] = '待复核：用所选画面解释本段配音'
            used = chain['used']
            previous = chain['previous']
            report.append({'shot_id': shot['id'], 'status': 'proposed', 'query': query,
                           'parts': len(chain['parts']), 'notes': chain['notes'],
                           'needs_visual_review': True})
        else:
            report.append({'shot_id': shot['id'], 'status': 'missing_material', 'query': query,
                           'reason': '没有满足语义词项、完整动作、时长、去重和片段数量约束的完整方案'})
    save(output, {'version': 1, 'project_sha256': fingerprint(root / 'project.json'), 'edit_sha256': fingerprint(source_path),
                  'database': str(Path(args.database).resolve()), 'edit': proposed, 'report': report,
                  'note': '基于已复核标签的本地规则规划，不证明视觉语义或衔接质量；未修改 edit.json。'})
    print(output)


def apply_plan(args):
    root = Path(args.project).resolve()
    path = root / 'plans/edit.json'
    proposal = read(args.proposal)
    if proposal['edit_sha256'] != fingerprint(path):
        raise ValueError('剪辑清单已改变，请重新生成方案')
    if proposal.get('project_sha256') != fingerprint(root / 'project.json'):
        raise ValueError('项目配置已改变，请重新生成方案')
    shots = expand_shots(proposal['edit']['shots'])
    db = ix.connect(proposal['database'])
    media_cache = {}
    try:
        for shot in shots:
            selection = shot.get('selection') or {}
            if not selection.get('clip_id') or not selection.get('labels_sha256'):
                continue  # Preexisting manual selections remain user choices.
            row = db.execute('SELECT * FROM clips WHERE id=?', (selection['clip_id'],)).fetchone()
            if not row or not row['reviewed'] or ix.digest_json(json.loads(row['labels'])) != selection['labels_sha256']:
                raise ValueError('素材标注已改变，请重新生成方案')
            from montage import portrait_geometry, probe
            if selection['path'] not in media_cache:
                portrait_geometry(probe(selection['path']))
                media_cache[selection['path']] = fingerprint(selection['path'])
            if selection.get('asset_hash') != row['asset_hash'] or selection.get('asset_hash') != media_cache[selection['path']]:
                raise ValueError('素材已改变，请重新生成方案')
            start = selection.get('source_start')
            duration = shot['end'] - shot['start']
            regions = usable_ranges(json.loads(row['labels']), row['start'], row['end'])
            if not number(start) or not any(
                start >= region['start'] - 1e-6 and start + duration <= region['end'] + 1e-6
                and (region['kind'] != 'action' or
                     (start <= region['action_start'] + 1e-6 and start + duration >= region['action_end'] - 1e-6))
                for region in regions
            ):
                raise ValueError('选片超出标注可用区间或截断完整动作，请重新生成方案')
    finally:
        db.close()
    backup_number = 1
    backup = path.with_name(f'edit.backup-{backup_number}.json')
    while backup.exists():
        backup_number += 1
        backup = path.with_name(f'edit.backup-{backup_number}.json')
    save(backup, read(path))
    save(path, proposal['edit'])
    print('已应用方案并备份旧清单；新选片均为待复核，缺素材项仍为空。')


def register(sub):
    p = sub.add_parser('auto-plan'); p.add_argument('project'); p.add_argument('--database', required=True)
    p.add_argument('--max-parts', type=int, default=4); p.add_argument('--min-part', type=float, default=0.8)
    p.add_argument('--min-score', type=float, default=0.35); p.set_defaults(func=auto_plan)
    p = sub.add_parser('apply-plan'); p.add_argument('project'); p.add_argument('proposal'); p.set_defaults(func=apply_plan)
