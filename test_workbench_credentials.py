import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench.backend import Workbench, Problem, credential_env_name
from workbench.server import load_local_env


class CredentialConfigurationTest(unittest.TestCase):
    def test_direct_key_is_private_persistent_and_blank_preserves(self):
        from vision_api import api_key
        with tempfile.TemporaryDirectory() as folder:
            app = Workbench(Path(folder), executor=False)
            config = {'base_url':'https://api.deepseek.com', 'model':'deepseek-flash', 'api_key':'sk-test-private'}
            status = app.set_config(config)
            self.assertTrue(status['vision_ready'])
            self.assertNotIn('sk-test-private', str(status))
            self.assertNotIn('sk-test-private', (Path(folder)/'vision-config.json').read_text())
            restored = Workbench(Path(folder), executor=False)
            self.assertEqual(api_key(restored.config()), 'sk-test-private')
            restored.set_config(dict(config, api_key=''))
            self.assertEqual(api_key(restored.config()), 'sk-test-private')

    def test_shell_references_and_secret_rejection(self):
        for value in (' DEEPSEEK_API_KEY ', '${DEEPSEEK_API_KEY}', '$env:DEEPSEEK_API_KEY', '$DEEPSEEK_API_KEY'):
            self.assertEqual(credential_env_name(value), 'DEEPSEEK_API_KEY')
        with self.assertRaises(Problem) as error:
            credential_env_name('sk-test-secret')
        self.assertNotIn('sk-test-secret', str(error.exception))

    def test_bom_file_and_saved_config(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
            os.environ.pop('DEEPSEEK_API_KEY', None)
            path = Path(folder) / '.env.workbench'
            path.write_text('DEEPSEEK_API_KEY="local-test-value"\n', encoding='utf-8-sig')
            load_local_env(path)
            app = Workbench(Path(folder) / 'state', executor=False)
            status = app.set_config({'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'api_key_env': '${DEEPSEEK_API_KEY}'})
            self.assertTrue(status['vision_ready'])
            self.assertNotIn('local-test-value', str(status))
            self.assertEqual(app.config()['api_key_env'], 'DEEPSEEK_API_KEY')


if __name__ == '__main__':
    unittest.main()
