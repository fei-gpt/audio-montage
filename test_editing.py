"""Scoped editing acceptance with real local media and mocked semantic requests."""
import io,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from montage import fingerprint,save
from runtime_environment import configure
configure()
from workbench.backend import Workbench,Problem
from workbench.edit_media import run
from video_document import write_document


class EditingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();root=Path(cls.media.name)
        cls.intro=root/'intro.mp4';cls.clip=root/'clip.mp4';cls.audio=root/'voice.mp3'
        run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=blue:s=90x160:r=30:d=1',
             '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',cls.intro])
        run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=red:s=90x160:r=30:d=3','-c:v','libx264',cls.clip])
        # PCM in an MP3-named container gives an exact two-second test timeline.
        run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','sine=frequency=880:duration=2','-f','wav',cls.audio])
    @classmethod
    def tearDownClass(cls):cls.media.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=Workbench(self.root/'state',executor=False);self.p=self.app.create_product('toy');self.w=self.app.create_workspace(self.p['id'],'toy');self.w2=self.app.create_workspace(self.p['id'],'other')
        self.inputs=self.root/'inputs';self.inputs.mkdir();shutil.copy2(self.intro,self.inputs/'1.mp4');shutil.copy2(self.audio,self.inputs/'1.mp3')
        (self.inputs/'1.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nShow the red toy.\n',encoding='utf-8')
        self.library=self.root/'library';self.library.mkdir();shutil.copy2(self.clip,self.library/'clip.mp4')
        self.app.attach_library(self.p['id'],self.w['id'],str(self.library),'prepared');self.app.scan(self.p['id'],self.w['id'])
        self.asset=self.app.visible_assets(self.w['id'])[0]
        task=self.root/'task.json';save(task,{'analysis':{'shot_boundaries':[],'transition_ranges':[]}})
        self.shot=self.app.store.put('shot',self.w['id'],{'asset_id':self.asset['id'],'asset_sha256':self.asset['sha256'],'start':0,'end':3,
            'review_decision':'keep','human_confirmed':True,'facts':'red toy','safe_trim_ranges':[{'start':0,'end':3}],'task_path':str(task)})
        write_document(self.library/'clip.mp4',self.asset['sha256'],complete=True,context={'visual_details':{'subject':'red toy'}})
    def tearDown(self):self.tmp.cleanup()
    def create(self,**kw):return self.app.editing.create(self.p['id'],self.w['id'],dict(input_path=str(self.inputs),timing_confirmed=True,rights_allowed=True,**kw))
    def task(self,b):return self.app.editing.tasks(self.w['id'],b['id'])[0]
    def op(self,b,op,body=None):
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],op,body or {})
        ids=[t['id'] for t in self.app.editing.tasks(self.w['id'],b['id']) if t['status']=='queued']
        self.app.editing.run(self.p['id'],self.w['id'],b['id'],ids,op)
    def proposal(self):return {'parts':[{'shot_id':self.shot['id'],'start':0,'frames':60,'reason':'red toy matches narration'}],'gaps':[]}
    def upload(self,file,kind,w=None):
        return self.app.editing.upload(self.p['id'],(w or self.w)['id'],file.name,kind,io.BytesIO(file.read_bytes()),file.stat().st_size)
    def test_uploaded_audio_only_reuses_library_and_preserves_script(self):
        narration=self.upload(self.audio,'narration')
        b=self.app.editing.create(self.p['id'],self.w['id'],{'narrations':[{'id':narration['id'],'script':'Show the red toy.'}],'rights_allowed':True})
        t=self.task(b);self.assertNotIn('intro',t);self.assertEqual(t['script'],'Show the red toy.')
        self.app.editing.check_inputs(b,t)
        # Existing real audio timing is reusable even when its media filename changes after upload.
        cache=self.app.wroot(self.w['id'])/'editing-audio';save(cache/(t['audio_sha256']+'-auto.json'),{'audio_sha256':t['audio_sha256'],'segments':[{'start':0,'end':2,'text':'Show the red toy.'}]})
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        self.op(b,'preview');t=self.task(b);self.assertEqual(t['status'],'awaiting_review',t.get('error'))
        self.assertEqual(t['preview']['report']['intro_seconds'],0);self.assertEqual(t['preview']['report']['duration'],2)
    def test_duration_mode_never_calls_model_and_renders(self):
        n=self.upload(self.audio,'narration')
        b=self.app.editing.create(self.p['id'],self.w['id'],{'narrations':[{'id':n['id']}],'rights_allowed':True,'matching_mode':'duration'})
        t=self.task(b);cache=self.app.wroot(self.w['id'])/'editing-audio'
        save(cache/(t['audio_sha256']+'-auto.json'),{'audio_sha256':t['audio_sha256'],'segments':[{'start':0,'end':1,'text':'unrelated'},{'start':1,'end':2,'text':'anything'}]})
        with patch('vision_api.call',side_effect=AssertionError('duration mode must not call any model')):
            self.op(b,'plan');t=self.task(b)
            self.assertEqual(t['status'],'planned',t.get('error'))
            self.assertEqual(t['plan']['matching_mode'],'duration')
            self.assertEqual([x['frames'] for x in t['plan']['parts']],[30,30])
            self.op(b,'preview');self.assertEqual(self.task(b)['status'],'awaiting_review')
    def test_upload_timing_uses_default_local_runtime_without_paid_api(self):
        n=self.upload(self.audio,'narration');b=self.app.editing.create(self.p['id'],self.w['id'],{
            'narrations':[{'id':n['id'],'script':'Show the red toy.'}],'rights_allowed':True})
        model=self.root/'bundled-model';model.mkdir()
        def transcribe(folder,selected,language,prompt):
            self.assertEqual(selected,model);self.assertEqual(prompt,'Show the red toy.')
            save(Path(folder)/'audio/timing.json',{'segments':[{'start':0,'end':2,'text':'Show the blue toy.'}]})
        with patch('workbench.local_asr.runtime',return_value=(self.audio,model)),patch('workbench.local_asr.transcribe',side_effect=transcribe) as asr,patch('vision_api.call',side_effect=AssertionError('no paid call')):
            self.op(b,'timing');self.assertEqual(asr.call_count,1)
        t=self.task(b);self.assertEqual(t['status'],'timing_ready',t.get('error'));self.assertFalse(t['script_check']['matched'])
        with patch('workbench.local_asr.transcribe',side_effect=AssertionError('reuse timing')):self.op(b,'timing')
        self.assertEqual(self.task(b)['status'],'timing_ready')
    def test_uploaded_bookends_music_and_account_scope(self):
        n=self.upload(self.audio,'narration');music=self.upload(self.audio,'music');clip=self.upload(self.intro,'clip')
        with self.assertRaises(Problem):self.app.editing.create(self.p['id'],self.w2['id'],{'narrations':[{'id':n['id']}]})
        b=self.app.editing.create(self.p['id'],self.w['id'],{'narrations':[{'id':n['id'],'script':'red toy'}],'music_id':music['id'],
            'clips':[{'id':clip['id'],'position':'intro'},{'id':clip['id'],'position':'outro'}],'rights_allowed':True})
        t=self.task(b);t['timeline']={'segments':[{'start':0,'end':2,'text':'red toy'}]};t['plan']=self.app.editing.validate_plan(b,t,self.proposal());t['plan_revision']='r';t['status']='running';self.app.store.put('edit_task',self.w['id'],t)
        result=self.app.editing.render(b,t,True);report=result['preview']['report']
        self.assertEqual(report['intro_seconds'],1);self.assertEqual(report['outro_seconds'],1);self.assertEqual(report['duration'],4)
        self.assertTrue(report['music_body_only']);self.assertFalse(report['music_looped']);self.assertEqual(report['music_volume'],.15)
    def test_upload_rejects_invalid_or_incomplete_media(self):
        with self.assertRaises(Problem):self.app.editing.upload(self.p['id'],self.w['id'],'x.exe','clip',io.BytesIO(b'bad'),3)
        with self.assertRaises(Problem):self.app.editing.upload(self.p['id'],self.w['id'],'x.mp3','narration',io.BytesIO(b'bad'),10)
    def test_preview_confirmation_and_output(self):
        b=self.create()
        with patch('vision_api.call',return_value=self.proposal()) as api:self.op(b,'plan');self.assertEqual(api.call_count,1)
        self.assertEqual(self.task(b)['status'],'planned');self.op(b,'preview');t=self.task(b)
        self.assertEqual(t['status'],'awaiting_review',t.get('error'))
        self.assertFalse(t.get('human_reviewed',False))
        with self.assertRaises(Problem):self.app.editing.action(self.p['id'],self.w['id'],b['id'],'output',{})
        self.op(b,'output',{'task_ids':[t['id']],'content_confirmed':True,'preview_sha256':t['preview']['sha256']})
        t=self.task(b);self.assertEqual(t['status'],'completed',t.get('error'))
        out=Path(t['output']['path']);self.assertTrue(out.is_file());self.assertTrue((out.parent/'制作记录.json').is_file())
        self.assertIn('00:00:01,000 --> 00:00:03,000',(out.parent/'captions.srt').read_text(encoding='utf-8'))
        self.assertEqual(fingerprint(self.inputs/'1.mp4'),fingerprint(self.intro))
        # Distinct sine waves prove the original intro and narration are on the correct sides of the join.
        import array
        def frequency(start):
            raw=run(['ffmpeg','-v','error','-ss',start,'-i',out,'-t','0.3','-ac','1','-ar','16000','-f','f32le','-']).stdout
            samples=array.array('f');samples.frombytes(raw)
            return sum(a<=0<b for a,b in zip(samples,samples[1:]))/.3
        self.assertAlmostEqual(frequency(.2),440,delta=10);self.assertAlmostEqual(frequency(1.2),880,delta=10)
    def test_direct_output_not_human_reviewed(self):
        b=self.create(mode='direct')
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        t=self.task(b);self.assertEqual(t['status'],'completed',t.get('error'));self.assertFalse(t.get('human_reviewed',False))
    def test_batch_duplicate_intervals_blocked(self):
        shutil.copy2(self.inputs/'1.mp4',self.inputs/'2.mp4');shutil.copy2(self.inputs/'1.mp3',self.inputs/'2.mp3');shutil.copy2(self.inputs/'1.srt',self.inputs/'2.srt')
        b=self.create()
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        tasks=self.app.editing.tasks(self.w['id'],b['id']);self.assertEqual([t['status'] for t in tasks],['planned','needs_attention']);self.assertIn('重复',tasks[1]['error'])
    def test_timing_cache_and_plan_resume_no_api(self):
        b=self.create()
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        (self.inputs/'1.srt').unlink()
        self.assertEqual(len(self.app.editing.timeline(b,self.task(b))['segments']),1)
        with patch('vision_api.call',side_effect=AssertionError('must reuse plan')):self.op(b,'resume')
        self.assertEqual(self.task(b)['status'],'planned')
    def test_manual_plan_uses_real_timeline_and_invalidates_preview(self):
        b=self.create();t=self.task(b)
        result=self.app.editing.action(self.p['id'],self.w['id'],b['id'],'save-plan',{'task_ids':[t['id']],'plan':self.proposal()})
        self.assertEqual(result['timeline']['audio_sha256'],t['audio_sha256']);self.assertEqual(result['status'],'planned')
        result['preview']={'sha256':'old','plan_revision':result['plan_revision']};self.app.store.put('edit_task',self.w['id'],result)
        revised=self.app.editing.action(self.p['id'],self.w['id'],b['id'],'save-plan',{'task_ids':[t['id']],'plan':self.proposal()})
        self.assertNotEqual(result['plan_revision'],revised['plan_revision']);self.assertNotIn('preview',revised)
    def test_account_scope_and_changed_sources(self):
        b=self.create()
        with self.assertRaises(Problem):self.app.editing.batch(self.p['id'],self.w2['id'],b['id'])
        with self.assertRaises(Problem):self.app.editing.directory(self.w2['id'],str(self.library))
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        (self.library/'clip.mp4').unlink();self.op(b,'preview');self.assertEqual(self.task(b)['status'],'needs_attention')
    def test_unsafe_trim_and_unconfirmed_assets_rejected(self):
        b=self.create();self.shot.pop('safe_trim_ranges');self.app.store.put('shot',self.w['id'],self.shot)
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        self.assertIn('安全',self.task(b)['error'])
        self.shot['review_decision']='uncertain';self.app.store.put('shot',self.w['id'],self.shot)
        self.assertEqual(self.app.editing.candidates(self.p['id'],self.w['id']),[])
    def test_action_truncation_and_timeline_hash_rejected(self):
        b=self.create();self.shot.update(action_start=.5,action_end=2.5);self.app.store.put('shot',self.w['id'],self.shot)
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        self.assertIn('完整动作',self.task(b)['error'])
        cache=self.app.wroot(self.w['id'])/'editing-audio';shutil.rmtree(cache)
        (self.inputs/'1.srt').unlink();save(self.inputs/'1.json',{'audio_sha256':'wrong','segments':[{'start':0,'end':2,'text':'wrong audio'}]})
        with self.assertRaisesRegex(ValueError,'其他音频'):self.app.editing.timeline(b,self.task(b))
    def test_pause_during_request_and_resume_preview_checkpoint(self):
        b=self.create()
        def stop(*args):
            self.app.editing.action(self.p['id'],self.w['id'],b['id'],'pause',{})
            return self.proposal()
        with patch('vision_api.call',side_effect=stop):self.op(b,'plan')
        self.assertEqual(self.task(b)['status'],'paused')
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'resume')
        self.assertEqual(self.task(b)['status'],'planned')
        # A queued preview interrupted by restart must resume preview, not silently replan.
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],'preview',{})
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],'pause',{})
        with patch('workbench.edit_media.render',side_effect=ValueError('preview checkpoint reached')) as renderer:
            self.op(b,'resume');self.assertEqual(renderer.call_count,1)
        self.assertIn('preview checkpoint',self.task(b)['error'])
    def test_invalid_pairs_natural_order_pause_cancel_restart(self):
        shutil.copy2(self.intro,self.inputs/'10.mp4');shutil.copy2(self.audio,self.inputs/'2.mp3')
        b=self.create();tasks=self.app.editing.tasks(self.w['id'],b['id']);self.assertEqual([t['name'] for t in tasks],['1','2','10'])
        self.assertEqual([t['status'] for t in tasks],['ready','invalid','invalid'])
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],'pause',{});self.assertEqual(self.task(b)['status'],'paused')
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],'plan',{});self.assertEqual(self.task(b)['status'],'queued')
        other=Workbench(self.app.root,executor=False);self.assertEqual(other.editing.tasks(self.w['id'],b['id'])[0]['status'],'interrupted')
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],'cancel',{});self.assertEqual(self.task(b)['status'],'cancelled')
