import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from workbench.backend import Workbench,Problem
class BulkReviewTest(unittest.TestCase):
 def app(self):
  return SimpleNamespace(workspace=Mock(),store=SimpleNamespace(all=Mock(return_value=[{'id':'pending'},{'id':'old','stale':True},{'id':'excluded','review_decision':'reject'},{'id':'done','review_decision':'keep'}])),review=Mock())
 def test_requires_confirmation(self):
  a=self.app()
  with self.assertRaises(Problem):Workbench.review_all(a,'p','w',{})
  a.review.assert_not_called()
 def test_scope_and_pending_only(self):
  a=self.app();r=Workbench.review_all(a,'p','w',{'content_confirmed':True});self.assertEqual(r['passed'],1);a.store.all.assert_called_once_with('shot','w');self.assertEqual(a.review.call_args.args[:3],('p','w','pending'))
 def test_invalid_source_reported(self):
  a=self.app();a.review.side_effect=Problem('source changed');r=Workbench.review_all(a,'p','w',{'content_confirmed':True});self.assertEqual(r['passed'],0);self.assertEqual(len(r['skipped']),1)
if __name__=='__main__':unittest.main()
