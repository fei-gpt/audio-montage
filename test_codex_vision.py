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
            schema={'type':'object','properties':{'subject':{'type':'string'}},'required':['subject'],'additionalProperties':False}
            def execute(command,**kwargs):
                seen.append(command)
                if command[1:]==['login','status']:return SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')
                self.assertEqual(command[command.index('--model')+1],'gpt-6-luna')
                self.assertEqual(command[command.index('--sandbox')+1],'read-only')
                self.assertIn('--image',command);self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
                self.assertEqual(json.loads(Path(command[command.index('--output-schema')+1]).read_text(encoding='utf-8')),schema)
                Path(command[command.index('-o')+1]).write_text('{"subject":"toy"}',encoding='utf-8')
                return SimpleNamespace(returncode=0)
            with patch('codex_vision.shutil.which',return_value='codex.exe'),patch('codex_vision.subprocess.run',side_effect=execute),patch('urllib.request.build_opener',side_effect=AssertionError('HTTP forbidden')):
                self.assertEqual(call(config,'observe',[{'time':0,'path':str(image)}],root/'cache',True,output_schema=schema),{'subject':'toy'})
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

    def test_local_config_rejection_can_be_archived_before_first_model_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);attempts=[]
            def execute(command,**kwargs):
                if command[1:]==['login','status']:return SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')
                self.assertNotIn('mcp_servers.codex_apps.enabled=false',command)
                attempts.append(command)
                if len(attempts)==1:
                    kwargs['stderr'].write('Error loading config.toml: invalid transport\nin mcp_servers.codex_apps\n')
                    return SimpleNamespace(returncode=1)
                Path(command[command.index('-o')+1]).write_text('{"ok":true}',encoding='utf-8')
                return SimpleNamespace(returncode=0)
            with patch('codex_vision.shutil.which',return_value='codex.exe'),patch('codex_vision.subprocess.run',side_effect=execute):
                with self.assertRaisesRegex(ValueError,'执行未完成'):call({'model':'gpt-6-luna'},'test',[],root,True)
                self.assertEqual(call({'model':'gpt-6-luna'},'test',[],root,True),{'ok':True})
            history=list((root/'attempt-history').glob('*/classification.json'))
            self.assertEqual(len(history),1)
            self.assertFalse(json.loads(history[0].read_text(encoding='utf-8'))['model_request_sent'])

    def test_job_override_is_scoped_and_never_calls_deepseek(self):
        from vision_api import call as route
        token=execution_config.set({'provider':'codex','model':'gpt-6-luna'})
        try:
            with patch('codex_vision.call',return_value={'ok':True}) as codex,patch('urllib.request.build_opener',side_effect=AssertionError('HTTP forbidden')):
                self.assertEqual(route({'base_url':'https://api.deepseek.com','model':'deepseek-flash'},'test',[],Path('.'),True),{'ok':True})
                self.assertEqual(codex.call_args.args[0]['model'],'gpt-6-luna')
        finally:execution_config.reset(token)
        self.assertIsNone(execution_config.get())


import test_workbench as fixtures


class CodexDefaultsTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.WorkbenchTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.WorkbenchTest.tearDownClass.__func__)
    setUp=fixtures.WorkbenchTest.setUp
    tearDown=fixtures.WorkbenchTest.tearDown
    attach=fixtures.WorkbenchTest.attach

    def test_fresh_install_and_jobs_default_to_luna_without_api_key(self):
        self.attach()
        with patch('shutil.which',return_value='codex.exe'):
            self.assertEqual(self.app.config()['model'],'gpt-6-luna')
            self.assertTrue(self.app.status()['vision_ready'])
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True)
        self.assertEqual(j['status'],'queued')
        self.assertEqual(j['analysis_config']['provider'],'codex')
        self.assertEqual(j['analysis_config']['model'],'gpt-6-luna')

    def test_codex_setting_does_not_require_or_store_a_deepseek_key(self):
        with patch('shutil.which',return_value='codex.exe'):
            result=self.app.set_config({'provider':'codex','model':'gpt-6-luna'})
        self.assertTrue(result['vision_ready'])
        self.assertEqual(self.app.config()['provider'],'codex')
        self.assertFalse((self.app.root/'credentials.json').exists())

    def test_generation_default_is_codex_and_deepseek_is_blocked(self):
        g=self.app.generation.create(self.p['id'],self.w['id'],{'brief':'Show the product','rights_allowed':True})
        self.assertEqual(g['provider'],'codex')
        self.assertEqual(g['settings']['codex_model'],'gpt-6-luna')
        with self.assertRaisesRegex(fixtures.Problem,'不调用DeepSeek'):
            self.app.generation.create(self.p['id'],self.w['id'],{'provider':'deepseek','brief':'Show the product','rights_allowed':True})

    def test_provider_switch_cannot_reissue_unknown_legacy_request(self):
        self.attach();a=self.app.store.all('asset',self.w['id'])[0]
        j={'id':'a'*32,'workspace_id':self.w['id'],'product_id':self.p['id']}
        folder=self.app.wroot(self.w['id'])/'tasks'/j['id']/a['id']/'vision-cache'
        folder.mkdir(parents=True);(folder/'legacy.attempt.json').write_text('{}',encoding='utf-8')
        with patch('codex_vision.call',side_effect=AssertionError('must not resend')):
            with self.assertRaisesRegex(fixtures.Problem,'历史API请求结果不明'):
                self.app.process_asset(j,a,self.p)
