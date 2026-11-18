"""Offline orchestration: no real copy, Dreamina submissions, or ElevenLabs calls."""
import base64,json,shutil,unittest,threading,urllib.request,urllib.error
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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
            with patch.object(self.app.editing,'action',side_effect=RuntimeError('queue unavailable')):
                self.action(g,'approve-intro',{'content_confirmed':True,'intro_sha256':g['intro']['sha256'],'allow_paid':True})
            interrupted=self.get(g)
            self.assertEqual(interrupted['status'],'needs_attention')
            with patch.object(self.app.editing,'create_uploaded',side_effect=AssertionError('must reuse linked batch')):
                self.action(g,'resume',{'allow_paid':True})
            self.assertEqual(self.get(g)['editing_batch_id'],interrupted['editing_batch_id'])
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
    def test_generation_task_uses_uploaded_first_frame_manuscript_and_parameters(self):
        from workbench.edit_media import run
        frame=self.root/'cover.png'
        run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=90x160',
             '-frames:v',1,'-c:v','png','-threads',1,frame])
        p,w=self.p['id'],self.w['id']
        service=self.app.generation
        task=service.create(p,w,{'rights_allowed':True,'manuscript':'Original user copy',
            'duration':8,'video_resolution':'1080p','jimeng_model':'seedance2.5',
            'first_frame':{'name':'cover.png','base64':base64.b64encode(frame.read_bytes()).decode()}})
        self.assertEqual(task['settings']['duration'],8)
        self.assertEqual(service.config()['duration'],5)
        with patch('codex_vision.call',return_value=self.script()) as codex:
            task['script']=service.scripts(task,True)
            self.assertIn('"manuscript": "Original user copy"',codex.call_args.args[1])
        commands=[]
        def cli(argv,folder,*args):
            commands.append(argv)
            if argv[1]=='image2video' and '-h' not in argv:
                return '{"submit_id":"image-123"}'
            if argv[1]=='query_result' and '-h' not in argv:
                return '{"gen_status":"querying"}'
            return 'seedance2.5'
        with patch.object(service,'command',side_effect=cli):
            service.jimeng(task)
        submit=next(argv for argv in commands if argv[1]=='image2video' and '-h' not in argv)
        self.assertEqual(Path(submit[submit.index('--image')+1]).read_bytes(),frame.read_bytes())
        self.assertEqual(submit[submit.index('--video_resolution')+1],'1080p')
        self.assertEqual(submit[submit.index('--duration')+1],'8')
        self.assertNotIn('--ratio',submit)

    def test_all_around_reference_passes_each_media_type_to_dreamina(self):
        from workbench.edit_media import run

        p,w=self.p['id'],self.w['id']
        service=self.app.generation
        frame=self.root/'reference.png'
        run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=160x90',
             '-frames:v',1,'-c:v','png','-threads',1,frame])
        refs=[{'kind':kind,'name':path.name,'base64':base64.b64encode(path.read_bytes()).decode()}
              for kind,path in [('image',frame),('video',self.clip),('audio',self.audio)]]
        body={'rights_allowed':True,'brief':'Use the supplied references','video_mode':'multimodal',
              'jimeng_model':'seedance2.0fast','references':refs}
        task=service.create(p,w,body)
        default_model=service.create(p,w,dict(body,jimeng_model='',video_resolution='4k'))
        self.assertEqual(default_model['settings']['video_resolution'],'4k')
        self.assertEqual([ref['kind'] for ref in task['references']],['image','video','audio'])
        with self.assertRaisesRegex(Problem,'至少需要'):
            service.create(p,w,dict(body,references=refs[-1:]))
        task['script']=self.script()
        def cli(argv,folder,*args):
            if '-h' in argv:return 'seedance2.0fast'
            if argv[1]=='multimodal2video':return '{"submit_id":"multimodal-123"}'
            if argv[1]=='query_result':return '{"gen_status":"querying"}'
            return '{}'
        with patch.object(service,'command',side_effect=cli) as command:
            service.jimeng(task)
        args=next(call.args[0] for call in command.call_args_list
                  if call.args[0][1]=='multimodal2video' and '-h' not in call.args[0])
        self.assertEqual(args[args.index('--ratio')+1],'9:16')
        for flag,path in [('--image',frame),('--video',self.clip),('--audio',self.audio)]:
            self.assertEqual(Path(args[args.index(flag)+1]).read_bytes(),path.read_bytes())
        self.assertEqual(task['submit_id'],'multimodal-123')

    def test_canvas_sample_uses_duration_ratio_and_requires_quote_confirmation(self):
        p,w=self.p['id'],self.w['id']
        service=self.app.generation
        encoded=base64.b64encode(self.audio.read_bytes()).decode()
        body={'sample':True,'video_mode':'multimodal','ratio':'3:4','duration':8,
              'rights_allowed':True,
              'references':[{'kind':'audio','name':'voice.wav','base64':encoded}]}
        with self.assertRaisesRegex(Problem,'请填写样片文稿'):
            service.create(p,w,dict(body,manuscript='   '))
        draft=service.create(p,w,dict(body,manuscript='Sample script'))
        ident=draft['id']
        def canvas(g,*args):
            command=args[:2]
            if command==('canvas','create'):
                return {'project':{'projectId':args[-1],'webUrl':'https://jimeng.jianying.com/ai-tool/canvas'}}
            if command==('resource','upload'):return {'resourceId':args[args.index('--resource-id')+1]}
            if command==('node','create'):
                self.assertEqual(args[args.index('--model')+1],'seedance_2.5_draft')
                self.assertEqual(args[args.index('--ratio')+1],'3:4')
                self.assertEqual(args[args.index('--duration')+1],'8')
                self.assertEqual(args[args.index('--resolution')+1],'480p')
                self.assertEqual(args[args.index('--prompt')+1],'Sample script')
                return {'node':{'nodeId':args[args.index('--node-id')+1]}}
            if command==('node','quote'):return {'totalMaxCredits':7,'confirmationRequired':True}
            if command==('node','confirm'):return {'creditConfirmationToken':'test-token'}
            if command==('node','run'):
                self.assertEqual(args[args.index('--submit-id')+1],service.get(p,w,ident)['submit_id'])
                return {}
            if command==('operation','status'):return {'resources':[{'state':'success'}]}
            self.fail(f'Unexpected CLI operation: {command}')
        with patch.object(service,'canvas_command',side_effect=canvas) as cli:
            service.action(p,w,ident,'start',{})
            service.run(p,w,ident,'start')
            quoted=service.get(p,w,ident)
            self.assertEqual((quoted['status'],quoted['sample_credits']),('awaiting_sample_approval',7))
            self.assertFalse(any(call.args[1:3]==('node','run') for call in cli.call_args_list))
            with self.assertRaises(Problem):service.action(p,w,ident,'approve-sample',{'allow_paid':True,'credits':6})
            service.action(p,w,ident,'approve-sample',{'allow_paid':True,'credits':7})
            service.run(p,w,ident,'approve-sample',True)
            self.assertEqual(service.get(p,w,ident)['status'],'sample_ready')
            with self.assertRaises(Problem):service.action(p,w,ident,'start',{})
            self.assertEqual(sum(call.args[1:3]==('node','run') for call in cli.call_args_list),1)

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

    def test_narration_batch_write_failure_does_not_block_the_account(self):
        service=self.app.generation
        p,w=self.p['id'],self.w['id']
        body={'scripts':['one','two'],'voice_id':'v','allow_paid':True}
        service.settings({'elevenlabs_api_key':'test-secret'})
        with self.app.store.db() as db:
            db.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON objects
                WHEN new.kind='narration' AND json_extract(new.body,'$.script')='two'
                BEGIN SELECT RAISE(ABORT,'second narration'); END""")
        with self.assertRaises(sqlite3.IntegrityError):service.create_narrations(p,w,body)
        self.assertEqual(self.app.store.all('narration',w),[])
        with self.app.store.db() as db:db.execute('DROP TRIGGER fail_second')
        self.assertEqual(len(service.create_narrations(p,w,body)['ids']),2)

    def test_closed_executor_releases_narrations_and_preserves_generation_approval(self):
        g=self.make()
        service=self.app.generation
        p,w=self.p['id'],self.w['id']
        body={'scripts':['one','two'],'voice_id':'v','allow_paid':True}
        g.update(sample=True,status='awaiting_sample_approval',sample_credits=5)
        service.put(g)
        with ThreadPoolExecutor() as stopped:pass
        with patch.object(self.app,'pool',stopped),patch('elevenlabs_adapter.request') as provider:
            with self.assertRaises(Problem) as failure:service.create_narrations(p,w,body)
            self.assertEqual(failure.exception.status,503)
            self.assertTrue(all(row['status']=='failed' for row in self.app.store.all('narration',w)))
            with self.assertRaises(Problem) as failure:
                service.action(p,w,g['id'],'approve-sample',{'allow_paid':True,'credits':5})
            self.assertEqual(failure.exception.status,503)
            restored=self.get(g)
            self.assertEqual(restored['status'],'awaiting_sample_approval')
            self.assertNotIn('submit_id',restored)
            self.assertNotIn('sample_approved_credits',restored)
            provider.assert_not_called()
        self.assertEqual(len(service.create_narrations(p,w,body)['ids']),2)

    def test_failed_automatic_sample_query_can_query_original_submission(self):
        g=self.make()
        service=self.app.generation
        g.update(sample=True,status='video_pending',submit_id='original',sample_canvas_id='canvas')
        service.put(g)
        with ThreadPoolExecutor() as stopped:pass
        with patch.object(self.app,'pool',stopped),patch.object(threading.Timer,'start'):
            service.schedule(g)
            first=service.timers[g['id']]
            service.schedule(g)
            latest=service.timers[g['id']]
            first.function()
            self.assertIs(service.timers.get(g['id']),latest)
            latest.function()
        self.assertNotIn(g['id'],service.timers)
        self.assertEqual(self.get(g)['status'],'interrupted')
        with patch.object(service,'canvas_command',return_value={'resources':[{'state':'success'}]}) as cli:
            self.action(g,'poll',{})
        self.assertEqual(self.get(g)['status'],'sample_ready')
        self.assertEqual(cli.call_args.args[1:],('operation','status','original','--project-id','canvas'))

    def test_continuation_without_valid_timestamps_reuses_audio_and_hands_off_for_local_asr(self):
        from montage import fingerprint,save
        g=self.make()
        g.update(script=self.script(),intro={'sha256':fingerprint(self.intro),'path':str(self.intro)},
                 intro_approval={'sha256':fingerprint(self.intro)},status='interrupted')
        service=self.app.generation
        service.put(g)
        response={'audio_base64':base64.b64encode(self.audio.read_bytes()).decode()}
        with ThreadPoolExecutor() as stopped:pass
        with patch('elevenlabs_adapter.request',return_value=(response,'receipt')) as provider:
            p,w=self.p['id'],self.w['id']
            with self.app.store.db() as db:
                db.execute("""CREATE TRIGGER fail_link BEFORE INSERT ON objects
                    WHEN new.kind='generation' AND json_extract(new.body,'$.editing_batch_id') IS NOT NULL
                    BEGIN SELECT RAISE(ABORT,'link write failed'); END""")
            self.action(g,'resume',{'allow_paid':True})
            self.assertIn('link write failed',self.get(g)['error'])
            self.assertEqual(self.app.store.all('edit_batch',w),[])
            self.assertEqual(self.app.store.all('edit_task',w),[])
            with self.app.store.db() as db:db.execute('DROP TRIGGER fail_link')
            service.action(p,w,g['id'],'resume',{'allow_paid':True})
            with patch.object(self.app,'pool',stopped):
                service.run(p,w,g['id'],'resume',True)
            failed=self.get(g)
            self.assertIn('editing_batch_id',failed,failed.get('error'))
            self.assertEqual(failed['status'],'needs_attention')
            self.assertFalse(failed.get('editing_started'))
            self.action(g,'resume',{'allow_paid':True})
            provider.assert_called_once()
        g=self.get(g);self.assertEqual(g['status'],'editing_ready',g.get('error'))
        batch=self.app.editing.batch(self.p['id'],self.w['id'],g['editing_batch_id'])
        task,=self.app.editing.tasks(self.w['id'],batch['id'])
        self.assertEqual(task['status'],'queued')
        self.assertEqual(task['script'],g['script']['continuation_copy'])
        self.assertEqual(fingerprint(task['audio']),fingerprint(self.audio))
        def transcribe(args):
            save(Path(args.project)/'audio/timing.json',{'segments':[{'start':0,'end':2,'text':task['script']}]})
        with patch('workbench.local_asr.runtime',return_value=(self.root/'no-python',self.root)),patch(
                'montage.transcribe',side_effect=transcribe) as local:
            timeline=self.app.editing.timeline(batch,task)
            self.assertEqual(timeline['source'],'local_transcription')
            local.assert_called_once()

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
