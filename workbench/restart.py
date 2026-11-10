"""Restart the Windows workbench and terminate its local worker processes."""
import os
import subprocess
import sys
import time


def restart(parent, args):
    time.sleep(0.5)  # Give the HTTP response time to reach the browser.
    command = (
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={parent}' "
        "| Select-Object -ExpandProperty ProcessId"
    )
    children = subprocess.check_output(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
        text=True,
    )
    for child in map(int, children.split()):
        if child != os.getpid():
            subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(child)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['taskkill.exe', '/F', '/PID', str(parent)], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.Popen([sys.executable, '-m', 'workbench.server', *args],
                     creationflags=subprocess.CREATE_NO_WINDOW,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    restart(int(sys.argv[1]), sys.argv[2:])
