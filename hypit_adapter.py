"""Optional Hypit media-analysis backend.

The adapter deliberately shells out to the installed Hypit CLI instead of
importing Hypit's private JavaScript packages.  This keeps the Python project
usable without Hypit while making Hypit's local media evidence available when
the user has it installed.
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def _hypit_command(value):
    local = Path(__file__).resolve().parent / '.hypit-runtime' / 'node_modules' / '.bin' / ('hypit.cmd' if os.name == 'nt' else 'hypit')
    candidate = value or os.environ.get('HYPIT_BIN') or (str(local) if local.is_file() else 'hypit')
    if Path(candidate).is_file():
        return str(Path(candidate).resolve())
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    raise ValueError(
        '找不到 Hypit CLI；请安装 @hypit/hypit，或设置 HYPIT_BIN 指向 hypit/hypit.CMD'
    )


def _run(command, cwd=None):
    # Windows resolves .CMD/.BAT launchers through cmd.exe when typed in a
    # shell, but subprocess.run(list) does not perform that shell lookup.
    # Keep shell execution disabled and invoke the launcher explicitly.
    if os.name == 'nt' and command and Path(command[0]).suffix.lower() in {'.cmd', '.bat'}:
        command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', *command]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if result.returncode:
        detail = (result.stderr or result.stdout)[-4000:]
        raise ValueError(f'Hypit 命令失败：{detail}')
    return result.stdout or ''


def _json_output(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Keep the adapter tolerant of a CLI wrapper that prints a short
        # informational line before its JSON result.
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise ValueError('Hypit 未返回可解析的 JSON 结果')


def analyze(args):
    source = Path(args.video).resolve()
    if not source.is_file():
        raise ValueError(f'参考视频不存在：{source}')
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f'输出目录已存在，为避免覆盖证据请换一个目录：{output}')
    hypit = _hypit_command(args.hypit)
    if args.every <= 0 or args.overview_frames < 1 or args.cell < 1 or args.columns < 1:
        raise ValueError('--every、--overview-frames、--cell、--columns 必须为正数')
    output.mkdir(parents=True)

    probe = _json_output(_run([hypit, 'media', 'probe', str(source), '--json']))
    (output / 'probe.json').write_text(
        json.dumps(probe, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    duration = float((probe.get('data') or probe).get('duration', 0))
    start = args.start if args.start is not None else 0.0
    end = args.end if args.end is not None else duration
    if end <= start:
        raise ValueError('分析结束时间必须大于开始时间')
    if duration and end > duration + 0.001:
        raise ValueError('分析区间超过参考视频时长')

    boundaries = _run([hypit, 'media', 'boundaries', str(source), '--json'])
    (output / 'boundaries.json').write_text(boundaries, encoding='utf-8')

    frames = output / 'frames'
    _run([hypit, 'media', 'frames', str(source), '--every', str(args.every),
          '--start', str(start), '--end', str(end), '--label-time', '--to', str(frames)])

    overview = output / 'overview.jpg'
    _run([hypit, 'media', 'tile', str(source), '--start', str(start), '--end', str(end),
          '--frames', str(args.overview_frames), '--cell', str(args.cell),
          '--columns', str(args.columns), '--to', str(overview)])

    tiles = output / 'tiles'
    _run([hypit, 'media', 'tiles', str(source), '--start', str(start), '--end', str(end),
          '--every', str(args.every), '--cell', str(args.cell), '--columns', str(args.columns),
          '--to', str(tiles)])

    manifest = {
        'version': 1,
        'backend': 'hypit-media',
        'source': str(source),
        'output': str(output),
        'probe': 'probe.json',
        'boundaries': 'boundaries.json',
        'frames': 'frames',
        'overview': 'overview.jpg',
        'tiles': 'tiles',
        'range': {'start': start, 'end': end},
        'sampling': {'every': args.every, 'overview_frames': args.overview_frames},
        'interpretation_status': 'evidence_prepared_not_semantically_judged',
        'note': 'Hypit boundaries are mechanical change candidates; editorial shot labels require human or vision review.'
    }
    (output / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(output)


def register(sub):
    parser = sub.add_parser(
        'hypit-analyze',
        help='用已安装的 Hypit media 组件准备参考视频的探测、边界、抽帧和时间网格证据'
    )
    parser.add_argument('video')
    parser.add_argument('--output', required=True)
    parser.add_argument('--hypit', default=None, help='Hypit CLI 路径；也可用 HYPIT_BIN')
    parser.add_argument('--start', type=float, default=None)
    parser.add_argument('--end', type=float, default=None)
    parser.add_argument('--every', type=float, default=1.0)
    parser.add_argument('--overview-frames', type=int, default=12)
    parser.add_argument('--cell', type=int, default=360)
    parser.add_argument('--columns', type=int, default=4)
    parser.set_defaults(func=analyze)
