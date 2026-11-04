import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from codex_vision import call
from vision_api import execution_config


class CodexVisionTest(unittest.TestCase):
    def test_explicit_model_images_and_cache_without_http(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);image=root/'frame.jpg';image.write_bytes(b'fixture')
            config={'provider':'codex','model':'gpt-6-luna'};seen=[]
            def execute(command,**kwargs):
                seen.append(command)
                if command[1:]==['login','status']:return SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')
                self.assertEqual(command[command.index('--model')+1],'gpt-6-luna')
                self.assertEqual(command[command.index('--sandbox')+1],'read-only')
                self.assertIn('--image',command);self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
                Path(command[command.index('-o')+1]).write_text('{"subject":"toy"}',encoding='utf-8')
                return SimpleNamespace(returncode=0)
            with patch('codex_vision.shutil.which',return_value='codex.exe'),patch('codex_vision.subprocess.run',side_effect=execute),patch('urllib.request.build_opener',side_effect=AssertionError('HTTP forbidden')):
                self.assertEqual(call(config,'observe',[{'time':0,'path':str(image)}],root/'cache',True),{'subject':'toy'})
                self.assertEqual(call(config,'observe',[{'time':0,'path':str(image)}],root/'cache',False),{'subject':'toy'})
            self.assertEqual(len(seen),2)

    def test_unknown_request_never_reissued(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def execute(command,**kwargs):
                if command[1:]==['login','status']:return SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')
                return SimpleNamespace(returncode=1)
            with patch('codex_vision.shutil.which',return_value='codex.exe'),patch('codex_vision.subprocess.run',side_effect=execute) as run:
                with self.assertRaisesRegex(ValueError,'执行未完成'):call({'model':'gpt-6-luna'},'test',[],root,True)
                self.assertEqual(run.call_count,2)
                with self.assertRaisesRegex(ValueError,'结果不明'):call({'model':'gpt-6-luna'},'test',[],root,True)
                self.assertEqual(run.call_count,2)

    def test_job_override_is_scoped_and_never_calls_deepseek(self):
        from vision_api import call as route
        token=execution_config.set({'provider':'codex','model':'gpt-6-luna'})
        try:
            with patch('codex_vision.call',return_value={'ok':True}) as codex,patch('urllib.request.build_opener',side_effect=AssertionError('HTTP forbidden')):
                self.assertEqual(route({'base_url':'https://api.deepseek.com','model':'deepseek-flash'},'test',[],Path('.'),True),{'ok':True})
                self.assertEqual(codex.call_args.args[0]['model'],'gpt-6-luna')
        finally:execution_config.reset(token)
        self.assertIsNone(execution_config.get())
