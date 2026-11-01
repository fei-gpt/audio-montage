"""Content-first task records and evidence-approved multi-range extraction."""
import copy
import csv
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from montage import read, save, probe, portrait_geometry, media_duration, fingerprint, number, run
from asset_index import digest_json
from workflow import archive


DIMENSIONS = ('content_legibility', 'temporal_integrity', 'technical_usability', 'evidence_sufficiency')
VERDICTS = {'pass', 'conditional', 'fail', 'unknown', 'not_applicable'}
DECISIONS = {'keep', 'reject', 'uncertain'}
MIN_CLIP_SECONDS = 1.0
MAX_CLIP_SECONDS = 4.0


def _now():
    return datetime.now().isoformat(timespec='seconds')


def hard_condition_ids(requirements):
    """Ordered ids of user hard conditions and exclusions; malformed entries are refused."""
    ids = []
    for group in ('hard', 'exclusions'):
        entries = (requirements or {}).get(group) or []
        if not isinstance(entries, list):
            raise ValueError('用户条件必须是数组')
        for entry in entries:
            rid = entry.get('id') if isinstance(entry, dict) else None
            if not isinstance(rid, str) or not rid.strip():
                raise ValueError('用户硬条件或排除项缺少 id，无法逐项核对')
            if rid not in ids:
                ids.append(rid)
    return ids


def content_problem(segment, requirements):
    """Return why a keep decision cannot be trusted yet, or None when every gate passes."""
    assessment = segment.get('assessment') or {}
    base = assessment.get('base') or {}
    if not isinstance(base, dict) or not set(DIMENSIONS).issubset(base):
        return '缺少通用标准的分维度判断，需人工补齐'
    if any(value not in VERDICTS for value in base.values()):
        return '通用维度判断值无效，需人工修正'
    if base.get('evidence_sufficiency') != 'pass':
        return '观察证据不足以确认保留'
    if any(value in {'fail', 'unknown'} for value in base.values()):
        return '通用标准存在未解决的问题'
    if 'conditional' in base.values() and not segment.get('use_conditions'):
        return '有条件可用但未说明使用条件'
    checks = {}
    for row in assessment.get('user') or []:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            return '用户条件结果格式无效'
        checks[row['id']] = row.get('result')
    for rid in hard_condition_ids(requirements):
        result = checks.get(rid)
        if result == 'fail':
            return f'用户硬条件 {rid} 未通过，本任务不可用'
        if result != 'pass':
            return f'用户硬条件 {rid} 结果未知，需人工确认'
    return None


def requirement_match(segment, requirements):
    """Summarize user-condition matching without inventing a score."""
    checks = {row.get('id'): row.get('result')
              for row in (segment.get('assessment') or {}).get('user') or [] if isinstance(row, dict)}
    ids = hard_condition_ids(requirements)
    if any(checks.get(rid) == 'fail' for rid in ids):
        return 'mismatch'
    if any(checks.get(rid) != 'pass' for rid in ids):
        return 'unknown'
    return 'match'


def prepare(args):
    root = Path(args.output).resolve()
    source = Path(args.video).resolve()
    info = probe(source)
    portrait_geometry(info)
    task = root / 'task.json'
    if task.exists():
        raise ValueError('任务已存在，请续接现有任务或选择新目录')
    digest = fingerprint(source)
    save(task, {'version': 1, 'source': str(source), 'source_sha256': digest,
                'duration': media_duration(info, 'video'), 'request': args.request,
                'duration_policy': 'single_take_complete_display',
                'standard': 'content-v2', 'min_clip_seconds': MIN_CLIP_SECONDS, 'max_clip_seconds': MAX_CLIP_SECONDS, 'keep_original_audio': True,
                'rights': {'usage': 'unknown'}, 'requirements': {'hard': [], 'preferences': [], 'exclusions': [], 'confirmed': False},
                'criteria': {'base_version': 'content-v2', 'profiles': ['general'], 'user_revision': 1},
                'analysis': {'overview': '', 'product_intent': {}, 'shot_boundaries': [],
                             'shot_boundary_reviewed': False, 'coverage': [], 'reviewed': False}, 'segments': [],
                'segment_example': {'id': 'S001', 'start': 0, 'end': 1,
                    'facts': '', 'editorial_value': '', 'quality_issues': [],
                    'content_roles': [], 'visible_claims': [], 'unsupported_claims': [],
                    'use_conditions': [], 'requirement_match': 'unknown',
                    'assessment': {'base': {}, 'profile': {}, 'user': []},
                    'alternatives': [], 'tradeoffs': [],
                    'display_intent': '', 'duration_reason': '', 'shot_review': {},
                    'review_record': {'source_continuity': 'not_checked',
                                     'display_effect': 'not_checked', 'export_checked': 'not_checked'},
                    'decision': 'uncertain', 'reason': '', 'evidence': [],
                    'boundary_reviewed': False}})
    save(root / 'progress.json', {'status': 'needs_observation', 'completed': [], 'remaining': ['observe_whole_video', 'understand_display_intent', 'verify_shot_boundaries', 'judge_content', 'review_boundaries', 'extract', 'review_actual_exports']})
    (root / 'resume.md').write_text('读取 task.json 和 CONTENT_STANDARD.md；先理解整片展示意图，再核实物理切镜，在单镜头内选材并密看边界；自动片段不可跨真实切镜。不要把示例当作判断结果。\n', encoding='utf-8')
    # Reuse the existing evidence tool without creating fake semantic labels.
    record = root / 'assets' / (digest + '.json')
    save(record, {'asset': {'paths': [str(source)], 'asset_hash': digest}})
    from understanding import observe
    observe(SimpleNamespace(record=str(record), start=0, end=None, every=2))
    print(task)


def _valid_evidence(evidence, start, end):
    if not evidence or not isinstance(evidence, list):
        return False
    for row in evidence:
        if not isinstance(row, dict) or not number(row.get('time')):
            return False
        if not start <= row['time'] <= end:
            return False
        path = row.get('path')
        if not isinstance(path, str) or not Path(path).is_file():
            return False
    return True


def shot_boundary_problem(task, segment):
    """Enforce recorded edit boundaries; this does not discover cuts visually."""
    a, b = segment['start'], segment['end']
    for cut in (task.get('analysis') or {}).get('shot_boundaries') or []:
        t = cut.get('time') if isinstance(cut, dict) else None
        if number(t) and a < t < b:
            return f'选区内部存在已记录切镜 {t:g} 秒，必须按物理镜头拆分后重新选区'
    return None


def single_take_exception(task, segment):
    """Evidence-backed continuity exception, never inferred from duration alone."""
    if task.get('duration_policy') != 'single_take_complete_display':
        return False
    shot = segment.get('shot_review') or {}
    if not isinstance(shot, dict):
        return False
    a, b = segment.get('start'), segment.get('end')
    lo, hi = shot.get('start'), shot.get('end')
    if not all(number(v) for v in (a, b, lo, hi)) or not lo <= a < b <= hi:
        return False
    if (shot.get('continuous') is not True or shot.get('reviewed') is not True
            or not segment.get('boundary_reviewed') or not shot.get('method')
            or not str(segment.get('display_intent') or '').strip()
            or not str(segment.get('duration_reason') or '').strip()
            or not _valid_evidence(shot.get('evidence'), a, b)):
        return False
    return shot_boundary_problem(task, segment) is None


def extract(args):
    task_path = Path(args.task).resolve()
    root = task_path.parent
    task = read(task_path)
    source = Path(task['source'])
    if fingerprint(source) != task['source_sha256']:
        raise ValueError('原视频改变，请重新分析')
    source_info = probe(source)
    portrait_geometry(source_info)
    actual_duration = media_duration(source_info, 'video')
    if not task.get('analysis', {}).get('reviewed'):
        raise ValueError('需要完成整片内容观察')
    if task.get('rights', {}).get('usage') != 'allowed':
        raise ValueError('需要有依据地确认素材使用权限')
    requirements = task.get('requirements') or {}
    if task.get('standard') == 'content-v2' and requirements.get('confirmed') is not True:
        raise ValueError('需要将用户原始要求整理为已核对的任务条件')
    hard_condition_ids(requirements)  # refuse malformed conditions before writing anything
    limit = min(task['duration'], actual_duration)
    selected, ids, manual_review, uncertain = [], set(), [], []
    for segment in task['segments']:
        decision = segment.get('decision')
        if decision not in DECISIONS:
            raise ValueError('decision 必须为 keep/reject/uncertain')
        if decision == 'reject':
            continue
        if decision == 'uncertain':
            uncertain.append(segment)
            continue
        sid, a, b = segment.get('id'), segment.get('start'), segment.get('end')
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('片段 ID 为空或重复')
        ids.add(sid)
        if not number(a) or not number(b) or not 0 <= a < b <= limit:
            raise ValueError('片段时间超出原视频')
        if not segment.get('boundary_reviewed') or not segment.get('facts') or not segment.get('reason'):
            raise ValueError('保留片段需要事实、选择理由和边界复核')
        if not _valid_evidence(segment.get('evidence'), a, b):
            raise ValueError('保留片段缺少有效的时间证据')
        boundary_problem = shot_boundary_problem(task, segment)
        if boundary_problem:
            uncertain.append(dict(segment, review_reason=boundary_problem))
            continue
        if not MIN_CLIP_SECONDS - 1e-9 <= b - a <= MAX_CLIP_SECONDS + 1e-9 and not single_take_exception(task, segment):
            manual_review.append(dict(segment, review_reason='候选时长不在默认1–4秒范围且未核实一镜到底展示例外，保留完整候选待审，禁止凑时长',
                                      source=str(source), duration=b - a))
            continue
        # Content judgement problems never abort the whole batch: the clip is
        # held back for review so the remaining verified clips still export.
        problem = content_problem(segment, requirements) if task.get('standard') == 'content-v2' else None
        if problem:
            uncertain.append(dict(segment, review_reason=problem + '；未进入自动 clips，需人工审核'))
            continue
        selected.append(segment)
    review_folder = root / 'manual-review-clips'
    active_review = set()
    for index, candidate in enumerate(manual_review, 1):
        identity = digest_json({'source': task['source_sha256'], 'start': candidate['start'],
                                'end': candidate['end'], 'audio': task.get('keep_original_audio', True)})
        review_video = review_folder / f'{index:04}-{identity[:12]}.mp4'
        active_review.add(review_video.name)
        if review_video.exists():
            try:
                review_info = probe(review_video)
                if abs(media_duration(review_info, 'video') - candidate['duration']) > .15:
                    raise ValueError('待审视频时长不符')
            except (ValueError, OSError, KeyError):
                archive(review_video)
                review_video.unlink()
        if not review_video.exists():
            review_folder.mkdir(parents=True, exist_ok=True)
            staged_review = review_video.with_suffix('.partial.mp4')
            audio_args = ['-map', '0:a:0?', '-c:a', 'aac'] if task.get('keep_original_audio', True) else ['-an']
            run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', candidate['start'], '-i', source,
                 '-t', candidate['duration'], '-map', '0:v:0', *audio_args, '-c:v', 'libx264',
                 '-pix_fmt', 'yuv420p', staged_review])
            run(['ffmpeg', '-v', 'error', '-nostdin', '-i', staged_review, '-f', 'null', '-'])
            staged_review.replace(review_video)
        candidate['review_video'] = str(review_video)
    if review_folder.is_dir():
        for existing in review_folder.glob('*.mp4'):
            if existing.name not in active_review and not existing.name.endswith('.partial.mp4'):
                archive(existing)
                existing.unlink()
    save(root / 'manual-review.json', {'min_clip_seconds': MIN_CLIP_SECONDS, 'max_clip_seconds': MAX_CLIP_SECONDS,
                                       'duration_policy': task.get('duration_policy', 'strict_1_4'), 'segments': manual_review})
    with (root / 'manual-review.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'source', 'start', 'end', 'duration', 'review_video', 'reason', 'review_reason'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(manual_review)
    destination = root / 'clips'
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'extraction.json'
    previous = read(manifest_path).get('clips', []) if manifest_path.exists() else []
    # Keep only current automatic deliverables in clips/; preserve superseded files.
    active_names = set()
    for index, s in enumerate(selected, 1):
        key = digest_json({'source_sha256': task['source_sha256'], 'id': s['id'],
                          'start': s['start'], 'end': s['end'], 'audio': task.get('keep_original_audio', True)})
        active_names.add(f'{index:04}-{key[:12]}.mp4')
    for existing in destination.glob('*.mp4'):
        if existing.name not in active_names and not existing.name.endswith('.partial.mp4'):
            archive(existing)
            existing.unlink()
    save(root / 'uncertain-review.json', {'segments': uncertain})
    completed = []
    for index, segment in enumerate(selected, 1):
        signature = {'source_sha256': task['source_sha256'], 'id': segment['id'],
                     'start': segment['start'], 'end': segment['end'],
                     'audio': task.get('keep_original_audio', True)}
        digest = digest_json(signature)
        output = destination / f'{index:04}-{digest[:12]}.mp4'
        old = next((r for r in previous if r.get('signature') == digest), None)
        if old and output.exists() and old.get('output_sha256') == fingerprint(output):
            completed.append(dict(old, reason=segment['reason'], single_take_exception=single_take_exception(task, segment)))
            continue
        staged = destination / f'{digest}.partial.mp4'
        audio = ['-map', '0:a:0?', '-c:a', 'aac'] if signature['audio'] else ['-an']
        run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', segment['start'], '-i', source,
             '-t', segment['end'] - segment['start'], '-map', '0:v:0', *audio,
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', staged])
        info = probe(staged)
        portrait_geometry(info)
        if not MIN_CLIP_SECONDS - 1e-6 <= media_duration(info, 'video') <= MAX_CLIP_SECONDS + 1e-6 and not single_take_exception(task, segment):
            raise ValueError('实际输出不在默认1–4秒范围且无核实的一镜到底展示例外，停止交付并人工审核')
        if abs(media_duration(info, 'video') - (segment['end'] - segment['start'])) > .15:
            raise ValueError('输出片段时长不符')
        run(['ffmpeg', '-v', 'error', '-nostdin', '-i', staged, '-f', 'null', '-'])
        archive(output)
        staged.replace(output)
        completed.append(dict(signature, signature=digest, output=str(output),
                              output_sha256=fingerprint(output), reason=segment['reason'],
                              single_take_exception=single_take_exception(task, segment)))
        save(manifest_path, {'clips': completed})
        save(root / 'progress.json', {'status': 'extracting', 'completed': completed,
                                     'remaining': [s['id'] for s in selected[index:]]})
    save(manifest_path, {'clips': completed, 'decisions': task['segments'], 'manual_review': manual_review, 'uncertain': uncertain})
    with (root / 'clips.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'start', 'end', 'output', 'reason'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(completed)
    save(root / 'progress.json', {'status': 'needs_manual_review' if manual_review or uncertain else 'completed', 'completed': completed,
                                    'remaining': [s.get('id') for s in manual_review + uncertain], 'manual_review': manual_review, 'uncertain': uncertain})
    print(manifest_path)


def entries(path):
    """Read a backfill file: a bare array or an object with decisions/selections."""
    data = read(path)
    if isinstance(data, dict):
        for key in ('decisions', 'selections', 'segments', 'entries'):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ValueError('回填文件需要 decisions 或 selections 数组')
    if not isinstance(data, list) or not data:
        raise ValueError('回填文件必须是非空数组')
    for row in data:
        if not isinstance(row, dict):
            raise ValueError('回填条目必须是对象')
    return data


def observed_windows(task):
    """Merged coverage windows; overlapping or touching batches count as one range."""
    raw = []
    for row in (task.get('analysis') or {}).get('coverage') or []:
        if isinstance(row, (list, tuple)) and len(row) == 2 and number(row[0]) and number(row[1]) and row[0] < row[1]:
            raw.append((float(row[0]), float(row[1])))
    merged = []
    for left, right in sorted(raw):
        if merged and left <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def within_windows(windows, start, end):
    return any(start >= left - 1e-6 and end <= right + 1e-6 for left, right in windows)


def frames_between(root, task, start, end):
    """Dense evidence inside a range; frames come from real local FFmpeg sampling."""
    record = root / 'assets' / (task['source_sha256'] + '.json')
    folder = root / 'evidence' / task['source_sha256']
    if not record.is_file() or not folder.is_dir():
        return []
    from understanding import observe
    observe(SimpleNamespace(record=str(record), start=start, end=end,
                            every=max(.1, (end - start) / 12)))
    frames = []
    for path in folder.glob('*.jpg'):
        try:
            time = float(path.stem)
        except ValueError:
            continue
        if start - 1e-9 <= time <= end + 1e-9:
            frames.append({'time': time, 'path': str(path)})
    return sorted(frames, key=lambda row: row['time'])


def audit(segment):
    return {key: segment.get(key) for key in
            ('id', 'start', 'end', 'decision', 'facts', 'reason', 'boundary_reviewed',
             'use_conditions', 'content_roles', 'assessment', 'display_intent', 'duration_reason',
             'shot_review', 'review_record')}


def append_log(root, rows):
    path = root / 'review-log.json'
    current = read(path) if path.exists() else {'entries': []}
    if isinstance(current, list):
        current = {'entries': current}
    current.setdefault('entries', []).extend(rows)
    save(path, current)


def _segment_map(task):
    return {s.get('id'): s for s in task['segments'] if isinstance(s.get('id'), str)}


def export_preconditions(task):
    """Same gates as extract, checked before a command mutates the task."""
    if not (task.get('analysis') or {}).get('reviewed'):
        raise ValueError('需要完成整片内容观察')
    if (task.get('rights') or {}).get('usage') != 'allowed':
        raise ValueError('需要有依据地确认素材使用权限；确认后再导出，或用 --no-extract 只回填记录')
    if task.get('standard') == 'content-v2' and (task.get('requirements') or {}).get('confirmed') is not True:
        raise ValueError('需要将用户原始要求整理为已核对的任务条件')


def review_segments(args):
    """Backfill human review decisions, keep history, then re-export."""
    task_path = Path(args.task).resolve()
    root = task_path.parent
    task = read(task_path)
    updates = entries(args.decisions)
    source = Path(task['source'])
    if fingerprint(source) != task['source_sha256']:
        raise ValueError('原视频改变，请重新分析')
    duration = min(task['duration'], media_duration(probe(source), 'video'))
    requirements = task.get('requirements') or {}
    known = _segment_map(task)
    if not getattr(args, 'no_extract', False):
        export_preconditions(task)
    staged = []
    for entry in updates:
        sid = entry.get('id')
        if not isinstance(sid, str) or sid not in known:
            raise ValueError(f'{sid}: 任务中没有该片段；新增候选或改区间请用 reselect-segments')
        segment = known[sid]
        before = copy.deepcopy(segment)
        updated = copy.deepcopy(segment)
        decision = entry.get('decision', updated.get('decision'))
        if decision not in DECISIONS:
            raise ValueError(f'{sid}: decision 必须为 keep/reject/uncertain')
        updated['decision'] = decision
        for field in ('facts', 'reason'):
            if field in entry:
                if not isinstance(entry[field], str):
                    raise ValueError(f'{sid}: {field} 必须是文字')
                updated[field] = entry[field].strip()
        for field in ('shot_review', 'display_intent', 'duration_reason', 'review_record'):
            if field in entry:
                updated[field] = copy.deepcopy(entry[field])
        for field in ('use_conditions', 'content_roles'):
            if field in entry:
                if not isinstance(entry[field], list):
                    raise ValueError(f'{sid}: {field} 必须是数组')
                updated[field] = entry[field]
        if 'assessment' in entry:
            if not isinstance(entry['assessment'], dict):
                raise ValueError(f'{sid}: assessment 必须是对象')
            merged = dict(updated.get('assessment') or {})
            merged.update(entry['assessment'])
            updated['assessment'] = merged
        if 'user' in entry:
            rows = entry['user']
            if not isinstance(rows, list):
                raise ValueError(f'{sid}: user 必须是数组')
            assessment = dict(updated.get('assessment') or {})
            merged = {r.get('id'): dict(r) for r in assessment.get('user') or [] if isinstance(r, dict)}
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row.get('result') not in VERDICTS:
                    raise ValueError(f'{sid}: user 结果需要 id 和有效 result')
                merged[row['id']] = dict(merged.get(row['id'], {}), **row)
            assessment['user'] = list(merged.values())
            updated['assessment'] = assessment
        if entry.get('boundary_reviewed') is True:
            updated['boundary_reviewed'] = True
        updated['requirement_match'] = requirement_match(updated, requirements)
        if decision == 'keep':
            if updated.get('boundary_reviewed') is not True:
                raise ValueError(f'{sid}: 标记 keep 前需要显式确认已复核边界（boundary_reviewed: true）')
            if not str(updated.get('facts') or '').strip() or not str(updated.get('reason') or '').strip():
                raise ValueError(f'{sid}: 标记 keep 需要事实与选择理由')
            problem = content_problem(updated, requirements) if task.get('standard') == 'content-v2' else None
            if problem:
                raise ValueError(f'{sid}: {problem}')
            a, b = updated.get('start'), updated.get('end')
            if not number(a) or not number(b) or not 0 <= a < b <= duration:
                raise ValueError(f'{sid}: 片段时间超出原视频')
            if not _valid_evidence(updated.get('evidence'), a, b):
                raise ValueError(f'{sid}: 保留片段缺少有效的时间证据')
        updated['review_method'] = 'manual_backfill'
        updated['reviewed_at'] = _now()
        staged.append((segment, before, updated, entry.get('note') or getattr(args, 'note', None) or ''))
    archive(task_path)
    rows = []
    for segment, before, updated, note in staged:
        rows.append({'at': _now(), 'command': 'review-segments', 'id': updated['id'],
                     'before': audit(before), 'after': audit(updated), 'note': note,
                     'reviewer': getattr(args, 'reviewer', None)})
        segment.clear()
        segment.update(updated)
    save(task_path, task)
    append_log(root, rows)
    print(f'已回填 {len(staged)} 条审核结论；旧 task.json 已归档到 history/。')
    if not getattr(args, 'no_extract', False):
        extract(SimpleNamespace(task=str(task_path)))


def reselect_segments(args):
    """Re-select boundaries by hand, keep the original interval, then re-export."""
    task_path = Path(args.task).resolve()
    root = task_path.parent
    task = read(task_path)
    updates = entries(args.selections)
    source = Path(task['source'])
    if fingerprint(source) != task['source_sha256']:
        raise ValueError('原视频改变，请重新分析')
    duration = min(task['duration'], media_duration(probe(source), 'video'))
    windows = observed_windows(task)
    if not windows:
        raise ValueError('任务缺少观察覆盖区间，无法确认重新选区仍在已观察范围')
    requirements = task.get('requirements') or {}
    known = _segment_map(task)
    if not getattr(args, 'no_extract', False):
        export_preconditions(task)
    staged = []
    for entry in updates:
        sid = entry.get('id')
        if not isinstance(sid, str) or sid not in known:
            raise ValueError(f'{sid}: 任务中没有该片段')
        segment = known[sid]
        before = copy.deepcopy(segment)
        updated = copy.deepcopy(segment)
        a, b = entry.get('start'), entry.get('end')
        if not number(a) or not number(b) or not 0 <= a < b <= duration:
            raise ValueError(f'{sid}: 新选区必须位于原视频范围内')
        if not within_windows(windows, a, b):
            raise ValueError(f'{sid}: 新选区超出已观察范围，请先补充观察再改边界')
        reason = entry.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'{sid}: 重新选区需要写明原因')
        decision = entry.get('decision', updated.get('decision'))
        if decision not in DECISIONS:
            raise ValueError(f'{sid}: decision 必须为 keep/reject/uncertain')
        old = (updated.get('start'), updated.get('end'))
        if 'original_start' not in updated:
            updated['original_start'], updated['original_end'] = old
        history = list(updated.get('boundary_history') or [])
        history.append({'source': 'manual_reselect', 'from': [old[0], old[1]], 'to': [a, b],
                        'reason': reason.strip(), 'at': _now()})
        updated['boundary_history'] = history
        updated['start'], updated['end'] = a, b
        updated['decision'] = decision
        updated['boundary_reviewed'] = True
        updated['review_method'] = 'manual_reselect'
        updated['reviewed_at'] = _now()
        evidence = frames_between(root, task, a, b)
        if not evidence:
            raise ValueError(f'{sid}: 新选区没有可用证据，请先补充观察')
        updated['evidence'] = evidence
        if decision == 'keep':
            if not str(updated.get('facts') or '').strip() or not str(updated.get('reason') or '').strip():
                raise ValueError(f'{sid}: 标记 keep 需要事实与选择理由')
            problem = content_problem(updated, requirements) if task.get('standard') == 'content-v2' else None
            if problem:
                raise ValueError(f'{sid}: {problem}')
            if not MIN_CLIP_SECONDS - 1e-9 <= b - a <= MAX_CLIP_SECONDS + 1e-9 and not single_take_exception(task, updated):
                print(f'{sid}: 新选区 {b - a:.3f} 秒超出默认范围且未核实一镜到底例外，将进入人工审核队列而不是自动 clips。')
        staged.append((segment, before, updated, reason.strip()))
    archive(task_path)
    rows = []
    for segment, before, updated, reason in staged:
        rows.append({'at': _now(), 'command': 'reselect-segments', 'id': updated['id'],
                     'before': audit(before), 'after': audit(updated), 'note': reason,
                     'reviewer': getattr(args, 'reviewer', None)})
        segment.clear()
        segment.update(updated)
    save(task_path, task)
    append_log(root, rows)
    print(f'已按新选区更新 {len(staged)} 条片段；原区间保留在 original_start/original_end 与 boundary_history。')
    if not getattr(args, 'no_extract', False):
        extract(SimpleNamespace(task=str(task_path)))


def register(sub):
    p = sub.add_parser('recognize-content', help='创建整片内容识别任务及概览证据，判断由视觉助手完成')
    p.add_argument('--video', required=True); p.add_argument('--request', required=True)
    p.add_argument('--output', required=True); p.set_defaults(func=prepare)
    p = sub.add_parser('extract-segments', help='导出内容任务中已核实的多个有效区间')
    p.add_argument('--task', required=True); p.set_defaults(func=extract)
    p = sub.add_parser('review-segments', help='回填人工审核结论并重新导出，保留历史')
    p.add_argument('--task', required=True); p.add_argument('--decisions', required=True)
    p.add_argument('--reviewer'); p.add_argument('--note'); p.add_argument('--no-extract', action='store_true')
    p.set_defaults(func=review_segments)
    p = sub.add_parser('reselect-segments', help='人工重新选区并导出，校验已观察范围且保留原区间')
    p.add_argument('--task', required=True); p.add_argument('--selections', required=True)
    p.add_argument('--reviewer'); p.add_argument('--no-extract', action='store_true')
    p.set_defaults(func=reselect_segments)
