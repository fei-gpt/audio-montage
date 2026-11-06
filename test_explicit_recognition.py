import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from explicit_recognition import VERSION, evidence_problem
from montage import fingerprint, read, run, save
from vision_api import analyze
from workbench.reference import fit_slot


class ExplicitEvidenceTest(unittest.TestCase):
    def test_real_frames_validated_before_the_interval_is_used_for_editing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root/'fixture.mp4'
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=90x160:r=20:d=2',
                 '-c:v','libx264',video])
            task = root/'task.json'
            save(task, {'source':str(video),'source_sha256':fingerprint(video),'duration':2,
                        'request':'展示可见变化','analysis_mode':'standard','evidence_standard':VERSION})
            save(root/'config.json', {})
            calls = []
            def model(config, prompt, frames, cache, paid):
                self.assertFalse(paid)
                self.assertTrue(all(Path(f['path']).is_file() for f in frames))
                calls.append([f['time'] for f in frames])
                if len(calls)==1:
                    return {'requirements':{},'segments':[{'start':0,'end':1,'focus_times':[.5]},
                                                          {'start':1,'end':2,'focus_times':[1.5]}]}
                start = 0 if len(calls)==2 else 1
                # Second response cites a frame never sent to the model.
                end_point = .8 if start==0 else 1.753
                point = {'kind':'change','purpose':'变化过程','required_start':start,
                         'required_end':start+.9,'points':[{'time':start,'fact':'前态'},
                         {'time':end_point,'fact':'后态'}],'unknowns':[]}
                return {'shot_review':dict(reviewed=True,continuous=True,start=start,end=start+1),
                        'temporal_observation':point,'facts':'画面发生变化','reason':'有两个状态',
                        'assessment':{'base':dict.fromkeys(('content_legibility','temporal_integrity',
                        'technical_usability','evidence_sufficiency'),'pass')},'boundary_reviewed':True,
                        'decision':'keep'}
            with patch('vision_api.call', side_effect=model):
                analyze(SimpleNamespace(task=task, config=root/'config.json', allow_paid=False))
            valid, invalid = read(task)['segments']
            self.assertIn(.45, calls[1])
            self.assertEqual(valid['decision'],'keep')
            self.assertEqual((valid['action_start'],valid['action_end']),(0,.9))
            self.assertEqual(invalid['decision'],'uncertain')
            self.assertIn('时间点',invalid['review_reason'])
            self.assertNotIn('action_start',invalid)
            candidate = dict(valid,frames=30,safe_trim_ranges=[{'start':0,'end':1}])
            self.assertIsNone(fit_slot(candidate,{'start':0,'end':.5}))

    def test_physical_cut_and_transition_split_but_pan_does_not(self):
        from explicit_recognition import split_at_boundaries
        candidate = dict(start=0,end=4,facts='整段判断')
        self.assertEqual(split_at_boundaries(candidate,{}),[candidate])
        pieces=split_at_boundaries(candidate,dict(cuts=[{'time':1.5}],transitions=[dict(start=2,end=2.3)]))
        self.assertEqual([(p['start'],p['end']) for p in pieces],[(0,1.5),(1.5,2),(2.3,4)])
        self.assertTrue(all('facts' not in p for p in pieces))

    def test_static_image_does_not_require_an_invented_action(self):
        record = dict(kind='state',purpose='外观',points=[dict(time=.5,fact='盒盖闭合')],
                      required_start=.5,required_end=.8,unknowns=['锁扣是否扣紧'])
        frames = [dict(time=.5)]
        self.assertIsNone(evidence_problem(record,frames,0,1))
        self.assertIsNotNone(evidence_problem(dict(record,kind='change'),frames,0,1))

    def test_reference_requires_visible_facts_and_preserves_action_stage_boundaries(self):
        from workbench.reference_structure import analyze as recognize
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root/'reference.mp4'
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=90x160:r=20:d=2',
                 '-c:v','libx264',video])
            app = SimpleNamespace(wroot=lambda _:root,config=lambda:{'provider':'codex','model':'gpt-6-luna'})
            ref = dict(path=str(video),duration=2,sha256=fingerprint(video))
            def local_evidence(folder, path, duration):
                save(folder/'boundaries.json',{'candidates':[{'score':.9,'at':1.0}]})
                return {'pages':[], 'frame_rate':20}
            beat = dict(subject='产品',purpose='展示',action='移动',composition='全景',
                        must_see=['产品入画'],flexible=['背景'])
            result = {'intent':'引入产品','beats':[dict(beat,start=0,end=.9,boundary_kind='start'),
                                                   dict(beat,start=.9,end=2,boundary_kind='phase')]}
            with patch('workbench.reference_structure.evidence',side_effect=local_evidence), patch('vision_api.call') as model:
                model.return_value=dict(result,beats=[dict(beat,start=0,end=2,boundary_kind='start',must_see=[])])
                with self.assertRaisesRegex(ValueError,'必须看见'):
                    recognize(app,'w',ref,False,timed=True)
                model.return_value=result
                analysis=recognize(app,'w',ref,False,timed=True)
                self.assertEqual(analysis['beats'][1]['start'],.9)
                self.assertEqual(analysis['evidence_standard'],VERSION)
                self.assertGreater(len(model.call_args.args[2]),1)
                recognize(app,'w',ref,False,timed=True)
                self.assertEqual(model.call_count,2)
