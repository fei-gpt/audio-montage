"""Content-first task records and evidence-approved multi-range extraction."""
import csv
from pathlib import Path
from types import SimpleNamespace
from montage import read, save, probe, portrait_geometry, media_duration, fingerprint, number, run


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
                'standard': 'content-v2', 'min_clip_seconds': 1.0, 'max_clip_seconds': 3.0, 'keep_original_audio': True,
                'rights': {'usage': 'unknown'}, 'requirements': {'hard': [], 'preferences': [], 'exclusions': [], 'confirmed': False},
                'criteria': {'base_version': 'content-v2', 'profiles': ['general'], 'user_revision': 1},
                'analysis': {'overview': '', 'coverage': [], 'reviewed': False}, 'segments': [],
                'segment_example': {'id': 'S001', 'start': 0, 'end': 1,
                    'facts': '', 'editorial_value': '', 'quality_issues': [],
                    'content_roles': [], 'visible_claims': [], 'unsupported_claims': [],
                    'use_conditions': [], 'requirement_match': 'unknown',
                    'assessment': {'base': {}, 'profile': {}, 'user': []},
                    'alternatives': [], 'tradeoffs': [],
                    'decision': 'uncertain', 'reason': '', 'evidence': [],
                    'boundary_reviewed': False}})
    save(root / 'progress.json', {'status': 'needs_observation', 'completed': [], 'remaining': ['observe_whole_video', 'judge_content', 'review_boundaries', 'extract']})
    (root / 'resume.md').write_text('读取 task.json 和 CONTENT_STANDARD.md；先观察整片，再密看候选动作。不要把示例当作判断结果。\n', encoding='utf-8')
    # Reuse the existing evidence tool without creating fake semantic labels.
    record = root / 'assets' / (digest + '.json')
    save(record, {'asset': {'paths': [str(source)], 'asset_hash': digest}})
    from understanding import observe
    observe(SimpleNamespace(record=str(record), start=0, end=None, every=2))
    print(task)


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
    if task.get('standard') == 'content-v2' and task.get('requirements', {}).get('confirmed') is not True:
        raise ValueError('需要将用户原始要求整理为已核对的任务条件')
    selected, ids, manual_review = [], set(), []
    for segment in task['segments']:
        if segment.get('decision') not in {'keep', 'reject', 'uncertain'}:
            raise ValueError('decision 必须为 keep/reject/uncertain')
        if segment['decision'] != 'keep':
            continue
        if task.get('standard') == 'content-v2':
            assessment = segment.get('assessment', {})
            base = assessment.get('base', {})
            required_dimensions = {'content_legibility', 'temporal_integrity', 'technical_usability', 'evidence_sufficiency'}
            if not required_dimensions.issubset(base):
                raise ValueError('缺少通用标准的分维度判断')
            if any(v not in {'pass', 'conditional', 'fail', 'unknown', 'not_applicable'} for v in base.values()):
                raise ValueError('通用维度判断值无效')
            if base['evidence_sufficiency'] != 'pass' or any(v in {'fail', 'unknown'} for v in base.values()):
                raise ValueError('保留项存在未解决的通用标准问题')
            if 'conditional' in base.values() and not segment.get('use_conditions'):
                raise ValueError('有条件可用的镜头必须说明使用条件')
            user_results = assessment.get('user', [])
            hard_ids = {r['id'] for group in ['hard', 'exclusions'] for r in task['requirements'].get(group, [])}
            checks = {r['id']: r.get('result') for r in user_results}
            if any(checks.get(rid) != 'pass' for rid in hard_ids):
                raise ValueError('用户硬性条件或排除规则未全部通过')
        sid, a, b = segment['id'], segment['start'], segment['end']
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('片段 ID 为空或重复')
        ids.add(sid)
        if not number(a) or not number(b) or not 0 <= a < b <= min(task['duration'], actual_duration):
            raise ValueError('片段时间超出原视频')
        if not segment.get('boundary_reviewed') or not segment.get('facts') or not segment.get('reason'):
            raise ValueError('保留片段需要事实、选择理由和边界复核')
        evidence = segment.get('evidence', [])
        if not evidence or any(not number(e.get('time')) or not a <= e['time'] <= b
                               or not Path(e.get('path', '')).is_file() for e in evidence):
            raise ValueError('保留片段缺少有效的时间证据')
        if b - a < 1.0 - 1e-9 or b - a > 3.0 + 1e-9:
            manual_review.append(dict(segment, review_reason='候选时长不在1–3秒范围，禁止自动补长、截断或作为有效片段交付，需人工审核',
                                      source=str(source), duration=b - a))
            continue
        selected.append(segment)
    review_folder = root / 'manual-review-clips'
    for index, candidate in enumerate(manual_review, 1):
        review_folder.mkdir(exist_ok=True)
        from asset_index import digest_json
        identity = digest_json({'source': task['source_sha256'], 'start': candidate['start'],
                                'end': candidate['end'], 'audio': task.get('keep_original_audio', True)})
        review_video = review_folder / f'{index:04}-{identity[:12]}.mp4'
        if not review_video.exists():
            staged_review = review_video.with_suffix('.partial.mp4')
            audio_args = ['-map', '0:a:0?', '-c:a', 'aac'] if task.get('keep_original_audio', True) else ['-an']
            run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', candidate['start'], '-i', source,
                 '-t', candidate['duration'], '-map', '0:v:0', *audio_args, '-c:v', 'libx264',
                 '-pix_fmt', 'yuv420p', staged_review])
            run(['ffmpeg', '-v', 'error', '-nostdin', '-i', staged_review, '-f', 'null', '-'])
            staged_review.replace(review_video)
        candidate['review_video'] = str(review_video)
    save(root / 'manual-review.json', {'min_clip_seconds': 1.0, 'max_clip_seconds': 3.0, 'segments': manual_review})
    with (root / 'manual-review.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'source', 'start', 'end', 'duration', 'review_video', 'reason', 'review_reason'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(manual_review)
    destination = root / 'clips'
    destination.mkdir(exist_ok=True)
    manifest_path = root / 'extraction.json'
    previous = read(manifest_path).get('clips', []) if manifest_path.exists() else []
    completed = []
    for index, segment in enumerate(selected, 1):
        signature = {'source_sha256': task['source_sha256'], 'id': segment['id'],
                     'start': segment['start'], 'end': segment['end'],
                     'audio': task.get('keep_original_audio', True)}
        from asset_index import digest_json
        digest = digest_json(signature)
        output = destination / f'{index:04}-{digest[:12]}.mp4'
        old = next((r for r in previous if r.get('signature') == digest), None)
        if old and output.exists() and old.get('output_sha256') == fingerprint(output):
            completed.append(dict(old, reason=segment['reason']))
            continue
        staged = destination / f'{digest}.partial.mp4'
        audio = ['-map', '0:a:0?', '-c:a', 'aac'] if signature['audio'] else ['-an']
        run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', segment['start'], '-i', source,
             '-t', segment['end'] - segment['start'], '-map', '0:v:0', *audio,
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', staged])
        info = probe(staged)
        portrait_geometry(info)
        if not 1.0 - 1e-6 <= media_duration(info, 'video') <= 3.0 + 1e-6:
            raise ValueError('实际输出不在1–3秒范围，停止交付并人工审核')
        if abs(media_duration(info, 'video') - (segment['end'] - segment['start'])) > .15:
            raise ValueError('输出片段时长不符')
        run(['ffmpeg', '-v', 'error', '-nostdin', '-i', staged, '-f', 'null', '-'])
        from workflow import archive
        archive(output)
        staged.replace(output)
        completed.append(dict(signature, signature=digest, output=str(output),
                              output_sha256=fingerprint(output), reason=segment['reason']))
        save(manifest_path, {'clips': completed})
        save(root / 'progress.json', {'status': 'extracting', 'completed': completed,
                                     'remaining': [s['id'] for s in selected[index:]]})
    save(manifest_path, {'clips': completed, 'decisions': task['segments'], 'manual_review': manual_review})
    with (root / 'clips.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'start', 'end', 'output', 'reason'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(completed)
    save(root / 'progress.json', {'status': 'needs_manual_review' if manual_review else 'completed', 'completed': completed,
                                    'remaining': [s['id'] for s in manual_review], 'manual_review': manual_review})
    print(manifest_path)


def register(sub):
    p = sub.add_parser('recognize-content', help='创建整片内容识别任务及概览证据，判断由视觉助手完成')
    p.add_argument('--video', required=True); p.add_argument('--request', required=True)
    p.add_argument('--output', required=True); p.set_defaults(func=prepare)
    p = sub.add_parser('extract-segments', help='导出内容任务中已核实的多个有效区间')
    p.add_argument('--task', required=True); p.set_defaults(func=extract)
