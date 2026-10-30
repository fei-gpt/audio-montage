"""Read-only source draft isolation and jy-draftc native-engine export."""
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

from montage import read, save, fingerprint, probe, portrait_geometry, media_duration


def invoke(tool, jy_dir, arguments, log):
    command = [str(tool), *arguments, '--jy-dir', str(jy_dir)]
    with Path(log).open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                timeout=1800, check=False)
    if result.returncode:
        raise ValueError(f'jy-draftc 失败（{result.returncode}），日志：{log}')


def isolate(data, track_id=None):
    tracks = [t for t in data.get('tracks', []) if t.get('type') == 'video' and t.get('segments')]
    if track_id:
        tracks = [t for t in tracks if t.get('id') == track_id]
    if len(tracks) != 1:
        raise ValueError('请选择唯一的视频轨道：多轨项目需要 --track 轨道ID')
    selected = tracks[0]
    output = []
    for index, segment in enumerate(selected['segments'], 1):
        target = segment.get('target_timerange', {})
        duration = target.get('duration')
        if type(duration) is not int or duration <= 0:
            raise ValueError('片段缺少有效的微秒时长')
        draft = copy.deepcopy(data)
        child = copy.deepcopy(segment)
        child['target_timerange']['start'] = 0
        track = copy.deepcopy(selected)
        track['segments'] = [child]
        draft['tracks'] = [track]
        draft['duration'] = duration
        draft['name'] = f'segment-{index:04}'
        output.append((index, segment, draft))
    return output


def execute(args):
    source = Path(args.draft).resolve()
    if not source.is_dir():
        raise ValueError('--draft 必须是草稿目录')
    output = Path(args.output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('输出目录必须位于原草稿之外且不能包含原草稿')
    tool = Path(args.tool or os.environ.get('JY_DRAFTC', '')).resolve()
    jy_dir = Path(args.jy_dir or os.environ.get('JY_INSTALL_DIR', '')).resolve()
    content = source / 'draft_content.json'
    if not content.is_file():
        raise ValueError('缺少 draft_content.json')
    signature = fingerprint(content)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'segments-export.json'
    if manifest_path.exists():
        manifest = read(manifest_path)
        if manifest.get('source_sha256') != signature or manifest.get('track') != args.track:
            raise ValueError('源草稿或轨道改变，请使用新的输出目录')
    else:
        manifest = {'source': str(source), 'source_sha256': signature, 'track': args.track,
                    'mode': 'isolated_video_segments', 'segments': []}
    if args.export and os.name != 'nt':
        raise ValueError('当前适配 jy-draftc Windows x64 引擎；请在装有匹配版本剪映的 Windows 运行')
    try:
        data = read(content)
    except (ValueError, UnicodeError):
        if not args.export:
            raise ValueError('草稿已加密：在 Windows 上加 --export，配置匹配的 jy-draftc 与剪映目录后处理')
        if not tool.is_file() or not (jy_dir / 'videoeditor.dll').is_file():
            raise ValueError('需要有效的 --tool 和包含 videoeditor.dll 的 --jy-dir')
        plain = output / 'plain'
        if not plain.exists():
            invoke(tool, jy_dir, ['-dc', str(source), '-o', str(plain)], output / 'decrypt.log')
        candidates = list(plain.rglob('draft_content.json'))
        if len(candidates) != 1:
            raise ValueError('无法唯一定位解密后的 draft_content.json，请检查 decrypt.log')
        data = read(candidates[0])
    canvas = data.get('canvas_config', {})
    if canvas.get('width', 0) * 16 != canvas.get('height', 0) * 9 or not canvas.get('width'):
        raise ValueError('当前项目仅接受 9:16 草稿画布')
    if args.export:
        if not tool.is_file() or not (jy_dir / 'videoeditor.dll').is_file():
            raise ValueError('需要有效的 --tool 和包含 videoeditor.dll 的 --jy-dir')
        invoke(tool, jy_dir, ['-v'], output / 'version.log')
    previous = {r['segment_id']: r for r in manifest['segments']}
    for index, segment, draft in isolate(data, args.track):
        sid = segment['id']
        name = f'{index:04}'
        folder = output / 'drafts' / name
        video = output / (name + '.mp4')
        row = {'segment_id': sid, 'index': index, 'source_timerange': segment.get('source_timerange'),
               'target_timerange': segment['target_timerange'], 'output': str(video), 'status': 'prepared'}
        if args.export and video.exists():
            old = previous.get(sid, {})
            if old.get('status') == 'exported' and old.get('output_sha256') == fingerprint(video):
                row = old
            else:
                raise ValueError(f'存在未确认的视频，不覆盖：{video}')
        else:
            folder.mkdir(parents=True, exist_ok=True)
            # Keep metadata and nested material resources; never rewrite original files.
            for item in source.iterdir():
                if item.name in {'draft_content.json', 'draft_info.json'}:
                    continue
                dest = folder / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            save(folder / 'draft_content.json', draft)
            save(folder / 'draft_info.json', draft)
            if args.export:
                invoke(tool, jy_dir, ['-ex', str(folder), '-o', str(video)], output / (name + '.log'))
                info = probe(video)
                portrait_geometry(info)
                if abs(media_duration(info, 'video') - segment['target_timerange']['duration'] / 1e6) > .15:
                    raise ValueError(f'{name}: 引擎输出时长不符')
                row.update(status='exported', output_sha256=fingerprint(video))
        previous[sid] = row
        manifest['segments'] = list(previous.values())
        save(manifest_path, manifest)
    print(manifest_path)


def register(sub):
    p = sub.add_parser('export-timeline-segments', help='用 jy-draftc 分别导出剪映时间线视频片段')
    p.add_argument('--draft', required=True); p.add_argument('--output', required=True)
    p.add_argument('--track'); p.add_argument('--tool'); p.add_argument('--jy-dir')
    p.add_argument('--export', action='store_true', help='实际调用 Windows 剪映引擎；默认只准备独立草稿')
    p.set_defaults(func=execute)
