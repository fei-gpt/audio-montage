import unittest
from workbench.batch_diversity import propose
from workbench.duration_planner import ascending
from workbench.perceptual import compare
import test_editing as fixtures


class BatchDiversityTest(unittest.TestCase):
    def test_joint_allocation_caps_usage_and_rotates_bookends(self):
        candidates=[dict(id=str(i),name=f'{i:03}.mp4',asset_sha256=str(i),start=0,end=2,frames=60,usage_count=0) for i in range(30)]
        result=propose(candidates,10,3,'fixed')
        self.assertEqual(result['proposed'],10)
        self.assertFalse(result['rendered'])
        self.assertTrue(all(v<=3 for v in result['usage_reservations'].values()))
        self.assertEqual(len({p[0]['asset_sha256'] for p in result['plans']}),10)
        for p in result['plans']:
            self.assertFalse(any(ascending(a['name'],b['name']) for a,b in zip(p,p[1:])))
        self.assertEqual(result,propose(candidates,10,3,'fixed'))

    def test_insufficient_pool_never_forces_more_outputs(self):
        c=[dict(name='one',asset_sha256='a',usage_count=3)]
        self.assertEqual(propose(c)['proposed'],0)

    def test_low_detail_is_unknown_not_duplicate(self):
        a=dict(source_sha256='a',frames=[]);b=dict(source_sha256='b',frames=[])
        self.assertIsNone(compare(a,b)['score'])


class UserApprovalTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.EditingTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.EditingTest.tearDownClass.__func__)
    setUp=fixtures.EditingTest.setUp
    tearDown=fixtures.EditingTest.tearDown
    def test_explicit_bulk_decision_does_not_fake_content_verification(self):
        self.shot.update(review_decision='uncertain',human_confirmed=False)
        self.app.store.put('shot',self.w['id'],self.shot)
        r=self.app.review_all(self.p['id'],self.w['id'],dict(approval_basis='user_instruction',user_authorized=True))
        self.assertEqual(r['passed'],1)
        s=self.app.store.get('shot',self.shot['id'],self.w['id'])
        self.assertEqual(s['review_decision'],'keep')
        self.assertEqual(s['review_basis'],'user_instruction')
        self.assertFalse(s['content_verified'])


class PerceptualMediaTest(unittest.TestCase):
    def test_reencode_matches_and_flat_video_is_not_automatically_grouped(self):
        import tempfile
        from pathlib import Path
        from workbench.edit_media import run
        from workbench.perceptual import signature
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a.mp4';b=root/'b.mp4';flat=root/'flat.mp4'
            run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','testsrc2=s=180x320:r=30:d=3','-c:v','libx264',a])
            run(['ffmpeg','-v','error','-nostdin','-y','-i',a,'-vf','scale=90:160','-c:v','libx264','-crf','30',b])
            run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=red:s=90x160:r=30:d=3','-c:v','libx264',flat])
            sa=signature(a,root/'cache');sb=signature(b,root/'cache');sf=signature(flat,root/'cache')
            self.assertTrue(compare(sa,sb)['candidate_duplicate'])
            self.assertIsNone(compare(sa,sf)['score'])
            self.assertEqual(signature(a,root/'cache'),sa)
