import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench.folder_picker import choose_folder, WINDOWS_SCRIPT
from workbench.backend import Problem


class FolderPickerTest(unittest.TestCase):
    def test_windows_selection_and_initial_not_in_command(self):
        with tempfile.TemporaryDirectory(prefix='material ') as folder:
            initial = "E:\\中文素材\\$x'; special"
            with patch('workbench.folder_picker.sys.platform', 'win32'), patch('workbench.folder_picker.subprocess.run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, str(Path(folder).resolve()), '')
                result = choose_folder(initial)
                self.assertFalse(result['cancelled'])
                self.assertEqual(result['path'], str(Path(folder).resolve()))
                self.assertIn('-STA', run.call_args.args[0])
                self.assertNotIn(initial, run.call_args.args[0])
                self.assertEqual(run.call_args.kwargs['env']['MONTAGE_PICKER_INITIAL'], initial)

    def test_cancel_failure_and_timeout(self):
        with patch('workbench.folder_picker.sys.platform', 'win32'), patch('workbench.folder_picker.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, '', '')
            self.assertTrue(choose_folder()['cancelled'])
            run.return_value = subprocess.CompletedProcess([], 1, '', 'failure')
            with self.assertRaises(Problem): choose_folder()
            run.side_effect = subprocess.TimeoutExpired('powershell', 300)
            with self.assertRaises(Problem): choose_folder()

    def test_native_script_parses_in_windows_powershell(self):
        import os
        if os.name != 'nt': self.skipTest('Windows only')
        ps = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        command = '$s=[Console]::In.ReadToEnd(); [scriptblock]::Create($s) | Out-Null'
        result = subprocess.run([str(ps), '-NoProfile', '-Command', command], input=WINDOWS_SCRIPT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
