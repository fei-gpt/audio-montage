import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell installer')
class InstallerTest(unittest.TestCase):
    def test_file_execution_and_install_contract(self):
        source = Path(__file__).parent / 'scripts/install-hypit.ps1'
        self.assertTrue(source.read_bytes().isascii())
        with tempfile.TemporaryDirectory(prefix='hypit install ') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            installer = root / 'scripts/install-hypit.ps1'
            shutil.copy2(source, installer)
            tools = root / 'tools'
            tools.mkdir()
            (tools / 'node.cmd').write_text('@echo off\necho v22.15.0\n', encoding='ascii')
            (tools / 'npm.cmd').write_text('@echo off\necho %* > "%~dp0args.txt"\nexit /b 0\n', encoding='ascii')
            runtime = root / '.hypit-runtime/node_modules'
            (runtime / '.bin').mkdir(parents=True)
            (runtime / '@hypit/hypit').mkdir(parents=True)
            (runtime / '@hypit/hypit/package.json').write_text('{"version":"0.3.1"}', encoding='ascii')
            (runtime / '.bin/hypit.cmd').write_text('@echo off\necho 0.3.1\n', encoding='ascii')
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
            ps = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run([str(ps), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(installer), '-NoProxy'], cwd=root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('@hypit/hypit@0.3.1', (tools / 'args.txt').read_text())
            self.assertTrue((root / '.hypit-runtime/INSTALL-MANIFEST.json').is_file())
