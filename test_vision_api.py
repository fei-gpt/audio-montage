import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import vision_api as v

class VisionAPITest(unittest.TestCase):
    def test_paid_gate_and_endpoint_restriction(self):
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.build_opener') as network:
            for base in ['https://example.com/v1', 'http://remote.example/v1']:
                with self.assertRaises(ValueError):
                    v.call({'base_url': base, 'model': 'vision'}, 'test', [], Path(tmp), False)
            network.assert_not_called()

    def test_compatible_payload_cache(self):
        import os
        import io
        import json
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'VISION_API_KEY': 'test-only'}):
            config = {'base_url': 'http://127.0.0.1:1234/v1', 'model': 'vision'}
            raw = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"segments":[]}'}}], 'usage': {'total_tokens': 10}}
            response = io.BytesIO(json.dumps(raw).encode())
            with patch('urllib.request.build_opener') as network:
                network.return_value.open.return_value = response
                self.assertEqual(v.call(config, 'test', [], Path(tmp), True), {'segments': []})
                request = network.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'http://127.0.0.1:1234/v1/chat/completions')
                self.assertEqual(json.loads(request.data)['model'], 'vision')
            with patch('urllib.request.build_opener') as network:
                self.assertEqual(v.call(config, 'test', [], Path(tmp), False), {'segments': []})
                network.assert_not_called()

    def test_overlap_has_single_owner_and_no_redundant_tail(self):
        windows = list(v.observation_windows(40))
        self.assertEqual([(a, b) for a, b, _, _ in windows], [(0, 20), (16, 36), (32, 40)])
        # The 19–22s action is fully visible in its owning batch.
        midpoint = 20.5
        owners = [(a, b) for a, b, left, right in windows if left <= midpoint < right]
        self.assertEqual(owners, [(16, 36)])
        self.assertEqual(list(v.observation_windows(20)), [(0, 20, 0, 20)])
        self.assertEqual(list(v.observation_windows(0)), [])

    def test_boundary_correction_must_stay_inside_observed_window(self):
        candidate = {'start': 18.5, 'end': 19.5}
        self.assertEqual(v.corrected_bounds(candidate, {}, 16, 36), (None, None))
        self.assertEqual(v.corrected_bounds(candidate, {'start': 18.5, 'end': 19.5}, 16, 36), (None, None))
        bounds, problem = v.corrected_bounds(candidate, {'start': 18.4, 'end': 19.9}, 16, 36)
        self.assertEqual(bounds, (18.4, 19.9))
        self.assertIsNone(problem)
        for payload in [{'start': 15.0, 'end': 19.9}, {'start': 18.4, 'end': 36.2},
                        {'start': 19.9, 'end': 18.4}, {'start': 18.4}, {'start': '18.4', 'end': 19.9}]:
            bounds, problem = v.corrected_bounds(candidate, payload, 16, 36)
            self.assertIsNone(bounds, payload)
            self.assertTrue(problem, payload)
        _, problem = v.corrected_bounds(candidate, {'start': 15.0, 'end': 19.9}, 16, 36)
        self.assertIn('已观察区间', problem)

    def test_dense_frames_stay_inside_the_interval(self):
        frames = v.dense_frames(Path('/tmp/frames'), 2.0, 3.2)
        self.assertEqual(len(frames), 12)
        self.assertEqual(frames[0]['time'], 2.0)
        self.assertTrue(all(2.0 <= row['time'] < 3.2 for row in frames))
        self.assertTrue(frames[0]['path'].endswith('2.000000.jpg'))

    def test_response_parsing_errors_are_explicit(self):
        import io
        import os
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'VISION_API_KEY': 'test-only'}):
            config = {'base_url': 'http://127.0.0.1:1234/v1', 'model': 'vision'}
            cases = [
                ({'choices': []}, '缺少 choices'),
                ({'choices': [{'finish_reason': 'stop', 'message': {'content': 'not json'}}]}, '有效 JSON'),
                ({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}, '未完整结束'),
                ({'choices': [{'finish_reason': 'stop', 'message': {'content': ''}}]}, '空内容'),
            ]
            for index, (raw, message) in enumerate(cases):
                with patch('urllib.request.build_opener') as network:
                    network.return_value.open.return_value = io.BytesIO(json.dumps(raw).encode())
                    # A failed attempt leaves a receipt, so each case needs its own cache.
                    with self.assertRaisesRegex(ValueError, message):
                        v.call(config, 'test', [], Path(tmp) / f'case{index}', True)
            fenced = {'choices': [{'finish_reason': 'stop', 'message': {'content': '```json\n{"segments": []}\n```'}}]}
            with patch('urllib.request.build_opener') as network:
                network.return_value.open.return_value = io.BytesIO(json.dumps(fenced).encode())
                self.assertEqual(v.call(config, 'fenced', [], Path(tmp) / 'fenced', True), {'segments': []})

    def test_missing_evidence_is_refused_before_the_request(self):
        import os
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'VISION_API_KEY': 'test-only'}):
            config = {'base_url': 'http://127.0.0.1:1234/v1', 'model': 'vision'}
            with patch('urllib.request.build_opener') as network:
                with self.assertRaisesRegex(ValueError, '证据图片缺失'):
                    v.call(config, 'test', [{'time': 1.0, 'path': str(Path(tmp) / 'gone.jpg')}], Path(tmp), True)
                network.assert_not_called()
