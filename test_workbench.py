"""Real media/account isolation tests. Model calls are mocked; no paid calls."""
import base64, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'.workbench-deps'))
from workbench.backend import Workbench, Problem, validate_reference_url
from workbench.server import make_server

class WorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.video=Path(cls.media.name)/'clip.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=90x160:r=30:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(cls.video)],check=True)
    @classmethod
    def tearDownClass(cls):cls.media.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.app=Workbench(self.root/'state',executor=False)
        self.p=self.app.create_product('产品');self.w=self.app.create_workspace(self.p['id'],'相同账号名称');self.b=self.app.create_workspace(self.p['id'],'相同账号名称')
        self.a_dir=self.root/'A';self.a_dir.mkdir();shutil.copy2(self.video,self.a_dir/'same.mp4')
        self.b_dir=self.root/'B';self.b_dir.mkdir();shutil.copy2(self.video,self.b_dir/'same.mp4')
    def tearDown(self):self.tmp.cleanup()
    def attach(self,w=None,kind='raw',path=None):
        w=w or self.w;path=path or self.a_dir
        self.app.attach_library(self.p['id'],w['id'],str(path),kind);self.app.scan(self.p['id'],w['id'])
        return self.app.store.all('asset',w['id'])[0]
    def test_account_isolation_identical_names_and_hashes(self):
        a=self.attach();b=self.attach(self.b,path=self.b_dir)
        self.assertEqual(a['sha256'],b['sha256']);self.assertNotEqual(a['id'],b['id'])
        self.assertTrue((self.app.wroot(self.w['id'])/'index.sqlite').exists())
        with self.assertRaises(Problem):self.app.store.get('asset',a['id'],self.b['id'])
        with self.assertRaises(Problem):self.app.media(self.p['id'],self.b['id'],'asset',a['id'],self.app.media_signature(self.p['id'],self.b['id'],'asset',a['id']))
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.b['id'],['nonexistent'])

    def test_sort_original_review_publish_and_isolate(self):
        from workbench.material_sorting import start,review
        p,w=self.p['id'],self.w['id']
        asset=self.attach()
        data=dict(asset_id=asset['id'],allow_paid=True)
        response=dict(segments=[dict(start=.2,end=1.6,labels=[],evidence='静态展示',
                                     continues_before=False,continues_after=False)])
        with patch('vision_api.call',return_value=response):
            # Exercise the actual interval publisher independently of Hypit installation.
            with patch('workbench.material_sorting.detect',return_value=[
                    dict(id='candidate',status='pending',reason='静态展示',start=.2,end=1.6,labels=[])]):
                job=start(self.app,p,w,data)
        change=dict(decision='confirm',segment_id='candidate',start=.3,end=1.5,labels=[])
        with self.assertRaises(Problem):review(self.app,p,self.b['id'],job['id'],change)
        result=review(self.app,p,w,job['id'],change)
        self.assertEqual(result['segments'][0]['status'],'confirmed')
        review(self.app,p,w,job['id'],change)
        clips=[a for a in self.app.visible_assets(w) if a['kind']=='prepared']
        self.assertEqual(len(clips),1)
        self.assertAlmostEqual(clips[0]['duration'],1.2,places=2)
        self.app.scan(p,w)
        for prepared in (True,False):
            candidate,=self.app.editing.candidates(p,w,use_prepared_files=prepared)
            self.assertEqual(candidate['origin_sha256'],asset['sha256'])
        with self.assertRaisesRegex(ValueError,'本批素材'):
            self.app.editing.check_batch_sources(dict(variant_count=2,rules={}),
                dict(id='two',batch_id='batch'),[candidate],
                [dict(id='one',batch_id='batch',status='completed',plan=dict(parts=[
                    dict(asset_sha256='different',origin_sha256=asset['sha256'])]))])

    def test_four_sword_light_out_is_confined_to_rotating_interval(self):
        from product_display import four_sword_fault
        from workbench.material_sorting import review
        for label in ('单把光剑旋转','静态展示','拆分光剑','展示不同灯效'):
            self.assertFalse(four_sword_fault([label],True,{}))
        self.assertFalse(four_sword_fault(['四把光剑旋转'],False,{}))
        self.assertTrue(four_sword_fault(['四把合体光剑旋转'],True,{}))
        p,w=self.p['id'],self.w['id']
        a=self.attach()
        fault=dict(id='fault',start=0,end=.8,status='fault',reason='一支熄灯',labels=['四把光剑旋转'])
        j=self.app.store.put('sorting',w,dict(asset_id=a['id'],sha256=a['sha256'],status='ready',segments=[fault]))
        with self.assertRaisesRegex(Problem,'熄灯故障'):
            review(self.app,p,w,j['id'],dict(decision='confirm',start=.6,end=2,labels=[]))
        result=review(self.app,p,w,j['id'],dict(decision='confirm',start=.8,end=2,labels=[]))
        self.assertEqual(result['segments'][-1]['status'],'confirmed')

    def test_sort_skips_subsecond_intervals(self):
        from workbench.material_sorting import split_pending,review
        p,w=self.p['id'],self.w['id']
        asset=self.attach()
        row=dict(id='short',status='pending',start=0,end=.999,labels=[],reason='静态展示')
        exact=dict(row,id='exact',end=1)
        self.assertEqual(split_pending([row,exact],asset['sha256']),[exact])
        job=self.app.store.put('sorting',w,dict(asset_id=asset['id'],workspace_id=w,
                               sha256=asset['sha256'],segments=[row,exact],status='ready'))
        with patch.object(self.app,'export_shots') as encode:
            for sid in ('short',None):
                result=review(self.app,p,w,job['id'],dict(decision='confirm',segment_id=sid,start=0,end=.9))
                self.assertTrue(result['skipped_short'])
            encode.assert_not_called()
        change=dict(decision='confirm',segment_id='exact',start=0,end=1,labels=[])
        with patch('workbench.material_sorting.media_duration',return_value=.99):
            self.assertTrue(review(self.app,p,w,job['id'],change)['skipped_short'])
        self.assertFalse(any(a['kind']=='prepared' for a in self.app.visible_assets(w)))
        result=review(self.app,p,w,job['id'],dict(change,segment_id=None))
        self.assertEqual(result['segments'][-1]['status'],'confirmed')

    def test_sort_long_action_across_windows(self):
        from workbench.material_sorting import detect,review,split_pending
        p,w=self.p['id'],self.w['id']
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'color=red:s=90x160:r=30000/1001:d=30','-c:v','libx264',
                        str(self.a_dir/'same.mp4')],check=True)
        asset=self.attach()
        def tiles(args,cwd,timeout):
            if args[2]=='probe':return '{"frameRate":29.97,"duration":29.123367}'
            folder=Path(cwd)/args[-1]
            folder.mkdir()
            (folder/'tile.jpg').touch()
        def window(start,end,before,after):
            return dict(segments=[dict(start=start,end=end,continues_before=before,continues_after=after,
                        labels=['旋转'],evidence='连续旋转')])
        with patch('workbench.material_sorting._hypit_command',return_value='hypit'), \
             patch('workbench.material_sorting._run',side_effect=tiles), \
             patch('vision_api.call',side_effect=[window(20,24,False,True),window(24,29.1234,True,False)]):
            rows=detect(self.app,w,asset,self.app.product(p))
        def bounds(rows):
            return [(r['start'],r['end']) for r in rows]
        def check_ranges(pieces,start,end):
            ranges=bounds(pieces)
            self.assertEqual((ranges[0][0],ranges[-1][1]),(start,end))
            self.assertEqual([b for a,b in ranges[:-1]],[a for a,b in ranges[1:]])
            self.assertEqual(len({r['id'] for r in pieces}),len(pieces))
            self.assertTrue(all(1.49999999<=b-a<=4 for a,b in ranges))
        check_ranges(rows,20,29.123367)
        self.assertTrue(all(r['labels']==['旋转'] for r in rows))
        for length in (3,4,4.01,8,8.01,60):
            original=[dict(rows[0],start=0,end=length)]
            pieces=split_pending(original,'source-one')
            check_ranges(pieces,0,length)
            if length<=4:self.assertEqual(pieces,original)
            else:
                self.assertEqual(bounds(pieces),bounds(split_pending(original,'source-one')))
                self.assertNotEqual(bounds(pieces),bounds(split_pending(original,'source-two')))
                self.assertGreater(len({round(b-a,3) for a,b in bounds(pieces)}),1)
        job=self.app.store.put('sorting',w,dict(asset_id=asset['id'],workspace_id=w,
                               sha256=asset['sha256'],segments=rows,status='ready'))
        change=dict(decision='confirm',start=0,end=8,labels=['旋转'])
        for attempt in range(2):
            job=review(self.app,p,w,job['id'],change)
            if attempt==0:saved=job['segments']
            else:self.assertEqual(job['segments'],saved)
        check_ranges(saved[len(rows):],0,8)
        row=saved[len(rows)]
        review(self.app,p,w,job['id'],dict(change,segment_id=row['id'],end=row['end']))
        clip,=[a for a in self.app.visible_assets(w) if a['kind']=='prepared']
        self.assertLessEqual(clip['duration'],4)
        self.assertAlmostEqual(clip['duration'],row['end']-row['start'],delta=.04)

    def test_new_sword_scan_suggests_once_and_preserves_review(self):
        from workbench.sword_recognition import run
        app=self.app;p=self.p['id'];w=self.w['id']
        old=self.attach()
        app.update_product(p,dict(name='lightplay'))
        shutil.copy2(self.video,self.a_dir/'new.mp4')
        (self.a_dir/'broken.mp4').write_bytes(b'invalid')
        with patch.object(app,'queue_sword') as queue:
            app.scan(p,w);app.scan(p,w)
            queue.assert_called_once()
        self.assertNotIn('sword_recognition',app.store.get('asset',old['id'],w))
        a=queue.call_args.args[2]
        self.assertIn('broken.mp4',app.workspace(p,w)['sword_scan_errors'][0]['file'])
        suggestion=dict(labels=['单把光剑旋转'],ranges=[dict(label='单把光剑旋转',start=0,end=1)],
                        status='suggested',reason='剑身绕指孔转动')
        with patch('workbench.sword_recognition.recognize',return_value=suggestion) as classify:
            run(app,p,w,a['id'],a['sha256']);run(app,p,w,a['id'],a['sha256'])
            classify.assert_called_once()
        current=app.store.get('asset',a['id'],w)
        self.assertFalse(current['category_review']['confirmed'])
        self.assertEqual(current['category_review']['labels'],suggestion['labels'])
        app.confirm_asset_category(p,w,a['id'],suggestion['labels'])
        self.assertEqual(app.store.get('asset',a['id'],w)['sword_recognition']['status'],'reviewed')

    def test_sword_failure_and_manual_edit_during_recognition(self):
        from workbench.sword_recognition import run
        app=self.app;p=self.p['id'];w=self.w['id'];app.update_product(p,dict(name='toy'))
        owner=app.create_product('lightplay')
        owner['profile']={'understood_at':'today'}
        app.store.put('product','root',owner)
        app.reference_knowledge(p,[owner['id']])
        a=self.attach()
        with patch('workbench.sword_recognition.recognize',side_effect=RuntimeError('Hypit 取帧失败')):
            run(app,p,w,a['id'],a['sha256'])
        current=app.store.get('asset',a['id'],w)
        self.assertEqual(current['sword_recognition']['status'],'unrecognized')
        self.assertIn('取帧失败',current['sword_recognition']['reason'])
        current['sword_recognition']={'status':'queued'};app.store.put('asset',w,current)
        def human(*args):
            app.confirm_asset_category(p,w,a['id'],['单把光剑旋转'])
            raise ValueError('识别中断')
        with patch('workbench.sword_recognition.recognize',side_effect=human):run(app,p,w,a['id'],a['sha256'])
        self.assertEqual(app.store.get('asset',a['id'],w)['sword_recognition']['status'],'reviewed')

    def test_product_rename_preserves_shared_editing_rules_and_refreshes_builtin_template(self):
        app=self.app
        owner=app.create_product('lightplay')
        owner['profile']={'understood_at':'today'}
        app.store.put('product','root',owner)
        alias=app.create_product('Shop B')['id']
        app.reference_knowledge(alias,[owner['id']])
        app.save_editing_guidelines(alias,'同一种展示最多连续三镜')
        for pid in (alias,owner['id']):
            app.update_product(pid,{'name':'Renamed '+pid[:4]})
        for pid in (alias,owner['id']):
            self.assertTrue(app.editing.light_sword_rhythm({'product_id':pid}))
            self.assertTrue(app.product(pid)['recognition_template_ready'])
            self.assertEqual(app.product(pid)['editing_guidelines'],'同一种展示最多连续三镜')
        vivi=app.create_product('meetokivivi')['id']
        # Simulate an older version that persisted a generated baseline during a metadata edit.
        app.store.put('product','root',app.product(vivi))
        app.update_product(vivi,{'name':'Vivi 新名称'})
        self.assertTrue(app.product(vivi)['sentence_editing_only'])
        self.assertTrue(app.product(vivi)['recognition_template_ready'])

    def test_removed_category_stays_in_history_but_not_new_plans(self):
        a=self.attach(kind='prepared');p,w=self.p['id'],self.w['id']
        self.app.update_product(p,{'name':'lightplay'})
        self.app.save_shot_categories(p,'旋转\n静态')
        self.app.confirm_asset_category(p,w,a['id'],['旋转','静态'])
        self.app.rename_shot_category(p,'旋转','转动')
        self.app.save_shot_categories(p,'转动')
        row,=self.app.editing.candidates(p,w,use_prepared_files=True)
        self.assertEqual(row['confirmed_categories'],['转动'])
        self.assertEqual(self.app.store.get('asset',a['id'],w)['user_category']['labels'],['旋转','静态'])
        self.app.save_shot_categories(p,'转动\n旋转')
        row,=self.app.editing.candidates(p,w,use_prepared_files=True)
        self.assertEqual(row['confirmed_categories'],['转动'])
        self.app.confirm_asset_category(p,w,a['id'],['旋转'])
        row,=self.app.editing.candidates(p,w,use_prepared_files=True)
        self.assertEqual(row['confirmed_categories'],['旋转'])

    def test_migration_is_atomic_and_separates_legacy_product_records(self):
        old={'products':[{'id':'a','name':'A'},{'id':'b','name':'B'}],
             'tasks':[{'id':'tb','productId':'b'}],
             'exports':[{'name':'unknown'},{'name':'A','productId':'a'},{'name':'B','taskId':'tb'}]}
        app=self.app
        with app.store.db() as db:
            db.execute("""CREATE TRIGGER fail_import BEFORE INSERT ON objects WHEN new.kind='migration'
                          BEGIN SELECT RAISE(ABORT,'migration failed'); END""")
        with self.assertRaises(sqlite3.IntegrityError):app.migrate(old)
        self.assertEqual(app.store.all('product','root'),[self.p])
        with app.store.db() as db:db.execute('DROP TRIGGER fail_import')
        created=app.migrate(old)['products']
        self.assertTrue(app.migrate(old)['already_imported'])
        def exports(app):
            return [[e['name'] for e in app.store.all('workspace',pid)[0]['legacy_snapshot']['exports']] for pid in created]
        self.assertEqual(exports(app),[['A'],['B']])
        record,=app.store.all('migration','root')
        self.assertEqual(record['snapshot'],old)
        # Previously imported copies are corrected from the original backup at startup.
        record.pop('scoped_snapshots');app.store.put('migration','root',record)
        for pid in created:
            ws,=app.store.all('workspace',pid);ws['legacy_snapshot']['exports']=old['exports']
            app.store.put('workspace',pid,ws)
        self.assertEqual(exports(Workbench(app.root,executor=False)),[['A'],['B']])

    def test_rejected_knowledge_job_is_resumable(self):
        from concurrent.futures import ThreadPoolExecutor
        p=self.p['id']
        with ThreadPoolExecutor() as stopped:pass
        with patch.object(self.app,'pool',stopped),patch('shutil.which',return_value='codex'):
            job=self.app.create_job(p,None,'understand',True)
            self.assertEqual(job['status'],'interrupted')
            self.assertEqual(self.app.resume(p,None,job['id'],True)['status'],'interrupted')
        with patch('shutil.which',return_value='codex'):
            self.assertEqual(self.app.resume(p,None,job['id'],True)['status'],'queued')
    def test_folder_parent_child_symlink_and_hardlink_rejected(self):
        self.attach()
        for path in [self.a_dir,self.root,self.a_dir/'sub']:
            path.mkdir(exist_ok=True)
            with self.assertRaises(Problem):self.app.attach_library(self.p['id'],self.b['id'],str(path),'raw')
        alias=self.root/'alias'
        try:alias.symlink_to(self.a_dir,target_is_directory=True)
        except OSError as exc:
            if getattr(exc,'winerror',None)==1314:self.skipTest('Windows symbolic-link privilege unavailable')
            raise
        with self.assertRaises(Problem):self.app.attach_library(self.p['id'],self.b['id'],str(alias),'raw')
        os.link(self.a_dir/'same.mp4',self.b_dir/'hardlink.mp4')
        self.app.attach_library(self.p['id'],self.b['id'],str(self.b_dir),'raw');scan=self.app.scan(self.p['id'],self.b['id'])
        self.assertEqual(len(scan['errors']),1);self.assertEqual(scan['count'],1)
    def test_incremental_missing_version_and_symlink_escape(self):
        a=self.attach();self.app.scan(self.p['id'],self.w['id']);self.assertEqual(len(self.app.store.all('asset',self.w['id'])),1)
        self.app.store.put('shot',self.w['id'],{'asset_id':a['id'],'stale':False})
        (self.a_dir/'same.mp4').unlink();self.app.scan(self.p['id'],self.w['id']);self.assertFalse(self.app.store.get('asset',a['id'],self.w['id'])['available'])
        try:(self.a_dir/'escape.mp4').symlink_to(self.b_dir/'same.mp4')
        except OSError as exc:
            if getattr(exc,'winerror',None)==1314:self.skipTest('Windows symbolic-link privilege unavailable')
            raise
        scan=self.app.scan(self.p['id'],self.w['id']);self.assertTrue(scan['errors'])
        shutil.copy2(self.video,self.a_dir/'same.mp4');self.app.scan(self.p['id'],self.w['id']);self.assertTrue(self.app.store.all('shot',self.w['id'])[0]['stale'])
    def test_default_codex_and_local_env_loader(self):
        from workbench.server import load_local_env
        self.assertEqual(self.app.config()['model'],'gpt-6-luna')
        self.assertEqual(self.app.config()['provider'],'codex')
        env=self.root/'local-env';env.write_text('DEEPSEEK_API_KEY="local-test"\nHOME=/bad\nVISION_API_KEY=$(touch bad)\n')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'existing-test'}):
            home=os.environ.get('HOME');load_local_env(env)
            self.assertEqual(os.environ['DEEPSEEK_API_KEY'],'existing-test')
            self.assertEqual(os.environ.get('HOME'),home)
            self.assertEqual(os.environ['VISION_API_KEY'],'$(touch bad)')
        with self.assertRaises(Problem):self.app.set_config({'base_url':'https://api.deepseek.com','model':'deepseek-reasoner'})

    def test_returning_identical_file_preserves_review_but_replacement_requires_new_confirmation(self):
        a=self.attach(kind='prepared');p,w=self.p['id'],self.w['id']
        product=self.app.store.get('product',p,'root')
        self.app.store.put('product','root',dict(product,shot_categories=['展示']))
        self.app.confirm_asset_category(p,w,a['id'],['展示'])
        shot=self.app.store.put('shot',w,{'asset_id':a['id'],'asset_sha256':a['sha256'],'human_confirmed':True})
        file=Path(a['path']);file.unlink();self.app.scan(p,w)
        shutil.copyfile(self.video,file)
        restored=self.app.scan(p,w)['assets'][0]
        self.assertTrue(restored['user_category']['confirmed'])
        self.assertEqual(restored['version'],a['version'])
        self.assertFalse(self.app.store.get('shot',shot['id'],w).get('stale'))
        with file.open('ab') as stream:stream.write(b'new version')
        replaced=self.app.scan(p,w)['assets'][0]
        self.assertNotIn('user_category',replaced)
        self.assertTrue(self.app.store.get('shot',shot['id'],w)['stale'])
        with self.assertRaisesRegex(Problem,'版本已变化'):
            self.app.confirm_asset_category(p,w,a['id'],['展示'],expected_sha=a['sha256'])
        self.app.confirm_asset_category(p,w,a['id'],['展示'],expected_sha=replaced['sha256'])

    def test_scan_reads_catalog_once_and_rejects_cross_account_hardlinks(self):
        self.attach(self.b,path=self.b_dir)
        os.link(self.b_dir/'same.mp4',self.a_dir/'other-account.mp4')
        self.app.attach_library(self.p['id'],self.w['id'],str(self.a_dir),'prepared')
        for number in range(4):
            shutil.copyfile(self.video,self.a_dir/f'{number}.mp4')
        with patch.object(self.app.store,'all',wraps=self.app.store.all) as calls:
            result=self.app.scan(self.p['id'],self.w['id'])
        self.assertEqual(result['count'],5)
        self.assertEqual(len(result['errors']),1)
        self.assertIn('另一账号',result['errors'][0]['error'])
        self.assertEqual(sum(c.args[0]=='asset' for c in calls.call_args_list),1)

    def test_machine_recognition_paused_by_default(self):
        with self.assertRaisesRegex(Problem,'素材机器识别已暂停'):
            self.app.create_job(self.p['id'],self.w['id'],'organize',True)
        self.assertEqual(self.app.store.all('job',self.w['id']),[])

    @patch.object(Workbench,'asset_recognition_enabled',True)
    def test_analysis_modes_and_explicit_reanalysis_are_preserved(self):
        self.attach()
        simple=self.app.create_job(self.p['id'],self.w['id'],'organize',False,analysis_mode='simple')
        self.p['recognition_template']={'id':'test','confirmed':True}
        from workbench.product_template import signature
        self.p['recognition_template']['source_signature']=signature(self.p)
        self.app.store.put('product','root',self.p)
        standard=self.app.create_job(self.p['id'],self.w['id'],'organize',False,analysis_mode='standard',force=True)
        self.assertNotEqual(simple['id'],standard['id'])
        self.assertEqual(simple['analysis_mode'],'simple')
        self.assertTrue(standard['force_reanalysis'])
        self.assertEqual(self.app.store.get('job',simple['id'],self.w['id'])['analysis_mode'],'simple')
        self.assertEqual(self.app.product(self.p['id'])['analysis_mode'],'standard')
        with self.assertRaises(Problem):self.app.create_job(self.p['id'],self.w['id'],'organize',False,analysis_mode='invalid')

    @patch.object(Workbench,'asset_recognition_enabled',True)
    def test_no_config_does_not_call_model_or_fake_completion(self):
        self.attach()
        self.app.set_config({'provider':'codex','model':'gpt-6-luna'})
        with patch('workbench.backend.shutil.which',return_value=None):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True)
        self.assertEqual(j['status'],'requires_configuration');self.assertEqual(j['progress'],0)
        with patch('workbench.backend.shutil.which',return_value=None),self.assertRaises(Problem):self.app.resume(self.p['id'],self.w['id'],j['id'],True)
    def test_restart_and_migration_stay_unassigned(self):
        old={'products':[{'id':'old','name':'旧产品','sources':[{'name':'x.mp4'}],'shots':[{'id':'s','decision':'keep'}]}],'tasks':[{'productId':'old','name':'旧任务'}],'exports':[]}
        imported=self.app.migrate(old);self.assertFalse(imported['already_imported']);self.assertTrue(self.app.migrate(old)['already_imported'])
        p=imported['products'][0];w=self.app.store.all('workspace',p)[0];self.assertFalse(w['assigned']);self.assertEqual(w['legacy_snapshot']['shots'][0]['decision'],'keep')
        with self.assertRaises(Problem):self.app.create_job(p,w['id'],'organize',True)
        with self.assertRaises(Problem):self.app.export(p,w['id'],['s'])
        job=self.app.store.put('job',self.w['id'],{'scope':self.w['id'],'status':'running','done':['checkpoint'],'kind':'organize'})
        restored=Workbench(self.root/'state',executor=False);self.assertEqual(restored.store.get('job',job['id'],self.w['id'])['status'],'interrupted');self.assertEqual(restored.store.get('job',job['id'],self.w['id'])['done'],['checkpoint'])
    def test_pdf_pages_and_bad_link(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject,NameObject,DictionaryObject
        writer=PdfWriter()
        for i in range(2):
            page=writer.add_blank_page(width=300,height=200);stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 20 60 Td (Product page {i+1}) Tj ET'.encode())
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})});page[NameObject('/Contents')]=writer._add_object(stream)
        out=io.BytesIO();writer.write(out)
        s=self.app.add_source(self.p['id'],{'name':'guide.pdf','data':base64.b64encode(out.getvalue()).decode()})
        self.assertEqual(len(s['pages']),2);self.assertIn('Product page 2',s['pages'][1]['text'])
        with patch('workbench.backend.fetch_reference',side_effect=Problem('网页被拦截')):
            s=self.app.add_source(self.p['id'],{'url':'https://www.amazon.com/item'});self.assertEqual(s['status'],'failed');self.assertIn('拦截',s['error'])
    def test_image_reference_and_source_bound_product_understanding(self):
        image=self.root/'image.jpg'
        subprocess.run(['ffmpeg','-v','error','-i',str(self.video),'-frames:v','1','-y',str(image)],check=True)
        source=self.app.add_source(self.p['id'],{'name':'product.jpg','data':base64.b64encode(image.read_bytes()).decode()})
        self.assertEqual(source['status'],'awaiting_understanding');self.assertTrue(Path(source['image']).is_file())
        answer={'suggested_name':'红色产品','appearance':['红色'],'claims':[{'text':'包装声称发光','source_id':source['id'],'page':None}],'demonstrations':['展示颜色'],'unknowns':['型号未知'],'conflicts':[],'references':[source['id']]}
        with patch('vision_api.call',return_value=answer):profile=self.app.understand(self.p['id'],True)
        self.assertEqual(profile['sources'][0]['id'],source['id']);self.assertEqual(self.app.store.get('source',source['id'],self.p['id'])['status'],'understood')
        self.app.store.put('source',self.p['id'],{'kind':'link','name':'new reference','text':'new information','status':'awaiting_understanding'})
        self.assertFalse({'claims','unknowns','conflicts'}.intersection(profile))
        answer=dict(answer,references=[{'source_id':'missing'}])
        with patch('vision_api.call',return_value=answer),self.assertRaises(Problem):self.app.understand(self.p['id'],True)

    @patch.object(Workbench,'asset_recognition_enabled',True)
    def test_public_reference_text_and_no_paid_consent(self):
        from email.message import Message
        from workbench.backend import fetch_reference
        headers=Message();headers['Content-Type']='text/html; charset=utf-8'
        response=io.BytesIO(('<html><h1>Product page</h1><p>'+('Description and specifications. '*10)+'</p><script>untrusted script</script></html>').encode());response.headers=headers;response.url='https://www.amazon.com/product'
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            result=fetch_reference('https://www.amazon.com/product')
        self.assertIn('Product page',result['text']);self.assertNotIn('untrusted script',result['text'])
        self.attach();self.app.set_config({'base_url':'http://localhost:9999/v1','model':'fake','api_key_env':'WB_TEST_KEY'})
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}):j=self.app.create_job(self.p['id'],self.w['id'],'organize',False)
        self.assertEqual(j['status'],'requires_consent');self.assertEqual(j['progress'],0)

    def test_url_blocks_private_network_and_bad_domains(self):
        for url in ['http://www.amazon.com/x','https://amazon.com.evil.test/x','https://127.0.0.1/x','file:///etc/passwd','https://user:pass@www.amazon.com/x']:
            with self.assertRaises(Problem):validate_reference_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(Problem):validate_reference_url('https://www.amazon.com/x')
    @patch.object(Workbench,'asset_recognition_enabled',True)
    def test_real_raw_pipeline_review_and_export(self):
        self.attach();self.app.set_config({'base_url':'http://127.0.0.1:9999/v1','model':'fake-vision','api_key_env':'WB_TEST_KEY'})
        base={'content_legibility':'pass','temporal_integrity':'pass','technical_usability':'pass','evidence_sufficiency':'pass'}
        def model(config,prompt,evidence,cache,allow):
            self.assertTrue(allow)
            if '先通览产品展示意图' in prompt:return {'subject':'红色物体','intent':'展示颜色','visible_result':'红色可见','unknowns':[]}
            if '返回 {"overview"' in prompt:return {'overview':'红色静态展示','requirements':{'hard':[],'preferences':[],'exclusions':[],'confirmed':True},'segments':[{'start':.1,'end':1.7,'facts':'红色画面','reason':'展示色彩','decision':'keep'}]}
            return {'facts':'红色画面','reason':'展示色彩','decision':'keep','boundary_reviewed':True,'assessment':{'base':base,'user':[]}}
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}),patch('vision_api.call',side_effect=model),patch('hypit_adapter.analyze'):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True,rights=True);self.app.run_job(j['id'],self.w['id'])
        j=self.app.store.get('job',j['id'],self.w['id']);self.assertEqual(j['status'],'awaiting_review',j.get('error'))
        shots=self.app.store.all('shot',self.w['id']);self.assertEqual(len(shots),1);shot=shots[0]
        with self.assertRaises(Problem):self.app.review(self.p['id'],self.b['id'],shot['id'],{'decision':'keep','content_confirmed':True})
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.w['id'],[shot['id']])
        self.app.review(self.p['id'],self.w['id'],shot['id'],{'decision':'keep','content_confirmed':True})
        result=self.app.export(self.p['id'],self.w['id'],[shot['id']]);self.assertTrue(Path(result['files'][0]['path']).is_file())
        out=Path(result['files'][0]['path'])
        before=list(out.parent.parent.iterdir())
        with patch('video_document.write_document',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.app.export(self.p['id'],self.w['id'],[shot['id']])
        self.assertEqual(list(out.parent.parent.iterdir()),before)
        out.write_bytes(b'other file')
        media_id=result['id']+'-0'
        with self.assertRaisesRegex(Problem,'已变化'):
            self.app.media(self.p['id'],self.w['id'],'export',media_id,self.app.media_signature(self.p['id'],self.w['id'],'export',media_id))
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.b['id'],[shot['id']])
    @patch.object(Workbench,'asset_recognition_enabled',True)
    def test_prepared_clips_remain_whole(self):
        self.attach(kind='prepared');self.app.set_config({'base_url':'http://localhost:9999/v1','model':'fake','api_key_env':'WB_TEST_KEY'})
        def model(config,prompt,evidence,cache,allow):
            if '先通览产品展示意图' in prompt:return {'subject':'红色','intent':'色彩','visible_result':'红色','unknowns':[]}
            if '返回 {"overview"' in prompt:return {'overview':'红色','requirements':{},'segments':[]}
            return {}
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}),patch('vision_api.call',side_effect=model),patch('hypit_adapter.analyze'):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True);self.app.run_job(j['id'],self.w['id'])
        shots=self.app.store.all('shot',self.w['id']);self.assertEqual(len(shots),1);self.assertEqual(shots[0]['start'],0);self.assertAlmostEqual(shots[0]['end'],2);self.assertEqual(shots[0]['review_decision'],'uncertain')

class HTTPIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=make_server(Path(self.tmp.name)/'state',0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.server.app.pool.shutdown(wait=True);self.tmp.cleanup()
    def request(self,path,body=None,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Workbench-Token']=self.server.token
        if origin:headers['Origin']=origin
        return urllib.request.urlopen(urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5)
    def test_browser_compression_preserves_full_state_and_small_poll_responses(self):
        import gzip
        self.server.app.store.put('product','root',{'name':'Large','extra_request':'long text '*12000})
        def state(encoding,path='/api/state?view=workbench'):
            req=urllib.request.Request(self.url+path,headers={'Accept-Encoding':encoding,'X-Workbench-Token':self.server.token})
            with urllib.request.urlopen(req) as response:return response.headers,response.read()
        headers,compressed=state('gzip, deflate')
        self.assertEqual(headers.get('Content-Encoding'),'gzip')
        headers,plain=state('gzip;q=0')
        self.assertIsNone(headers.get('Content-Encoding'))
        self.assertEqual(json.loads(gzip.decompress(compressed)),json.loads(plain))
        headers,unchanged=state('gzip','/api/state?view=workbench&since='+json.loads(plain)['revision'])
        self.assertIsNone(headers.get('Content-Encoding'))
        self.assertEqual(json.loads(unchanged),{'unchanged':True})

    def test_api_token_origin_and_cross_product(self):
        for token,origin in [(False,None),(True,'https://evil.test')]:
            with self.assertRaises(urllib.error.HTTPError) as cm:self.request('/api/state',token=token,origin=origin)
            self.assertEqual(cm.exception.code,403)
        p=json.load(self.request('/api/products',{'name':'P'}));q=json.load(self.request('/api/products',{'name':'Q'}))
        w=json.load(self.request(f"/api/products/{p['id']}/workspaces",{'name':'A'}))
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request(f"/api/products/{q['id']}/workspaces/{w['id']}/scan",{})
        self.assertEqual(cm.exception.code,404)
        with self.assertRaises(urllib.error.HTTPError):self.request('/%2e%2e/backend.py',token=False)
    def test_background_poll_skips_unchanged_state_and_observes_writes(self):
        full=json.load(self.request('/api/state'))
        query='/api/state?since='+full['revision']
        with patch.object(self.server.app.store,'all',side_effect=AssertionError('unnecessary catalog read')):
            self.assertEqual(json.load(self.request(query)),{'unchanged':True})
        product=json.load(self.request('/api/products',{'name':'New'}))
        changed=json.load(self.request(query))
        self.assertNotEqual(changed['revision'],full['revision'])
        self.assertEqual(changed['products'][0]['id'],product['id'])
        json.load(self.request('/api/generation/settings',{'duration':8}))
        changed=json.load(self.request('/api/state?since='+changed['revision']))
        self.assertEqual(changed['generation_config']['duration'],8)
        app=self.server.app
        w=app.create_workspace(product['id'],'workspace')
        details={'display_categories':['旋转'],'light_sword':{'evidence':'灯光变化'},'other':'full observation'}
        app.store.put('shot',w['id'],{'asset_id':'a','facts':'full facts','visual_details':details})
        def shot(state):return state['products'][0]['workspaces'][0]['shots'][0]
        summary=json.load(self.request('/api/state?view=workbench'))
        self.assertNotIn('facts',shot(summary))
        self.assertEqual(shot(summary)['visual_details']['light_sword'],details['light_sword'])
        self.assertEqual(shot(json.load(self.request('/api/state?since='+summary['revision'])))['facts'],'full facts')
        with patch.object(app,'asset_recognition_enabled',True):
            self.assertEqual(shot(json.load(self.request('/api/state?view=workbench')))['visual_details'],details)
    def test_media_range_and_account_forgery(self):
        a=self.server.app;p=a.create_product('P');w=a.create_workspace(p['id'],'A');b=a.create_workspace(p['id'],'B')
        folder=Path(self.tmp.name)/'media';folder.mkdir();file=folder/'x.mp4';file.write_bytes(b'0123456789')
        lib=a.attach_library(p['id'],w['id'],str(folder),'raw')
        from workbench.backend import digest
        asset=a.store.put('asset',w['id'],{'library_id':lib['id'],'path':str(file),'sha256':digest(file)})
        sig=a.media_signature(p['id'],w['id'],'asset',asset['id']);path=f"/api/products/{p['id']}/workspaces/{w['id']}/media/asset/{asset['id']}?sig={sig}"
        req=urllib.request.Request(self.url+path,headers={'Range':'bytes=2-5'})
        with urllib.request.urlopen(req) as response:self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345')
        with self.assertRaises(urllib.error.HTTPError):self.request(path.replace(w['id'],b['id']),token=False)

if __name__=='__main__':unittest.main()
