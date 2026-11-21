"""Make project-local media tools available to Python and child processes."""
import os
import shutil
from pathlib import Path


def resolve_codex(configured=None):
    for name in (configured, 'codex'):
        if name and (binary := shutil.which(name)):
            return binary
    local = os.environ.get('LOCALAPPDATA')
    if os.name == 'nt' and local:
        root = Path(local) / 'OpenAI' / 'Codex' / 'bin'
        candidates = sorted(root.glob('*/codex.exe'), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        candidates = [Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')]
    return next((binary for path in candidates if (binary := shutil.which(str(path)))), None)


def configure():
    repo = Path(__file__).resolve().parent
    candidates = [repo / '.media-runtime' / 'bin']
    # Finder-launched processes do not inherit the terminal PATH.
    codex_dir = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS')
    if (codex_dir / 'codex').is_file():
        candidates.append(codex_dir)
    if os.environ.get('MONTAGE_MEDIA_BIN'):
        candidates.insert(0, Path(os.environ['MONTAGE_MEDIA_BIN']))
    for folder in reversed(candidates):
        if folder.is_dir():
            entries = os.environ.get('PATH', '').split(os.pathsep)
            if str(folder) not in entries:
                os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
