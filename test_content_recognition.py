import unittest
from argparse import Namespace
import test_pipeline as fixtures
import montage as m
import content_recognition as c


class ContentExtractionTest(unittest.TestCase):
    setUp = fixtures.PipelineTest.setUp
    tearDown = fixtures.PipelineTest.tearDown

    def test_multiple_ranges_and_resume(self):
        root = self.root / 'content'
        c.prepare(Namespace(video=self.video, request='保留红色展示的两个区间', output=root))
        task_path = root / 'task.json'
        task = m.read(task_path)
        with self.assertRaises(ValueError):
            c.extract(Namespace(task=task_path))
        evidence = m.read(next((root / 'evidence').glob('*/observation-*.json')))['evidence']
        task['rights']['usage'] = 'allowed'
        task['analysis']['reviewed'] = True
        task['requirements']['confirmed'] = True
        task['segments'] = [dict(id=str(i), start=a, end=b, facts='合成红色画面',
            assessment={'base': {k: 'pass' for k in ['content_legibility', 'temporal_integrity', 'technical_usability', 'evidence_sufficiency']}, 'user': []},
            decision='keep', reason='满足合成测试要求', boundary_reviewed=True,
            evidence=[next(e for e in evidence if a <= e['time'] <= b)])
            for i, (a, b) in enumerate([(0, 1), (2, 3)])]
        m.save(task_path, task)
        c.extract(Namespace(task=task_path))
        first = m.read(root / 'extraction.json')['clips']
        self.assertEqual(len(first), 2)
        c.extract(Namespace(task=task_path))
        self.assertEqual(first, m.read(root / 'extraction.json')['clips'])
        self.assertEqual(m.read(root / 'progress.json')['status'], 'completed')

    def test_real_cut_content_audio_and_invalid_ranges(self):
        import subprocess
        import copy
        from unittest.mock import patch
        source = self.root / 'two-scenes.mp4'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=180x320:r=30:d=2',
               '-f', 'lavfi', '-i', 'color=blue:s=180x320:r=30:d=2',
               '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
               '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '2:a',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', source])
        root = self.root / 'two-task'
        c.prepare(Namespace(video=source, request='分别提取两种画面', output=root))
        path = root / 'task.json'
        task = m.read(path)
        evidence = m.read(next((root / 'evidence').glob('*/observation-*.json')))['evidence']
        task['rights']['usage'] = 'allowed'
        task['analysis']['reviewed'] = True
        task['requirements'].update(confirmed=True, hard=[{'id': 'product', 'text': '目标产品'}])
        task['segments'] = [dict(id=str(i), start=a, end=b, facts='合成色块', reason='区间测试',
            decision='keep', boundary_reviewed=True,
            assessment={'base': {k: 'pass' for k in ['content_legibility', 'temporal_integrity', 'technical_usability', 'evidence_sufficiency']},
                        'user': [{'id': 'product', 'result': 'pass'}]},
            evidence=[next(e for e in evidence if a <= e['time'] <= b)])
            for i, (a, b) in enumerate([(0, 1), (2, 3)])]
        for kind in ['range', 'condition', 'unknown']:
            bad = copy.deepcopy(task)
            if kind == 'range': bad['segments'][0]['end'] = 99
            elif kind == 'condition': bad['segments'][0]['assessment']['user'][0]['result'] = 'fail'
            else: bad['segments'][0]['assessment']['base']['evidence_sufficiency'] = 'unknown'
            m.save(path, bad)
            if kind == 'range':
                # A structurally broken task is still refused before any encoding.
                with self.assertRaises(ValueError), patch.object(c, 'run') as runner:
                    c.extract(Namespace(task=path))
                runner.assert_not_called()
                continue
            # Content problems hold back only that clip instead of failing the batch.
            c.extract(Namespace(task=path))
            self.assertEqual([row['id'] for row in m.read(root / 'extraction.json')['clips']], ['1'])
            pending = m.read(root / 'uncertain-review.json')['segments']
            self.assertEqual([row['id'] for row in pending], ['0'])
            expected = '用户硬条件 product 未通过' if kind == 'condition' else '观察证据不足'
            self.assertIn(expected, pending[0]['review_reason'])
            self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')
        m.save(path, task)
        real_run = c.run
        calls = []
        def interrupted(arguments):
            if '-movflags' in arguments:
                calls.append(arguments)
                if len(calls) == 2:
                    raise OSError('simulated interruption')
            return real_run(arguments)
        with patch.object(c, 'run', side_effect=interrupted), self.assertRaises(OSError):
            c.extract(Namespace(task=path))
        self.assertEqual(len(m.read(root / 'extraction.json')['clips']), 1)
        c.extract(Namespace(task=path))
        clips = m.read(root / 'extraction.json')['clips']
        self.assertEqual(len(clips), 2)
        for row, channel in zip(clips, [0, 2]):
            info = m.probe(row['output'])
            self.assertAlmostEqual(m.media_duration(info, 'video'), 1, delta=.05)
            self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
            pixels = subprocess.run(['ffmpeg', '-v', 'error', '-i', row['output'], '-frames:v', '1',
                '-vf', 'scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
            self.assertGreater(pixels[channel], 150)
        task['keep_original_audio'] = False
        m.save(path, task)
        c.extract(Namespace(task=path))
        for row in m.read(root / 'extraction.json')['clips']:
            self.assertFalse(any(s['codec_type'] == 'audio' for s in m.probe(row['output'])['streams']))

    def test_three_second_limit_routes_complete_long_action_to_review(self):
        root = self.root / 'duration-task'
        c.prepare(Namespace(video=self.video, request='完整动作', output=root))
        path = root / 'task.json'
        task = m.read(path)
        task['rights']['usage'] = 'allowed'
        task['analysis']['reviewed'] = True
        task['requirements']['confirmed'] = True
        evidence = m.read(next((root / 'evidence').glob('*/observation-*.json')))['evidence']
        task['segments'] = [dict(id=str(i), start=0, end=end, facts='合成测试', reason='保留完整单元',
            decision='keep', boundary_reviewed=True, evidence=[evidence[0]],
            assessment={'base': {k: 'pass' for k in ['content_legibility', 'temporal_integrity', 'technical_usability', 'evidence_sufficiency']}, 'user': []})
            for i, end in enumerate([1, 3, .9, 3.1])]
        m.save(path, task)
        c.extract(Namespace(task=path))
        manifest = m.read(root / 'extraction.json')
        self.assertEqual(len(manifest['clips']), 2)
        self.assertEqual([r['end'] for r in manifest['clips']], [1, 3])
        pending = m.read(root / 'manual-review.json')['segments']
        self.assertEqual(len(pending), 2)
        self.assertEqual([r['end'] for r in pending], [.9, 3.1])
        self.assertTrue(all(__import__('pathlib').Path(r['review_video']).is_file() for r in pending))
        self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')

        # Moving a previously accepted clip to manual review must retire its old output.
        task['segments'][0]['end'] = 3.2
        m.save(path, task)
        c.extract(Namespace(task=path))
        self.assertEqual(len(list((root / 'clips').glob('*.mp4'))), 1)
        self.assertTrue(list((root / 'clips/history').glob('*.mp4')))


class ShotContinuityExportTest(unittest.TestCase):
    setUp = fixtures.PipelineTest.setUp
    tearDown = fixtures.PipelineTest.tearDown

    def task(self):
        root = self.root / 'continuity-task'
        c.prepare(Namespace(video=self.video, request='保留完整展示效果', output=root))
        path = root / 'task.json'
        task = m.read(path)
        task['rights']['usage'] = 'allowed'
        task['analysis'].update(reviewed=True, coverage=[[0, 4]])
        task['requirements']['confirmed'] = True
        evidence = m.read(next((root / 'evidence').glob('*/observation-*.json')))['evidence']
        segment = dict(id='S1', start=0, end=4, facts='合成连续红色画面',
            reason='验证完整展示时长例外', decision='keep', boundary_reviewed=True,
            evidence=evidence, display_intent='完整持续展示', duration_reason='保留4秒结果观察',
            shot_review=dict(start=0, end=4, continuous=True, reviewed=True,
                             method='synthetic continuous source', evidence=evidence),
            assessment={'base': {k: 'pass' for k in c.DIMENSIONS}, 'user': []})
        task['segments'] = [segment]
        return root, path, task, segment

    def test_verified_single_take_exports_full_length_and_requires_evidence(self):
        root, path, task, segment = self.task()
        m.save(path, task)
        c.extract(Namespace(task=path))
        clips = m.read(root / 'extraction.json')['clips']
        self.assertEqual(len(clips), 1)
        self.assertTrue(clips[0]['single_take_exception'])
        self.assertAlmostEqual(m.media_duration(m.probe(clips[0]['output']), 'video'), 4, delta=.05)
        segment['shot_review']['reviewed'] = False
        m.save(path, task)
        c.extract(Namespace(task=path))
        self.assertEqual(m.read(root / 'extraction.json')['clips'], [])
        self.assertEqual(len(m.read(root / 'manual-review.json')['segments']), 1)
        self.assertEqual(len(list((root / 'clips').glob('*.mp4'))), 0)

    def test_recorded_cut_blocks_short_and_long_exports_but_allows_cut_at_endpoint(self):
        root, path, task, segment = self.task()
        task['analysis']['shot_boundaries'] = [{'time': 2, 'type': 'hard_cut', 'reason': 'fixture cut'}]
        # Both default-length clips and purported continuity exceptions must be refused.
        for end in [3, 4]:
            segment['end'] = end
            m.save(path, task)
            c.extract(Namespace(task=path))
            self.assertEqual(m.read(root / 'extraction.json')['clips'], [])
            pending = m.read(root / 'uncertain-review.json')['segments']
            self.assertIn('切镜', pending[0]['review_reason'])
        segment['end'] = 2
        segment['evidence'] = [e for e in segment['evidence'] if e['time'] <= 2]
        m.save(path, task)
        c.extract(Namespace(task=path))
        self.assertEqual(len(m.read(root / 'extraction.json')['clips']), 1)
