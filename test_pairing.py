import tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
from workbench.pairing import inspect_folder
from workbench.backend import Problem
import test_editing as fixtures

class NamingTest(unittest.TestCase):
    def test_natural_order_missing_conflict_and_nonrecursive(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['10.mp4','10.mp3','2.mp4','2.mp3','missing.mp4','voice.mp3','SS.mp4','ß.mp4','ss.mp3','note.txt']:(root/name).write_bytes(b'fixture')
            (root/'nested').mkdir();(root/'nested'/'nested.mp4').write_bytes(b'x')
            r=inspect_folder(root)
            self.assertEqual([x['key'] for x in r['rows']][:2],['2','10'])
            self.assertEqual(r['paired_count'],2);self.assertEqual(r['problem_count'],3)
            self.assertNotIn('nested',[x['key'] for x in r['rows']])
            before=r['snapshot'];(root/'new.mp3').write_bytes(b'new');self.assertNotEqual(before,inspect_folder(root)['snapshot'])

class PairBatchTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.EditingTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.EditingTest.tearDownClass.__func__)
    setUp=fixtures.EditingTest.setUp
    tearDown=fixtures.EditingTest.tearDown
    task=fixtures.EditingTest.task
    op=fixtures.EditingTest.op
    def body(self):
        r=self.app.editing.inspect_pairs(self.p['id'],self.w['id'],{'input_path':str(self.inputs)})
        return {'input_mode':'paired','input_path':str(self.inputs),'pairing_snapshot':r['snapshot'],'rights_allowed':True,'auto_preview':True}
    def test_batch_pairs_keep_distinct_fronts_and_skip_missing(self):
        shutil.copy2(self.intro,self.inputs/'2.mp4');shutil.copy2(self.audio,self.inputs/'2.mp3');shutil.copy2(self.audio,self.inputs/'orphan.mp3')
        b=self.app.editing.create(self.p['id'],self.w['id'],self.body());tasks=self.app.editing.tasks(self.w['id'],b['id'])
        self.assertEqual([t['name'] for t in tasks],['1','2'])
        self.assertEqual(b['pairing_report']['problem_count'],1)
        self.assertNotEqual(tasks[0]['intro'],tasks[1]['intro']);self.assertEqual(b['rules']['matching_mode'],'duration');self.assertEqual(b['rules']['timing_basis'],'audio_duration')
    def test_changed_folder_requires_recheck(self):
        body=self.body();(self.inputs/'new.mp3').write_bytes(b'changed')
        with self.assertRaisesRegex(Problem,'重新检查'):self.app.editing.create(self.p['id'],self.w['id'],body)
        self.assertEqual(self.app.editing.list(self.p['id'],self.w['id']),[])
    def test_total_duration_preview_and_output_without_asr_or_model(self):
        body=self.body();body['mode']='direct';b=self.app.editing.create(self.p['id'],self.w['id'],body)
        with patch('workbench.editing.load_document',side_effect=AssertionError('prepared files need no analysis')),patch('vision_api.call',side_effect=AssertionError('no model')),patch('workbench.local_asr.transcribe',side_effect=AssertionError('no ASR')):
            self.op(b,'plan')
        t=self.task(b);self.assertEqual(t['status'],'completed',t.get('error'));self.assertEqual(t['timeline']['source'],'audio_duration')
        self.assertEqual(t['output']['report']['intro_seconds'],1);self.assertEqual(t['output']['report']['body_seconds'],2)
        self.assertTrue(t['output']['report']['intro_audio_preserved'])
    def test_other_account_folder_is_rejected(self):
        with self.assertRaises(Problem):self.app.editing.inspect_pairs(self.p['id'],self.w2['id'],{'input_path':str(self.library)})

if __name__=='__main__':unittest.main()
