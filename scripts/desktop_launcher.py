"""Windows desktop entry point for the local editing workbench."""
import http.client
import msvcrt
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8768
URL = f"http://127.0.0.1:{PORT}/#editing"


def install_shortcut():
    command = """
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop '视频剪辑工作台.lnk'))
$link.TargetPath = Join-Path (Get-Location).Path 'start-workbench.cmd'
$link.WorkingDirectory = (Get-Location).Path
$link.Save()
"""
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                   cwd=ROOT, check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def ready():
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
    try:
        conn.request("GET", "/")
        response = conn.getresponse()
        page = response.read(300000)
        if response.status != 200 or b"window.WORKBENCH_TOKEN=" not in page or b'id="editingNav"' not in page:
            raise RuntimeError(f"本机 {PORT} 端口已被其他服务使用。")
        return True
    except ConnectionRefusedError:
        return False
    finally:
        conn.close()


def launch():
    data = ROOT / ".workbench-data"
    data.mkdir(exist_ok=True)
    with (data / "launcher.lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            if not ready():
                python = ROOT / ".venv" / "Scripts" / "python.exe"
                log = data / "launcher.log"
                with log.open("ab") as stream:
                    process = subprocess.Popen(
                        [str(python) if python.is_file() else sys.executable, "-m", "workbench.server", "--port", str(PORT)],
                        cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW,
                        stdin=subprocess.DEVNULL, stdout=stream, stderr=stream)
                deadline = time.monotonic() + 45
                while not ready():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError(f"服务未就绪，请检查启动日志 {log}")
                    time.sleep(.35)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    if not webbrowser.open(URL):
        print("请在浏览器中打开", URL)


if __name__ == "__main__":
    try:
        install_shortcut()
        launch()
    except Exception as exc:
        sys.exit(f"启动失败：{exc}")
