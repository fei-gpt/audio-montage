import tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from workbench.backend import Workbench,Problem
from workbench.product_template import validate,signature,prompt

class ProductTemplateTest(unittest.TestCase):
    def test_generate_confirm_and_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp),executor=False);p=app.create_product('收纳盒');p['profile']={'understood_at':'today','appearance':['白色盒体']};app.store.put('product','root',p)
            result={'summary':'收纳盒','dimensions':[{'id':'lid','label':'盒盖状态','values':['open','closed','unknown'],'evidence_rule':'看到盒盖位置'}]}
            with patch('vision_api.call',return_value=result):t=app.generate_template(p['id'],True)
            self.assertFalse(t['confirmed']);t=app.confirm_template(p['id'],{'id':t['id']});self.assertTrue(t['confirmed'])
            self.assertEqual(len(app.store.all('product_template',p['id'])),2)
            p=app.product(p['id']);p['extra_request']='只观察开盖';app.store.put('product','root',p)
            with self.assertRaises(Problem):app.confirm_template(p['id'],{'id':t['id']})
            self.assertIn('product_observations',prompt(t))
    def test_missing_product_info_and_invalid_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Workbench(Path(tmp),executor=False);p=app.create_product('新产品')
            with self.assertRaises(Problem):app.generate_template(p['id'],False)
        with self.assertRaises(ValueError):validate({'dimensions':[]})
