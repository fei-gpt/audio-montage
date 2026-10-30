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
