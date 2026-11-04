import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hypit_adapter as h


class HypitRangeTest(unittest.TestCase):
    def test_probe_precision_is_clamped_and_shorter_ranges_preserved(self):
        self.assertEqual(h._analysis_range(3.733,0,3.733333),(0,3.733))
        self.assertEqual(h._analysis_range(3.733,1,2.25),(1,2.25))
        self.assertEqual(h._analysis_range(3.733),(0,3.733))
        self.assertEqual(h._analysis_range(3.734,0,3.733333),(0,3.733333))
    def test_invalid_ranges_are_not_silently_accepted(self):
        for duration,start,end in [(3.733,0,4),(3.733,-1,2),(3.733,3.7331,3.7333),(3.733,1,1),(0,0,1),(3.733,0,float('nan')),(3.733,float('inf'),4)]:
            with self.assertRaises(ValueError):h._analysis_range(duration,start,end)
    def test_all_sampling_commands_use_the_same_valid_range(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input.mp4';source.write_bytes(b'fixture');output=root/'evidence';commands=[]
            def run(command,cwd=None):
                commands.append(command)
                return json.dumps({'duration':3.733}) if command[2]=='probe' else '{}'
            args=SimpleNamespace(video=str(source),output=str(output),hypit='test',start=0,end=3.733333,every=1,overview_frames=12,cell=180,columns=4)
            with patch.object(h,'_hypit_command',return_value='test'),patch.object(h,'_run',side_effect=run):h._analyze(args)
            sampled=[x for x in commands if x[2] in {'frames','tile','tiles'}]
            self.assertEqual(len(sampled),3)
            for command in sampled:self.assertEqual(command[command.index('--end')+1],'3.733')
            manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['requested_range']['end'],3.733333)
            self.assertEqual(manifest['range']['end'],3.733)
