"""Open a native folder dialog in a separate STA process on Windows."""
import os
import subprocess
import sys
from pathlib import Path

from workbench.backend import Problem


def browse_folders(path=''):
    """Read folder names only; the loopback server authenticates this endpoint."""
    if not path:
        roots = [Path(f'{letter}:\\') for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'] if sys.platform == 'win32' else [Path('/')]
        return {'path': '', 'parent': None, 'folders': [
            {'name': str(root), 'path': str(root)} for root in roots if root.is_dir()]}
    folder = Path(path).expanduser()
    if not folder.is_absolute():
        raise Problem('请选择磁盘或填写完整的文件夹路径')
    try:
        folder = folder.resolve(strict=True)
        if not folder.is_dir():
            raise Problem('该路径不是文件夹')
        children = []
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        children.append({'name': entry.name, 'path': str(folder / entry.name)})
                except OSError:
                    continue
        children.sort(key=lambda item: item['name'].casefold())
    except OSError:
        raise Problem('无法访问该文件夹，请选择其他位置') from None
    return {'path': str(folder), 'parent': str(folder.parent) if folder.parent != folder else '', 'folders': children}


WINDOWS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Select the existing video material folder'
$dialog.ShowNewFolderButton = $false
if ($env:MONTAGE_PICKER_INITIAL -and (Test-Path -LiteralPath $env:MONTAGE_PICKER_INITIAL -PathType Container)) {
    $dialog.SelectedPath = $env:MONTAGE_PICKER_INITIAL
}
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
try {
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Write($dialog.SelectedPath)
    }
} finally {
    $dialog.Dispose()
    $owner.Dispose()
}
'''


def choose_folder(initial=''):
    try:
        if sys.platform == 'win32':
            executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            env = dict(os.environ, MONTAGE_PICKER_INITIAL=str(initial or ''))
            result = subprocess.run([str(executable), '-NoProfile', '-STA', '-Command', WINDOWS_SCRIPT],
                                    env=env, capture_output=True, text=True, encoding='utf-8',
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=300)
        elif sys.platform == 'darwin':
            result = subprocess.run(['osascript', '-e', 'POSIX path of (choose folder with prompt "选择已有视频素材库")'],
                                    capture_output=True, text=True, encoding='utf-8', timeout=300)
            if result.returncode and '(-128)' in result.stderr:
                return {'path': '', 'cancelled': True}
        else:
            return {'manual': True, 'message': '当前平台请填写素材文件夹绝对路径'}
    except subprocess.TimeoutExpired:
        raise Problem('文件夹选择超时，请重新点击选择文件夹') from None
    except OSError:
        raise Problem('无法打开系统文件夹窗口，请确认工作台在本机桌面用户下启动') from None
    if result.returncode:
        raise Problem('系统文件夹窗口启动失败，请从本机桌面启动工作台后重试')
    path = result.stdout.strip().lstrip('\ufeff')
    if not path:
        return {'path': '', 'cancelled': True}
    selected = Path(path)
    if not selected.is_absolute() or not selected.is_dir():
        raise Problem('选择的文件夹不存在或无法访问，请重新选择')
    return {'path': str(selected.resolve()), 'cancelled': False}
