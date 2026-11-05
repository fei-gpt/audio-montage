import unittest
from workbench.duration_planner import plan_by_duration
class DurationPlanTest(unittest.TestCase):
 def c(self,id,frames=30,ranges=()):return dict(id=id,asset_sha256=id,start=0,end=frames/30,frames=frames,safe_trim_ranges=list(ranges),action_start=None,action_end=None)
 def test_sentence_boundaries_and_no_text_dependency(self):
  cs=[self.c('a'),self.c('b')];tl={'segments':[{'end':1,'text':'anything'},{'end':2,'text':'unrelated'}]}
  r=plan_by_duration(cs,tl,2);self.assertEqual([p['frames'] for p in r['parts']],[30,30]);self.assertNotEqual(r['parts'][0]['shot_id'],r['parts'][1]['shot_id'])
  tl['segments'][0]['text']='changed';self.assertEqual(r,plan_by_duration(cs,tl,2))
 def test_no_unsafe_trim(self):
  with self.assertRaises(ValueError):plan_by_duration([self.c('a',60)],{'segments':[{'end':1}]},1)
 def test_safe_trim(self):
  r=plan_by_duration([self.c('a',60,[{'start':0,'end':2}])],{'segments':[{'end':1}]},1);self.assertEqual(r['parts'][0]['frames'],30)
 def test_used_excluded(self):
  with self.assertRaises(ValueError):plan_by_duration([self.c('a')],{'segments':[{'end':1}]},1,[{'asset_sha256':'a','start':0,'end':1}])
if __name__=='__main__':unittest.main()
