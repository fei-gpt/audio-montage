"""Readable, path-independent video analysis stored beside the source video."""
import json
from pathlib import Path
from montage import fingerprint, save

SCHEMA = 2
VISUAL_PROMPT = '''
轻量差异识别：只记影响选材的可见区别，不做全景细节盘点。
visual_details只返回actions（一句话主要展示）、distinctive_features（最多3个短语，各不超过20字）。
差异可包括展示方式、主要效果、数量或显著场景变化；没有明显差异就写“常规展示”，不强行找不同。
不逐项描述墙面、地板、衣袖、手势、摆设、光线、构图，不输出逐帧事件或参数推测。
facts、reason、intent、visible_result各用一句短句，避免重复；仅真正影响产品识别或选材的未知项才记录。
差异来自本片可见特征；没有其他视频证据时不声称已做跨视频对比。切镜和动作边界仍按证据判断。
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
