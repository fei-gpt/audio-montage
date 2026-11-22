"""Scoped editing acceptance with real local media and mocked semantic requests."""
import io,json,shutil,tempfile,unittest
import sqlite3
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
        cls.short_clips={}
        for frames in (3,15,31):
            path=root/f'minimum-{frames}.mp4'
            run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=green:s=90x160:r=30',
                 '-frames:v',str(frames),'-c:v','libx264',path])
            cls.short_clips[frames]=path
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
        # The library minimum includes unreviewed sources, which cannot be selected.
        EditingTest.add_minimum_source(self,15)
        task=self.root/'task.json';save(task,{'analysis':{'shot_boundaries':[],'transition_ranges':[]}})
        self.shot=self.app.store.put('shot',self.w['id'],{'asset_id':self.asset['id'],'asset_sha256':self.asset['sha256'],'start':0,'end':3,
            'review_decision':'keep','human_confirmed':True,'facts':'red toy','safe_trim_ranges':[{'start':0,'end':3}],'task_path':str(task)})
        write_document(self.library/'clip.mp4',self.asset['sha256'],complete=True,context={'visual_details':{'subject':'red toy'}})
    def add_minimum_source(self,frames):
        source=self.short_clips[frames]
        shutil.copy2(source,self.library/source.name)
        self.app.scan(self.p['id'],self.w['id'])

    def tearDown(self):self.tmp.cleanup()

    def test_minimum_uses_shortest_existing_source(self):
        w=self.w['id']
        self.assertEqual(self.app.editing.minimum_shot_frames(w),15)
        b=self.create()
        task=self.task(b)
        (self.library/self.short_clips[15].name).unlink()
        self.assertEqual(self.app.editing.minimum_shot_frames(w),90)
        self.add_minimum_source(31)
        self.assertEqual(self.app.editing.minimum_shot_frames(w),31)
        (self.library/self.short_clips[31].name).unlink()
        with self.assertRaisesRegex(ValueError,'90'):
            self.app.editing.validate_plan(b,task,self.proposal())

    def test_short_ending_is_removed_before_last_shot_check_and_voice_render(self):
        batch=self.create(matching_mode='semantic')
        part=self.proposal()['parts'][0]
        proposal={'parts':[dict(part,frames=54),dict(part,start=1.8,frames=6)]}
        rule=dict(ordinal=None,frame=None,last=True,label='静态展示',excluded=[],preferred=False,text='最后一镜用静态展示')
        batch['rules']['shot_requests']=[rule]
        self.app.store.put('edit_batch',self.w['id'],batch)
        with patch('vision_api.call',return_value=proposal):
            self.op(batch,'plan')
        self.assertIn('最后一镜用静态展示',self.task(batch)['error'])
        self.asset['user_category']={'labels':['静态展示'],'confirmed':True}
        self.app.store.put('asset',self.w['id'],self.asset)
        with patch('vision_api.call',return_value=proposal):
            self.op(batch,'plan')
        task=self.task(batch)
        self.assertEqual(task['status'],'planned',task.get('error'))
        self.assertEqual([p['frames'] for p in task['plan']['parts']],[60])
        self.op(batch,'preview')
        self.assertEqual(self.task(batch)['preview']['report']['body_seconds'],2)

    def test_reference_tail_threshold_is_strict(self):
        from workbench.editing import remove_short_ending
        for frames,expected in ((14,[30]),(15,[30,15]),(16,[30,16])):
            parts=[dict(frames=30),dict(frames=frames)]
            self.assertEqual([p['frames'] for p in remove_short_ending(parts,15,{},False)],expected)

    def test_preview_check_repairs_only_blocked_range_in_original_task(self):
        from workbench.usage import SCHEMA
        import shutil
        w,p=self.w['id'],self.p['id']
        edit=self.app.editing
        b=self.create(matching_mode='duration')
        t=self.task(b)
        other=self.library/'blue.mp4'
        shutil.copy2(self.intro,other)
        self.app.scan(p,w)
        blue=next(a for a in self.app.visible_assets(w) if a['name']==other.name)
        write_document(other,blue['sha256'],complete=True)
        self.app.store.put('shot',w,dict(self.shot,id='blue',asset_id=blue['id'],asset_sha256=blue['sha256'],end=1,safe_trim_ranges=[]))
        raw=dict(self.proposal()['parts'][0],frames=30)
        t['plan']=edit.validate_plan(b,t,dict(parts=[raw,dict(raw,start=1)]))
        t.update(plan_revision='first',status='planned')
        self.app.store.put('edit_task',w,t)
        save(Path(str(self.asset['path'])+'.usage.json'),dict(schema=SCHEMA,source_sha256=self.asset['sha256'],
             references=[dict(task_id=str(n),ranges=[[0,30]]) for n in range(3)]))
        result=edit.action(p,w,b['id'],'replacement-options',dict(task_id=t['id']))
        self.assertEqual([x['index'] for x in result['issues']],[0])
        alt=next(x for x in result['issues'][0]['options'] if x['shot_id']=='blue')
        body=dict(task_ids=[t['id']],plan_revision='first',changes={'0':[alt['shot_id'],alt['asset_sha256'],alt['start']]})
        edit.action(p,w,b['id'],'repair-shots',body)
        edit.run(p,w,b['id'],[t['id']],'preview')
        revised=self.task(b)
        self.assertEqual(revised['status'],'awaiting_review',revised.get('error'))
        self.assertEqual(revised['plan']['parts'][1],t['plan']['parts'][1])
        self.assertEqual(revised['preview']['report']['body_seconds'],2)
        self.assertFalse(edit.action(p,w,b['id'],'preview-check',dict(task_id=t['id']))['issues'])

    def test_reference_preview_omits_short_final_beat(self):
        from workbench.reference import span_key
        w=self.w['id']
        tail=next(a for a in self.app.visible_assets(w) if a['id']!=self.asset['id'])
        write_document(tail['path'],tail['sha256'],complete=True)
        self.app.store.put('shot',w,dict(self.shot,id='tail',asset_id=tail['id'],asset_sha256=tail['sha256'],end=.5,safe_trim_ranges=[dict(start=0,end=.5)]))
        ref=self.upload(self.intro,'reference')
        batch=self.app.editing.create_uploaded(self.p['id'],w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        beats=[dict(start=0,end=.8),dict(start=.8,end=1)]
        proposal={'parts':[dict(reference_beat=i,shot_id=s,reason='符合参考动作') for i,s in enumerate([self.shot['id'],'tail'],1)]}
        with patch('workbench.reference_structure.analyze',return_value={'beats':beats}),patch('workbench.reference.select_slots',return_value=proposal),patch('workbench.reference.screen_sources',side_effect=lambda app,b,c:(c,[])),patch('workbench.reference.audit_choices',side_effect=lambda app,b,rows,paid,stop:{span_key(x):{'verdict':'different_shoot'} for row in rows for x in row}):
            self.op(batch,'plan')
            task=self.task(batch)
            self.assertEqual(task['status'],'planned',task.get('error'))
            self.assertEqual([p['frames'] for p in task['plan']['parts']],[24])
            self.op(batch,'preview')
            self.assertEqual(self.task(batch)['preview']['report']['body_seconds'],.8)

    def test_browsing_reuses_hash_and_rechecks_replaced_file(self):
        from workbench.editing import listed_fingerprint
        path=self.root/'replacement.mp4'
        path.write_bytes(b'first')
        with patch('workbench.editing.fingerprint',wraps=fingerprint) as hashed:
            before=listed_fingerprint(path)
            self.assertEqual(listed_fingerprint(path),before)
            self.assertEqual(hashed.call_count,1)
            replacement=self.root/'new.mp4'
            replacement.write_bytes(b'other')
            replacement.replace(path)
            self.assertNotEqual(listed_fingerprint(path),before)
            self.assertEqual(hashed.call_count,2)

    def test_validate_existing_plan_hashes_only_selected_footage(self):
        edit=self.app.editing;w=self.w['id']
        other=next(a for a in self.app.visible_assets(w) if a['id']!=self.asset['id'])
        self.app.store.put('shot',w,dict(self.shot,id='other-shot',asset_id=other['id'],asset_sha256=other['sha256']))
        batch=self.create();task=self.task(batch)
        with patch('workbench.editing.fingerprint',wraps=fingerprint) as hashed:
            edit.validate_plan(batch,task,self.proposal())
        files=[Path(call.args[0]) for call in hashed.call_args_list]
        self.assertIn(Path(self.asset['path']),files)
        self.assertNotIn(Path(other['path']),files)
        Path(self.asset['path']).write_bytes(b'replaced')
        with self.assertRaisesRegex(ValueError,'当前可用素材'):
            edit.validate_plan(batch,task,self.proposal())

    def test_all_batch_creation_paths_publish_every_task_together(self):
        edit,store=self.app.editing,self.app.store
        p,w=self.p['id'],self.w['id']
        narration=self.upload(self.audio,'narration')
        reference=self.upload(self.intro,'reference')
        old=edit.create(p,w,{'narrations':[{'id':narration['id']}],'rights_allowed':True})
        source=store.put('edit_task',w,dict(self.task(old),status='planned',plan=self.proposal()))
        for file in (self.inputs/'1.mp4',self.inputs/'1.mp3'):
            shutil.copyfile(file,file.with_stem('2'))
        pairs={'input_mode':'paired','input_path':str(self.inputs)}
        pairs['pairing_snapshot']=edit.inspect_pairs(p,w,pairs)['snapshot']
        root=edit.folder(w,old['id']).parent
        creators={
            'narration':lambda:edit.create(p,w,{'narrations':[{'id':narration['id']}],'variant_count':5})['id'],
            'silent reference':lambda:edit.create(p,w,{'reference_id':reference['id'],'variant_count':5})['id'],
            'folder pairs':lambda:edit.create(p,w,pairs)['id'],
            'regeneration':lambda:edit.action(p,w,old['id'],'regenerate',{'task_ids':[source['id']],'variant_count':5})['id'],
        }
        for entry,create in creators.items():
            with self.subTest(entry=entry):
                prior=(edit.list(p,w),set(root.iterdir()),store.all('edit_task',w))
                version=store.revision
                with store.db() as db:
                    db.execute("""CREATE TRIGGER fail_second_task BEFORE INSERT ON objects
                        WHEN new.kind='edit_task' AND EXISTS (SELECT 1 FROM objects WHERE kind='edit_task'
                        AND json_extract(body,'$.batch_id')=json_extract(new.body,'$.batch_id'))
                        BEGIN SELECT RAISE(ABORT,'second task'); END""")
                try:
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'second task'):create()
                finally:
                    with store.db() as db:db.execute('DROP TRIGGER fail_second_task')
                self.assertEqual(store.revision,version)
                self.assertEqual(prior,(edit.list(p,w),set(root.iterdir()),store.all('edit_task',w)))
                bid=create()
                tasks=edit.tasks(w,bid)
                self.assertEqual(len(tasks),2 if entry=='folder pairs' else 5)
                if entry=='silent reference':
                    self.assertTrue(all(Path(t['audio']).is_file() for t in tasks))
        self.assertEqual(store.get('edit_task',source['id'],w),source)

    def test_group_state_changes_are_atomic_and_cancelled_tasks_stay_closed(self):
        edit,store=self.app.editing,self.app.store
        p,w=self.p['id'],self.w['id']
        voice=self.upload(self.audio,'narration')
        b=edit.create(p,w,{'narrations':[{'id':voice['id']}],'variant_count':5})
        bid=b['id'];cancelled=edit.tasks(w,bid)[0]['id']
        edit.action(p,w,bid,'cancel',{'task_ids':[cancelled]})
        closed=store.get('edit_task',cancelled,w)
        for operation,status in [('pause','paused'),('resume','queued'),('cancel','cancelled')]:
            before=edit.tasks(w,bid)
            # Interrupt one of the four active tasks after an earlier update in this transaction.
            with store.db() as db:
                db.execute(f"""CREATE TRIGGER fail_update BEFORE INSERT ON objects
                    WHEN new.kind='edit_task' AND new.id='{before[3]['id']}' AND json_extract(new.body,'$.status')='{status}'
                    BEGIN SELECT RAISE(ABORT,'state change'); END""")
            try:
                with self.assertRaisesRegex(sqlite3.IntegrityError,'state change'):edit.action(p,w,bid,operation,{})
            finally:
                with store.db() as db:db.execute('DROP TRIGGER fail_update')
            self.assertEqual(edit.tasks(w,bid),before)
            edit.action(p,w,bid,operation,{})
            self.assertEqual(store.get('edit_task',cancelled,w),closed)
            self.assertTrue(all(t['status']==status for t in edit.tasks(w,bid) if t['id']!=cancelled))

    def test_pause_and_resume_preserve_tasks_already_waiting_for_review(self):
        edit,store=self.app.editing,self.app.store
        p,w=self.p['id'],self.w['id'];voice=self.upload(self.audio,'narration')
        b=edit.create(p,w,{'narrations':[{'id':voice['id']}],'variant_count':5})
        live,*idle=edit.tasks(w,b['id'])
        saved=[]
        for t,status in zip(idle,['awaiting_review','planned','completed','invalid']):
            saved.append(store.put('edit_task',w,dict(t,status=status)))
        for operation,expected in [('pause','paused'),('resume','queued')]:
            edit.action(p,w,b['id'],operation,{})
            self.assertEqual(store.get('edit_task',live['id'],w)['status'],expected)
            self.assertEqual([store.get('edit_task',t['id'],w) for t in saved],saved)

    def test_executor_rejection_can_resume_in_original_record(self):
        from concurrent.futures import ThreadPoolExecutor
        edit=self.app.editing;b=self.create();p,w=self.p['id'],self.w['id']
        task=self.task(b)
        with ThreadPoolExecutor(max_workers=1) as stopped:pass
        with patch.object(self.app,'pool',stopped):
            self.assertEqual(edit.action(p,w,b['id'],'plan',{})['queued'],0)
        self.assertEqual(self.task(b)['status'],'interrupted')
        self.assertEqual(edit.action(p,w,b['id'],'resume',{})['queued'],1)
        self.assertEqual(self.task(b)['id'],task['id'])
        self.assertEqual(self.task(b)['operation'],'plan')

    def test_previous_worker_cannot_claim_or_overwrite_requeued_task(self):
        from workbench.editing import Stopped
        from concurrent.futures import ThreadPoolExecutor
        import threading
        edit=self.app.editing;batch=self.create()
        p,w,bid=self.p['id'],self.w['id'],batch['id']
        gate=threading.Barrier(2)
        def submit():
            gate.wait(timeout=5)
            try:return edit.action(p,w,bid,'plan',{})['queued']
            except Problem as exc:return exc.status
        with ThreadPoolExecutor(2) as workers:
            calls=[workers.submit(submit) for _ in range(2)]
            self.assertEqual(sorted(call.result(timeout=10) for call in calls),[1,409])
        old=self.task(batch)
        edit.action(p,w,bid,'pause',{})
        edit.action(p,w,bid,'resume',{})
        new=self.task(batch)
        with self.assertRaises(Stopped):edit.check_stop(old)
        with patch.object(edit,'plan') as planner:
            edit.run(p,w,bid,[old['id']],'plan',True,old['queue_attempt'])
            planner.assert_not_called()
        self.assertNotEqual(new['queue_attempt'],old['queue_attempt'])
        self.assertEqual(self.task(batch),new)
    def create(self,**kw):return self.app.editing.create(self.p['id'],self.w['id'],dict(input_path=str(self.inputs),timing_confirmed=True,rights_allowed=True,**kw))
    def task(self,b):return self.app.editing.tasks(self.w['id'],b['id'])[0]
    def op(self,b,op,body=None):
        self.app.editing.action(self.p['id'],self.w['id'],b['id'],op,body or {})
        ids=[t['id'] for t in self.app.editing.tasks(self.w['id'],b['id']) if t['status']=='queued']
        self.app.editing.run(self.p['id'],self.w['id'],b['id'],ids,op)
    def proposal(self):return {'parts':[{'shot_id':self.shot['id'],'start':0,'frames':60,'reason':'red toy matches narration'}],'gaps':[]}
    def upload(self,file,kind,w=None):
        return self.app.editing.upload(self.p['id'],(w or self.w)['id'],file.name,kind,io.BytesIO(file.read_bytes()),file.stat().st_size)
    def test_manual_cues_shared_batch_and_independent_review(self):
        p,w=self.p['id'],self.w['id']
        edit=self.app.editing
        voice=self.upload(self.audio,'narration')
        sound=self.upload(self.audio,'sound')
        cue=dict(anchor='time',seconds=.2,text='亮相',sound_id=sound['id'])
        body=dict(narrations=[dict(id=voice['id']),dict(id=voice['id'])],rights_allowed=True,cues=[cue])
        other=self.upload(self.audio,'sound',self.w2)
        with self.assertRaises(Problem):
            edit.create_uploaded(p,w,dict(body,cues=[dict(cue,sound_id=other['id'])]))
        b=edit.create_uploaded(p,w,body)
        a,sibling=edit.tasks(w,b['id'])
        a.update(plan=edit.validate_plan(b,a,self.proposal()),plan_revision='first',status='planned')
        self.app.store.put('edit_task',w,a)
        self.op(b,'preview',dict(task_ids=[a['id']]))
        a=self.app.store.get('edit_task',a['id'],w)
        self.assertEqual(a['preview']['report']['cue_schedule'],[{'frame':6}])
        edit.action(p,w,b['id'],'save-cues',dict(task_ids=[a['id']],plan_revision='first',cues=[dict(cue,seconds=.6)]))
        edit.run(p,w,b['id'],[a['id']],'preview')
        revised=self.app.store.get('edit_task',a['id'],w)
        self.assertEqual(revised['preview']['report']['cue_schedule'],[{'frame':18}])
        self.assertEqual(revised['plan']['parts'],a['plan']['parts'])
        self.assertNotIn('cues',self.app.store.get('edit_task',sibling['id'],w))
        self.assertEqual(edit.batch(p,w,b['id'])['rules']['cues'][0]['seconds'],.2)
        with self.assertRaises(Problem):
            edit.action(p,w,b['id'],'output',dict(task_ids=[a['id']],content_confirmed=True,preview_sha256=a['preview']['sha256'],plan_revision='first'))
        self.op(b,'output',dict(task_ids=[a['id']],content_confirmed=True,preview_sha256=revised['preview']['sha256'],plan_revision=revised['plan_revision']))
        self.assertEqual(self.app.store.get('edit_task',a['id'],w)['output']['report']['cue_schedule'],[{'frame':18}])

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
    def test_generated_narration_requirements_are_scoped_to_each_task(self):
        p,w=self.p['id'],self.w['id']
        product=self.app.store.get('product',p,'root')
        self.app.store.put('product','root',dict(product,shot_categories=['主体展示','静态展示']))
        edit=self.app.editing
        first=self.upload(self.audio,'narration')
        second=self.upload(self.audio,'narration')
        for upload in (first,second):
            self.app.store.put('edit_upload',w,dict(upload,generated_narration=True))
        common='最后一镜优先用静态展示'
        specific='第一镜必须用主体展示'
        batch=edit.create(p,w,{'narrations':[{'id':first['id'],'request':specific},{'id':second['id']}],
            'request':common,'matching_mode':'duration','rights_allowed':True})
        tasks={task['audio']:task for task in edit.tasks(w,batch['id'])}
        first_task,second_task=tasks[first['path']],tasks[second['path']]
        self.assertEqual([r['text'] for r in edit.task_batch(batch,first_task)['rules']['shot_requests']],[common,specific])
        self.assertEqual([r['text'] for r in edit.task_batch(batch,second_task)['rules']['shot_requests']],[common])
        self.assertEqual(batch['rules']['request'],common)
        checked=edit.inspect_narration_request(p,w,{'id':first['id'],'common':common,'request':specific})
        self.assertEqual(checked['requirements'][1]['labels'],['主体展示'])
        checked=edit.inspect_narration_request(p,w,{'id':first['id'],'request':'全片排除静态展示'})
        self.assertEqual(checked['requirements'][0]['excluded'],['静态展示'])
        with self.assertRaisesRegex(Problem,'同一镜头的剪辑要求冲突'):
            edit.inspect_narration_request(p,w,{'id':first['id'],'common':'第一镜必须用静态展示','request':specific})
        with self.assertRaisesRegex(Problem,'未匹配到展示类别'):
            edit.inspect_narration_request(p,w,{'id':first['id'],'request':'第一镜必须用不存在的类别'})
        with self.assertRaises(Problem):
            edit.inspect_narration_request(p,self.w2['id'],{'id':first['id'],'request':specific})

    def test_batch_checks_each_narration_before_creating_any_task(self):
        p,w=self.p['id'],self.w['id']
        edit=self.app.editing
        self.app.store.put('product','root',dict(self.app.product(p),shot_categories=['静态展示']))
        first=self.upload(self.audio,'narration')
        second=self.upload(self.audio,'narration')
        self.app.store.put('edit_upload',w,dict(second,name='短配音.mp3',duration=1))
        narrations=[{'id':first['id']},{'id':second['id']}]
        for generated in (False,True):
            if generated:
                for item in (first,second):
                    record=self.app.store.get('edit_upload',item['id'],w)
                    self.app.store.put('edit_upload',w,dict(record,generated_narration=True))
            with self.assertRaisesRegex(Problem,'第 2 条.*短配音.*成片起止之间'):
                edit.create(p,w,{'narrations':narrations,'request':'00:00:01:15 必须用静态展示'})
        narrations[1]['request']='第一镜必须用不存在的类别'
        with self.assertRaisesRegex(Problem,'第 2 条.*未匹配到展示类别'):
            edit.create(p,w,{'narrations':narrations})
        with self.assertRaisesRegex(Problem,'10000'):
            edit.create(p,w,{'narrations':[narrations[0]],'request':' '*10000+'x'})
        self.assertFalse(self.app.store.all('edit_batch',w))
        self.assertFalse(self.app.store.all('edit_task',w))
        narrations[1]['request']='00:00:00:15 必须用静态展示'
        batch=edit.create(p,w,{'narrations':narrations})
        tasks=edit.tasks(w,batch['id'])
        self.assertEqual(len(tasks),2)
        short=next(t for t in tasks if t['name']=='短配音.mp3')
        self.assertEqual(edit.task_batch(batch,short)['rules']['required_cut_frames'],[15])
        narrations[1]['request']='画面柔和，按文案选片'
        semantic=edit.create(p,w,{'narrations':narrations,'matching_mode':'semantic'})
        short=next(t for t in edit.tasks(w,semantic['id']) if t['name']=='短配音.mp3')
        self.assertEqual(edit.task_batch(semantic,short)['rules']['request'],narrations[1]['request'])

    def test_inspection_and_planning_use_same_extended_timeline(self):
        p,w=self.p['id'],self.w['id']
        edit=self.app.editing
        self.app.store.put('product','root',dict(self.app.product(p),shot_categories=['静态展示']))
        voice=self.upload(self.audio,'narration')
        self.app.store.put('edit_upload',w,dict(voice,generated_narration=True))
        music=self.upload(self.audio,'music')
        self.app.store.put('edit_upload',w,dict(music,duration=16))
        text='00:00:11:00 必须用静态展示'
        for length in ({'target_duration':16},{'follow_music':True}):
            settings=dict(length,music_id=music['id'])
            checked=edit.inspect_narration_request(p,w,dict(settings,id=voice['id'],request=text))
            batch=edit.create(p,w,dict(settings,narrations=[{'id':voice['id'],'request':text}]))
            self.assertEqual(checked['requirements'],edit.task_batch(batch,self.task(batch))['rules']['shot_requests'])
            self.assertEqual(checked['requirements'][0]['frame'],330)
        for settings in ({},{'target_duration':1,'music_id':music['id']},{'follow_music':True},
                         {'follow_music':True,'music_id':voice['id']},
                         {'follow_music':True,'music_id':self.upload(self.audio,'music',self.w2)['id']}):
            with self.assertRaises(Problem):
                edit.inspect_narration_request(p,w,dict(settings,id=voice['id'],request=text))

    def test_common_exclusions_match_inspector_and_actual_selection(self):
        p,w=self.p['id'],self.w['id'];edit=self.app.editing
        product=self.app.store.get('product',p,'root')
        self.app.store.put('product','root',dict(product,shot_categories=['主体展示','安装光剑','拆分光剑']))
        upload=self.upload(self.audio,'narration')
        self.app.store.put('edit_upload',w,dict(upload,generated_narration=True))
        text='全片排除安装光剑+拆分光剑'
        checked=edit.inspect_narration_request(p,w,{'id':upload['id'],'common':text})
        batch=edit.create(p,w,{'narrations':[{'id':upload['id']}],'request':text,'rights_allowed':True})
        self.assertEqual(batch['rules']['global_shot_requests'],checked['requirements'])
        self.app.store.put('asset',w,dict(self.asset,user_category={'labels':['拆分光剑'],'confirmed':True}))
        with self.assertRaisesRegex(ValueError,'排除的素材类别'):
            edit.validate_plan(batch,self.task(batch),self.proposal())
        preference='第一镜优先用主体展示，排除安装光剑+拆分光剑'
        checked=edit.inspect_narration_request(p,w,{'id':upload['id'],'request':preference})
        self.assertEqual(checked['requirements'][0]['excluded'],['安装光剑','拆分光剑'])
        batch=edit.create(p,w,{'narrations':[{'id':upload['id']}],'request':preference,'rights_allowed':True})
        with self.assertRaisesRegex(ValueError,'排除的素材类别'):
            edit.validate_plan(batch,self.task(batch),self.proposal())

    def test_ten_generated_narrations_render_with_one_shared_background_track(self):
        import array
        import math

        p,w=self.p['id'],self.w['id']
        for i in range(1,10):
            path=self.library/f'batch-{i}.mp4'
            run(['ffmpeg','-v','error','-f','lavfi','-i',
                 f'color=0x{(i * 21):02x}5522:s=90x160:r=30:d=3','-c:v','libx264',path])
        self.app.scan(p,w)
        for asset in self.app.visible_assets(w):
            if asset['name'].startswith('batch-'):
                write_document(Path(asset['path']),asset['sha256'],complete=True,context={})
                self.app.store.put('shot',w,{**self.shot,'id':asset['id']+'-shot',
                    'asset_id':asset['id'],'asset_sha256':asset['sha256']})
        narrations=[]
        cache=self.app.wroot(w)/'editing-audio'
        for i in range(10):
            path=self.root/f'narration-{i}.mp3'
            run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=frequency={700+10*i}:duration=2','-f','wav',path])
            upload=self.upload(path,'narration')
            self.app.store.put('edit_upload',w,dict(upload,generated_narration=True,script=f'Copy {i}'))
            save(cache/(upload['sha256']+'-auto.json'),{'audio_sha256':upload['sha256'],
                 'segments':[{'start':0,'end':2,'text':f'Copy {i}'}]})
            narrations.append({'id':upload['id']})
        music=self.root/'shared-music.mp3'
        run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=330:duration=3',music])
        batch=self.app.editing.create(p,w,{'narrations':narrations,'music_id':self.upload(music,'music')['id'],
            'music_volume':30,'matching_mode':'duration','mode':'direct','rights_allowed':True})
        self.op(batch,'plan')
        tasks=self.app.editing.tasks(w,batch['id'])
        self.assertEqual(len(tasks),10)
        self.assertEqual(len({part['asset_sha256'] for task in tasks for part in task.get('plan',{}).get('parts',[])}),10,
                         [task.get('error') for task in tasks])
        for task in tasks:
            with self.subTest(task=task['name']):
                self.assertEqual(task['status'],'completed',task.get('error'))
                output=task['output']
                self.assertEqual(output['report']['duration'],2)
                self.assertEqual(output['report']['music_volume'],.3)
                pcm=run(['ffmpeg','-v','error','-ss','0.2','-i',output['path'],'-t','0.5',
                         '-ac','1','-ar','8000','-f','f32le','-']).stdout
                samples=array.array('f')
                samples.frombytes(pcm)
                self.assertGreater(len(samples),3000)
                def magnitude(frequency):
                    omega=2*math.pi*frequency/8000
                    sine=sum(sample*math.sin(omega*i) for i,sample in enumerate(samples))
                    cosine=sum(sample*math.cos(omega*i) for i,sample in enumerate(samples))
                    return 2*math.hypot(sine,cosine)/len(samples)
                self.assertGreater(magnitude(330),.01)
                self.assertGreater(magnitude(700+10*int(task['script'].split()[-1])),.02)

    def test_uploaded_music_uses_its_duration_without_transcription(self):
        music=self.upload(self.audio,'music')
        b=self.app.editing.create(self.p['id'],self.w['id'],{'primary_music_id':music['id'],'rights_allowed':True})
        t=self.task(b)
        self.assertEqual(t['audio_sha256'],music['sha256'])
        self.assertIsNone(b['music'])
        with patch('workbench.local_asr.transcribe',side_effect=AssertionError('music needs no ASR')),patch('vision_api.call',side_effect=AssertionError('music needs no model')):
            self.op(b,'plan')
            self.assertEqual(self.task(b)['status'],'planned')
            self.op(b,'preview')
        t=self.task(b)
        self.assertEqual(t['status'],'awaiting_review',t.get('error'))
        self.assertEqual(t['preview']['report']['duration'],2)

    def test_history_music_custom_length(self):
        music=self.upload(self.audio,'music')
        create=self.app.editing.create
        body=dict(primary_music_id=music['id'],rights_allowed=True)
        with self.assertRaisesRegex(Problem,'不能超过'):
            create(self.p['id'],self.w['id'],dict(body,target_duration=3))
        batch=create(self.p['id'],self.w['id'],dict(body,target_duration=1.2))
        self.op(batch,'plan')
        self.op(batch,'preview')
        task=self.task(batch)
        self.assertEqual(task['status'],'awaiting_review',task.get('error'))
        self.assertAlmostEqual(task['preview']['report']['duration'],1.2,places=2)
        self.assertEqual(task['audio_duration'],2)

    def test_music_can_end_five_frames_early_but_voice_must_fit(self):
        eng=self.app.editing
        for extra in (5,6):
            audio=self.root/f'music-{extra}.wav'
            run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=880:sample_rate=48000',
                 '-af',f'atrim=end_sample={(90+extra)*1600}',audio])
            music=self.upload(audio,'music')
            b=eng.create(self.p['id'],self.w['id'],dict(primary_music_id=music['id'],rights_allowed=True))
            self.op(b,'plan')
            t=self.task(b)
            if extra==6:
                self.assertNotEqual(t['status'],'planned')
                continue
            self.assertEqual(t['status'],'planned',t.get('error'))
            self.op(b,'preview')
            t=self.task(b)
            self.assertEqual(t['preview']['report']['duration'],3)
            voice_batch=dict(b,rules=dict(b['rules'],audio_kind='voice'))
            with self.assertRaisesRegex(ValueError,'配音'):
                eng.validate_plan(voice_batch,t,t['plan'])

    def test_confirmed_prepared_clip_without_shots_enters_duration_pool(self):
        p,w=self.p['id'],self.w['id']
        asset=next(a for a in self.app.visible_assets(w) if a['id']!=self.asset['id'])
        def ids(**kwargs):
            return {c['id'] for c in self.app.editing.candidates(p,w,**kwargs)}
        self.assertNotIn(asset['id'],ids())
        label='主体展示'
        self.app.store.put('product','root',dict(self.app.product(p),shot_categories=[label]))
        self.app.confirm_asset_category(p,w,asset['id'],[label])
        self.assertIn(asset['id'],ids())
        self.assertNotIn(asset['id'],ids(active_versions=True))

    def test_music_required_cut_trims_prepared_clips_and_checks_export_plan(self):
        self.p['name']='lightplay'
        self.app.store.put('product','root',self.p)
        source=self.app.store.get('asset',self.shot['asset_id'],self.w['id'])
        source['user_category']={'labels':['单把光剑旋转'],'confirmed':True}
        self.app.store.put('asset',self.w['id'],source)
        self.shot['facts']='平稳清晰的单把旋转展示'
        self.shot.pop('safe_trim_ranges')
        self.app.store.put('shot',self.w['id'],self.shot)
        shutil.copy2(self.intro,self.library/'other.mp4')
        self.app.scan(self.p['id'],self.w['id'])
        a=next(a for a in self.app.visible_assets(self.w['id']) if a['name']=='other.mp4')
        write_document(a['path'],a['sha256'],complete=True)
        a['user_category']={'labels':['四把合体光剑旋转'],'confirmed':True}
        self.app.store.put('asset',self.w['id'],a)
        self.app.store.put('shot',self.w['id'],dict(self.shot,id='other',asset_id=a['id'],asset_sha256=a['sha256'],end=1,facts='四把合体旋转变色',visual_details={'light_sword':{'arrangement':'connected_four'}}))
        music=self.upload(self.audio,'music')
        b=self.app.editing.create(self.p['id'],self.w['id'],{
            'primary_music_id':music['id'],'rights_allowed':True,'request':'第一镜必须用单把光剑旋转；00:00:01:00 必须用四个光剑旋转'})
        self.op(b,'plan')
        t=self.task(b)
        self.assertEqual(t['status'],'planned',t.get('error'))
        parts=t['plan']['parts']
        self.assertEqual(parts[0]['frames'],30)
        self.assertEqual([part['source_name'] for part in parts[:2]],['clip.mp4','other.mp4'])
        self.assertEqual(sum(part['frames'] for part in parts),60)
        self.assertNotEqual(parts[0]['asset_sha256'],parts[1]['asset_sha256'])
        with self.assertRaisesRegex(ValueError,'跨过指定'):
            self.app.editing.validate_plan(b,t,self.proposal())
        self.op(b,'preview')
        self.assertEqual(self.task(b)['status'],'awaiting_review',self.task(b).get('error'))
        from subprocess import check_output
        output=self.task(b)['preview']['path']
        pixels=check_output(['ffmpeg','-v','error','-i',output,'-vf',
                             r'select=between(n\,29\,30),scale=1:1','-pix_fmt','rgb24',
                             '-fps_mode','passthrough','-f','rawvideo','-'])
        self.assertEqual(len(pixels),6)
        self.assertLess((pixels[0]-pixels[2])*(pixels[3]-pixels[5]),0)

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
    def test_reference_aspect_ratios_are_independent_of_production_clips(self):
        for size in ('480x854','160x90','96x96'):
            with self.subTest(size=size):
                video=self.root/f'{size}.mp4'
                run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=s={size}:r=30:d=1',
                     '-c:v','libx264',video])
                ref=self.upload(video,'reference')
                batch=self.app.editing.create_uploaded(self.p['id'],self.w['id'],{'reference_id':ref['id']})
                self.app.editing.check_inputs(batch,self.task(batch))
                self.assertEqual(self.upload(video,'clip')['kind'],'clip')

    def test_reference_can_repeat_display_with_or_without_narration(self):
        edit=self.app.editing
        p,w=self.p['id'],self.w['id']
        self.app.store.put('product','root',dict(self.app.product(p),light_sword_product=True))
        batch=self.create(matching_mode='semantic')
        task=dict(self.task(batch),audio_duration=2)
        candidates={}
        parts=[]
        for i in range(4):
            key=f'shot-{i}'
            labels=['展示不同灯效','四把光剑旋转' if i%2 else '单把光剑旋转']
            candidates[key]=dict(id=key,asset_id=key,asset_sha256=key,name=key+'a.mp4',
                                 start=0,end=.5,frames=15,safe_trim_ranges=[],
                                 action_start=None,action_end=None,confirmed_categories=labels)
            parts.append(dict(shot_id=key,reference_beat=i+1,start=0,frames=15,reason='符合参考动作'))
        plan={'parts':parts}
        with self.assertRaisesRegex(ValueError,'展示不同灯效.*最多出现一次'):
            edit.validate_plan(batch,task,plan,candidates)
        for candidate in candidates.values():
            candidate['confirmed_categories']=['四把光剑旋转']
        self.assertEqual(len(edit.validate_plan(batch,task,plan,candidates)['parts']),4)
        ref=self.upload(self.intro,'reference')
        task.update(reference_analysis={'beats':[dict(start=i*.5,end=(i+1)*.5,purpose='旋转') for i in range(4)]},
                    plan={'light_sword_rotations':True})
        for silent in (True,False):
            reference=dict(batch,reference=ref,rules=dict(batch['rules'],reference_matching=2,
                           reference_evidence='hypit-structure-v1',reference_only=silent))
            checked=edit.validate_plan(reference,task,plan,candidates)
            self.assertEqual(len(checked['parts']),4)
            self.assertFalse(checked['light_sword_rotations'])

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
            self.assertEqual(changed['plan']['parts'][0]['asset_sha256'],asset['sha256'])
            self.assertEqual(changed['plan']['parts'][0]['frames'],60)
            with self.assertRaises(Problem):eng.action(p,w,b['id'],'replace-shot',body)
            self.op(b,'preview');self.assertEqual(self.task(b)['preview']['report']['body_seconds'],2)
        with self.assertRaises(Problem):eng.media(p,self.w2['id'],t['id']+'-2')

    def test_reference_missing_tail_extends_real_footage_through_output(self):
        self.add_minimum_source(3)
        from workbench.reference import span_key
        eng=self.app.editing
        w,p=self.w['id'],self.p['id']
        self.app.save_editing_guidelines(p,'本产品普通剪辑的专用测试要求')
        ref=self.upload(self.intro,'reference')
        b=eng.create_uploaded(p,w,dict(reference_id=ref['id'],matching_mode='semantic',mode='preview',rights_allowed=True))
        beat=dict(purpose='展示',action='旋转',subject='产品',composition='近景')
        beats=[dict(beat,start=0,end=.1),dict(beat,start=.1,end=1)]
        proposal={'parts':[{'reference_beat':1,'shot_id':'unlisted','reason':'bad',
                            'alternatives':[{'shot_id':self.shot['id'],'reason':'清楚的产品封面'}]}],
                  'gaps':[{'reference_beat':2,'reason':'缺少独立实拍'}]}
        def audit(app,b,rows,paid,stop):
            return {span_key(x):{'verdict':'different_shoot'} for row in rows for x in row}
        with patch('workbench.reference_structure.analyze',return_value={'beats':beats}), patch('vision_api.call',return_value=proposal) as model, patch('workbench.reference.audit_choices',side_effect=audit), patch('workbench.reference.screen_sources',side_effect=lambda app,b,c:(c,[])):
            self.op(b,'plan')
            model.assert_called_once()
            self.assertNotIn('本产品普通剪辑的专用测试要求',model.call_args.args[1])
            self.assertNotIn('剪辑总纲必须遵守',model.call_args.args[1])
            t=self.task(b)
            self.assertEqual(t['status'],'planned',t.get('error'))
            self.assertEqual(t['plan']['parts'][0]['frames'],30)
            self.assertEqual(t['plan']['reference_gaps'],[])
            self.op(b,'preview')
            t=self.task(b)
            self.assertEqual(t['status'],'awaiting_review',t.get('error'))
            self.assertEqual(t['preview']['report']['body_seconds'],1)
            self.op(b,'output',dict(task_ids=[t['id']],content_confirmed=True,preview_sha256=t['preview']['sha256']))
            self.assertEqual(self.task(b)['output']['report']['body_seconds'],1)

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
        out=Path(t['output']['path']);self.assertTrue(out.is_file())
        self.assertEqual(out.name,f"{self.library.name}-{t['id'][:8]}.mp4")
        self.assertEqual(list(out.parent.iterdir()),[out])
        task_root=self.app.editing.folder(self.w['id'],b['id'])/t['id']
        preview=Path(t['preview']['path'])
        self.assertEqual(list(preview.parent.iterdir()),[preview])
        self.assertFalse(list(task_root.glob('render-*')))
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

    def test_preview_replacement_and_history_deletion_keep_only_committed_media(self):
        batch=self.create()
        p,w=self.p['id'],self.w['id']
        edit=self.app.editing
        with patch('vision_api.call',return_value=self.proposal()):self.op(batch,'plan')
        self.op(batch,'preview')
        first=self.task(batch)
        ident=first['id']+'-0'
        old=edit.media(p,w,ident)
        with patch('workbench.edit_media.render',side_effect=ValueError('encode failed')):
            self.op(batch,'preview')
        self.assertIn('encode failed',self.task(batch)['error'])
        self.assertEqual(edit.media(p,w,ident),old)

        self.op(batch,'preview')
        second=edit.media(p,w,ident)
        self.assertNotEqual(old,second)
        self.assertFalse(old.exists())
        edit.action(p,w,batch['id'],'save-plan',{'task_ids':[first['id']],'plan':self.proposal()})
        self.assertFalse(second.exists())
        self.op(batch,'preview')
        latest=self.task(batch)['preview']
        current=Path(latest['path'])
        other=current.with_name('user-note.txt')
        other.write_text('keep',encoding='utf-8')
        with patch.object(self.app.store,'put_many',side_effect=sqlite3.OperationalError('commit failed')):
            with self.assertRaises(sqlite3.OperationalError):
                edit.action(p,w,batch['id'],'delete-record',{'delete_previews':True})
        self.assertEqual(edit.media(p,w,ident),current)
        for _ in range(2):
            self.assertTrue(edit.action(p,w,batch['id'],'delete-record',{'delete_previews':True})['deleted'])
        self.assertFalse(current.exists())
        self.assertTrue(other.is_file())
        self.assertTrue((self.inputs/'1.mp4').is_file())
        self.assertEqual(edit.list(p,w),[])
        for media_id in (ident,first['id']+'-'+latest['sha256']+'-0'):
            with self.assertRaises(Problem) as error:edit.media(p,w,media_id)
            self.assertEqual(error.exception.status,404)

    def test_retired_preview_cleanup_resumes_after_a_file_lock(self):
        batch=self.create()
        t=self.task(batch)
        p,w=self.p['id'],self.w['id']
        edit=self.app.editing
        root=edit.folder(w,batch['id'])/t['id']
        old,current,changed=[root/('preview-'+letter*32)/'preview.mp4' for letter in 'abc']
        for path,source in ((old,self.clip),(current,self.intro),(changed,self.intro)):
            path.parent.mkdir(parents=True)
            shutil.copyfile(source,path)
        old_sha=fingerprint(old)
        new_sha=fingerprint(current)
        t.update(preview={'path':str(old),'sha256':old_sha},
                 pending_media={'kind':'preview','media':{'path':str(current),'sha256':new_sha}})
        with patch.object(Path,'unlink',side_effect=PermissionError('file in use')):
            edit.finish_publication(t)
        self.assertTrue(old.is_file())
        saved=self.task(batch)
        self.assertEqual(saved['retired_previews'],{str(old):old_sha})
        self.assertEqual(edit.media(p,w,t['id']+'-'+new_sha+'-0'),current)
        with self.assertRaises(Problem) as error:edit.media(p,w,t['id']+'-'+old_sha+'-0')
        self.assertEqual(error.exception.status,404)
        outside=self.inputs/'1.mp4'
        saved['retired_previews'].update({str(changed):old_sha,str(outside):new_sha,str(current):new_sha})
        self.app.store.put('edit_task',w,saved)
        self.app=Workbench(self.root/'state',executor=False)
        self.assertFalse(old.exists())
        for path in (current,changed,outside):self.assertTrue(path.is_file())
        self.assertNotIn('retired_previews',self.task(batch))
        self.app.editing.action(p,w,batch['id'],'delete-record',{})
        self.assertTrue(current.is_file())
        with self.assertRaises(Problem) as error:self.app.editing.media(p,w,t['id']+'-0')
        self.assertEqual(error.exception.status,404)

    def test_restart_recovers_published_movie_without_rendering_again(self):
        class ServiceStopped(BaseException):pass
        b=self.create(mode='direct')
        put=self.app.store.put
        def stop_before_completed_record(kind,scope,record):
            if kind=='edit_task' and record.get('status')=='completed':
                raise ServiceStopped()
            return put(kind,scope,record)
        with patch('vision_api.call',return_value=self.proposal()),patch.object(self.app.store,'put',side_effect=stop_before_completed_record):
            with self.assertRaises(ServiceStopped):self.op(b,'plan')
        files=list(Path(b['output_path']).rglob('*.mp4'))
        self.assertEqual(len(files),1)
        self.app=Workbench(self.root/'state',executor=False)
        t=self.task(b)
        self.assertEqual(t['status'],'completed')
        self.assertEqual(Path(t['output']['path']),files[0])
        self.assertEqual(t['output']['sha256'],fingerprint(files[0]))
        self.assertEqual(t['usage_sync']['errors'],[])
        from workbench.usage import ledger
        self.assertEqual(set(ledger(self.app.store)[self.asset['sha256']]),{t['id']})
        with patch('workbench.edit_media.render',side_effect=AssertionError('already rendered')):self.op(b,'resume')
        self.assertEqual(list(Path(b['output_path']).rglob('*.mp4')),files)

    def test_same_batch_manual_change_between_planning_and_save(self):
        edit=self.app.editing;p,w=self.p['id'],self.w['id']
        first=self.upload(self.audio,'narration');second=self.upload(self.audio,'narration')
        batch=edit.create(p,w,{'narrations':[{'id':first['id']},{'id':second['id']}],'rights_allowed':True})
        one,two=edit.tasks(w,batch['id'])
        alternative={'parts':[dict(self.proposal()['parts'][0],start=1)]}
        def planned_before_manual_save(b,t,*args,**kwargs):
            t['plan']=edit.validate_plan(b,t,self.proposal())
            t['plan_revision']='first-revision'
            edit.action(p,w,b['id'],'save-plan',{'task_ids':[two['id']],'plan':alternative})
            return t
        with patch.object(edit,'plan',side_effect=planned_before_manual_save),patch.object(edit,'timeline',return_value={'segments':[]}):
            self.op(batch,'plan',{'task_ids':[one['id']]})
        saved=self.app.store.get('edit_task',one['id'],w)
        self.assertEqual(saved['status'],'needs_attention')
        self.assertIn('本批素材不能重复',saved['error'])
        self.assertNotIn('plan',saved)
        self.assertEqual(self.app.store.get('edit_task',two['id'],w)['plan']['parts'][0]['start'],1)

    def test_candidate_order_survives_out_of_order_updates(self):
        p,w=self.p['id'],self.w['id'];edit=self.app.editing
        voice=self.upload(self.audio,'narration')
        batch=edit.create(p,w,{'narrations':[{'id':voice['id']}],'variant_count':5})
        tasks=edit.tasks(w,batch['id'])
        for task in reversed(tasks):self.app.store.put('edit_task',w,dict(task,status='planned'))
        for rows in (edit.tasks(w,batch['id']),edit.list(p,w)[0]['tasks']):
            self.assertEqual([task['variant'] for task in rows],list(range(1,6)))

    def test_restart_checks_staged_preview_contents_before_recovering(self):
        b=self.create();w=self.w['id'];edit=self.app.editing
        for valid in (True,False):
            task=self.task(b)
            final=edit.folder(w,b['id'])/task['id']/('preview-'+str(valid))/'preview.mp4'
            final.parent.mkdir(parents=True)
            staged=final.with_name('.rendering.tmp')
            shutil.copyfile(self.clip,staged)
            media={'path':str(final),'sha256':fingerprint(staged),'report':{},'plan_revision':'rev'}
            if not valid:staged.write_bytes(b'incomplete')
            task.update(status='running',plan_revision='rev',pending_media={'kind':'preview','media':media})
            self.app.store.put('edit_task',w,task)
            self.app=Workbench(self.root/'state',executor=False)
            recovered=self.task(b)
            self.assertNotIn('pending_media',recovered)
            if valid:
                self.assertEqual(recovered['status'],'awaiting_review')
                self.assertEqual(fingerprint(final),media['sha256'])
            else:
                self.assertEqual(recovered['status'],'interrupted')
                self.assertFalse(final.exists())
                self.assertFalse(staged.exists())

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
        with patch.object(self.app.editing,'candidates',return_value=original+[other]),patch('vision_api.call',side_effect=AssertionError('no model')),patch.object(self.app.editing,'history',wraps=self.app.editing.history) as history:
            planned=self.app.editing.plan(second,task,False)
        self.assertEqual(history.call_count,2)  # Search snapshot and fresh final validation.
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

    def test_preview_zoom_with_odd_intermediate_width(self):
        from workbench.edit_media import render
        _,report=render(None,self.audio,[dict(path=self.clip,start=0,frames=60,zoom=1.025)],
                        self.root/'zoom-preview',preview=True)
        self.assertEqual((report['width'],report['height'],report['duration']),(360,640,2))
        self.assertTrue(report['decode_checked'])

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

    def test_changed_subtitles_and_bound_timestamps_supersede_cached_timeline(self):
        b=self.create();task=self.task(b)
        def timeline():return self.app.editing.timeline(b,task)
        self.assertEqual(timeline()['source'],'import')
        (self.inputs/'1.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nUpdated.\n',encoding='utf-8')
        self.assertEqual(timeline()['segments'][0]['text'],'Updated.')
        segments=[{'start':0,'end':1.5,'text':'Aligned.'}]
        source=self.inputs/'1.timing.json'
        save(source,segments)
        self.assertEqual(timeline()['segments'],segments)
        bound={'source':'elevenlabs_timestamps','audio_sha256':task['audio_sha256'],'segments':segments}
        save(source,bound)
        self.assertEqual(timeline()['source'],'elevenlabs_timestamps')
        save(source,dict(bound,audio_sha256='different-audio'))
        with self.assertRaisesRegex(ValueError,'其他音频'):timeline()
        source.unlink();(self.inputs/'1.srt').unlink()
        self.assertEqual(timeline()['source'],'elevenlabs_timestamps')

    def test_discarded_sibling_revisions_do_not_block_a_new_plan(self):
        batch=self.create();task=self.task(batch)
        task['revision_root']='shared-root'
        prior_batch=self.create();prior=self.task(prior_batch)
        prior.update(revision_root='shared-root',status='planned',
                     plan=self.app.editing.validate_plan(prior_batch,prior,self.proposal()))
        self.app.store.put('edit_task',self.w['id'],prior)
        parts=prior['plan']['parts']
        def compare():return self.app.editing.duplicate_check(task,parts)
        with self.assertRaisesRegex(ValueError,'完全重复'):compare()
        prior['status']='cancelled';self.app.store.put('edit_task',self.w['id'],prior)
        self.assertEqual(compare()['matches'],[])
        prior['status']='planned';self.app.store.put('edit_task',self.w['id'],prior)
        self.app.editing.action(self.p['id'],self.w['id'],prior_batch['id'],'delete-record',{})
        self.assertEqual(compare()['matches'],[])
        task['regenerated_from']=prior['id']
        with self.assertRaisesRegex(ValueError,'60%'):compare()

    def test_new_sentence_timing_requires_a_new_plan_and_preview(self):
        batch=self.create()
        with patch('vision_api.call',return_value=self.proposal()):self.op(batch,'plan')
        self.op(batch,'preview')
        task=self.task(batch)
        path=Path(task['preview']['path'])
        task['human_reviewed']=True
        self.app.store.put('edit_task',self.w['id'],task)
        self.op(batch,'timing')
        self.assertEqual(self.task(batch)['preview'],task['preview'])
        self.assertTrue(path.is_file())
        (self.inputs/'1.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nNew cut.\n',encoding='utf-8')
        self.op(batch,'timing')
        revised=self.task(batch)
        self.assertEqual(revised['status'],'timing_ready')
        self.assertEqual(revised['timeline']['segments'][0]['text'],'New cut.')
        self.assertNotIn('preview',revised)
        self.assertFalse(path.exists())
        self.assertNotIn('plan',revised)
        self.assertFalse(revised['human_reviewed'])
        self.assertEqual(revised['plan_history'][-1]['plan'],task['plan'])
    def test_manual_plan_uses_real_timeline_and_invalidates_preview(self):
        b=self.create();t=self.task(b)
        result=self.app.editing.action(self.p['id'],self.w['id'],b['id'],'save-plan',{'task_ids':[t['id']],'plan':self.proposal()})
        self.assertEqual(result['timeline']['audio_sha256'],t['audio_sha256']);self.assertEqual(result['status'],'planned')
        result['preview']={'sha256':'old','plan_revision':result['plan_revision']};self.app.store.put('edit_task',self.w['id'],result)
        revised=self.app.editing.action(self.p['id'],self.w['id'],b['id'],'save-plan',{'task_ids':[t['id']],'plan':self.proposal()})
        self.assertNotEqual(result['plan_revision'],revised['plan_revision']);self.assertNotIn('preview',revised)
    def test_reviewed_preview_stays_bound_to_prepared_footage_after_same_name_replacement(self):
        p,w=self.p['id'],self.w['id'];edit=self.app.editing
        # Isolate same-name replacement: both versions of the only source and the narration last three seconds.
        (self.library/self.short_clips[15].name).unlink()
        self.app.scan(p,w)
        run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','sine=frequency=880:duration=3',
             '-f','wav',self.inputs/'1.mp3'])
        (self.inputs/'1.srt').write_text('1\n00:00:00,000 --> 00:00:03,000\nShow the red toy.\n',encoding='utf-8')
        pairs={'input_path':str(self.inputs),'input_mode':'paired','rights_allowed':True}
        pairs['pairing_snapshot']=edit.inspect_pairs(p,w,pairs)['snapshot']
        batch=edit.create(p,w,pairs);bid=batch['id']
        self.op(batch,'plan');self.op(batch,'preview')
        task=self.task(batch)
        self.assertEqual(task['status'],'awaiting_review',task.get('error'))
        part=task['plan']['parts'][0];path=self.library/part['source_name']
        self.assertEqual(part['shot_id'],part['asset_id'])
        confirm={'task_ids':[task['id']],'content_confirmed':True,'preview_sha256':task['preview']['sha256'],
                 'plan_revision':task['plan_revision']}
        with self.assertRaises(Problem):edit.action(p,w,bid,'output',dict(confirm,plan_revision='older-revision'))
        self.app.scan(p,w)
        self.assertNotIn('source_warning',edit.list(p,w)[0]['tasks'][0])
        edit.action(p,w,bid,'output',confirm)
        run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=blue:s=90x160:r=30:d=3','-c:v','libx264',path])
        self.app.scan(p,w)
        asset=self.app.store.get('asset',part['asset_id'],w)
        self.app.store.put('product','root',dict(self.app.product(p),shot_categories=['主体展示']))
        self.app.confirm_asset_category(p,w,asset['id'],['主体展示'],expected_sha=asset['sha256'])
        self.assertNotEqual(part['asset_sha256'],asset['sha256'])
        edit.run(p,w,bid,[task['id']],'output')
        stopped=self.task(batch)
        self.assertEqual(stopped['status'],'needs_attention')
        self.assertIn(path.name,stopped['error'])
        self.assertEqual(stopped['plan'],task['plan'])
        self.assertNotIn('output',stopped)
        self.assertTrue(Path(stopped['preview']['path']).is_file())
        self.assertIn(path.name,edit.list(p,w)[0]['tasks'][0]['source_warning'])
        with self.assertRaisesRegex(Problem,path.name):edit.action(p,w,bid,'output',confirm)
        retry=edit.action(p,w,bid,'regenerate',{'task_ids':[task['id']]})
        edit.run(p,w,retry['id'],[retry['task_id']],'plan')
        new=self.app.store.get('edit_task',retry['task_id'],w)
        self.assertEqual(new['status'],'awaiting_review',new.get('error'))
        self.assertEqual(new['plan']['parts'][0]['asset_sha256'],asset['sha256'])
        self.op(edit.batch(p,w,retry['id']),'output',{'content_confirmed':True,'preview_sha256':new['preview']['sha256']})
        self.assertEqual(self.app.store.get('edit_task',new['id'],w)['status'],'completed')
        shutil.copyfile(self.clip,path)
        self.app.scan(p,w)
        self.assertFalse(any(t.get('source_warning') for b in edit.list(p,w) for t in b['tasks']))

    def test_renderer_checks_saved_source_after_selection_before_encoding(self):
        from workbench.edit_media import render
        batch=self.create(mode='direct')
        def replace_before_encoding(*args,**kwargs):
            part=args[2][0]
            shutil.copyfile(self.intro,part['path'])
            with patch('workbench.edit_media.run',side_effect=AssertionError('changed source reached encoder')):
                return render(*args,**kwargs)
        with patch('vision_api.call',return_value=self.proposal()),patch('workbench.edit_media.render',side_effect=replace_before_encoding):
            self.op(batch,'plan')
        task=self.task(batch)
        self.assertEqual(task['status'],'needs_attention')
        self.assertIn('与剪辑方案中的版本不一致',task['error'])
        self.assertNotIn('output',task)
        self.assertFalse(list(Path(batch['output_path']).rglob('*.mp4')))

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
