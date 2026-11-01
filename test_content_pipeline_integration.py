"""End-to-end offline run: simulated vision API -> candidates -> dense review -> clips.

The HTTP boundary is faked; every frame, every clip and every duration is produced
by the real local FFmpeg from synthetic 9:16 media. No network, no paid service.
"""
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import montage as m
import content_recognition as c
import vision_api as v

BASE_PASS = {k: 'pass' for k in ['content_legibility', 'temporal_integrity',
                                 'technical_usability', 'evidence_sufficiency']}
REQUIREMENTS = {'hard': [{'id': 'H1', 'text': '必须看到主体完整动作',
                          'source_quote': '找出完整动作', 'confirmed': True}],
                'preferences': [], 'exclusions': [{'id': 'E1', 'text': '排除明显遮挡',
                                                   'source_quote': '排除严重遮挡'}],
                'confirmed': True}


def review(decision='keep', **extra):
    row = {'facts': '合成色块场景中的完整动作', 'reason': '满足本次要求',
           'decision': decision, 'boundary_reviewed': True, 'use_conditions': [],
           'content_roles': ['demonstration'],
           'assessment': {'base': dict(BASE_PASS),
                          'user': [{'id': 'H1', 'result': 'pass'}, {'id': 'E1', 'result': 'pass'}]}}
    row.update(extra)
    return row


class _Response:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return io.BytesIO(json.dumps(self.raw).encode())

    def __exit__(self, *exc):
        return False


class FakeVisionService:
    """Stands in for the OpenAI-compatible endpoint; answers from a canned script."""

    def __init__(self, batches, reviews):
        self.batches = batches
        self.reviews = reviews
        self.calls = []

    def build_opener(self, *args, **kwargs):
        service = self

        class Opener:
            def open(self, request, timeout=None):
                payload = json.loads(request.data)
                content = payload['messages'][0]['content']
                text = content[0]['text']
                images = [part for part in content if part['type'] == 'image_url']
                for part in images:
                    data = part['image_url']['url'].split(',', 1)[1]
                    assert data[:4] == '/9j/', 'evidence must be real JPEG frames'
                kind = 'batch' if '本批区间' in text else 'review'
                service.calls.append({'kind': kind, 'images': len(images), 'prompt': text})
                answer = service.answer(text)
                return _Response({'choices': [{'finish_reason': 'stop',
                                               'message': {'content': json.dumps(answer, ensure_ascii=False)}}],
                                  'usage': {'total_tokens': 1}})

        return Opener()

    def answer(self, prompt):
        batch = re.search(r'本批区间([\d.]+)—([\d.]+)秒', prompt)
        if batch:
            return self.batches[round(float(batch.group(1)), 3)]
        found = re.search(r'候选：(\{.*\})\n本批已观察区间', prompt, re.S)
        if not found:
            raise AssertionError('unexpected prompt: ' + prompt[-200:])
        candidate = json.loads(found.group(1))
        key = (round(candidate['start'], 3), round(candidate['end'], 3))
        if key not in self.reviews:
            raise AssertionError(f'no scripted review for {key}')
        return self.reviews[key]


class ContentPipelineIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / '整片.mp4'
        scenes = [('red', 6), ('blue', 6), ('green', 8), ('yellow', 10), ('magenta', 10)]
        command = ['ffmpeg', '-v', 'error']
        for name, seconds in scenes:
            command += ['-f', 'lavfi', '-i', f'color=c={name}:s=90x160:r=10:d={seconds}']
        command += ['-filter_complex', '[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0[v]',
                    '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)]
        m.run(command)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def service(self):
        batches = {
            0.0: {'overview': '红色、蓝色、绿色场景依次出现',
                  'requirements': REQUIREMENTS,
                  'segments': [
                      {'start': 2.0, 'end': 3.2, 'facts': '红色场景操作', 'reason': '完整动作', 'decision': 'keep'},
                      {'start': 5.0, 'end': 9.5, 'facts': '蓝色场景长动作', 'reason': '完整但超长', 'decision': 'keep'},
                      {'start': 12.0, 'end': 19.98, 'facts': '绿色场景贴边动作', 'reason': '可能跨窗', 'decision': 'keep'},
                  ]},
            16.0: {'overview': '绿色到黄色场景',
                   'segments': [
                       {'start': 18.5, 'end': 19.5, 'facts': '绿色场景收尾', 'reason': '动作完整', 'decision': 'keep'},
                       {'start': 25.0, 'end': 26.0, 'facts': '黄色场景细节', 'reason': '细节可用', 'decision': 'keep'},
                   ]},
            32.0: {'overview': '品红场景',
                   'segments': [
                       {'start': 37.0, 'end': 38.0, 'facts': '品红场景动作', 'reason': '动作可用', 'decision': 'keep'},
                       {'start': 34.0, 'end': 35.2, 'decision': 'keep'},
                   ]},
        }
        reviews = {
            (2.0, 3.2): review(),
            (5.0, 9.5): review(reason='完整动作共4.5秒，不截断'),
            (12.0, 19.98): review(reason='动作延伸到窗口边缘'),
            (18.5, 19.5): review(start=18.4, end=19.9, reason='密集帧显示动作从18.4开始、19.9结束'),
            (25.0, 26.0): review(assessment={'base': dict(BASE_PASS),
                                             'user': [{'id': 'H1', 'result': 'unknown'},
                                                      {'id': 'E1', 'result': 'pass'}]}),
            (37.0, 38.0): review(start=31.0, end=38.0, reason='试图把区间扩到窗口外'),
            # A keep without facts/reason must not become an unexportable clip.
            (34.0, 35.2): {'decision': 'keep', 'boundary_reviewed': True,
                           'assessment': {'base': dict(BASE_PASS),
                                          'user': [{'id': 'H1', 'result': 'pass'},
                                                   {'id': 'E1', 'result': 'pass'}]}},
        }
        return FakeVisionService(batches, reviews)

    def prepare_task(self, name):
        root = self.root / name
        c.prepare(Namespace(video=self.video, request='找出完整动作，排除严重遮挡', output=root))
        config = root / 'vision.fake.json'
        m.save(config, {'base_url': 'http://127.0.0.1:9/v1', 'model': 'fake-vision'})
        return root, root / 'task.json', config

    def run_api(self, task_path, config, service):
        with patch('urllib.request.build_opener', service.build_opener), \
                patch.dict(os.environ, {'VISION_API_KEY': 'offline-test-only'}):
            v.analyze(Namespace(task=str(task_path), config=str(config), allow_paid=True))

    def test_simulated_api_to_dense_review_to_split_export(self):
        root, path, config = self.prepare_task('pipeline')
        service = self.service()
        self.run_api(path, config, service)
        task = m.read(path)

        # Batch framing: three overlapping windows, real frames attached to each call.
        self.assertEqual([(b['start'], b['end']) for b in m.read(root / 'api-analysis.json')['batches']],
                         [(0.0, 20.0), (16.0, 36.0), (32.0, 40.0)])
        batch_calls = [row for row in service.calls if row['kind'] == 'batch']
        self.assertEqual([row['images'] for row in batch_calls], [10, 10, 4])
        review_calls = [row for row in service.calls if row['kind'] == 'review']
        self.assertEqual(len(review_calls), 7)
        self.assertTrue(all(row['images'] >= 3 for row in review_calls))
        self.assertTrue(list((root / 'vision-cache').glob('*.json')))
        self.assertTrue((root / 'api-progress.json').is_file())

        segments = {s['id']: s for s in task['segments']}
        self.assertEqual(list(segments), ['S0001', 'S0002', 'S0003', 'S0004', 'S0005', 'S0006', 'S0007'])
        self.assertEqual(task['requirements']['confirmed'], True)
        self.assertEqual([row['id'] for row in task['requirements']['hard']], ['H1'])
        self.assertEqual([row['id'] for row in task['requirements']['exclusions']], ['E1'])
        self.assertTrue(task['analysis']['reviewed'])

        self.assertEqual(segments['S0001']['decision'], 'keep')
        self.assertEqual(segments['S0001']['requirement_match'], 'match')
        self.assertEqual(segments['S0002']['decision'], 'keep')

        # Dense review may correct a boundary, but the original interval stays on record.
        corrected = segments['S0004']
        self.assertEqual((corrected['start'], corrected['end']), (18.4, 19.9))
        self.assertEqual((corrected['original_start'], corrected['original_end']), (18.5, 19.5))
        self.assertEqual(corrected['boundary_history'][0]['from'], [18.5, 19.5])
        self.assertEqual(corrected['boundary_history'][0]['to'], [18.4, 19.9])
        self.assertTrue(corrected['boundary_corrected'])
        self.assertTrue(all(18.4 <= e['time'] <= 19.9 for e in corrected['evidence']))
        self.assertEqual(len(corrected['evidence']), 12)

        # A correction outside the observed window is refused, never extrapolated.
        rejected = segments['S0006']
        self.assertEqual((rejected['start'], rejected['end']), (37.0, 38.0))
        self.assertEqual(rejected['decision'], 'uncertain')
        self.assertIn('已观察区间', rejected['review_reason'])
        self.assertNotIn('boundary_corrected', rejected)

        self.assertEqual(segments['S0003']['decision'], 'uncertain')
        self.assertIn('边缘', segments['S0003']['review_reason'])
        # Hard condition unknown blocks keep before export, not after.
        self.assertEqual(segments['S0005']['decision'], 'uncertain')
        self.assertIn('H1', segments['S0005']['review_reason'])
        self.assertEqual(segments['S0005']['requirement_match'], 'unknown')
        # A keep without facts cannot become a clip that fails at export time.
        self.assertEqual(segments['S0007']['decision'], 'uncertain')
        self.assertIn('事实', segments['S0007']['review_reason'])

        # Export: only verified 1-4s clips; long and unresolved candidates stay for humans.
        task['rights']['usage'] = 'allowed'
        m.save(path, task)
        c.extract(Namespace(task=path))
        manifest = m.read(root / 'extraction.json')
        self.assertEqual([row['id'] for row in manifest['clips']], ['S0001', 'S0004'])
        self.assertEqual([row['id'] for row in m.read(root / 'manual-review.json')['segments']], ['S0002'])
        self.assertEqual([row['id'] for row in m.read(root / 'uncertain-review.json')['segments']],
                         ['S0003', 'S0005', 'S0006', 'S0007'])
        self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')
        for row, colour in zip(manifest['clips'], [0, 1]):
            info = m.probe(row['output'])
            self.assertTrue(1 <= m.media_duration(info, 'video') <= 4)
            pixels = subprocess.run(['ffmpeg', '-v', 'error', '-i', row['output'], '-frames:v', '1',
                                     '-vf', 'scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                                    capture_output=True, check=True).stdout
            self.assertGreater(pixels[colour], 120)
        self.assertTrue(Path(m.read(root / 'manual-review.json')['segments'][0]['review_video']).is_file())

        # Human backfill resolves the unknown hard condition and re-exports.
        decisions = root / 'decisions.json'
        decisions.write_text(json.dumps([{
            'id': 'S0005', 'decision': 'keep', 'boundary_reviewed': True,
            'user': [{'id': 'H1', 'result': 'pass', 'reason': '人工逐帧看过'},
                     {'id': 'E1', 'result': 'pass'}],
            'note': '人工补看黄色场景'}], ensure_ascii=False), encoding='utf-8')
        c.review_segments(Namespace(task=path, decisions=str(decisions), reviewer='tester'))
        self.assertEqual([row['id'] for row in m.read(root / 'extraction.json')['clips']],
                         ['S0001', 'S0004', 'S0005'])
        self.assertTrue(list((root / 'history').glob('task-*.json')))
        self.assertEqual(m.read(root / 'review-log.json')['entries'][-1]['reviewer'], 'tester')

        # Manual re-selection on the window-edge candidate exports the new interval only.
        selections = root / 'selections.json'
        selections.write_text(json.dumps([{
            'id': 'S0003', 'start': 13.0, 'end': 14.2, 'decision': 'keep',
            'reason': '贴边动作实际在13.0–14.2完成'}], ensure_ascii=False), encoding='utf-8')
        c.reselect_segments(Namespace(task=path, selections=str(selections)))
        final = m.read(root / 'extraction.json')['clips']
        self.assertEqual([row['id'] for row in final], ['S0001', 'S0003', 'S0004', 'S0005'])
        moved = next(s for s in m.read(path)['segments'] if s['id'] == 'S0003')
        self.assertEqual((moved['original_start'], moved['original_end']), (12.0, 19.98))
        self.assertEqual(moved['boundary_history'][0]['to'], [13.0, 14.2])
        self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')
        self.assertEqual([row['id'] for row in m.read(root / 'manual-review.json')['segments']], ['S0002'])

    def test_analyze_refuses_to_overwrite_existing_judgements(self):
        root, path, config = self.prepare_task('guarded')
        service = self.service()
        self.run_api(path, config, service)
        with self.assertRaisesRegex(ValueError, '任务已有镜头判断'):
            self.run_api(path, config, service)

    def test_paid_gate_blocks_analysis_without_flag(self):
        root, path, config = self.prepare_task('gated')
        service = self.service()
        with patch('urllib.request.build_opener', service.build_opener), \
                patch.dict(os.environ, {'VISION_API_KEY': 'offline-test-only'}):
            with self.assertRaisesRegex(ValueError, 'allow-paid'):
                v.analyze(Namespace(task=str(path), config=str(config), allow_paid=False))
        self.assertEqual(service.calls, [])
        self.assertEqual(m.read(path)['segments'], [])


if __name__ == '__main__':
    unittest.main()
