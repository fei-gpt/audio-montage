"""Read-only, offline handoff checks. Never starts jobs or calls a model."""
import argparse
from contextlib import closing
import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def inspect(data):
    from runtime_environment import configure
    configure()
    sys.path.insert(0, str(REPO / '.workbench-deps'))
    checks = []

    def add(name, ready, note, required=False):
        checks.append(dict(name=name, ready=bool(ready), note=note, required=required))

    add('Python', sys.version_info >= (3, 10), sys.version.split()[0], True)
    for tool in ('ffmpeg', 'ffprobe'):
        add(tool, shutil.which(tool), '未找到时运行 scripts/install-media.ps1', True)
    add('PDF文字提取', importlib.util.find_spec('pypdf'),
        '可选：python -m pip install --target .workbench-deps -r requirements-workbench.txt')
    config = Path(data) / 'vision-config.json'
    try:
        cfg = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        if not isinstance(cfg, dict):
            raise ValueError('配置必须为对象')
        add('识别配置', cfg.get('provider', 'codex') == 'codex' and
            cfg.get('model', 'gpt-6-luna') == 'gpt-6-luna', '固定 Codex / gpt-6-luna')
        add('Codex CLI', shutil.which(cfg.get('codex_bin') or 'codex'),
            '新电脑需安装CLI、重新保存识别设置并使用自己的ChatGPT登录；模型权限尚未联网验证')
    except (OSError, ValueError, TypeError) as exc:
        add('识别配置', False, type(exc).__name__ + '：请在识别设置中重新保存')
    from workbench.local_asr import status
    asr = status()
    add('本地断句识别', asr['ready'], asr['note'] + '；整条配音时长模式不需要ASR')
    db = Path(data) / 'catalog.sqlite'
    missing = []
    try:
        if db.exists():
            # Read the live database without constructing Workbench/Store or updating jobs.
            with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
                for kind, raw in conn.execute("SELECT kind,body FROM objects WHERE kind IN ('asset','library')"):
                    obj = json.loads(raw)
                    path = obj.get('path')
                    if path and not Path(path).exists():
                        missing.append(dict(kind=kind, path=path))
        add('素材路径', not missing, f'{len(missing)} 个路径不可访问；不会自动重绑或重新识别')
    except (OSError, ValueError, sqlite3.Error) as exc:
        add('素材路径', False, type(exc).__name__ + '：请核对复制的数据目录')
    return dict(checks=checks, missing_paths=missing,
                required_ready=all(c['ready'] for c in checks if c['required']),
                online_verified=False)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=REPO / '.workbench-data')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = inspect(args.data)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report['checks']:
            print(f"[{'就绪' if item['ready'] else '待处理'}] {item['name']}：{item['note']}")
        for item in report['missing_paths']:
            print('  路径不可访问：' + item['path'])
        print('只读离线检查完成。未验证登录、模型权限、真实ASR或外部生成服务。')
    return 0 if report['required_ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
