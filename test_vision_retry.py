import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import vision_api as v


class RetryTest(unittest.TestCase):
    def test_explicit_retry_archives_only_matching_receipt(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, VISION_API_KEY='test-only'):
            cache=Path(folder)
            config={'base_url':'http://localhost:9999/v1','model':'fake'}
            with patch('urllib.request.build_opener') as network:
                network.return_value.open.side_effect=TimeoutError()
                with self.assertRaises(ValueError):v.call(config,'test',[],cache,True)
            receipt=next(cache.glob('*.attempt.json'))
            self.assertEqual(json.loads(receipt.read_text())['error_type'],'TimeoutError')
            with patch('urllib.request.build_opener') as network:
                with self.assertRaisesRegex(ValueError,'重新发送'):v.call(config,'test',[],cache,True)
                network.assert_not_called()
            token=v.retry_incomplete.set(True)
            try:
                with patch('urllib.request.build_opener') as network:
                    network.return_value.open.return_value=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]}).encode())
                    self.assertEqual(v.call(config,'test',[],cache,True),{})
                self.assertEqual(len(list((cache/'attempt-history').glob('*.json'))),1)
            finally:v.retry_incomplete.reset(token)
            with patch('urllib.request.build_opener') as network:
                self.assertEqual(v.call(config,'test',[],cache,False),{})
                network.assert_not_called()
