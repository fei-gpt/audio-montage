import base64, io, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'.workbench-deps'))
from pypdf import PdfWriter
from workbench.backend import Workbench


class PdfUploadTest(unittest.TestCase):
    def test_repeated_upload_and_failed_retry_keep_one_record(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(folder,executor=False);p=app.create_product('PDF test')
            pdf=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(pdf)
            body={'name':'test.pdf','data':base64.b64encode(pdf.getvalue()).decode()}
            first=app.add_source(p['id'],body)
            self.assertEqual(first['status'],'awaiting_understanding')
            self.assertEqual(len(first['pages']),1)
            self.assertEqual(app.add_source(p['id'],body)['id'],first['id'])
            first.update(status='failed',error='old error');app.store.put('source',p['id'],first)
            restored=app.add_source(p['id'],body)
            self.assertEqual(restored['id'],first['id'])
            self.assertEqual(restored['status'],'awaiting_understanding')
            self.assertNotIn('error',restored)
            self.assertEqual(len(app.store.all('source',p['id'])),1)
