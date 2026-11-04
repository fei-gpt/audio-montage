"""Make project-local media tools available to Python and child processes."""
import os
from pathlib import Path


def configure():
    repo = Path(__file__).resolve().parent
    candidates = [repo / '.media-runtime' / 'bin']
    if os.environ.get('MONTAGE_MEDIA_BIN'):
        candidates.insert(0, Path(os.environ['MONTAGE_MEDIA_BIN']))
    for folder in reversed(candidates):
        if folder.is_dir():
            entries = os.environ.get('PATH', '').split(os.pathsep)
            if str(folder) not in entries:
                os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
