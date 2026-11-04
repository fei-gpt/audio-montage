import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from workbench.backend import Workbench
from workbench.knowledge import knowledge_archive


class KnowledgePackageTest(unittest.TestCase):
    def test_text_only_archive_and_reuse_without_original_files_or_api(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder),executor=False)
            p=app.create_product('原产品');q=app.create_product('新产品')
            p['profile']={'understood_at':'test','appearance':['蓝色玩具'],'claims':[{'text':'发光','source_id':'original-image'}],'references':['original-image'],'unknowns':['声音未确认']}
            app.store.put('product','root',p)
            with zipfile.ZipFile(io.BytesIO(knowledge_archive(p))) as archive:
                self.assertEqual(archive.namelist(),['product-knowledge.md','product-knowledge.json'])
                self.assertIn('蓝色玩具',archive.read('product-knowledge.md').decode('utf-8'))
            with patch('vision_api.call',side_effect=AssertionError('unexpected API')):
                app.reference_knowledge(q['id'],[p['id']])
                app.reference_knowledge(q['id'],[p['id']])
                result=app.understand(q['id'],False)
            sources=app.store.all('source',q['id'])
            self.assertEqual(len(sources),1)
            self.assertEqual(sources[0]['kind'],'knowledge')
            self.assertNotIn('image',sources[0]);self.assertNotIn('path',sources[0])
            self.assertEqual(result['appearance'],['蓝色玩具'])
            self.assertEqual(result['unknowns'],['声音未确认'])
            self.assertEqual(result['claims'][0]['source_id'],sources[0]['id'])
