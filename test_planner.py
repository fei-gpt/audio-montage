"""Real-media tests for trimming, multi-part coverage and duplicate avoidance."""
import copy
import importlib.util
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import montage as m
import asset_index as ix
import planner as p


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / 'library'
        self.library.mkdir()
        self.audio = self.root / 'voice.wav'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', self.audio])
        self.red, self.blue = self.library / 'red.mp4', self.library / 'blue.mp4'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=180x320:r=30:d=4',
               '-f', 'lavfi', '-i', 'sine=frequency=880:duration=4', '-c:v', 'libx264', '-c:a', 'aac', self.red])
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=180x320:r=30:d=4',
               '-c:v', 'libx264', self.blue])
        self.project = self.root / 'project'
        m.init(Namespace(project=self.project, audio=self.audio, width=180, height=320, fps=30))
        m.save(self.project / 'audio/timing.json', {'reviewed': True,
               'segments': [{'start': 0, 'end': 6, 'text': 'A color display.'}]})
        self.edit = {'shots': [{'id': 'S001', 'start': 0, 'end': 6, 'text': 'A color display.',
                      'query': 'color display', 'purpose': '展示色块', 'required': [], 'forbidden': [],
                      'reviewed': False, 'selection': None}]}
        m.save(self.project / 'plans/edit.json', self.edit)

    def tearDown(self):
        self.tmp.cleanup()

    def create_index(self):
        self.db = self.root / 'index.sqlite'
        ix.index_library(Namespace(library=self.library, database=self.db, window=6, scene=0.3))
        data = m.read(self.db.with_suffix('.label-queue.json'))
        for row in data['clips']:
            row['labels'].update(description='color display', subject='color panel', scene='plain background',
                                  usable_ranges=[{'start': row['start'], 'end': row['end'], 'kind': 'static', 'priority': 1}])
            row['reviewed'] = True
        labels = self.root / 'labels.json'
        m.save(labels, data)
        ix.import_labels(Namespace(database=self.db, labels=labels))
        return data

    def test_precise_action_and_static_trim(self):
        candidate = {'path': str(self.red), 'clip_id': 'a', 'asset_hash': 'hash',
                     'labels_sha256': 'labels', 'visual': {}, 'description': 'close lid'}
        action = p.usable_ranges({'usable_ranges': [{'start': 0, 'end': 4, 'kind': 'action',
                   'action_start': 1, 'action_end': 3}]}, 0, 4)[0]
        selected = p.trim_window(candidate, action, 2)
        self.assertEqual(selected['source_start'], 1)
        self.assertIsNone(p.trim_window(candidate, action, 1.5))
        self.assertEqual(p.trim_window(candidate, p.usable_ranges({}, 0, 4)[0], 2)['source_start'], 1)
        with self.assertRaises(ValueError):
            p.usable_ranges({'usable_ranges': [{'start': -1, 'end': 3}]}, 0, 4)

    def test_auto_plan_apply_and_shortage(self):
        self.create_index()
        args = Namespace(project=self.project, database=self.db, max_parts=4, min_part=0.8, min_score=0.35)
        p.auto_plan(args)
        proposal = self.project / 'plans/proposal.json'
        data = m.read(proposal)
        parts = data['edit']['shots'][0]['selection']['parts']
        self.assertEqual(len(parts), 2)
        self.assertAlmostEqual(sum(s['duration'] for s in parts), 6)
        self.assertEqual(len({s['asset_hash'] for s in parts}), 2)
        self.assertIsNone(m.read(self.project / 'plans/edit.json')['shots'][0]['selection'])
        p.apply_plan(Namespace(project=self.project, proposal=proposal))
        self.assertTrue((self.project / 'plans/edit.backup-1.json').exists())
        self.assertFalse(m.read(self.project / 'plans/edit.json')['shots'][0]['reviewed'])
        self.assertFalse(m.validate(self.project)[3]['errors'])
        with self.assertRaises(ValueError):
            p.apply_plan(Namespace(project=self.project, proposal=proposal))
        candidates = ix.search(self.db, 'color display', 0, limit=20)
        self.assertIsNone(p.select_chain(candidates, 9, [], max_parts=4))
        single = p.select_chain(candidates, 2, [])
        self.assertEqual(len(single['parts']), 1)
        self.assertIsNone(p.select_chain(candidates[:1], 4.2, []))

    def test_proposal_rechecks_ranges_and_labels(self):
        self.create_index()
        p.auto_plan(Namespace(project=self.project, database=self.db, max_parts=4, min_part=0.8, min_score=0.35))
        path = self.project / 'plans/proposal.json'
        original = m.read(path)
        altered = copy.deepcopy(original)
        altered['edit']['shots'][0]['selection']['parts'][0]['source_start'] = 3.9
        m.save(path, altered)
        with self.assertRaisesRegex(ValueError, '可用区间'):
            p.apply_plan(Namespace(project=self.project, proposal=path))
        self.assertFalse((self.project / 'plans/edit.backup-1.json').exists())
        m.save(path, original)
        with ix.connect(self.db) as db:
            db.execute('UPDATE clips SET reviewed=0')
        with self.assertRaisesRegex(ValueError, '标注已改变'):
            p.apply_plan(Namespace(project=self.project, proposal=path))

    def test_multi_part_video_draft_and_audio(self):
        data = copy.deepcopy(self.edit)
        data['shots'][0].update(reviewed=True, selection={'parts': [
            {'path': str(self.red), 'source_start': 0.5, 'duration': 3},
            {'path': str(self.blue), 'source_start': 0.25, 'duration': 3}]})
        m.save(self.project / 'plans/edit.json', data)
        m.render(Namespace(project=self.project, final=True))
        video = self.project / 'out/final.mp4'
        for second, channel in [(1, 0), (4, 2)]:
            pixels = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(second), '-i', str(video),
                '-frames:v', '1', '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                capture_output=True, check=True).stdout
            self.assertGreater(pixels[channel], 150)
        self.assertAlmostEqual(float(m.probe(video)['format']['duration']), 6, delta=0.1)
        m.review(Namespace(project=self.project, final=True))
        self.assertEqual(len(list((self.project / 'qa/frames').glob('*.jpg'))), 6)
        m.set_audio(Namespace(project=self.project, keep_original_audio=True))
        m.render(Namespace(project=self.project, final=False))
        self.assertEqual(m.read(self.project / 'qa/preview-render.json')['original_audio_missing_shots'], ['S001.2'])
        if importlib.util.find_spec('pyJianYingDraft'):
            m.export_draft(Namespace(project=self.project, name='multipart', allow_unreviewed=False))
            draft = m.read(self.project / 'out/multipart/draft_content.json')
            segments = next(t for t in draft['tracks'] if t['type'] == 'video')['segments']
            self.assertEqual(len(segments), 2)
            self.assertEqual([s['target_timerange']['start'] for s in segments], [0, 3000000])
            self.assertTrue(all(s['volume'] == 1 for s in segments))
            self.assertEqual(len(next(t for t in draft['tracks'] if t['type'] == 'text')['segments']), 1)

    def test_global_dedup_and_duration_guards(self):
        self.create_index()
        data = copy.deepcopy(self.edit)
        data['shots'] = [dict(data['shots'][0], id=f'S{i+1:03}', start=i*3, end=(i+1)*3) for i in range(2)]
        m.save(self.project / 'plans/edit.json', data)
        p.auto_plan(Namespace(project=self.project, database=self.db, max_parts=4, min_part=0.8, min_score=0.35))
        proposal = m.read(self.project / 'plans/proposal.json')
        selected = [s['selection']['parts'][0] for s in proposal['edit']['shots']]
        self.assertNotEqual(selected[0]['asset_hash'], selected[1]['asset_hash'])
        data = copy.deepcopy(self.edit)
        data['shots'][0].update(reviewed=True, selection={'parts': [
            {'path': str(self.red), 'source_start': 0.5, 'duration': 3},
            {'path': str(self.red), 'source_start': 0.5, 'duration': 3}]})
        m.save(self.project / 'plans/edit.json', data)
        self.assertTrue(any('重复使用' in w for w in m.validate(self.project)[3]['warnings']))
        with self.assertRaises(ValueError):
            m.render(Namespace(project=self.project, final=True))
        data['shots'][0]['selection']['parts'][1]['duration'] = 2
        m.save(self.project / 'plans/edit.json', data)
        with self.assertRaisesRegex(ValueError, '总时长'):
            m.validate(self.project)


if __name__ == '__main__':
    unittest.main(verbosity=2)
