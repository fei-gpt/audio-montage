"""Real media/account isolation tests. Model calls are mocked; no paid calls."""
import base64, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'.workbench-deps'))
from workbench.backend import Workbench, Problem, validate_reference_url
from workbench.server import make_server

class WorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.video=Path(cls.media.name)/'clip.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=90x160:r=30:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(cls.video)],check=True)
    @classmethod
    def tearDownClass(cls):cls.media.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.app=Workbench(self.root/'state',executor=False)
        self.p=self.app.create_product('产品');self.w=self.app.create_workspace(self.p['id'],'相同账号名称');self.b=self.app.create_workspace(self.p['id'],'相同账号名称')
        self.a_dir=self.root/'A';self.a_dir.mkdir();shutil.copy2(self.video,self.a_dir/'same.mp4')
        self.b_dir=self.root/'B';self.b_dir.mkdir();shutil.copy2(self.video,self.b_dir/'same.mp4')
    def tearDown(self):self.tmp.cleanup()
    def attach(self,w=None,kind='raw',path=None):
        w=w or self.w;path=path or self.a_dir
        self.app.attach_library(self.p['id'],w['id'],str(path),kind);self.app.scan(self.p['id'],w['id'])
        return self.app.store.all('asset',w['id'])[0]
    def test_account_isolation_identical_names_and_hashes(self):
        a=self.attach();b=self.attach(self.b,path=self.b_dir)
        self.assertEqual(a['sha256'],b['sha256']);self.assertNotEqual(a['id'],b['id'])
        self.assertTrue((self.app.wroot(self.w['id'])/'index.sqlite').exists())
        with self.assertRaises(Problem):self.app.store.get('asset',a['id'],self.b['id'])
        with self.assertRaises(Problem):self.app.media(self.p['id'],self.b['id'],'asset',a['id'],self.app.media_signature(self.p['id'],self.b['id'],'asset',a['id']))
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.b['id'],['nonexistent'])
    def test_folder_parent_child_symlink_and_hardlink_rejected(self):
        self.attach()
        for path in [self.a_dir,self.root,self.a_dir/'sub']:
            path.mkdir(exist_ok=True)
            with self.assertRaises(Problem):self.app.attach_library(self.p['id'],self.b['id'],str(path),'raw')
        alias=self.root/'alias'
        try:alias.symlink_to(self.a_dir,target_is_directory=True)
        except OSError as exc:
            if getattr(exc,'winerror',None)==1314:self.skipTest('Windows symbolic-link privilege unavailable')
            raise
        with self.assertRaises(Problem):self.app.attach_library(self.p['id'],self.b['id'],str(alias),'raw')
        os.link(self.a_dir/'same.mp4',self.b_dir/'hardlink.mp4')
        self.app.attach_library(self.p['id'],self.b['id'],str(self.b_dir),'raw');scan=self.app.scan(self.p['id'],self.b['id'])
        self.assertEqual(len(scan['errors']),1);self.assertEqual(scan['count'],1)
    def test_incremental_missing_version_and_symlink_escape(self):
        a=self.attach();self.app.scan(self.p['id'],self.w['id']);self.assertEqual(len(self.app.store.all('asset',self.w['id'])),1)
        self.app.store.put('shot',self.w['id'],{'asset_id':a['id'],'stale':False})
        (self.a_dir/'same.mp4').unlink();self.app.scan(self.p['id'],self.w['id']);self.assertFalse(self.app.store.get('asset',a['id'],self.w['id'])['available'])
        try:(self.a_dir/'escape.mp4').symlink_to(self.b_dir/'same.mp4')
        except OSError as exc:
            if getattr(exc,'winerror',None)==1314:self.skipTest('Windows symbolic-link privilege unavailable')
            raise
        scan=self.app.scan(self.p['id'],self.w['id']);self.assertTrue(scan['errors'])
        shutil.copy2(self.video,self.a_dir/'same.mp4');self.app.scan(self.p['id'],self.w['id']);self.assertTrue(self.app.store.all('shot',self.w['id'])[0]['stale'])
    def test_default_codex_and_local_env_loader(self):
        from workbench.server import load_local_env
        self.assertEqual(self.app.config()['model'],'gpt-6-luna')
        self.assertEqual(self.app.config()['provider'],'codex')
        env=self.root/'local-env';env.write_text('DEEPSEEK_API_KEY="local-test"\nHOME=/bad\nVISION_API_KEY=$(touch bad)\n')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'existing-test'}):
            home=os.environ.get('HOME');load_local_env(env)
            self.assertEqual(os.environ['DEEPSEEK_API_KEY'],'existing-test')
            self.assertEqual(os.environ.get('HOME'),home)
            self.assertEqual(os.environ['VISION_API_KEY'],'$(touch bad)')
        with self.assertRaises(Problem):self.app.set_config({'base_url':'https://api.deepseek.com','model':'deepseek-reasoner'})

    def test_no_config_does_not_call_model_or_fake_completion(self):
        self.attach()
        self.app.set_config({'provider':'codex','model':'gpt-6-luna'})
        with patch('workbench.backend.shutil.which',return_value=None):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True)
        self.assertEqual(j['status'],'requires_configuration');self.assertEqual(j['progress'],0)
        with patch('workbench.backend.shutil.which',return_value=None),self.assertRaises(Problem):self.app.resume(self.p['id'],self.w['id'],j['id'],True)
    def test_restart_and_migration_stay_unassigned(self):
        old={'products':[{'id':'old','name':'旧产品','sources':[{'name':'x.mp4'}],'shots':[{'id':'s','decision':'keep'}]}],'tasks':[{'productId':'old','name':'旧任务'}],'exports':[]}
        imported=self.app.migrate(old);self.assertFalse(imported['already_imported']);self.assertTrue(self.app.migrate(old)['already_imported'])
        p=imported['products'][0];w=self.app.store.all('workspace',p)[0];self.assertFalse(w['assigned']);self.assertEqual(w['legacy_snapshot']['shots'][0]['decision'],'keep')
        with self.assertRaises(Problem):self.app.create_job(p,w['id'],'organize',True)
        with self.assertRaises(Problem):self.app.export(p,w['id'],['s'])
        job=self.app.store.put('job',self.w['id'],{'scope':self.w['id'],'status':'running','done':['checkpoint'],'kind':'organize'})
        restored=Workbench(self.root/'state',executor=False);self.assertEqual(restored.store.get('job',job['id'],self.w['id'])['status'],'interrupted');self.assertEqual(restored.store.get('job',job['id'],self.w['id'])['done'],['checkpoint'])
    def test_pdf_pages_and_bad_link(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject,NameObject,DictionaryObject
        writer=PdfWriter()
        for i in range(2):
            page=writer.add_blank_page(width=300,height=200);stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 20 60 Td (Product page {i+1}) Tj ET'.encode())
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})});page[NameObject('/Contents')]=writer._add_object(stream)
        out=io.BytesIO();writer.write(out)
        s=self.app.add_source(self.p['id'],{'name':'guide.pdf','data':base64.b64encode(out.getvalue()).decode()})
        self.assertEqual(len(s['pages']),2);self.assertIn('Product page 2',s['pages'][1]['text'])
        with patch('workbench.backend.fetch_reference',side_effect=Problem('网页被拦截')):
            s=self.app.add_source(self.p['id'],{'url':'https://www.amazon.com/item'});self.assertEqual(s['status'],'failed');self.assertIn('拦截',s['error'])
    def test_image_reference_and_source_bound_product_understanding(self):
        image=self.root/'image.jpg'
        subprocess.run(['ffmpeg','-v','error','-i',str(self.video),'-frames:v','1','-y',str(image)],check=True)
        source=self.app.add_source(self.p['id'],{'name':'product.jpg','data':base64.b64encode(image.read_bytes()).decode()})
        self.assertEqual(source['status'],'awaiting_understanding');self.assertTrue(Path(source['image']).is_file())
        answer={'suggested_name':'红色产品','appearance':['红色'],'claims':[{'text':'包装声称发光','source_id':source['id'],'page':None}],'demonstrations':['展示颜色'],'unknowns':['型号未知'],'conflicts':[],'references':[source['id']]}
        with patch('vision_api.call',return_value=answer):profile=self.app.understand(self.p['id'],True)
        self.assertEqual(profile['sources'][0]['id'],source['id']);self.assertEqual(self.app.store.get('source',source['id'],self.p['id'])['status'],'understood')
        self.app.store.put('source',self.p['id'],{'kind':'link','name':'new reference','text':'new information','status':'awaiting_understanding'})
        answer=dict(answer,claims=[{'text':'捏造来源','source_id':'missing'}])
        with patch('vision_api.call',return_value=answer),self.assertRaises(Problem):self.app.understand(self.p['id'],True)

    def test_public_reference_text_and_no_paid_consent(self):
        from email.message import Message
        from workbench.backend import fetch_reference
        headers=Message();headers['Content-Type']='text/html; charset=utf-8'
        response=io.BytesIO(('<html><h1>Product page</h1><p>'+('Description and specifications. '*10)+'</p><script>untrusted script</script></html>').encode());response.headers=headers;response.url='https://www.amazon.com/product'
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            result=fetch_reference('https://www.amazon.com/product')
        self.assertIn('Product page',result['text']);self.assertNotIn('untrusted script',result['text'])
        self.attach();self.app.set_config({'base_url':'http://localhost:9999/v1','model':'fake','api_key_env':'WB_TEST_KEY'})
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}):j=self.app.create_job(self.p['id'],self.w['id'],'organize',False)
        self.assertEqual(j['status'],'requires_consent');self.assertEqual(j['progress'],0)

    def test_url_blocks_private_network_and_bad_domains(self):
        for url in ['http://www.amazon.com/x','https://amazon.com.evil.test/x','https://127.0.0.1/x','file:///etc/passwd','https://user:pass@www.amazon.com/x']:
            with self.assertRaises(Problem):validate_reference_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(Problem):validate_reference_url('https://www.amazon.com/x')
    def test_real_raw_pipeline_review_and_export(self):
        self.attach();self.app.set_config({'base_url':'http://127.0.0.1:9999/v1','model':'fake-vision','api_key_env':'WB_TEST_KEY'})
        base={'content_legibility':'pass','temporal_integrity':'pass','technical_usability':'pass','evidence_sufficiency':'pass'}
        def model(config,prompt,evidence,cache,allow):
            self.assertTrue(allow)
            if '先通览产品展示意图' in prompt:return {'subject':'红色物体','intent':'展示颜色','visible_result':'红色可见','unknowns':[]}
            if '返回 {"overview"' in prompt:return {'overview':'红色静态展示','requirements':{'hard':[],'preferences':[],'exclusions':[],'confirmed':True},'segments':[{'start':.1,'end':1.7,'facts':'红色画面','reason':'展示色彩','decision':'keep'}]}
            return {'facts':'红色画面','reason':'展示色彩','decision':'keep','boundary_reviewed':True,'assessment':{'base':base,'user':[]}}
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}),patch('vision_api.call',side_effect=model),patch('hypit_adapter.analyze'):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True,rights=True);self.app.run_job(j['id'],self.w['id'])
        j=self.app.store.get('job',j['id'],self.w['id']);self.assertEqual(j['status'],'awaiting_review',j.get('error'))
        shots=self.app.store.all('shot',self.w['id']);self.assertEqual(len(shots),1);shot=shots[0]
        with self.assertRaises(Problem):self.app.review(self.p['id'],self.b['id'],shot['id'],{'decision':'keep','content_confirmed':True})
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.w['id'],[shot['id']])
        self.app.review(self.p['id'],self.w['id'],shot['id'],{'decision':'keep','content_confirmed':True})
        result=self.app.export(self.p['id'],self.w['id'],[shot['id']]);self.assertTrue(Path(result['files'][0]['path']).is_file())
        with self.assertRaises(Problem):self.app.export(self.p['id'],self.b['id'],[shot['id']])
    def test_prepared_clips_remain_whole(self):
        self.attach(kind='prepared');self.app.set_config({'base_url':'http://localhost:9999/v1','model':'fake','api_key_env':'WB_TEST_KEY'})
        def model(config,prompt,evidence,cache,allow):
            if '先通览产品展示意图' in prompt:return {'subject':'红色','intent':'色彩','visible_result':'红色','unknowns':[]}
            if '返回 {"overview"' in prompt:return {'overview':'红色','requirements':{},'segments':[]}
            return {}
        with patch.dict(os.environ,{'WB_TEST_KEY':'fake'}),patch('vision_api.call',side_effect=model),patch('hypit_adapter.analyze'):
            j=self.app.create_job(self.p['id'],self.w['id'],'organize',True);self.app.run_job(j['id'],self.w['id'])
        shots=self.app.store.all('shot',self.w['id']);self.assertEqual(len(shots),1);self.assertEqual(shots[0]['start'],0);self.assertAlmostEqual(shots[0]['end'],2);self.assertEqual(shots[0]['review_decision'],'uncertain')

class HTTPIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=make_server(Path(self.tmp.name)/'state',0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.server.app.pool.shutdown(wait=True);self.tmp.cleanup()
    def request(self,path,body=None,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Workbench-Token']=self.server.token
        if origin:headers['Origin']=origin
        return urllib.request.urlopen(urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5)
    def test_api_token_origin_and_cross_product(self):
        for token,origin in [(False,None),(True,'https://evil.test')]:
            with self.assertRaises(urllib.error.HTTPError) as cm:self.request('/api/state',token=token,origin=origin)
            self.assertEqual(cm.exception.code,403)
        p=json.load(self.request('/api/products',{'name':'P'}));q=json.load(self.request('/api/products',{'name':'Q'}))
        w=json.load(self.request(f"/api/products/{p['id']}/workspaces",{'name':'A'}))
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request(f"/api/products/{q['id']}/workspaces/{w['id']}/scan",{})
        self.assertEqual(cm.exception.code,404)
        with self.assertRaises(urllib.error.HTTPError):self.request('/%2e%2e/backend.py',token=False)
    def test_media_range_and_account_forgery(self):
        a=self.server.app;p=a.create_product('P');w=a.create_workspace(p['id'],'A');b=a.create_workspace(p['id'],'B')
        folder=Path(self.tmp.name)/'media';folder.mkdir();file=folder/'x.mp4';file.write_bytes(b'0123456789')
        lib=a.attach_library(p['id'],w['id'],str(folder),'raw')
        from workbench.backend import digest
        asset=a.store.put('asset',w['id'],{'library_id':lib['id'],'path':str(file),'sha256':digest(file)})
        sig=a.media_signature(p['id'],w['id'],'asset',asset['id']);path=f"/api/products/{p['id']}/workspaces/{w['id']}/media/asset/{asset['id']}?sig={sig}"
        req=urllib.request.Request(self.url+path,headers={'Range':'bytes=2-5'})
        with urllib.request.urlopen(req) as response:self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345')
        with self.assertRaises(urllib.error.HTTPError):self.request(path.replace(w['id'],b['id']),token=False)

if __name__=='__main__':unittest.main()
