import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from montage import fingerprint
from workbench.reference import analyze

class ReferenceTests(unittest.TestCase):
    def test_reference_version_and_invalid_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'video.mp4';source.write_bytes(b'source')
            upload={'path':str(source),'sha256':fingerprint(source),'duration':1}
            app=SimpleNamespace(wroot=lambda w:root/w,config=lambda:{'model':'test'})
            def render(args,**kw):Path(args[-1]).write_bytes(b'frame')
            beat={'start':0,'end':1,'purpose':'演示','subject':'产品','action':'旋转','composition':'近景'}
            with patch('workbench.reference.subprocess.run',side_effect=render),patch('vision_api.call',return_value={'beats':[beat]}):
                result=analyze(app,'A',upload,False)
                self.assertFalse(result['boundaries_verified'])
                self.assertTrue((root/'A'/'reference-evidence').is_dir())
            with patch('vision_api.call',return_value={'beats':[dict(beat,end=2)]}),self.assertRaisesRegex(ValueError,'区间无效'):analyze(app,'A',upload,False)
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'已改变'):analyze(app,'A',upload,False)

    def test_reference_length_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a';source.write_bytes(b'a')
            with self.assertRaisesRegex(ValueError,'120秒'):
                analyze(None,'A',{'path':str(source),'sha256':fingerprint(source),'duration':121},False)
