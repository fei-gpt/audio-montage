import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from workbench.preflight import inspect


class PreflightTest(unittest.TestCase):
    def test_fresh_install_does_not_create_data_or_start_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'absent'
            report = inspect(data)
            self.assertFalse(data.exists())
            self.assertEqual(report['missing_paths'], [])
            self.assertFalse(report['online_verified'])

    def test_missing_paths_reported_without_mutating_running_job_or_leaking_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            job = json.dumps({'status': 'running', 'secret': 'private-secret'})
            db = data / 'catalog.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE objects(kind TEXT,body TEXT)')
                conn.executemany('INSERT INTO objects VALUES(?,?)', [
                    ('job', job), ('asset', json.dumps({'path': str(data / 'missing.mp4')}))])
            before = db.read_bytes()
            report = inspect(data)
            self.assertEqual(len(report['missing_paths']), 1)
            self.assertEqual(db.read_bytes(), before)
            self.assertNotIn('private-secret', json.dumps(report))

    def test_malformed_config_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'vision-config.json').write_text('[]', encoding='utf-8')
            report = inspect(Path(tmp))
            self.assertTrue(any(c['name'] == '识别配置' and not c['ready'] for c in report['checks']))
