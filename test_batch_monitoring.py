import shutil,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import test_workbench as fixtures
from understanding import sample_times,observe
from vision_api import dense_frames
from montage import save


class BatchMonitoringTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.WorkbenchTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.WorkbenchTest.tearDownClass.__func__)
    setUp=fixtures.WorkbenchTest.setUp
    tearDown=fixtures.WorkbenchTest.tearDown
    attach=fixtures.WorkbenchTest.attach
    def test_single_file_failure_does_not_stop_remaining_batch(self):
        shutil.copy2(self.video,self.a_dir/'second.mp4');self.attach()
        w=self.w['id'];assets=self.app.store.all('asset',w)
        j=self.app.store.put('job',w,{'id':'a'*32,'kind':'organize','scope':w,'workspace_id':w,'product_id':self.p['id'],
            'status':'queued','done':[],'allow_paid':True,'rights_allowed':True,'continue_on_error':True,'asset_ids':[a['id'] for a in assets]})
        seen=[]
        def process(job,asset,product):
            seen.append(asset['id'])
            if asset['id']==assets[0]['id']:raise ValueError('uncertain paid result: do not resend')
        with patch.object(self.app,'process_asset',side_effect=process):self.app.run_job(j['id'],w)
        result=self.app.store.get('job',j['id'],w)
        self.assertEqual(seen,[a['id'] for a in assets]);self.assertEqual(len(result['done']),1)
        self.assertEqual(result['status'],'partial_failure');self.assertEqual(len(result['asset_errors']),1)
        self.assertFalse(next(iter(result['asset_errors'].values()))['automatic_paid_retry'])
    def test_authorization_errors_stop_the_batch(self):
        self.attach();w=self.w['id']
        j=self.app.store.put('job',w,{'kind':'organize','scope':w,'workspace_id':w,'product_id':self.p['id'],
            'status':'queued','done':[],'allow_paid':True,'rights_allowed':True,'continue_on_error':True})
        with patch.object(self.app,'process_asset',side_effect=ValueError('视觉 API HTTP 401')):self.app.run_job(j['id'],w)
        self.assertEqual(self.app.store.get('job',j['id'],w)['status'],'failed')
    def test_frame_generation_and_dense_reference_share_rounding(self):
        end=3.733333;every=end/12;root=self.root/'observe';record=root/'assets/source.json'
        save(record,{'asset':{'asset_hash':'hash','paths':['fixture']}})
        def render(cmd):Path(cmd[-1]).write_bytes(b'image')
        with patch('understanding.source',return_value=('fixture',end)),patch('understanding.run',side_effect=render):
            observe(SimpleNamespace(record=record,start=0,end=end,every=every))
        frames=dense_frames(root/'evidence/hash',0,end)
        self.assertEqual(len(frames),12);self.assertIn('1.866667.jpg',[Path(f['path']).name for f in frames])
        self.assertTrue(all(Path(f['path']).is_file() for f in frames))
        self.assertTrue(all(t<end for t in sample_times(0,end,every)))

    def test_pause_stops_before_next_asset_and_resume_keeps_checkpoint(self):
        self.attach();w=self.w['id']
        j=self.app.store.put('job',w,{'kind':'organize','scope':w,'workspace_id':w,'product_id':self.p['id'],'status':'queued','done':[],'allow_paid':True,'rights_allowed':True})
        self.app.pause(self.p['id'],w,j['id'])
        with patch.object(self.app,'process_asset') as process:self.app.run_job(j['id'],w)
        process.assert_not_called()
        self.assertEqual(self.app.store.get('job',j['id'],w)['status'],'interrupted')
        self.app.resume(self.p['id'],w,j['id'],True,retry_failed=False)
        self.assertFalse((self.app.root/'pause-requests'/(j['id']+'.json')).exists())
