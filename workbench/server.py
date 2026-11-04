"""Loopback-only HTTP API. All account media operations use nested scoped routes."""
import argparse, base64, hashlib, json, mimetypes, os, re, secrets, subprocess, sys, urllib.parse
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO));sys.path.insert(0,str(REPO/'.workbench-deps'))
from runtime_environment import configure
configure()
from workbench.backend import Workbench, Problem
STATIC=Path(__file__).parent/'static'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def json(self,obj,status=200):
        data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def guard(self):
        host=self.headers.get('Host','')
        if host not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:raise Problem('无效本地主机',403)
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:raise Problem('不允许跨站访问',403)
    def token(self):
        import hmac
        if not hmac.compare_digest(self.headers.get('X-Workbench-Token',''),self.server.token):raise Problem('请从本机工作台打开操作',403)
    @property
    def app(self):return self.server.app
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def do_PATCH(self):self.handle_request('PATCH')
    def handle_request(self,method):
        try:
            self.guard();url=urllib.parse.urlsplit(self.path);path=url.path
            media=re.fullmatch(r'/api/products/([a-f0-9]+)/workspaces/([a-f0-9]+)/media/(asset|export)/([a-f0-9-]+)',path)
            if media and method=='GET':
                p,w,k,ident=media.groups();sig=urllib.parse.parse_qs(url.query).get('sig',[''])[0];return self.serve_file(self.app.media(p,w,k,ident,sig))
            if not path.startswith('/api/'):
                if method!='GET':raise Problem('方法不允许',405)
                name=urllib.parse.unquote(path).lstrip('/') or 'index.html';file=(STATIC/name).resolve()
                if STATIC.resolve() not in file.parents:raise Problem('路径不存在',404)
                if name=='index.html':
                    data=file.read_text(encoding='utf-8').replace('/*BOOTSTRAP*/',f'window.WORKBENCH_TOKEN={json.dumps(self.server.token)};').encode('utf-8');return self.serve_bytes(data,'text/html; charset=utf-8')
                return self.serve_file(file)
            self.token();body={}
            if method!='GET':
                length=int(self.headers.get('Content-Length','0'))
                if length>45_000_000:raise Problem('请求文件过大',413)
                body=json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body,dict):raise Problem('请求需要对象')
            package=re.fullmatch(r'/api/products/([a-f0-9]+)/knowledge.zip',path)
            if package and method=='GET':
                from workbench.knowledge import knowledge_archive
                product=self.app.product(package[1])
                if not product.get('profile',{}).get('understood_at'):raise Problem('产品尚无已理解的文字语料')
                return self.serve_bytes(knowledge_archive(product),'application/zip',f'product-{package[1][:8]}-knowledge.zip')
            return self.json(self.route(method,path,body,urllib.parse.parse_qs(url.query)))
        except Problem as exc:self.json({'error':str(exc)},exc.status)
        except (ValueError,KeyError,TypeError,IndexError) as exc:self.json({'error':'参数或记录无效：'+str(exc)[:500]},400)
        except BrokenPipeError:pass
        except Exception as exc:self.json({'error':str(exc)[:1200]},500)
    def route(self,method,path,b,q):
        app=self.app;s=app.store
        if path=='/api/state' and method=='GET':
            products=s.all('product','root')
            for p in products:
                p.update(app.product(p['id']))
                p['sources']=s.all('source',p['id']);p['jobs']=s.all('job',p['id']);p['workspaces']=s.all('workspace',p['id'])
                for w in p['workspaces']:
                    w.update(libraries=s.all('library',w['id']),assets=s.all('asset',w['id']),shots=s.all('shot',w['id']),jobs=s.all('job',w['id']),exports=s.all('export',w['id']))
                    w['assets']=app.visible_assets(w['id'])
                    for a in w['assets']:a['media_url']=self.media_url(p['id'],w['id'],'asset',a['id'])
                    for e in w['exports']:
                        for i,f in enumerate(e['files']):f['media_url']=self.media_url(p['id'],w['id'],'export',e['id']+'-'+str(i))
            return {'products':products,'capabilities':app.status()}
        if path=='/api/settings' and method=='POST':return app.set_config(b)
        if path=='/api/products' and method=='POST':return app.create_product(b.get('name',''))
        if path=='/api/migrate' and method=='POST':return app.migrate(b)
        if path=='/api/choose-folder' and method=='POST':
            from workbench.folder_picker import choose_folder
            return choose_folder(b.get('initial',''))
        m=re.fullmatch(r'/api/products/([a-f0-9]+)(?:/(.*))?',path)
        if not m:raise Problem('接口不存在',404)
        p,tail=m.groups();app.product(p)
        if not tail and method=='PATCH':
            obj=app.product(p)
            for field in ['name','extra_request']:
                if field in b:obj[field]=str(b[field]).strip()[:10000]
            if not obj['name']:raise Problem('产品名称不能为空')
            return s.put('product','root',obj)
        if tail=='sources' and method=='POST':return app.add_source(p,b)
        if tail=='sources/reference' and method=='POST':return app.reference_sources(p,b.get('selections'))
        if tail=='knowledge/reference' and method=='POST':return app.reference_knowledge(p,b.get('product_ids'))
        if tail=='understand' and method=='POST':return app.create_job(p,None,'understand',b.get('allow_paid'))
        if tail=='workspaces' and method=='POST':return app.create_workspace(p,b.get('name',''))
        if tail and tail.startswith('jobs/') and tail.endswith('/resume') and method=='POST':return app.resume(p,None,tail.split('/')[1],b.get('allow_paid'),b.get('retry_failed',False))
        m=re.fullmatch(r'workspaces/([a-f0-9]+)(?:/(.*))?',tail or '')
        if not m:raise Problem('接口不存在',404)
        w,rest=m.groups();ws=app.workspace(p,w)
        if not rest and method=='PATCH':
            if b.get('name'):ws['name']=str(b['name']).strip()[:100]
            if b.get('assigned') is True:ws['assigned']=True
            return s.put('workspace',p,ws)
        if rest=='libraries' and method=='POST':return app.attach_library(p,w,b.get('path',''),b.get('kind'))
        if rest=='scan' and method=='POST':return app.scan(p,w)
        if rest=='start' and method=='POST':return app.create_job(p,w,'organize',b.get('allow_paid'),b.get('request',''),b.get('rights_allowed'),b.get('asset_ids'))
        if rest and rest.startswith('jobs/') and rest.endswith('/resume') and method=='POST':return app.resume(p,w,rest.split('/')[1],b.get('allow_paid'),b.get('retry_failed',False))
        if rest=='search' and method=='GET':
            query=q.get('q',[''])[0].lower();return {'shots':[x for x in s.all('shot',w) if query in (x.get('facts','')+' '+x.get('reason','')).lower() and not x.get('stale')]}
        if rest and rest.startswith('shots/') and method=='PATCH':return app.review(p,w,rest.split('/')[1],b)
        if rest=='export' and method=='POST':return app.export(p,w,b.get('shot_ids',[]))
        raise Problem('接口不存在',404)
    def media_url(self,p,w,kind,ident):return f'/api/products/{p}/workspaces/{w}/media/{kind}/{ident}?sig='+self.app.media_signature(p,w,kind,ident)
    def serve_bytes(self,data,type_,filename=None):
        self.send_response(200);self.send_header('Content-Type',type_);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(data)
    def serve_file(self,path):
        if not path.is_file():raise Problem('文件不存在',404)
        size=path.stat().st_size;start=0;end=size-1;status=200
        if self.headers.get('Range'):
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
            if not match:raise Problem('Range无效',416)
            left,right=match.groups()
            if left:start=int(left);end=min(int(right),end) if right else end
            elif right:start=max(0,size-int(right))
            else:raise Problem('Range无效',416)
            if start>end or start>=size:raise Problem('Range越界',416)
            status=206
        self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start);remaining=end-start+1
            while remaining:
                chunk=f.read(min(65536,remaining))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)

def make_server(root,port=8767):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.token=secrets.token_urlsafe(32);server.app=Workbench(root);return server

def load_local_env(path):
    """Read only named credentials, never execute shell content or replace process values."""
    if not path.exists(): return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        key,sep,value=line.partition('=')
        key=key.strip();value=value.strip()
        if key not in {'DEEPSEEK_API_KEY','VISION_API_KEY','HYPIT_BIN'} or not sep: continue
        if len(value)>1 and value[0]==value[-1] and value[0] in {'"', "'"}: value=value[1:-1]
        if value: os.environ.setdefault(key,value)


def main():
    load_local_env(REPO/'.env.workbench')
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8766);parser.add_argument('--data',default=str(REPO/'.workbench-data'));args=parser.parse_args()
    server=make_server(args.data,args.port);print(f'素材工作台 http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.app.pool.shutdown(wait=False,cancel_futures=True);server.server_close()

if __name__=='__main__':main()
