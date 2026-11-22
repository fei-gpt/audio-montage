"""Manual text and sound cues on the finished edit's 30 fps clock."""
import math
import sys
import unicodedata


def number(value, low, high, field):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{field}须在 {low} 至 {high} 之间')
    return value


def validate(rows, get_sound):
    if not isinstance(rows, list) or len(rows) > 40:
        raise ValueError('每条视频最多设置 40 项文字和音效')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('文字和音效设置无效')
        anchor = row.get('anchor')
        if anchor not in ('shot', 'last', 'category', 'time'):
            raise ValueError('请选择触发位置')
        cue = {'anchor': anchor, 'seconds': number(row.get('seconds', 0), 0, 86400, '触发秒数')}
        if anchor == 'shot':
            shot = row.get('shot')
            if type(shot) is not int or not 1 <= shot <= 999:
                raise ValueError('镜号须为 1 至 999 的整数')
            cue['shot'] = shot
        if anchor == 'category':
            label = row.get('category')
            if not isinstance(label, str) or not 0 < len(label.strip()) <= 200:
                raise ValueError('请选择展示类别')
            cue['category'] = label.strip()
        text = row.get('text', '')
        if not isinstance(text, str) or len(text) > 200 or '\x00' in text:
            raise ValueError('画面文字最多 200 字')
        if text.strip():
            position = row.get('position', 'bottom')
            if position not in ('top', 'middle', 'bottom'):
                raise ValueError('文字位置无效')
            cue.update(text=text.strip(), position=position,
                       duration=number(row.get('duration', 1.5), 0.04, 600, '文字显示秒数'))
        if row.get('sound_id'):
            sound = get_sound(row['sound_id'])
            cue.update(sound_id=sound['id'], sound_name=sound['name'],
                       volume=number(row.get('volume', 35), 0, 100, '音效音量'))
        if 'text' not in cue and 'sound_id' not in cue:
            raise ValueError('每项请填写文字或选择音效')
        result.append(cue)
    return result


def schedule(cues, parts, head_frames, total_frames):
    starts = []
    cursor = head_frames
    for part in parts:
        starts.append(cursor)
        cursor += part['frames']
    result = []
    for cue in cues:
        anchor = cue['anchor']
        index = None
        if anchor == 'last':
            index = len(parts) - 1
        elif anchor == 'shot':
            index = cue['shot'] - 1
        elif anchor == 'category':
            index = next((i for i, p in enumerate(parts) if cue['category'] in p.get('confirmed_categories', [])), -1)
        if index is not None and not 0 <= index < len(parts):
            result.append({'skipped': '未匹配到指定镜头'})
            continue
        frame = (starts[index] if index is not None else 0) + round(cue['seconds'] * 30)
        if frame >= total_frames:
            result.append({'skipped': '触发位置超出成片'})
            continue
        result.append({'frame': frame})
    return result


def wrap_text(text):
    lines = []
    for paragraph in text.splitlines():
        line = ''
        width = 0
        for char in paragraph:
            units = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
            if width + units > 32:
                lines.append(line)
                line, width = '', 0
            line += char
            width += units
        lines.append(line)
    return '\n'.join(lines)


def text_filter(folder, index, cue, frame, height):
    filename = f'overlay-{index}.txt'
    (folder / filename).write_text(wrap_text(cue['text']), encoding='utf-8')
    y = {'top': 'h*0.10', 'middle': '(h-th)/2', 'bottom': 'h*0.85-th'}[cue['position']]
    font = 'Microsoft YaHei' if sys.platform == 'win32' else 'PingFang SC' if sys.platform == 'darwin' else 'sans-serif'
    end = frame + max(1, round(cue['duration'] * 30))
    return (f"drawtext=textfile={filename}:expansion=none:font='{font}':fontsize={height//25}:"
            f"fontcolor=white:borderw={max(1,height//480)}:bordercolor=black:x=(w-tw)/2:y={y}:"
            f"enable='gte(n,{frame})*lt(n,{end})'")
