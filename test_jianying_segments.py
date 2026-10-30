import unittest
from jianying_segments import isolate


class SegmentIsolationTest(unittest.TestCase):
    def test_isolation_preserves_source_trim_and_effects(self):
        data = {'duration': 9000000, 'tracks': [
            {'id': 'v', 'type': 'video', 'segments': [
                {'id': 'a', 'source_timerange': {'start': 2000000, 'duration': 3000000},
                 'target_timerange': {'start': 5000000, 'duration': 3000000},
                 'extra_material_refs': ['effect'], 'speed': 1}]},
            {'id': 'audio', 'type': 'audio', 'segments': [{'id': 'music'}]}]}
        result = isolate(data)
        child = result[0][2]
        self.assertEqual(child['duration'], 3000000)
        self.assertEqual(len(child['tracks']), 1)
        self.assertEqual(child['tracks'][0]['segments'][0]['source_timerange']['start'], 2000000)
        self.assertEqual(child['tracks'][0]['segments'][0]['target_timerange']['start'], 0)
        self.assertEqual(child['tracks'][0]['segments'][0]['extra_material_refs'], ['effect'])
        self.assertEqual(data['tracks'][0]['segments'][0]['target_timerange']['start'], 5000000)

    def test_multiple_tracks_require_choice(self):
        tracks = [{'id': str(i), 'type': 'video', 'segments': [{'id': str(i),
                   'target_timerange': {'start': 0, 'duration': 1000}}]} for i in range(2)]
        with self.assertRaises(ValueError):
            isolate({'tracks': tracks})
        self.assertEqual(len(isolate({'tracks': tracks}, '1')), 1)
