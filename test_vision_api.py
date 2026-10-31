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
