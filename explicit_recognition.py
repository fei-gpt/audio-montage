"""Evidence contract for new explicit-standard recognition tasks."""
import bisect
import json
import subprocess
import tempfile
from pathlib import Path

from montage import number

VERSION = 'timed-observation-v1'
GUIDE = Path(__file__).with_name('EXPLICIT_RECOGNITION.md')
REVIEW = """
返回 temporal_observation 对象：kind 为 state（外观或持续状态）或 change（可见变化）；
purpose 写本选区的展示用途，unknowns 为未确认事项的字符串数组，可为空。
points 按时间列出 {time, fact}，time 必须引用随请求图片的原视频秒数，fact 只写该帧所见。
change 至少给出不同时间的起始和结果状态。若用途依赖具体触发动作，还要引用触发画面。
required_start、required_end 是为这个用途必须保留的原片区间，包含所有上述证据点。
真实切镜不可放进同一选区，已知结果不代表看到触发。依据不足可返回 uncertain。
"""


def evidence_problem(observation, frames, start, end):
    if not isinstance(observation, dict) or observation.get('kind') not in ('state', 'change'):
        return '缺少区分持续状态与动作变化的记录'
    purpose = observation.get('purpose')
    unknowns = observation.get('unknowns')
    if not isinstance(purpose, str) or not purpose.strip() or not isinstance(unknowns, list) or not all(isinstance(x, str) for x in unknowns):
        return '缺少展示用途或未确认项记录'
    lo, hi = observation.get('required_start'), observation.get('required_end')
    if not (number(lo) and number(hi) and start <= lo < hi <= end):
        return '必要展示区间无效或超出候选'
    times = {round(f['time'], 6) for f in frames}
    points = observation.get('points')
    if not isinstance(points, list) or len(points) < (2 if observation['kind'] == 'change' else 1):
        return '可见状态或变化过程缺少带时码依据'
    previous = None
    for point in points:
        if not isinstance(point, dict):
            return '画面证据格式无效'
        t, fact = point.get('time'), point.get('fact')
        if (not number(t) or not lo <= t < hi or round(t, 6) not in times
                or (previous is not None and t <= previous)
                or not isinstance(fact, str) or not fact.strip()):
            return '画面事实未按顺序绑定本次实际观察到的时间点'
        previous = t
    return None


def split_at_boundaries(candidate, boundaries):
    """Give each side of a confirmed edit its own independent dense review."""
    lo, hi = candidate['start'], candidate['end']
    edges = {c['time'] for c in boundaries.get('cuts', []) if lo < c['time'] < hi}
    transitions = boundaries.get('transitions', [])
    for transition in transitions:
        edges.update(t for t in (transition['start'], transition['end']) if lo < t < hi)
    if not edges and not any(lo < t['end'] and hi > t['start'] for t in transitions):
        return [candidate]
    bounds = sorted({lo, hi} | edges)
    return [dict(start=a, end=b, focus_times=candidate.get('focus_times', []))
            for a, b in zip(bounds, bounds[1:])
            if not any(a < t['end'] and b > t['start'] for t in transitions)]


class TimedFrames:
    """Sample decoded frame numbers, labelled with actual presentation times."""

    def __init__(self, source, folder):
        self.source = source
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        raw = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time',
            '-of', 'json', str(source)], timeout=300)
        frames = json.loads(raw)['frames']
        pts = [float(f['best_effort_timestamp_time']) for f in frames]
        if not pts or pts != sorted(pts):
            raise ValueError('原片缺少可定位的显示时间戳')
        self.times = [round(t-pts[0], 6) for t in pts]

    def sample(self, start, end, every, focus=(), *, exact=()):
        from understanding import sample_times
        targets = list(sample_times(start, end, every))
        targets.extend(t for t in exact if number(t) and start <= t < end)
        for moment in focus:
            if number(moment) and start <= moment < end:
                targets.extend(sample_times(max(start, moment-.15), min(end, moment+.15), .05))
        first = bisect.bisect_left(self.times, start)
        stop = bisect.bisect_left(self.times, end)
        if first >= stop:
            return []
        indices = sorted({min(stop-1, bisect.bisect_left(self.times, t, first, stop))
                          for t in targets} | {first, stop-1})
        dest = {i:self.folder/f'{self.times[i]:.6f}.jpg' for i in indices}
        missing = [i for i in indices if not dest[i].is_file()]
        if missing:
            selection = '+'.join(f'eq(n,{i})' for i in missing)
            with tempfile.TemporaryDirectory(dir=self.folder) as tmp:
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(self.source),
                    '-map', '0:v:0', '-vf', f"select='{selection}',scale=512:-2",
                    '-fps_mode', 'passthrough', '-frames:v', str(len(missing)), '-q:v', '3',
                    str(Path(tmp)/'%06d.jpg')], check=True, timeout=300)
                images = sorted(Path(tmp).glob('*.jpg'))
                if len(images) != len(missing):
                    raise ValueError('时间证据图片数量与所选原帧不一致')
                for image, i in zip(images, missing):
                    image.replace(dest[i])
        return [{'time':self.times[i], 'path':str(dest[i])} for i in indices]
