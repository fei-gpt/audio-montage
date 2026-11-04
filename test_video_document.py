import json
import shutil
import tempfile
import unittest
from pathlib import Path
from montage import fingerprint
from video_document import document_path, load_document, write_document


class VideoDocumentTest(unittest.TestCase):
    def test_move_and_change_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'clip.mp4';source.write_bytes(b'video')
            digest=fingerprint(source)
            path=write_document(source,digest,context={'visual_details':{'background':'白色毛毯','shot_size':'特写'}},segments=[{'evidence':[{'time':1,'path':'C:/old/frame.jpg'}]}],complete=True)
            data=load_document(source)
            self.assertEqual(data['context']['visual_details']['background'],'白色毛毯')
            self.assertNotIn('C:/old/frame.jpg',path.read_text(encoding='utf-8'))
            moved=root/'moved';moved.mkdir()
            shutil.move(str(source),moved/source.name);shutil.move(str(path),moved/path.name)
            self.assertEqual(load_document(moved/source.name),data)
            (moved/source.name).write_bytes(b'changed')
            self.assertIsNone(load_document(moved/source.name))

    def test_hypit_update_keeps_existing_semantic_result(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'clip.mp4';source.write_bytes(b'video')
            digest=fingerprint(source)
            write_document(source,digest,context={'visual_details':{'background':'wood'}},complete=True)
            write_document(source,digest,hypit={'probe.json':{'duration':2}})
            self.assertTrue(load_document(source)['complete'])
            self.assertEqual(load_document(source)['hypit']['probe.json']['duration'],2)
