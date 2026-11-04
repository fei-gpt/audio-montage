import tempfile
import unittest
from pathlib import Path
from workbench.backend import Workbench, Problem


class SourceReuseTest(unittest.TestCase):
    def test_reference_preserves_origin_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'state',executor=False)
            p=app.create_product('Original');q=app.create_product('Target')
            file=app.root/'image.png';file.write_bytes(b'original')
            original=app.store.put('source',p['id'],{'name':'image.png','kind':'image','status':'understood','path':str(file),'image':str(file),'pages':[]})
            selections=[{'product_id':p['id'],'source_id':original['id']}]
            result=app.reference_sources(q['id'],selections*2)
            self.assertEqual(result['count'],1)
            linked=result['sources'][0]
            self.assertNotEqual(linked['id'],original['id'])
            self.assertEqual(linked['reference']['source_id'],original['id'])
            self.assertEqual(linked['status'],'awaiting_understanding')
            app.reference_sources(q['id'],selections)
            self.assertEqual(len(app.store.all('source',q['id'])),1)
            self.assertEqual(app.store.get('source',original['id'],p['id']),original)
            self.assertEqual(file.read_bytes(),b'original')
            self.assertFalse(app.product(q['id'])['profile'])

    def test_missing_or_forged_batch_does_not_partially_import(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'state',executor=False)
            p=app.create_product('P');q=app.create_product('Q')
            source=app.store.put('source',p['id'],{'name':'link','kind':'link','status':'understood'})
            with self.assertRaises(Problem):
                app.reference_sources(q['id'],[{'product_id':p['id'],'source_id':source['id']},{'product_id':q['id'],'source_id':source['id']}])
            self.assertEqual(app.store.all('source',q['id']),[])
