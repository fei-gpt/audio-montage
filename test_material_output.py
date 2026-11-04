import json, unittest
from pathlib import Path
from unittest.mock import patch
import test_workbench as fixtures
from workbench.backend import Problem
from montage import save


class MaterialOutputTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.WorkbenchTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.WorkbenchTest.tearDownClass.__func__)
    setUp=fixtures.WorkbenchTest.setUp
    tearDown=fixtures.WorkbenchTest.tearDown
    attach=fixtures.WorkbenchTest.attach
    # Run only the focused output cases, without invoking Hypit or a model.
    def fixture(self, kind):
        a=self.attach(kind=kind);w=self.w['id']
        task=self.root/'task.json';save(task,{'analysis':{'shot_boundaries':[],'transition_ranges':[]}})
        j=self.app.store.put('job',w,{'rights_allowed':True})
        s=self.app.store.put('shot',w,{'asset_id':a['id'],'asset_sha256':a['sha256'],
            'task_path':str(task),'job_id':j['id'],'kind':kind,'start':0,'end':2,
            'facts':'red scene','review_decision':'uncertain','stale':False})
        return a,s

    def test_prepared_saves_review_without_export(self):
        a,s=self.fixture('prepared')
        self.app.review(self.p['id'],self.w['id'],s['id'],{'decision':'keep','content_confirmed':True})
        doc=json.loads(Path(a['path']+'.analysis.json').read_text(encoding='utf-8'))
        self.assertEqual(doc['reviews'][0]['review_decision'],'keep')
        with patch('workbench.backend.subprocess.run') as encode:
            with self.assertRaises(Problem):self.app.export(self.p['id'],self.w['id'],[s['id']])
            encode.assert_not_called()

    def test_raw_export_has_adjacent_json(self):
        a,s=self.fixture('raw')
        self.app.review(self.p['id'],self.w['id'],s['id'],{'decision':'keep','content_confirmed':True})
        result=self.app.export(self.p['id'],self.w['id'],[s['id']])
        f=result['files'][0];self.assertTrue(Path(f['path']).is_file())
        doc=json.loads(Path(f['json_path']).read_text(encoding='utf-8'))
        self.assertEqual(doc['video_name'],'001.mp4')
        self.assertEqual(doc['origin']['source_sha256'],a['sha256'])
        self.assertEqual(doc['clip']['start'],0)
