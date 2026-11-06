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
    def test_reference_only_preview_and_local_replacement(self):
        ref=self.upload(self.intro,'reference')
        w=self.w['id'];p=self.p['id'];eng=self.app.editing
        b=eng.create_uploaded(p,w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        b['rules'].pop('reference_evidence')  # A saved batch from before the fixed reference clock.
        self.app.store.put('edit_batch',w,b)
        beat=dict(start=0,end=1,purpose='展示',subject='产品',action='旋转',composition='近景')
        path=self.library/'alternative.mp4'
        run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=180x320:r=30:d=2','-c:v','libx264',path])
        self.app.scan(p,w);asset=next(a for a in self.app.visible_assets(w) if a['name']==path.name)
        shot=dict(self.shot,id='alt',asset_id=asset['id'],asset_sha256=asset['sha256'],end=2,safe_trim_ranges=[])
        self.app.store.put('shot',w,shot);write_document(path,asset['sha256'],complete=True,context={})
        proposal=self.proposal();part=proposal['parts'][0]
        part.update(reference_beat=1,alternatives=[{'shot_id':'alt','reason':'不同拍摄的近景'}])
        # Pure-color synthetic sources carry no framing detail; screening has its own media test.
        from workbench.reference import span_key
        verdicts=lambda app,b,rows,paid,stop:{span_key(x):{'verdict':'different_shoot'} for row in rows for x in row}
        with patch('workbench.reference.audit_choices',side_effect=verdicts),patch('workbench.reference.analyze',return_value={'beats':[beat]}),patch('vision_api.call',return_value=proposal),patch('workbench.reference.screen_sources',side_effect=lambda app,b,c:(c,[])):
            self.op(b,'plan');t=self.task(b);self.assertEqual(t['status'],'planned',t.get('error'))
            self.op(b,'preview');t=self.task(b);self.assertEqual(t['status'],'awaiting_review',t.get('error'))
            body=dict(task_ids=[t['id']],index=0,option=1,plan_revision=t['plan_revision'])
            changed=eng.action(p,w,b['id'],'replace-shot',body)
            self.assertNotIn('preview',changed);self.assertEqual(changed['plan']['parts'][0]['shot_id'],'alt')
            self.assertEqual(changed['plan']['parts'][0]['frames'],60)
            with self.assertRaises(Problem):eng.action(p,w,b['id'],'replace-shot',body)
            self.op(b,'preview');self.assertEqual(self.task(b)['preview']['report']['body_seconds'],2)
        with self.assertRaises(Problem):eng.media(p,self.w2['id'],t['id']+'-2')

    def test_reference_clock_keeps_three_frame_intro_and_missing_tail(self):
        from workbench.reference import span_key
        eng=self.app.editing
        w,p=self.w['id'],self.p['id']
        ref=self.upload(self.intro,'reference')
        b=eng.create_uploaded(p,w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        beat=dict(purpose='展示',action='旋转',subject='产品',composition='近景')
        beats=[dict(beat,start=0,end=.1),dict(beat,start=.1,end=1)]
        proposal={'parts':[{'reference_beat':1,'shot_id':'unlisted','reason':'bad',
                            'alternatives':[{'shot_id':self.shot['id'],'reason':'清楚的产品封面'}]}],
                  'gaps':[{'reference_beat':2,'reason':'缺少独立实拍'}]}
        def audit(app,b,rows,paid,stop):
            return {span_key(x):{'verdict':'different_shoot'} for row in rows for x in row}
        with patch('workbench.reference_structure.analyze',return_value={'beats':beats}), patch('vision_api.call',return_value=proposal), patch('workbench.reference.audit_choices',side_effect=audit), patch('workbench.reference.screen_sources',side_effect=lambda app,b,c:(c,[])):
            self.op(b,'plan')
            t=self.task(b)
            self.assertEqual(t['status'],'planned',t.get('error'))
            self.assertEqual(t['plan']['parts'][0]['frames'],3)
            gap=t['plan']['reference_gaps'][0]
            self.assertEqual((gap['start_frame'],gap['frames']),(3,27))
            self.op(b,'preview')
            t=self.task(b)
            self.assertEqual(t['status'],'awaiting_review',t.get('error'))
            self.assertEqual(t['preview']['report']['body_seconds'],1)
            with self.assertRaisesRegex(Problem,'待补实拍'):
                eng.action(p,w,b['id'],'output',dict(task_ids=[t['id']],content_confirmed=True,preview_sha256=t['preview']['sha256']))
            self.assertFalse(self.task(b).get('human_reviewed',False))

    def test_diagnostics_and_regression_samples_are_versioned_and_scoped(self):
        from workbench.reference_review import diagnose,record
        eng=self.app.editing
        p,w=self.p['id'],self.w['id']
        ref=self.upload(self.intro,'reference')
        b=eng.create_uploaded(p,w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        t=self.task(b)
        beat=dict(start=0,end=1,purpose='显示结果',action='亮起',subject='灯',must_see=['从灭到亮'])
        t['reference_analysis']={'beats':[beat]}
        self.app.store.put('edit_task',w,t)
        root=eng.folder(w,b['id'])/t['id']
        save(root/'reference-stock.json',{'x':{'name':'固定展示','facts':'一直亮着','analysis_version':'old'}})
        save(root/'api-cache'/'slots-1.json',{'slots':[{'reference_beat':1,'choices':[{'id':'x'}],
                                                        'excluded':[['z','no_safe_fit']]}]})
        save(root/'proposal.json',{'gaps':[{'reference_beat':1,'reason':'没有拍到亮起'}]})
        args=(self.app,p,w,b['id'],t['id'])
        report=diagnose(*args)
        row=report['rows'][0]
        self.assertEqual(row['candidates'][0]['facts'],'一直亮着')
        self.assertEqual(row['excluded'][0]['reason'],'no_safe_fit')
        self.assertEqual(row['notes'],['没有拍到亮起'])
        body=dict(revision=report['revision'],beat=1,stage='recognition',scope='product',expected='须看见从灭到亮')
        case=record(*args,'samples',body)
        self.assertEqual(case['id'],record(*args,'samples',body)['id'])
        self.assertEqual(len(diagnose(*args)['cases']),1)
        with self.assertRaises(Problem):record(*args,'samples',dict(body,revision='stale'))
        with self.assertRaises(Problem):diagnose(self.app,p,self.w2['id'],b['id'],t['id'])
        other=eng.create_uploaded(p,w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        newer=self.task(other);newer['reference_analysis']={'beats':[beat]}
        self.app.store.put('edit_task',w,newer)
        args2=(self.app,p,w,other['id'],newer['id'])
        comparison=diagnose(*args2)
        self.assertEqual(comparison['rows'][0]['cases'],[case['id']])
        checked=record(*args2,'checks',dict(revision=comparison['revision'],beat=1,case_id=case['id'],outcome='fail'))
        self.assertEqual(checked['checks'][0]['task_id'],newer['id'])
        self.assertEqual(checked['evidence']['notes'],['没有拍到亮起'])

    def test_semantic_version_choice_only_applies_to_its_asset_in_its_workspace(self):
        eng=self.app.editing;p=self.p['id'];w=self.w['id']
        old=dict(self.shot,analysis_version='A')
        new=dict(old,id='another-shot',analysis_version='B')
        for shot in (old,new):self.app.store.put('shot',w,shot)
        body=dict(sha256=self.asset['sha256'],previous=None,version='B')
        self.app.select_standard_version(p,w,self.asset['id'],body)
        picked=eng.candidates(p,w,active_versions=True)
        self.assertEqual([c['analysis_version'] for c in picked],['B'])
        self.assertEqual(len(eng.candidates(p,w)),2)
        with self.assertRaises(Problem):self.app.select_standard_version(p,w,self.asset['id'],dict(body,version='A'))
        with self.assertRaises(Problem):self.app.select_standard_version(p,self.w2['id'],self.asset['id'],body)
        self.app.select_standard_version(p,w,self.asset['id'],dict(body,previous='B',version=None))
        self.assertEqual(len(eng.candidates(p,w,active_versions=True)),2)

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

    def test_short_intro_audio_overhang_survives_the_cut(self):
        import array
        from workbench.edit_media import render
        intro=self.root/'short-overhang.mp4'
        voice=self.root/'silent.wav'
        run(['ffmpeg','-v','error','-i',self.intro,'-f','lavfi','-i','sine=frequency=440:duration=1.09',
             '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',intro])
        run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1',voice])
        out,report=render(intro,voice,[dict(path=self.clip,start=0,frames=30)],self.root/'tail-preview',True)
        self.assertEqual(report['duration'],2)
        self.assertAlmostEqual(report['intro_audio_tail_seconds'],.09,delta=.01)
        def peak(start):
            samples=array.array('f')
            samples.frombytes(run(['ffmpeg','-v','error','-i',out,'-ss',start,'-t','0.04',
                                   '-vn','-ac','1','-f','f32le','-']).stdout)
            return max(map(abs,samples))
        self.assertGreater(peak('1.02'),.02)
        self.assertLess(peak('1.25'),.002)
    def test_batch_duplicate_intervals_blocked(self):
        shutil.copy2(self.inputs/'1.mp4',self.inputs/'2.mp4');shutil.copy2(self.inputs/'1.mp3',self.inputs/'2.mp3');shutil.copy2(self.inputs/'1.srt',self.inputs/'2.srt')
        b=self.create()
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        tasks=self.app.editing.tasks(self.w['id'],b['id']);self.assertEqual([t['status'] for t in tasks],['planned','needs_attention']);self.assertIn('重复',tasks[1]['error'])
    def test_cross_batch_exact_body_rejected_but_partial_reuse_allowed(self):
        b=self.create(mode='direct')
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        self.assertEqual(self.task(b)['status'],'completed')
        second=self.create();task=self.task(second)
        with self.assertRaisesRegex(ValueError,'完全重复'):
            self.app.editing.validate_plan(second,task,self.proposal())
        # Split the exact same interval into two consecutive parts: still duplicate.
        split={'parts':[dict(self.proposal()['parts'][0],frames=30),dict(self.proposal()['parts'][0],start=1,frames=30)]}
        with self.assertRaisesRegex(ValueError,'完全重复'):
            self.app.editing.validate_plan(second,task,split)
        # A one-frame shift plus a zoom is still essentially the same edit.
        shifted={'parts':[dict(self.proposal()['parts'][0],start=1/30,zoom=1.05)]}
        with self.assertRaisesRegex(ValueError,'近乎重复'):
            self.app.editing.validate_plan(second,task,shifted)
        partial={'parts':[dict(self.proposal()['parts'][0],start=1)]}
        self.app.editing.validate_plan(second,task,partial)
        peer=dict(task,id='same-batch-peer',plan=self.app.editing.validate_plan(second,task,partial),status='planned')
        self.app.store.put('edit_task',self.w['id'],peer)
        # Partial reuse remains allowed within a batch too.
        self.app.editing.validate_plan(second,task,{'parts':[dict(self.proposal()['parts'][0],start=.5)]})
        self.assertTrue(any(0<m['body_overlap']<1 for m in task['dedup_report']['matches']))
        self.assertTrue(task['dedup_report']['partial_reuse_allowed'])

    def test_direct_batch_allocates_before_render_and_reuses_saved_plans(self):
        shutil.copy2(self.intro,self.inputs/'2.mp4')
        run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-f','wav',self.inputs/'2.mp3'])
        b=self.create(mode='direct',matching_mode='duration',timing_basis='audio_duration')
        engine=self.app.editing
        original=engine.candidates(self.p['id'],self.w['id'])
        # A second logical source isolates the allocation decision. The first
        # render is intercepted so resume can be exercised before any output.
        alternative=dict(original[0],id='alternate',asset_sha256='alternate')
        snapshots=[]
        def interrupt(*args):
            snapshots.append(engine.tasks(self.w['id'],b['id']))
            raise ValueError('simulated encoder failure')
        with patch.object(engine,'candidates',return_value=original+[alternative]),patch.object(engine,'render',side_effect=interrupt),patch('vision_api.call',side_effect=AssertionError('unexpected model call')):
            self.op(b,'plan')
            plans=[t['plan'] for t in snapshots[0]]
            self.assertEqual([p['selection_strategy'] for p in plans],['batch_duration']*2)
            self.assertEqual([sum(s['frames'] for s in p['parts']) for p in plans],[60,30])
            self.assertNotEqual(plans[0]['parts'][0]['asset_sha256'],plans[1]['parts'][0]['asset_sha256'])
            with patch('workbench.duration_planner.plan_by_duration',side_effect=AssertionError('replanned')):
                self.op(b,'resume')
            self.assertEqual(len(snapshots),4)
            self.assertEqual([t['plan'] for t in snapshots[-1]],plans)

    def test_direct_batch_renders_three_and_isolates_exhausted_intro(self):
        for number,duration in [(2,1.5),(3,1),(4,.5)]:
            shutil.copy2(self.intro,self.inputs/f'{number}.mp4')
            run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=duration={duration}','-f','wav',self.inputs/f'{number}.mp3'])
        b=self.create(mode='direct',matching_mode='duration',timing_basis='audio_duration')
        with patch('vision_api.call',side_effect=AssertionError('unexpected model call')):
            self.op(b,'plan')
        tasks=self.app.editing.tasks(self.w['id'],b['id'])
        self.assertEqual([t['status'] for t in tasks],['completed']*3+['needs_attention'],[t.get('error') for t in tasks])
        for t in tasks[:3]:
            self.assertTrue(Path(t['output']['path']).is_file())
        self.assertIn('固定开头或结尾',tasks[3]['error'])

    def test_duration_search_skips_historical_duplicate_without_model(self):
        b=self.create(mode='direct')
        with patch('vision_api.call',return_value=self.proposal()):self.op(b,'plan')
        second=self.create(matching_mode='duration');task=self.task(second)
        other=dict(self.shot,id='alternative-shot',asset_sha256='different-source',start=0,end=2,frames=60,safe_trim_ranges=[],action_start=None,action_end=None)
        original=self.app.editing.candidates(self.p['id'],self.w['id'])
        with patch.object(self.app.editing,'candidates',return_value=original+[other]),patch('vision_api.call',side_effect=AssertionError('no model')):
            planned=self.app.editing.plan(second,task,False)
        self.assertNotEqual(self.app.editing.visual_sequence(planned['plan']['parts']),self.app.editing.visual_sequence(self.task(b)['plan']['parts']))

    def test_semantic_whole_only_duration_gap_is_local(self):
        self.shot['safe_trim_ranges']=[]
        self.app.store.put('shot',self.w['id'],self.shot)
        batch=self.create(matching_mode='semantic')
        with patch('vision_api.call') as call:
            self.op(batch,'plan')
            call.assert_not_called()
        task=self.task(batch)
        self.assertEqual(task['status'],'needs_attention')
        self.assertIn('60帧',task['error'])

    def test_output_reservation_blocks_duplicate_before_encoder(self):
        first=self.create();task=self.task(first)
        task['plan']=self.app.editing.validate_plan(first,task,self.proposal())
        task.update(status='running',dedup_reserved=True)
        self.app.store.put('edit_task',self.w['id'],task)
        second=self.create();other=self.task(second)
        with self.assertRaisesRegex(ValueError,'完全重复'):
            self.app.editing.validate_plan(second,other,self.proposal())
        task['status']='needs_attention';self.app.store.put('edit_task',self.w['id'],task)
        self.app.editing.validate_plan(second,other,self.proposal())

    def test_common_outro_reported_without_blocking_different_bodies(self):
        first=self.create();task=self.task(first)
        first['clips']=[{'position':'outro','sha256':'shared-outro'}]
        self.app.store.put('edit_batch',self.w['id'],first)
        task.update(output={'sha256':'old-output'},plan={'parts':[{'asset_sha256':'source-a','start':0,'end':2,'frames':60}]})
        self.app.store.put('edit_task',self.w['id'],task)
        second=self.create();second['clips']=first['clips'];self.app.store.put('edit_batch',self.w['id'],second)
        other=self.task(second)
        report=self.app.editing.duplicate_check(other,[{'asset_sha256':'source-b','start':0,'end':2,'frames':60}])
        self.assertTrue(report['matches'][0]['shared_uploaded_outro'])
        self.assertEqual(report['matches'][0]['body_overlap'],0)
        # Same source with a disjoint ending is a source reuse hint, not
        # an identical ending or an identical body.
        different_cut=self.app.editing.duplicate_check(other,[{'asset_sha256':'source-a','start':2,'end':4,'frames':60}])
        match=different_cut['matches'][0]
        self.assertTrue(match['same_ending_source'])
        self.assertFalse(match['same_ending'])
        self.assertEqual(match['body_overlap'],0)

    def test_zoom_preview_and_output_preserve_portrait_and_duration(self):
        b=self.create();proposal=self.proposal();proposal['parts'][0]['zoom']=1.05
        with patch('vision_api.call',return_value=proposal):self.op(b,'plan')
        self.op(b,'preview');t=self.task(b)
        self.assertEqual(t['status'],'awaiting_review',t.get('error'))
        self.assertEqual(t['plan']['parts'][0]['zoom'],1.05)
        self.op(b,'output',{'content_confirmed':True,'preview_sha256':t['preview']['sha256']})
        t=self.task(b);self.assertEqual(t['status'],'completed',t.get('error'))
        self.assertEqual(t['output']['report']['duration'],3)

    def test_direct_batch_random_zoom_renders_without_model_or_fake_review(self):
        b=self.create(mode='direct',matching_mode='duration')
        with patch('vision_api.call',side_effect=AssertionError('no model')):
            self.op(b,'plan')
        t=self.task(b)
        self.assertEqual(t['status'],'completed',t.get('error'))
        self.assertTrue(all(p['zoom'] in (1.025,1.05) for p in t['plan']['parts']))
        self.assertFalse(t.get('human_reviewed',False))
        self.assertEqual(t['output']['report']['duration'],3)
        original=json.loads(json.dumps(t['plan']))
        self.app.editing.vary_plan(b,t,t['plan'])
        self.assertEqual(t['plan'],original)

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
