import tempfile
import unittest
from pathlib import Path
from workbench.backend import Workbench


class VisibleAssetsTest(unittest.TestCase):
    def test_deleted_and_foreign_assets_are_hidden_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            app=Workbench(root/'state',executor=False)
            product=app.create_product('P')
            account=app.create_workspace(product['id'],'A')['id']
            other=app.create_workspace(product['id'],'B')['id']
            library=root/'media';library.mkdir()
            lib=app.attach_library(product['id'],account,str(library),'prepared')
            file=library/'clip.mp4';file.write_bytes(b'test')
            asset=app.store.put('asset',account,{'library_id':lib['id'],'path':str(file),'available':True})
            self.assertEqual([a['id'] for a in app.visible_assets(account)],[asset['id']])
            self.assertEqual(app.visible_assets(other),[])
            file.unlink()
            self.assertEqual(app.visible_assets(account),[])
            self.assertEqual(app.store.get('asset',asset['id'],account)['id'],asset['id'])
            outside=root/'outside.mp4';outside.write_bytes(b'test')
            app.store.put('asset',account,dict(asset,path=str(outside)))
            self.assertEqual(app.visible_assets(account),[])
