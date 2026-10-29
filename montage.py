#!/usr/bin/env python3
"""Local audio-led montage. Only download-model explicitly accesses the network."""
import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import hashlib
import shutil
import os
import textwrap
import difflib
from pathlib import Path
from fractions import Fraction


def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr[-4000:])
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path]))


def media_duration(info, kind):
    streams = [s for s in info['streams'] if s['codec_type'] == kind
               and not (kind == 'video' and s.get('disposition', {}).get('attached_pic'))]
    if not streams:
        raise ValueError(f'输入没有可用的 {kind} 轨道')
    values = []
    for value in [streams[0].get('duration'), info.get('format', {}).get('duration')]:
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                values.append(value)
        except (ValueError, TypeError):
            pass
    if not values:
        raise ValueError('无法确定媒体有效时长')
    return min(values)


def portrait_geometry(info):
    """Require exact 9:16 display geometry, including pixel shape and rotation."""
    streams = [s for s in info['streams'] if s['codec_type'] == 'video']
    if len(streams) != 1 or streams[0].get('disposition', {}).get('attached_pic'):
        raise ValueError('视频轨道无法唯一确定，排除该素材')
    stream = streams[0]
    w, h = stream.get('width'), stream.get('height')
    if type(w) is not int or type(h) is not int or min(w, h) <= 0:
        raise ValueError('无法确定视频尺寸，排除该素材')
    sar = stream.get('sample_aspect_ratio')
    dar = stream.get('display_aspect_ratio')
    def ratio(value):
        parsed = Fraction(str(value).replace(':', '/'))
        if parsed <= 0:
            raise ValueError('无效的视频像素比例')
        return parsed
    display = Fraction(w, h)
    try:
        if sar not in [None, 'N/A', '0:1']:
            display *= ratio(sar)
        elif dar not in [None, 'N/A', '0:1']:
            display = ratio(dar)
    except (ValueError, ZeroDivisionError):
        raise ValueError('无法确定视频显示比例，排除该素材')
    rotation = stream.get('tags', {}).get('rotate', 0)
    for side in stream.get('side_data_list', []):
        if 'rotation' in side:
            rotation = side['rotation']
            break
    try:
        rotation = float(rotation) % 180
    except (ValueError, TypeError):
        raise ValueError('旋转信息无效，排除该素材')
    if not math.isfinite(rotation) or rotation not in [0, 90]:
        raise ValueError('非直角旋转无法确认 9:16，排除该素材')
    if rotation == 90:
        display = 1 / display
    if display != Fraction(9, 16):
        raise ValueError(f'素材显示比例为 {display.numerator}:{display.denominator}，仅允许 9:16')
    return {'coded_width': w, 'coded_height': h, 'rotation': rotation,
            'display_ratio': '9:16', 'stream_index': stream.get('index', 0)}


def require_portrait_output(config):
    w, h = config.get('width'), config.get('height')
    if type(w) is not int or type(h) is not int or min(w, h) <= 0 or w * 16 != h * 9:
        raise ValueError('项目输出只允许 9:16，例如 1080×1920 或 720×1280')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: interruption must not truncate a plan or an index report.
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=Path(path).parent, delete=False) as tmp:
        name = tmp.name
        try:
            json.dump(value, tmp, ensure_ascii=False, indent=2, allow_nan=False)
            tmp.write('\n')
        except Exception:
            Path(name).unlink(missing_ok=True)
            raise
    os.replace(name, path)


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def timestamp(value):
    h, m, s = value.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def srt_time(value):
    ms = round(value * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'


def timing(path):
    if Path(path).suffix.lower() == '.json':
        data = read(path)
        return data['segments'] if isinstance(data, dict) else data
    segments = []
    for block in re.split(r'\n\s*\n', Path(path).read_text(encoding='utf-8-sig').strip()):
        lines = block.strip().splitlines()
        at = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if at is None:
            raise ValueError('SRT 段落缺少时间戳')
        start, end = lines[at].split('-->')
        segments.append({'start': timestamp(start.strip()), 'end': timestamp(end.strip()),
                         'text': '\n'.join(lines[at + 1:])})
    return segments


def check_segments(segments, duration):
    if not segments:
        raise ValueError('时间轴不能为空')
    previous = 0
    for i, s in enumerate(segments):
        if not number(s.get('start')) or not number(s.get('end')):
            raise ValueError(f'段落 {i + 1} 时间无效')
        if s['start'] < 0 or s['start'] < previous - 0.001 or s['end'] <= s['start'] or s['end'] > duration + 0.001:
            raise ValueError(f'段落 {i + 1} 越界、重叠或时长无效')
        if not isinstance(s.get('text'), str) or not s['text'].strip():
            raise ValueError(f'段落 {i + 1} 文案为空')
        word_end = s['start']
        for word in s.get('words', []):
            if (not number(word.get('start')) or not number(word.get('end')) or
                    word['start'] < word_end - 0.001 or word['end'] < word['start'] or
                    word['start'] < s['start'] - 0.001 or word['end'] > s['end'] + 0.001 or
                    not isinstance(word.get('text'), str)):
                raise ValueError(f'段落 {i + 1} 词级时间戳无效')
            word_end = word['end']
        previous = s['end']


def init(args):
    audio = Path(args.audio).resolve()
    info = probe(audio)
    if not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise ValueError('输入文件没有音轨')
    root = Path(args.project).resolve()
    config = root / 'project.json'
    if config.exists():
        raise ValueError('项目已存在，请使用新的目录')
    if any(type(v) is not int or v <= 0 for v in [args.width, args.height, args.fps]) or args.width % 2 or args.height % 2:
        raise ValueError('宽高必须为正偶数，fps 必须为正整数')
    require_portrait_output({'width': args.width, 'height': args.height})
    save(config, {'version': 2, 'audio': str(audio), 'audio_sha256': fingerprint(audio),
                  'duration': media_duration(info, 'audio'),
                  'width': args.width, 'height': args.height, 'fps': args.fps,
                  'language': getattr(args, 'language', 'auto'), 'fit': 'contain',
                  'keep_original_audio': getattr(args, 'keep_original_audio', False)})
    for folder in ['audio', 'plans', 'out', 'qa']:
        (root / folder).mkdir(exist_ok=True)
    print(config)


def set_audio(args):
    path = Path(args.project).resolve() / 'project.json'
    config = read(path)
    if type(args.keep_original_audio) is not bool:
        raise ValueError('保留原声选项必须是布尔值')
    config['keep_original_audio'] = args.keep_original_audio
    save(path, config)
    print('保留原视频声音：' + ('已勾选' if args.keep_original_audio else '未勾选（默认）'))


def settings(args):
    # A small native settings window, not a separate web application.
    import tkinter as tk
    from tkinter import ttk, messagebox
    config = read(Path(args.project).resolve() / 'project.json')
    if type(config.get('keep_original_audio', False)) is not bool:
        raise ValueError('keep_original_audio 必须为 true/false')
    window = tk.Tk()
    window.title('混剪设置')
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    choice = tk.BooleanVar(value=config.get('keep_original_audio', False))
    ttk.Checkbutton(frame, text='保留原视频声音', variable=choice).pack(anchor='w')
    ttk.Label(frame, text='默认不勾选。此设置统一应用于整条成片和剪映草稿。').pack(anchor='w', pady=(10, 16))
    buttons = ttk.Frame(frame)
    buttons.pack(anchor='e')
    def commit():
        try:
            set_audio(argparse.Namespace(project=args.project, keep_original_audio=choice.get()))
        except (ValueError, OSError) as exc:
            messagebox.showerror('保存失败', str(exc), parent=window)
            return
        window.destroy()
    ttk.Button(buttons, text='取消', command=window.destroy).pack(side='left', padx=(0, 8))
    ttk.Button(buttons, text='保存', command=commit).pack(side='left')
    window.mainloop()


def import_timing(args):
    root = Path(args.project)
    config = read(root / 'project.json')
    if (root / 'audio/timing.json').exists():
        raise ValueError('已有时间轴，拒绝覆盖；请先备份移走，避免使已有选片失效')
    segments = timing(args.timing)
    check_segments(segments, config['duration'])
    save(root / 'audio/timing.json', {'segments': segments, 'reviewed': False,
                                    'language': config.get('language', 'auto'),
                                    'note': '导入的时间戳尚未人工复核；不会按字数估算时间。'})
    print(f'已导入 {len(segments)} 段；原时间戳和停顿保留。')


def phrases(segments, max_chars=None, max_seconds=None, language='en'):
    max_chars = max_chars or (15 if language == 'zh' else 78)
    max_seconds = max_seconds or (4 if language == 'zh' else 5)
    output = []
    for segment in segments:
        words = segment.get('words') or []
        if not words:
            output.append(segment)
            continue
        pending = []
        def flush():
            if pending:
                start, end = pending[0]['start'], pending[-1]['end']
                if end > start:
                    output.append({'start': start, 'end': end,
                                   'text': ''.join(w['text'] for w in pending).strip(),
                                   'words': list(pending)})
                elif output:
                    # Zero-duration ASR tokens may carry punctuation/particles.
                    output[-1]['text'] += ''.join(w['text'] for w in pending)
                    output[-1].setdefault('words', []).extend(pending)
                else:
                    raise ValueError('识别词缺少可用时长，请人工校正时间轴')
                pending.clear()
        for index, word in enumerate(words):
            if pending and (len(''.join(w['text'] for w in pending) + word['text']) > max_chars or
                            word['end'] - pending[0]['start'] > max_seconds or
                            (language != 'zh' and len(pending) >= 12)):
                flush()
            pending.append(word)
            token = word['text'].strip()
            abbreviation = token.casefold() in {'mr.', 'mrs.', 'ms.', 'dr.', 'sr.', 'sra.', 'srta.', 'ud.', 'uds.', 'e.g.', 'i.e.'}
            decimal = (token.endswith('.') and token[:-1].isdigit() and index + 1 < len(words)
                       and words[index + 1]['text'].strip()[:1].isdigit())
            if re.search(r'[，。！？；、,.!?;][\"”\')\]]*$', token) and not abbreviation and not decimal:
                flush()
        flush()
    return output


def transcribe(args):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ValueError('尚未安装 faster-whisper。也可以直接用 import-timing 导入已有 SRT/JSON。')
    model_path = Path(args.model).resolve()
    if not model_path.is_dir():
        raise ValueError('--model 必须是已有本地模型目录，不自动下载模型')
    root = Path(args.project)
    config = read(root / 'project.json')
    if (root / 'audio/timing.json').exists():
        raise ValueError('已有时间轴，拒绝覆盖；请先备份并移走旧文件')
    language = args.language or config.get('language', 'auto')
    if language not in {'auto', 'en', 'es', 'zh'}:
        raise ValueError('language 必须为 auto/en/es/zh')
    signature = {'audio_sha256': fingerprint(config['audio']), 'model_path': str(model_path),
                 'language_requested': language, 'task': 'transcribe', 'backend': 'faster-whisper'}
    model = WhisperModel(str(model_path), device='cpu', compute_type='int8', local_files_only=True,
                         cpu_threads=max(1, min(4, os.cpu_count() or 1)))
    # Decode through the already required FFmpeg instead of coupling file input
    # to PyAV API changes across versions. Whisper expects mono float32, 16 kHz.
    import numpy as np
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', config['audio'],
                              '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                              capture_output=True)
    if decoded.returncode:
        raise ValueError(decoded.stderr.decode(errors='replace')[-1000:])
    samples = np.frombuffer(decoded.stdout, dtype=np.float32).copy()
    if not len(samples) or float(np.max(np.abs(samples))) < 0.0001:
        raise ValueError('音频为空或接近静音，停止转写以避免生成幻觉字幕')
    results, detected = model.transcribe(samples, language=None if language == 'auto' else language,
                                  task='transcribe', word_timestamps=True, condition_on_previous_text=False,
                                  initial_prompt=args.prompt)
    segments = [{'start': s.start, 'end': s.end, 'text': s.text.strip(),
                 'words': [{'start': w.start, 'end': w.end, 'text': w.word} for w in (s.words or [])]}
                for s in results if s.text.strip()]
    signature.update({'language_detected': detected.language,
                      'language_probability': detected.language_probability})
    save(root / 'audio/raw-transcript.json', {'segments': segments, 'provenance': signature})
    check_segments(segments, config['duration'])
    segments = phrases(segments, language=detected.language)
    check_segments(segments, config['duration'])
    save(root / 'audio/timing.json', {'segments': segments, 'reviewed': False, 'provenance': signature,
                                    'language': detected.language,
                                    'note': 'ASR 估计时间戳，需核对文案和边界，不等于强制对齐。'})
    export_srt(root, segments)
    print(f'已本地转写 {len(segments)} 段，需复核。')


def download_model(args):
    dest = Path(args.output).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('HF_HOME', str(dest / '.hf-cache'))
    os.environ.setdefault('HF_XET_CACHE', str(dest / '.xet-cache'))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    if args.endpoint:
        if not args.endpoint.startswith('https://'):
            raise ValueError('模型服务 endpoint 必须是 https URL')
        os.environ['HF_ENDPOINT'] = args.endpoint.rstrip('/')
    from faster_whisper.utils import download_model as download
    # Cache resides with the chosen model, not in the user's home directory.
    path = download(args.name, output_dir=str(dest), cache_dir=str(dest / '.cache'))
    print(path)


def compare_script(args):
    root = Path(args.project).resolve()
    source = Path(args.script).read_text(encoding='utf-8-sig')
    recognized = ' '.join(s['text'] for s in read(root / 'audio/timing.json')['segments'])
    pattern = r"[^\W_]+(?:['’][^\W_]+)*"
    expected = re.findall(pattern, source.casefold(), flags=re.UNICODE)
    actual = re.findall(pattern, recognized.casefold(), flags=re.UNICODE)
    if not expected:
        raise ValueError('原稿没有可比较的文字')
    comparison = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    changes = [{'type': tag, 'expected': expected[a:b], 'recognized': actual[c:d]}
               for tag, a, b, c, d in comparison.get_opcodes() if tag != 'equal']
    report = {'reference': str(Path(args.script).resolve()), 'differences': changes,
              'exact_token_match': not changes, 'reference_tokens': len(expected),
              'recognized_tokens': len(actual),
              'note': '保留重音、数字和原词差异供人工核对；忽略大小写和大部分标点。未修改字幕，不执行强制对齐。'}
    save(root / 'qa/transcript-comparison.json', report)
    print(f'发现 {len(changes)} 处词项差异，见 qa/transcript-comparison.json')


def preflight(args):
    import importlib.util
    root = Path(args.project).resolve()
    config = read(root / 'project.json')
    require_portrait_output(config)
    audio = probe(config['audio'])
    stream = next((s for s in audio['streams'] if s['codec_type'] == 'audio'), None)
    if not stream:
        raise ValueError('配音不存在可用音轨')
    report = {'language': config.get('language', 'auto'),
              'audio': {'duration': float(audio['format']['duration']),
                        'sample_rate': stream.get('sample_rate'), 'channels': stream.get('channels'),
                        'sha256_matches': not config.get('audio_sha256') or fingerprint(config['audio']) == config['audio_sha256']},
              'tools': {k: shutil.which(k) for k in ['ffmpeg', 'ffprobe']},
              'packages': {k: bool(importlib.util.find_spec(k)) for k in ['faster_whisper', 'pyJianYingDraft']},
              'free_disk_gb': round(shutil.disk_usage(root).free / 1024 ** 3, 2),
              'output': {k: config[k] for k in ['width', 'height', 'fps', 'fit']},
              'keep_original_audio': config.get('keep_original_audio', False),
              'notes': ['auto 为整条音频检测主要语言；已知是英文或西语时建议明确设为 en/es。',
                        '字幕保留配音原语言；检索跨语言需要已有双语描述、别名或同语言 query。']}
    save(root / 'qa/preflight.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['audio']['sha256_matches']:
        raise ValueError('配音已变化，请重新建项目')


def export_draft(args):
    try:
        import pyJianYingDraft as draft
    except ImportError:
        raise ValueError('请先安装 requirements.txt 中的 pyJianYingDraft')
    root = Path(args.project).resolve()
    config, shots, segments, report = validate(root)
    if report['errors']:
        raise ValueError('校验失败：\n' + '\n'.join(report['errors']))
    if report['warnings'] and not args.allow_unreviewed:
        raise ValueError('请先完成复核，或明确使用 --allow-unreviewed 导出待审草稿')
    target = (root / 'out' / args.name).resolve()
    if target.parent != (root / 'out').resolve():
        raise ValueError('草稿名称必须为单层目录名')
    if target.exists():
        raise ValueError('草稿目录已存在，拒绝覆盖')
    # Stage the entire export so a failed export cannot leave a partial draft.
    with tempfile.TemporaryDirectory(prefix='draft-', dir=root) as tmp:
        package = Path(tmp) / args.name
        script = draft.DraftFolder(tmp).create_draft(args.name, config['width'], config['height'],
                                                    config['fps'], maintrack_adsorb=False)
        media = package / 'media'
        media.mkdir()
        copied = {}
        def copy_media(path):
            source = Path(path).resolve()
            key = fingerprint(source)
            filename = key[:16] + source.suffix.lower()
            if key not in copied:
                shutil.copy2(source, media / filename)
                copied[key] = str(target / 'media' / filename)
            return copied[key]
        # Library needs files to exist when reading their metadata. Build with
        # original paths, then rewrite material paths to final bundled copies.
        script.append_tracks([draft.TrackSpec(draft.TrackType.video, 'main_video'),
                              draft.TrackSpec(draft.TrackType.audio, 'voice'),
                              draft.TrackSpec(draft.TrackType.text, 'captions')])
        mapping = {}
        for shot in shots:
            selection = shot['selection']
            source = str(Path(selection['path']).resolve())
            mapping[source] = copy_media(source)
            tr = draft.Timerange(round(shot['start'] * 1e6), round(shot['end'] * 1e6) - round(shot['start'] * 1e6))
            segment = draft.VideoSegment(source, tr,
                         source_timerange=draft.Timerange(round(selection['source_start'] * 1e6), tr.duration),
                         volume=1.0 if config.get('keep_original_audio', False) else 0.0)
            # Sources already passed the strict 9:16 display check; no crop or
            # enlargement is used to turn an ineligible source into portrait.
            script.add_segment(segment, 'main_video')
        audio = str(Path(config['audio']).resolve())
        mapping[audio] = copy_media(audio)
        script.add_segment(draft.AudioSegment(audio, draft.Timerange(0, round(config['duration'] * 1e6))), 'voice')
        for s in segments:
            script.add_segment(draft.TextSegment(subtitle_text(s['text']),
                draft.Timerange(round(s['start'] * 1e6), round(s['end'] * 1e6) - round(s['start'] * 1e6)),
                style=draft.TextStyle(size=8.0), clip_settings=draft.ClipSettings(transform_y=-0.8)), 'captions')
        data = json.loads(script.dumps())
        data['id'] = __import__('uuid').uuid4().hex.upper()
        def rewrite(value):
            if isinstance(value, dict):
                return {k: rewrite(v) for k, v in value.items()}
            if isinstance(value, list):
                return [rewrite(v) for v in value]
            if isinstance(value, str):
                return mapping.get(value, value)
            return value
        data = rewrite(data)
        save(package / 'draft_content.json', data)
        save(package / 'draft_info.json', data)
        meta = read(package / 'draft_meta_info.json')
        meta.update({'draft_id': data['id'], 'draft_name': args.name,
                     'draft_fold_path': str(target), 'draft_root_path': str(target.parent),
                     'tm_duration': data['duration']})
        save(package / 'draft_meta_info.json', meta)
        save(package / 'media_manifest.json', {'original_to_bundled': mapping,
            'note': '绝对路径绑定当前位置；移动草稿包后需重导或重新链接素材。'})
        save(package / 'export_report.json', {'track_count': len(data['tracks']),
             'video_segments': len(shots), 'subtitle_segments': len(segments),
             'duration_us': data['duration'], 'draft_id': data['id'],
             'editor_open_verified': False, 'platform': sys.platform,
             'keep_original_audio': config.get('keep_original_audio', False),
             'warnings': report['warnings'],
             'note': '独立草稿包。未注册到剪映草稿列表，未验证当前 Mac 剪映兼容性。'})
        package.rename(target)
    print(target)


def build(args):
    root = Path(args.project)
    config = read(root / 'project.json')
    data = read(root / 'audio/timing.json')
    segments = data['segments']
    check_segments(segments, config['duration'])
    if (root / 'plans/edit.json').exists():
        raise ValueError('edit.json 已存在，拒绝覆盖已有选片')
    shots, cursor = [], 0.0
    for s in segments:
        if s['start'] > cursor + 0.001:
            shots.append({'start': cursor, 'end': s['start'], 'text': '', 'purpose': '停顿期间画面待编排'})
        shots.append({'start': s['start'], 'end': s['end'], 'text': s['text'], 'purpose': ''})
        cursor = s['end']
    if cursor < config['duration'] - 0.001:
        shots.append({'start': cursor, 'end': config['duration'], 'text': '', 'purpose': '结尾画面待编排'})
    for i, s in enumerate(shots):
        s.update({'id': f'S{i + 1:03}', 'query': '', 'required': [], 'forbidden': [],
                  'selection': None, 'reviewed': False})
    save(root / 'plans/edit.json', {'version': 1, 'shots': shots})
    print('已生成待编排清单。初始按转写段落拆分，可按语义合并或细分镜头。')


def expand_shots(shots):
    """Resolve multi-source selections to continuous, ordinary render segments."""
    output = []
    for shot in shots:
        selection = shot.get('selection')
        if not isinstance(selection, dict) or 'parts' not in selection:
            output.append(shot)
            continue
        parts = selection['parts']
        if not isinstance(parts, list) or not parts:
            raise ValueError(f'{shot["id"]}: 多段素材清单为空')
        if 'path' in selection:
            raise ValueError(f'{shot["id"]}: selection 不可同时包含 path 和 parts')
        cursor = shot['start']
        for index, part in enumerate(parts):
            duration = part.get('duration')
            if not number(duration) or duration <= 0:
                raise ValueError(f'{shot["id"]}: 子片段时长无效')
            child = dict(shot)
            child.update({'id': f'{shot["id"]}.{index + 1}', 'parent_id': shot['id'],
                          'start': cursor, 'end': cursor + duration,
                          'selection': {k: v for k, v in part.items() if k != 'duration'}})
            output.append(child)
            cursor += duration
        if abs(cursor - shot['end']) > 0.00001:
            raise ValueError(f'{shot["id"]}: 子片段总时长与配音分镜不一致')
        output[-1]['end'] = shot['end']
    return output


def validate(root):
    config = read(root / 'project.json')
    require_portrait_output(config)
    shots = expand_shots(read(root / 'plans/edit.json')['shots'])
    segments = read(root / 'audio/timing.json')['segments']
    check_segments(segments, config['duration'])
    errors, warnings, advisories, cursor, ids = [], [], [], 0.0, set()
    if not shots:
        errors.append('镜头清单为空')
    for key in ['width', 'height', 'fps']:
        if not isinstance(config.get(key), int) or config[key] <= 0:
            errors.append(f'{key} 必须是正整数')
    if config['width'] % 2 or config['height'] % 2:
        errors.append('宽高必须是偶数')
    if config.get('fit') != 'contain':
        errors.append('仅允许原比例缩放；不通过 cover 裁剪接纳非 9:16 素材')
    if type(config.get('keep_original_audio', False)) is not bool:
        errors.append('keep_original_audio 必须为 true/false')
    audio = probe(config['audio'])
    if config.get('audio_sha256') and fingerprint(config['audio']) != config['audio_sha256']:
        errors.append('配音内容已改变，请重新建立项目和时间轴')
    if abs(media_duration(audio, 'audio') - config['duration']) > 0.05:
        errors.append('配音文件时长已改变，请重新建立时间轴')
    source_cache, used_ranges = {}, {}
    for shot in shots:
        sid = shot.get('id', '?')
        if sid in ids:
            errors.append(f'{sid}: 镜头 ID 重复')
        ids.add(sid)
        start, end = shot.get('start'), shot.get('end')
        if not number(start) or not number(end) or end <= start:
            errors.append(f'{sid}: 时间无效')
            continue
        if abs(start - cursor) > 0.001:
            errors.append(f'{sid}: 镜头时间轴不连续（停顿也需要画面）')
        cursor = end
        if not shot.get('purpose'):
            warnings.append(f'{sid}: 尚未填写画面目的')
        sel = shot.get('selection')
        if not sel:
            errors.append(f'{sid}: 缺素材')
            continue
        try:
            source_path = str(Path(sel['path']).resolve())
            if source_path not in source_cache:
                source_cache[source_path] = (probe(source_path), fingerprint(source_path))
            media, source_hash = source_cache[source_path]
            if sel.get('rights', {}).get('usage') == 'prohibited':
                raise ValueError('素材被明确标记为禁止使用')
            from library_tools import policy
            warnings.extend(f'{sid}: {issue}' for issue in policy(sel, shot.get('product_model') or config.get('product_model')))
            target_model = shot.get('product_model') or config.get('product_model')
            if target_model:
                product = sel.get('product', {})
                if product.get('reuse_scope') != 'generic_context' and not (
                    product.get('reuse_scope') == 'product_specific' and product.get('model') == target_model
                ):
                    raise ValueError('选片产品身份不符合项目型号；请重新检索确认产品身份的素材')
            portrait_geometry(media)
            if not any(s['codec_type'] == 'video' for s in media['streams']):
                raise ValueError('素材没有视频轨道')
            ss = sel['source_start']
            if not number(ss) or ss < 0 or ss + end - start > media_duration(media, 'video') + 0.001:
                raise ValueError('素材区间越界或不够长；不会自动变速、循环或定格')
            if sel.get('asset_hash') and sel['asset_hash'] != source_hash:
                raise ValueError('素材内容已改变，请重新检索')
            if 'allowed_start' in sel and (ss < sel['allowed_start'] - 0.001 or ss + end - start > sel['allowed_end'] + 0.001):
                raise ValueError('选片越过已标注的可用区间')
            if 'action_start' in sel and (ss > sel['action_start'] + 0.001 or ss + end - start < sel['action_end'] - 0.001):
                raise ValueError('选片截断了标注为必须完整保留的动作')
            for previous_id, previous_start, previous_end in used_ranges.get(source_hash, []):
                if min(ss + end - start, previous_end) - max(ss, previous_start) > 0.05 and not shot.get('allow_reuse', False):
                    warnings.append(f'{sid}: 与 {previous_id} 重复使用同一画面区间；请换片，或明确设 allow_reuse=true')
            used_ranges.setdefault(source_hash, []).append((sid, ss, ss + end - start))
            video = next(s for s in media['streams'] if s['codec_type'] == 'video')
            if video.get('color_transfer') in {'smpte2084', 'arib-std-b67'}:
                advisories.append(f'{sid}: HDR 素材需检查色彩，当前未自动进行专业色调映射')
        except (KeyError, ValueError, OSError) as exc:
            errors.append(f'{sid}: {exc}')
        if not shot.get('reviewed'):
            warnings.append(f'{sid}: 尚未确认音画语义匹配和裁切')
    if abs(cursor - config['duration']) > 0.001:
        errors.append('画面总时长与配音时长不同')
    if not read(root / 'audio/timing.json').get('reviewed'):
        warnings.append('配音文案和时间戳尚未复核')
    for i, segment in enumerate(segments, 1):
        text = subtitle_text(segment['text'])
        if len(text.splitlines()) > 2:
            advisories.append(f'字幕 {i}: 超过两行，建议拆分或缩短')
        if len(re.sub(r'\s+', '', text)) / (segment['end'] - segment['start']) > 22:
            advisories.append(f'字幕 {i}: 阅读速度较快，建议检查')
    report = {'errors': errors, 'warnings': warnings, 'advisories': advisories,
              'note': '自动检查仅覆盖结构和媒体有效性，不证明语义匹配或艺术质量。'}
    save(root / 'qa/validation.json', report)
    return config, shots, segments, report


def subtitle_text(text):
    if re.search(r'[\u3400-\u9fff]', text):
        return text
    # Never split a word, hyphenated product name, contraction or accented word.
    text = ' '.join(text.split())
    words = text.split()
    if 40 < len(text) <= 78 and len(words) >= 4:
        alternatives = []
        weak_ends = set('a an the of to and in on with for el la los las de del al y en con para por'.split())
        for at in range(2, len(words) - 1):
            left, right = ' '.join(words[:at]), ' '.join(words[at:])
            if max(len(left), len(right)) <= 40:
                penalty = abs(len(left) - len(right)) + (20 if words[at - 1].casefold() in weak_ends else 0)
                alternatives.append((penalty, left, right))
        if alternatives:
            _, left, right = min(alternatives)
            return left + '\n' + right
    return '\n'.join(textwrap.wrap(text, width=40,
                                  break_long_words=False, break_on_hyphens=False))


def export_srt(root, segments):
    content = '\n\n'.join(f'{i}\n{srt_time(s["start"])} --> {srt_time(s["end"])}\n{subtitle_text(s["text"])}'
                           for i, s in enumerate(segments, 1))
    (root / 'out/captions.srt').write_text(content + '\n', encoding='utf-8')


def inputs_signature(root):
    config = read(root / 'project.json')
    shots = expand_shots(read(root / 'plans/edit.json')['shots'])
    source_paths = {str(Path(s['selection']['path']).resolve()) for s in shots if s.get('selection')}
    snapshot = {'config': config, 'audio': fingerprint(config['audio']),
                'timing': read(root / 'audio/timing.json')['segments'],
                'shots': [{'start': s['start'], 'end': s['end'],
                           'selection': {k: s.get('selection', {}).get(k) for k in ['path', 'source_start']}}
                          for s in shots],
                'sources': {p: fingerprint(p) for p in sorted(source_paths)}}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def review(args):
    root = Path(args.project).resolve()
    config = read(root / 'project.json')
    shots = expand_shots(read(root / 'plans/edit.json')['shots'])
    video = root / 'out' / ('final.mp4' if args.final else 'preview.mp4')
    if not video.exists():
        raise ValueError('请先渲染对应的预览或成片')
    record = root / 'qa' / ('final-render.json' if args.final else 'preview-render.json')
    if not record.exists():
        raise ValueError('缺少渲染版本记录，请重新渲染')
    provenance = read(record)
    if (provenance.get('inputs_sha256') != inputs_signature(root) or
            provenance.get('video_sha256') != fingerprint(video)):
        raise ValueError('剪辑清单或视频已改变，请重新渲染后审片，避免检查旧版本')
    folder = root / 'qa/frames'
    folder.mkdir(parents=True, exist_ok=True)
    lines = ['# 逐镜头审片表', '', '抽帧用于检查构图与素材；动作连续性和音画同步必须播放完整视频检查。', '']
    for i, shot in enumerate(shots):
        lines.extend([f'## {shot["id"]} · {shot["start"]:.3f}—{shot["end"]:.3f} 秒', '',
                      shot.get('text', '') or '（停顿）', '', f'画面目的：{shot.get("purpose", "")}', ''])
        for label, fraction in [('begin', 0.1), ('middle', 0.5), ('end', 0.9)]:
            t = min(shot['start'] + (shot['end'] - shot['start']) * fraction,
                    config['duration'] - 1 / config['fps'])
            dest = folder / f'{i + 1:04}-{label}.jpg'
            run(['ffmpeg', '-v', 'error', '-y', '-nostdin', '-ss', max(0, t), '-i', video,
                 '-frames:v', '1', '-vf', 'scale=360:-2', dest])
            if not dest.exists():
                raise ValueError(f'{shot["id"]}: 审片抽帧失败')
            lines.extend([f'![{label} · {t:.3f}s]({dest.as_posix()})', ''])
        lines.extend(['- [ ] 主体、动作与文案一致', '- [ ] 裁切、重复和节奏可接受',
                      '- [ ] 播放检查关键动作与旁白同步', ''])
    report = root / 'qa/review.md'
    report.write_text('\n'.join(lines), encoding='utf-8')
    print(report)


def render(args):
    root = Path(args.project).resolve()
    config, shots, segments, report = validate(root)
    if report['errors']:
        raise ValueError('校验失败：\n' + '\n'.join(report['errors']))
    if args.final and report['warnings']:
        raise ValueError('正式输出需要先处理复核项：\n' + '\n'.join(report['warnings']))
    output = root / 'out' / ('final.mp4' if args.final else 'preview.mp4')
    from workflow import archive
    archive(output)
    w, h, fps = config['width'], config['height'], config['fps']
    if not args.final:
        ratio = min(1, 640 / max(w, h))
        w, h = max(2, round(w * ratio / 2) * 2), max(2, round(h * ratio / 2) * 2)
    with tempfile.TemporaryDirectory(prefix='render-', dir=root) as tmp:
        paths, original_audio_paths, missing_audio = [], [], []
        audio_presence = {}
        for i, shot in enumerate(shots):
            sel = shot['selection']
            dest = Path(tmp) / f'{i:05}.mp4'
            fit = f'scale={w}:{h}'  # Eligible sources have exact 9:16 display ratio.
            frame_count = round(shot['end'] * fps) - round(shot['start'] * fps)
            if i == len(shots) - 1:
                frame_count += max(0, math.ceil(config['duration'] * fps) - round(config['duration'] * fps))
            if frame_count < 1:
                raise ValueError(f'{shot["id"]}: 镜头不足一帧，请合并镜头')
            run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', sel['source_start'], '-i', sel['path'],
                 '-an', '-vf', fit + f',setsar=1,trim=duration={shot["end"] - shot["start"]},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={1 / fps},fps={fps}',
                 '-frames:v', frame_count,
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'fast', dest])
            paths.append(dest)
            if config.get('keep_original_audio', False):
                audio_dest = Path(tmp) / f'{i:05}.wav'
                audio_duration = frame_count / fps
                if sel['path'] not in audio_presence:
                    audio_presence[sel['path']] = any(s['codec_type'] == 'audio' for s in probe(sel['path'])['streams'])
                has_audio = audio_presence[sel['path']]
                if has_audio:
                    # first_pts=0 preserves a source track's delayed start by
                    # filling silence instead of moving the sound earlier.
                    run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', sel['source_start'],
                         '-i', sel['path'], '-map', '0:a:0', '-vn', '-af',
                         f'aresample=48000:async=1:first_pts=0,atrim=duration={shot["end"] - shot["start"]},apad,atrim=duration={audio_duration}',
                         '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', audio_dest])
                else:
                    missing_audio.append(shot['id'])
                    run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi',
                         '-i', 'anullsrc=r=48000:cl=stereo', '-t', audio_duration,
                         '-c:a', 'pcm_s16le', audio_dest])
                original_audio_paths.append(audio_dest)
        listing = Path(tmp) / 'concat.txt'
        listing.write_text(''.join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in paths))
        joined = Path(tmp) / 'joined.mp4'
        run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'concat', '-safe', '0', '-i', listing,
             '-c', 'copy', joined])
        staged = Path(tmp) / 'result.mp4'
        command = ['ffmpeg', '-v', 'error', '-nostdin', '-i', joined, '-i', config['audio']]
        audio_map = ['-map', '1:a:0']
        if config.get('keep_original_audio', False):
            original_listing = Path(tmp) / 'original-audio.txt'
            original_listing.write_text(''.join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in original_audio_paths))
            original_track = Path(tmp) / 'original.wav'
            run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'concat', '-safe', '0',
                 '-i', original_listing, '-c:a', 'pcm_s16le', original_track])
            command += ['-i', original_track, '-filter_complex',
                        '[1:a:0][2:a:0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98:latency=1[mixed]']
            audio_map = ['-map', '[mixed]']
        run(command + ['-map', '0:v:0'] + audio_map + ['-t', config['duration'], '-c:v', 'copy',
             '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', staged])
        run(['ffmpeg', '-v', 'error', '-nostdin', '-i', staged, '-f', 'null', '-'])
        result = probe(staged)
        actual = float(result['format']['duration'])
        if abs(actual - config['duration']) > max(0.1, 2 / fps):
            raise ValueError('输出时长检查失败')
        staged.rename(output)
    export_srt(root, segments)
    render_report = {'output': str(output), 'duration': actual,
                                 'expected_duration': config['duration'], 'decode_passed': True,
                                 'subtitle_mode': 'external SRT', 'semantic_review': 'manual',
                                 'keep_original_audio': config.get('keep_original_audio', False),
                                 'original_audio_missing_shots': missing_audio,
                                 'edit_sha256': fingerprint(root / 'plans/edit.json'),
                                 'inputs_sha256': inputs_signature(root),
                                 'video_sha256': fingerprint(output)}
    save(root / 'qa/render.json', render_report)
    save(root / 'qa' / ('final-render.json' if args.final else 'preview-render.json'), render_report)
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init'); p.add_argument('project'); p.add_argument('--audio', required=True)
    p.add_argument('--width', type=int, default=1080); p.add_argument('--height', type=int, default=1920)
    p.add_argument('--fps', type=int, default=30); p.set_defaults(func=init)
    p.add_argument('--language', choices=['auto', 'en', 'es', 'zh'], default='auto')
    p.add_argument('--keep-original-audio', action='store_true', default=False)
    p = sub.add_parser('settings'); p.add_argument('project'); p.set_defaults(func=settings)
    p = sub.add_parser('set-audio'); p.add_argument('project')
    p.add_argument('--keep-original-audio', action=argparse.BooleanOptionalAction, default=False); p.set_defaults(func=set_audio)
    p = sub.add_parser('import-timing'); p.add_argument('project'); p.add_argument('timing'); p.set_defaults(func=import_timing)
    p = sub.add_parser('transcribe'); p.add_argument('project'); p.add_argument('--model', required=True)
    p.add_argument('--language', choices=['auto', 'en', 'es', 'zh'], default=None)
    p.add_argument('--prompt', default=None); p.set_defaults(func=transcribe)
    p = sub.add_parser('download-model'); p.add_argument('name', choices=['tiny', 'base', 'small', 'medium', 'large-v3'])
    p.add_argument('--output', required=True); p.add_argument('--endpoint', default=None); p.set_defaults(func=download_model)
    p = sub.add_parser('compare-script'); p.add_argument('project'); p.add_argument('--script', required=True); p.set_defaults(func=compare_script)
    p = sub.add_parser('preflight'); p.add_argument('project'); p.set_defaults(func=preflight)
    p = sub.add_parser('build-plan'); p.add_argument('project'); p.set_defaults(func=build)
    p = sub.add_parser('validate'); p.add_argument('project')
    def check(args):
        report = validate(Path(args.project))[3]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report['errors']:
            raise ValueError('校验未通过')
    p.set_defaults(func=check)
    p = sub.add_parser('render'); p.add_argument('project'); p.add_argument('--final', action='store_true'); p.set_defaults(func=render)
    p = sub.add_parser('review'); p.add_argument('project'); p.add_argument('--final', action='store_true'); p.set_defaults(func=review)
    p = sub.add_parser('export-draft'); p.add_argument('project'); p.add_argument('--name', default='jianying_draft')
    p.add_argument('--allow-unreviewed', action='store_true'); p.set_defaults(func=export_draft)
    import asset_index
    asset_index.register(sub)
    import planner
    planner.register(sub)
    import understanding
    understanding.register(sub)
    import workflow
    workflow.register(sub)
    import library_tools
    library_tools.register(sub)
    import elevenlabs_adapter
    elevenlabs_adapter.register(sub)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
