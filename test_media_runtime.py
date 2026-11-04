import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent / '.workbench-deps'))
import montage
import hypit_adapter


class MediaRuntimeTest(unittest.TestCase):
    def test_encode_probe_extract_and_hypit_evidence(self):
        with tempfile.TemporaryDirectory(prefix='media smoke ') as folder:
            root = Path(folder)
            source = root / 'reference.mp4'
            montage.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=180x320:rate=30:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', source])
            self.assertEqual(montage.portrait_geometry(montage.probe(source))['display_ratio'], '9:16')
            output = root / 'clip.mp4'
            montage.run(['ffmpeg', '-v', 'error', '-i', source, '-ss', '0.25', '-t', '1', '-c:v', 'libx264', output])
            montage.run(['ffmpeg', '-v', 'error', '-i', output, '-f', 'null', '-'])
            hypit_adapter.analyze(SimpleNamespace(video=str(source), output=str(root/'hypit'), hypit=None, start=0, end=2, every=1, overview_frames=4, cell=180, columns=2))
            self.assertTrue((root/'hypit/manifest.json').is_file())
            self.assertTrue((root/'hypit/overview.jpg').is_file())

    def test_scanned_pdf_render(self):
        from pypdf import PdfWriter
        from workbench.pdf_pages import render_pdf
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=300)
            writer.write(root/'scan.pdf')
            render_pdf(root/'scan.pdf', root/'pages')
            self.assertTrue((root/'pages/page-001.jpg').is_file())
