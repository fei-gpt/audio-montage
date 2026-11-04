import tempfile
import unittest
from pathlib import Path
from workbench.backend import Workbench, Problem


class SourceReuseTest(unittest.TestCase):
    def test_new_source_only_is_sent_to_model(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'state',executor=False)
            p=app.create_product('P')
            old=app.store.put('source',p['id'],{'name':'old.png','kind':'image','status':'understood','image':'missing-old-file.png'})
            p['profile']={'understood_at':'old','appearance':['existing knowledge'],'references':[old['id']]}
            app.store.put('product','root',p)
            new=app.store.put('source',p['id'],{'name':'new link','kind':'link','status':'awaiting_understanding','text':'new text'})
            response={key:[] for key in ('appearance','claims','demonstrations','unknowns','conflicts')}
            response.update(appearance=['new knowledge'],references=[new['id']])
            with patch('vision_api.call',return_value=response) as call:
                app.understand(p['id'],True)
                self.assertEqual(call.call_args.args[2],[])
                self.assertNotIn('old.png',call.call_args.args[1])
                self.assertIn('new text',call.call_args.args[1])
            self.assertEqual(app.product(p['id'])['profile']['appearance'],['existing knowledge','new knowledge'])

    def test_reference_preserves_origin_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'state',executor=False)
            p=app.create_product('Original');q=app.create_product('Target')
            file=app.root/'image.png';file.write_bytes(b'original')
            original=app.store.put('source',p['id'],{'name':'image.png','kind':'image','status':'understood','path':str(file),'image':str(file),'pages':[]})
            p['profile']={'understood_at':'test','appearance':['blue toy'],'claims':[{'text':'claim','source_id':original['id']}],'references':[original['id']]}
            app.store.put('product','root',p)
            selections=[{'product_id':p['id'],'source_id':original['id']}]
            result=app.reference_sources(q['id'],selections*2)
            self.assertEqual(result['count'],1)
            linked=result['sources'][0]
            self.assertNotEqual(linked['id'],original['id'])
            self.assertEqual(linked['reference']['source_id'],original['id'])
            self.assertEqual(linked['status'],'understood')
            app.reference_sources(q['id'],selections)
            self.assertEqual(len(app.store.all('source',q['id'])),1)
            self.assertEqual(app.store.get('source',original['id'],p['id']),original)
            self.assertEqual(file.read_bytes(),b'original')
            self.assertEqual(app.product(q['id'])['profile']['appearance'],['blue toy'])
            from unittest.mock import patch
            with patch('vision_api.call',side_effect=AssertionError('unexpected API')):
                reused=app.understand(q['id'],False)
                self.assertEqual(reused['claims'][0]['source_id'],linked['id'])

    def test_missing_or_forged_batch_does_not_partially_import(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'state',executor=False)
            p=app.create_product('P');q=app.create_product('Q')
            source=app.store.put('source',p['id'],{'name':'link','kind':'link','status':'understood'})
            with self.assertRaises(Problem):
                app.reference_sources(q['id'],[{'product_id':p['id'],'source_id':source['id']},{'product_id':q['id'],'source_id':source['id']}])
            self.assertEqual(app.store.all('source',q['id']),[])
