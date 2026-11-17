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
        self.assertEqual(batch['rules']['matching_mode'],'semantic')
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
    def test_narration_name_uses_minute_opening_and_short_voice(self):
        from workbench.generation import narration_name
        item={'id':'12345678abcd','created_at':'2026-11-17T09:30:59+0800',
              'script':'See this light, now!','voice_name':'Rachel / Warm Narrator'}
        expected='11-17_09-30_See-this_Rachel.mp3'
        self.assertEqual(narration_name(item,set()),expected)
        self.assertEqual(narration_name(item,{expected.casefold()}),expected[:-4]+'_12345678.mp3')
        self.assertIn('_拿起光剑看看_',narration_name(dict(item,script='拿起光剑看看效果'),set()))

    def test_standalone_narrations_partial_failure_and_batch_handoff(self):
        from io import BytesIO
        from workbench.backend import Workbench
        p,w=self.p['id'],self.w['id']
        service=self.app.generation
        service.settings({'voice_id':'default-voice','elevenlabs_api_key':'test-secret'})
        chars=list('Show red toy.')
        step=2/len(chars)
        audio={'audio_base64':base64.b64encode(self.audio.read_bytes()).decode()}
        aligned=dict(audio,alignment={'characters':chars,
            'character_start_times_seconds':[i*step for i in range(len(chars))],
            'character_end_times_seconds':[(i+1)*step for i in range(len(chars))]})
        scripts=['Show red toy.','Lost result','No alignment','Lost result']
        body={'scripts':scripts,'voice_id':'selected-voice','voice_name':'Test Voice'}
        with self.assertRaises(Problem):service.create_narrations(p,w,body)
        ids=service.create_narrations(p,w,dict(body,allow_paid=True))['ids']
        with self.assertRaises(Problem):service.create_narrations(p,w,dict(body,allow_paid=True))
        items=[self.app.store.get('narration',ident,w) for ident in ids]
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[
                BytesIO(json.dumps(aligned).encode()),OSError('connection lost'),BytesIO(json.dumps(audio).encode())]
            service.run_narrations(p,w,items)
            self.assertEqual(opener.return_value.open.call_count,3)
            request=opener.return_value.open.call_args_list[0].args[0]
            self.assertIn('/selected-voice/with-timestamps',request.full_url)
            self.assertEqual(json.loads(request.data)['text'],scripts[0])
        self.assertEqual(service.config()['voice_id'],'default-voice')
        app=Workbench(self.app.root,executor=False)
        items=[app.store.get('narration',ident,w) for ident in ids]
        self.assertEqual([item['status'] for item in items],['completed','failed','completed','failed'])
        self.assertIn('已有尝试记录',items[-1]['error'])
        self.assertEqual(items[0]['duration'],2)
        ident=items[0]['upload_id']
        sig=app.media_signature(p,w,'narration',ident)
        self.assertEqual(app.media(p,w,'narration',ident,sig).read_bytes(),self.audio.read_bytes())
        other=self.w2['id']
        with self.assertRaises(Problem):app.media(p,other,'narration',ident,app.media_signature(p,other,'narration',ident))
        edit=app.editing
        narrations=[{'id':item['upload_id']} for item in items if item['status']=='completed']
        batch=edit.create(p,w,{'narrations':narrations,'rights_allowed':True,'matching_mode':'semantic'})
        tasks=edit.tasks(w,batch['id'])
        self.assertEqual({task['script'] for task in tasks},{scripts[0],scripts[2]})
        self.assertTrue(edit.distinct_batch_sources(batch))
        first=next(t for t in tasks if t['script']==scripts[0])
        self.assertEqual(edit.timeline(batch,first)['source'],'elevenlabs_timestamps')
        missing=next(t for t in tasks if t['script']==scripts[2])
        self.assertFalse(Path(missing['audio']).with_suffix('.timing.json').exists())
        first['plan']=edit.validate_plan(batch,first,self.proposal())
        app.store.put('edit_task',w,first)
        with self.assertRaisesRegex(ValueError,'本批素材不能重复'):
            edit.validate_plan(batch,missing,self.proposal())
        from montage import save
        fallback=dict(batch,rules=dict(batch['rules'],language='en',model_path=str(self.root)))
        def local_transcription(args):
            save(Path(args.project)/'audio/timing.json',{'segments':[{'start':0,'end':2,'text':'No alignment'}]})
        with patch('workbench.local_asr.runtime',return_value=(self.root/'no-python',self.root)),patch(
                'montage.transcribe',side_effect=local_transcription) as transcribe:
            self.assertEqual(edit.timeline(fallback,missing)['source'],'local_transcription')
            transcribe.assert_called_once()
        other_upload=items[2]['upload_id']
        with self.assertRaises(Problem):edit.create(p,other,{'narrations':[{'id':other_upload}],'rights_allowed':True})
        variants=edit.create(p,w,{'narrations':narrations[:1],'variant_count':5,'rights_allowed':True})
        self.assertEqual(len(edit.tasks(w,variants['id'])),5)

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
            voice_result={'audio_base64':base64.b64encode(self.audio.read_bytes()).decode()}
            with patch('elevenlabs_adapter.request',return_value=(voice_result,'receipt')):
                payload=json.dumps({'scripts':['HTTP narration'],'voice_id':'test-voice','allow_paid':True}).encode()
                narrations=req(path+'/narrations',payload,{'Content-Type':'application/json'})
                app.pool.submit(lambda:None).result(timeout=15)
            workspace=next(item for item in req('/api/state')['products'][0]['workspaces'] if item['id']==w['id'])
            narration,=workspace['narrations']
            self.assertEqual(narration['id'],narrations['ids'][0])
            self.assertEqual(narration['status'],'completed',narration.get('error'))
            with urllib.request.urlopen(base+narration['media_url']) as media:
                self.assertEqual(media.read(),self.audio.read_bytes())
            self.assertFalse(narration['used'])
            generated_batch=app.editing.create(p['id'],w['id'],{
                'narrations':[{'id':narration['upload_id']}],'rights_allowed':True})
            task,=app.editing.tasks(w['id'],generated_batch['id'])
            def used():
                current=next(item for item in req('/api/state')['products'][0]['workspaces'] if item['id']==w['id'])
                return current['narrations'][0]['used']
            task.update(status='needs_attention',human_reviewed=True)
            app.store.put('edit_task',w['id'],task)
            self.assertFalse(used())
            task.update(status='completed',output={'path':'test.mp4'},human_reviewed=False)
            app.store.put('edit_task',w['id'],task)
            self.assertTrue(used())
            task['human_reviewed']=True
            app.store.put('edit_task',w['id'],task)
            self.assertTrue(used())
            g=req(path+'/generation',json.dumps({'brief':'demo','rights_allowed':True}).encode(),{'Content-Type':'application/json'})
            self.assertEqual(g['status'],'draft')
        finally:
            server.shutdown();server.server_close();app.generation.close();app.pool.shutdown(wait=True)
