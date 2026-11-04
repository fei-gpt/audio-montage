"""Readable, path-independent video analysis stored beside the source video."""
import json
from pathlib import Path
from montage import fingerprint, save

SCHEMA = 2
VISUAL_PROMPT = '''
逐项描述实际画面区别，不能仅写“产品演示”或“旋转灯效”。返回 visual_details 对象，包含：
shot_size（远景/全景/中景/近景/特写及主体占比）、subject（产品颜色、形态、数量、朝向）、
people_hands（人物/手的数量、左右手、握持方式、衣袖）、actions（动作先后与变化）、
background（墙面/桌面/地面材质、颜色、纹理、摆设、空间位置）、
objects（其他可见元素、位置、遮挡关系）、camera（俯仰角度、正侧面、固定或运镜）、
lighting（环境明暗、光源、反光与LED颜色轨迹）、composition（构图与主体位置）、
distinctive_features（用于区别其他视频的具体可见特征数组）、
temporal_events（含start/end/description的事件数组）、unknowns（看不清或采样不能证实的内容）。
细节必须来自所给帧，不推测未见背景。相同用途不等于相同画面，不能仅凭动作或产品名合并。
'''


def document_path(source):
    source = Path(source)
    return source.with_name(source.name + '.analysis.json')


def portable(value):
    if isinstance(value, dict):
        return {k: portable(v) for k,v in value.items()
                if k not in {'path','source','output','task_path','review_video','manifest','probe_path'}}
    if isinstance(value, list):return [portable(v) for v in value]
    return value


def load_document(source, source_hash=None):
    path = document_path(source)
    if not path.is_file():return None
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('schema') != SCHEMA or data.get('source_sha256') != (source_hash or fingerprint(source)):
            return None
        return data
    except (ValueError, OSError, AttributeError):return None


def write_document(source, source_hash, **sections):
    path = document_path(source)
    existing = load_document(source, source_hash)
    if path.exists() and existing is None:
        # Preserve unrelated, malformed, or old-version documents.
        from workflow import archive
        archive(path)
    data = existing or {'schema': SCHEMA, 'video_name': Path(source).name,
                        'source_sha256': source_hash,
                        '说明': '与视频一起移动即可。只读画面观察可复用；人工审核、使用权限不会自动继承。'}
    data.update(portable(sections))
    save(path, data)
    return path
