import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import elevenlabs_adapter as e
from montage import save


class ElevenLabsOfflineTest(unittest.TestCase):
    def test_character_alignment_preserves_word_times(self):
        result = {'alignment': {'characters': list('Hi all'),
                  'character_start_times_seconds': [0, .1, .2, .4, .5, .6],
                  'character_end_times_seconds': [.1, .2, .3, .5, .6, .8]}}
        words = e.aligned_words(result, 'tts', 'en')
        self.assertEqual([w['text'] for w in words], ['Hi ', 'all'])
        self.assertEqual(words[1]['start'], .4)
        self.assertEqual(words[1]['end'], .8)

    def test_paid_gate_makes_no_network_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'allow-paid'):
                e.request(Path(tmp), 'speech-to-text', {}, None, False)
            network.assert_not_called()

    def test_cached_response_needs_no_key_or_network(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.build_opener') as network:
            root = Path(tmp)
            signature = {'endpoint': 'forced-alignment', 'fields': {'text': 'Hello'}, 'audio_sha256': None}
            digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
            save(root / 'audio/elevenlabs-cache' / (digest + '.json'), {'words': []})
            result, actual = e.request(root, 'forced-alignment', {'text': 'Hello'}, None, False)
            self.assertEqual(actual, digest)
            self.assertEqual(result, {'words': []})
            network.assert_not_called()

    def test_transcription_and_alignment(self):
        for mode in ['transcribe', 'align']:
            words = e.aligned_words({'words': [{'text': 'Hello', 'start': .2, 'end': .8}]}, mode, 'en')
            self.assertEqual(words[0]['start'], .2)
            self.assertEqual(words[0]['text'], 'Hello ')

    def test_simultaneous_identical_requests_send_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from io import BytesIO
        import json
        fields={'text':'Hello'}
        ready=Barrier(2)
        serialize=json.dumps
        def wait_before_submission(value,*args,**kwargs):
            if value is fields:ready.wait(timeout=5)
            return serialize(value,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.build_opener') as network:
            network.return_value.open.side_effect=lambda *a,**kw:BytesIO(b'{"words":[]}')
            def submit():return e.request(Path(tmp),'forced-alignment',fields,None,True,'test-key')
            with patch.object(json,'dumps',side_effect=wait_before_submission),ThreadPoolExecutor(2) as pool:
                jobs=[pool.submit(submit) for _ in range(2)]
                for job in jobs:
                    try:result,_=job.result()
                    except ValueError as exc:self.assertIn('已有尝试记录',str(exc))
                    else:self.assertEqual(result,{'words':[]})
            self.assertEqual(submit()[0],{'words':[]})
            network.return_value.open.assert_called_once()
