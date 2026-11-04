"""Offline orchestration: no real copy, Dreamina submissions, or ElevenLabs calls."""
import base64,json,shutil,unittest,threading,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
import test_editing as fixtures
from workbench.backend import Problem


class GenerationTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.EditingTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.EditingTest.tearDownClass.__func__)
    setUp=fixtures.EditingTest.setUp
    tearDown=fixtures.EditingTest.tearDown
    proposal=fixtures.EditingTest.proposal
    def make(self,provider='codex'):
        self.app.generation.settings({'voice_id':'test-voice','elevenlabs_api_key':'test-secret'})
        return self.app.generation.create(self.p['id'],self.w['id'],{'brief':'Show the red toy','provider':provider,'rights_allowed':True,'language':'en'})
    def script(self):return {'ai_copy':'Look at this toy.','jimeng_prompt':'Vertical product introduction with synchronized speech.','continuation_copy':'Show red toy.','visual_requirements':'red toy demonstration','language':'en'}
    def get(self,g):return self.app.generation.get(self.p['id'],self.w['id'],g['id'])
    def action(self,g,op,body):
        self.app.generation.action(self.p['id'],self.w['id'],g['id'],op,body)
        self.app.generation.run(self.p['id'],self.w['id'],g['id'],op,body.get('allow_paid',False))
    def cli_success(self,argv,folder,*args):
        if '-h' in [str(x) for x in argv]:return 'seedance2.0fast'
        if argv[1]=='text2video':return json.dumps({'submit_id':'external-123','gen_status':'querying'})
        if argv[1]=='query_result':
            downloads=Path(folder)/'jimeng-result';downloads.mkdir(exist_ok=True);shutil.copy2(self.intro,downloads/'generated.mp4')
            return json.dumps({'gen_status':'success'})
        return '{}'
    def test_intro_confirmation_gates_tts_and_handoff_reuses_timing(self):
        g=self.make()
        with patch('codex_vision.call',return_value=self.script()),patch.object(self.app.generation,'command',side_effect=self.cli_success),patch('elevenlabs_adapter.request') as tts:
            self.action(g,'start',{'allow_paid':True});tts.assert_not_called()
        g=self.get(g);self.assertEqual(g['status'],'awaiting_intro_review',g.get('error'));self.assertEqual(g['submit_id'],'external-123')
        with self.assertRaises(Problem):self.app.generation.action(self.p['id'],self.w['id'],g['id'],'approve-intro',{'content_confirmed':True,'intro_sha256':'wrong','allow_paid':True})
        chars=list('Show red toy.');step=2/len(chars)
        result={'audio_base64':base64.b64encode(self.audio.read_bytes()).decode(),'alignment':{
            'characters':chars,'character_start_times_seconds':[i*step for i in range(len(chars))],
            'character_end_times_seconds':[(i+1)*step for i in range(len(chars))]}}
        with patch('elevenlabs_adapter.request',return_value=(result,'tts-hash')) as tts:
            self.action(g,'approve-intro',{'content_confirmed':True,'intro_sha256':g['intro']['sha256'],'allow_paid':True})
            self.assertEqual(tts.call_count,1);self.assertEqual(tts.call_args.kwargs['api_key_value'],'test-secret')
        g=self.get(g);self.assertEqual(g['status'],'editing_ready',g.get('error'))
        batch=self.app.editing.batch(self.p['id'],self.w['id'],g['editing_batch_id']);task=self.app.editing.tasks(self.w['id'],batch['id'])[0]
        self.assertEqual(task['status'],'queued');self.assertEqual(task['script'],'Show red toy.')
        with patch('vision_api.call',return_value=self.proposal()),patch('montage.transcribe',side_effect=AssertionError('do not transcribe generated TTS')):
            self.app.editing.run(self.p['id'],self.w['id'],batch['id'],[task['id']],'plan',True)
        task=self.app.editing.tasks(self.w['id'],batch['id'])[0];self.assertEqual(task['status'],'awaiting_review',task.get('error'))
        self.assertEqual(task['timeline']['source'],'elevenlabs_timestamps')
        self.assertEqual(task['preview']['report']['duration'],3)
    def test_poll_only_never_resubmits_and_unknown_submit_blocks_retry(self):
        g=self.make();calls=[]
        def pending(argv,folder,*args):
            calls.append(argv[1])
            if '-h' in [str(x) for x in argv]:return 'help'
            if argv[1]=='text2video':return '{"submit_id":"external-abc","gen_status":"querying"}'
            return '{"gen_status":"querying"}'
        with patch('codex_vision.call',return_value=self.script()),patch.object(self.app.generation,'command',side_effect=pending):
            self.action(g,'start',{'allow_paid':True});self.action(g,'poll',{})
        self.assertEqual(calls.count('text2video'),2) # help + one paid submit only
        self.assertEqual(self.get(g)['status'],'video_pending')
        other=self.make()
        def lost(argv,folder,*args):
            if argv[1]=='text2video' and '-h' not in argv:raise ValueError('connection lost after submit')
            return 'help'
        with patch('codex_vision.call',return_value=self.script()),patch.object(self.app.generation,'command',side_effect=lost):self.action(other,'start',{'allow_paid':True})
        with patch.object(self.app.generation,'command',side_effect=AssertionError('must not resubmit')):self.action(other,'start',{'allow_paid':True})
        self.assertIn('结果不明',self.get(other)['error'])
    def test_settings_are_private_scope_and_unpaid_actions_rejected(self):
        g=self.make();status=self.app.generation.status();self.assertTrue(status['elevenlabs_key_ready']);self.assertNotIn('test-secret',json.dumps(status))
        with self.assertRaises(Problem):self.app.generation.get(self.p['id'],self.w2['id'],g['id'])
        with self.assertRaises(Problem):self.app.generation.action(self.p['id'],self.w['id'],g['id'],'start',{})
    def test_codex_reuses_saved_structured_output(self):
        g=self.make('codex')
        with patch('codex_vision.call',return_value=self.script()) as codex:
            a=self.app.generation.scripts(g,True);b=self.app.generation.scripts(g,True)
        self.assertEqual(a,b);self.assertEqual(codex.call_count,1)
        self.assertEqual(codex.call_args.args[0]['model'],'gpt-6-luna')
    def test_http_binary_upload_generation_routes_and_private_settings(self):
        from workbench.server import make_server
        server=make_server(self.root/'http-state',0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        app=server.app;p=app.create_product('http');w=app.create_workspace(p['id'],'a');other=app.create_workspace(p['id'],'b')
        base=f'http://127.0.0.1:{server.server_port}';path=f"/api/products/{p['id']}/workspaces/{w['id']}"
        def req(url,body=None,headers=None):
            h={'X-Workbench-Token':server.token};h.update(headers or {})
            return json.load(urllib.request.urlopen(urllib.request.Request(base+url,data=body,headers=h)))
        try:
            uploaded=req(path+'/editing/uploads',self.audio.read_bytes(),{'X-File-Name':'voice.mp3','X-Upload-Kind':'narration','Content-Type':'application/octet-stream'})
            self.assertNotIn('path',uploaded)
            body=json.dumps({'narrations':[{'id':uploaded['id'],'script':'red toy'}],'rights_allowed':True}).encode()
            batch=req(path+'/editing/batches',body,{'Content-Type':'application/json'});self.assertEqual(batch['input_mode'],'uploads')
            with self.assertRaises(urllib.error.HTTPError):req(path.replace(w['id'],other['id'])+'/editing/batches',body,{'Content-Type':'application/json'})
            settings=req('/api/generation/settings',json.dumps({'elevenlabs_api_key':'private-value'}).encode(),{'Content-Type':'application/json'})
            self.assertNotIn('private-value',json.dumps(settings))
            g=req(path+'/generation',json.dumps({'brief':'demo','rights_allowed':True}).encode(),{'Content-Type':'application/json'})
            self.assertEqual(g['status'],'draft')
        finally:
            server.shutdown();server.server_close();app.generation.close();app.pool.shutdown(wait=True)
