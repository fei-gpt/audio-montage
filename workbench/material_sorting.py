"""Review action intervals on original footage and publish confirmed clips."""
import math
import random
import shutil
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from hypit_adapter import _hypit_command, _json_output, _run
from montage import media_duration, probe
from product_display import FOUR_SWORD_FAULT_PROMPT, four_sword_fault, uses_light_sword_categories
from recognition_schema import array, obj
from video_document import document_path, write_document
from workbench.backend import Problem, digest, uid

MIN_CLIP_SECONDS = 1
MAX_CLIP_SECONDS = 4
MIN_SPLIT_SECONDS = 1.5
publish_lock = threading.Lock()


def interval(start, end, duration):
    if not all(type(x) in (int, float) and math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration:
        raise Problem('请核对片段起止秒数，结束位置须在原片内')
    return start, end


def split_pending(rows, source_hash):
    """Vary cut lengths while keeping retries reproducible and reserving a usable tail."""
    result = []
    for row in rows:
        start, end = row['start'], row['end']
        if row['status'] == 'pending' and end < start + MIN_CLIP_SECONDS:
            continue
        if row['status'] != 'pending' or end <= start + MAX_CLIP_SECONDS:
            result.append(row)
            continue
        rng = random.Random(f'{source_hash}:{float(start).hex()}:{float(end).hex()}')
        left = start
        while end > left + MAX_CLIP_SECONDS:
            upper = min(MAX_CLIP_SECONDS, end - left - MIN_SPLIT_SECONDS)
            right = round(left + rng.uniform(MIN_SPLIT_SECONDS, upper), 9)
            result.append(dict(row, id=row['id'] if left == start else uid(), start=left, end=right))
            left = right
        result.append(dict(row, id=uid(), start=left, end=end))
    return result


def detect(app, w, asset, product):
    from vision_api import call
    path = app.asset_path(w, asset['id'])
    categories = product.get('shot_categories', [])
    sword = uses_light_sword_categories(product) or product['name'].casefold() in {'toy','lightplay'}
    fault_field = {'light_out':{'type':'boolean'}} if sword else {}
    schema = obj(segments=array(obj(start={'type':'number'}, end={'type':'number'},
                                    labels=array({'type':'string'}), evidence={'type':'string'},
                                    continues_before={'type':'boolean'}, continues_after={'type':'boolean'}, **fault_field)))
    config = app.config()
    if config.get('provider') != 'codex':
        raise Problem('请在识别服务设置中配置 Codex 视觉模型')
    with TemporaryDirectory(prefix='material-sort-') as tmp:
        folder = Path(tmp)
        src = folder / ('source' + path.suffix.lower())
        shutil.copyfile(path, src)
        if digest(src) != asset['sha256']:
            raise Problem('原片已变化，请重新扫描')
        cli = _hypit_command(None)
        info = _json_output(_run([cli,'media','probe',src.name,'--json'],cwd=tmp,timeout=90))
        frame = 1 / float(info['frameRate'])
        duration = min(asset['duration'], float(info['duration']))
        result = []
        for offset in range(0, math.ceil(duration), 24):
            stop = min(duration, offset + 24)
            if stop - offset < frame:break
            grids = folder / str(offset)
            _run([cli,'media','tiles',src.name,'--start',str(offset),'--end',str(max(offset,stop-frame)),
                  '--every','0.5','--columns','3' if sword else '6','--rows','3' if sword else '4','--cell','440' if sword else '200','--to',grids.name],cwd=tmp,timeout=300)
            pages = sorted(grids.glob('*.jpg'))
            if not pages:raise Problem('Hypit 未取得可读画面')
            prompt = (f'按图上原片绝对时码识别 {product["name"]} 在 {offset} 至 {stop:.4f} 秒内可独立剪用的完整展示。'
                      f'当前产品类别为 {categories}。有类别时仅从中选；尚未设置类别时用简短中文描述可见的展示动作。'
                      '无法归类返回空标签。排除等待、失焦和遮挡；按动作或真实切镜分段，'
                      '连续动作中的颜色变化不另切。每段返回绝对起止秒数、可见依据、标签；窗口截断同一动作时标注'
                      'continues_before/continues_after。没有可用画面返回空数组。')
            if sword:
                prompt += FOUR_SWORD_FAULT_PROMPT + '故障段也必须在 segments 单列返回，并标记四把旋转标签。'
                prompt += '区分单把绕指旋转和四把连接同一中心旋转，不能根据拖影或同框数量猜测。'
            response = call(config,prompt,[dict(time=offset,path=str(page)) for page in pages],
                            app.wroot(w)/'sorting-cache'/asset['sha256'],True,output_schema=schema)
            for row in response['segments']:
                # The prompt displays four decimals. Its rounded endpoint can be
                # fractionally later than the probed last timestamp.
                end = row['end']
                if type(end) in (int,float) and end > stop and end == round(stop,4):
                    end = stop
                start,end = interval(row['start'],end,stop)
                if start < offset or result and start < result[-1]['end']:
                    raise Problem('模型返回的动作区间重叠或越界，请人工补段')
                labels = list(dict.fromkeys(x for x in row['labels'] if isinstance(x,str) and 0<len(x)<=40 and (not categories or x in categories)))
                status = 'fault' if sword and four_sword_fault(labels,row['light_out'],product) else 'pending'
                if (result and result[-1]['status']==status and row['continues_before'] and result[-1]['continues_after']
                        and start-offset <= .5 and 0 <= offset-result[-1]['end'] <= .5
                        and set(labels)==set(result[-1]['labels'])):
                    result[-1].update(end=end,continues_after=row['continues_after'])
                else:
                    result.append(dict(id=uid(), start=start,end=end,labels=labels,reason=row['evidence'],
                                       continues_after=row['continues_after'],status=status))
    return split_pending(result, asset['sha256'])


def start(app,p,w,body):
    if not app.workspace(p,w)['assigned']:raise Problem('请先分配账号')
    aid = body.get('asset_id')
    with app.lock:
        asset = app.store.get('asset',aid,w)
        app.asset_path(w,aid,check_hash=False)
        if asset['kind']!='raw':raise Problem('请选择原始视频')
        existing = next((r for r in app.store.all('sorting',w) if
                         r['asset_id']==aid and r['sha256']==asset['sha256']),None)
        if existing and not (body.get('retry') is True and existing['status']=='failed'
                                 and not existing['segments']):return existing
        if body.get('allow_paid') is not True:raise Problem('请允许本次画面识别')
        job = app.store.put('sorting',w,dict(workspace_id=w,asset_id=aid,sha256=asset['sha256'],
                            name=asset['name'],status='running',segments=[],**({'id':existing['id']} if existing else {})))
    def process():
        try:
            segments = detect(app,w,asset,app.product(p))
            app.asset_path(w,aid)
            job.update(segments=segments,status='ready')
        except Exception as exc:
            job.update(status='failed',error=str(exc)[:700])
        app.store.put('sorting',w,job)
    if app.pool:app.pool.submit(process)
    else:process()
    return job


def review(app,p,w,jid,body):
    if not app.workspace(p,w)['assigned']:raise Problem('请先分配账号')
    with publish_lock:
        job = app.store.get('sorting',jid,w)
        if job['status']=='running':raise Problem('请等待本次识别结束',409)
        source = app.store.get('asset',job['asset_id'],w)
        if source['sha256']!=job['sha256']:raise Problem('原片已替换，请重新整理',409)
        app.asset_path(w,source['id'])
        sid = body.get('segment_id')
        row = next((r for r in job['segments'] if r['id']==sid),None)
        if sid and row is None:raise Problem('片段不存在',404)
        def skip_short():
            if sid:
                row.update(status='skipped',skip_reason='不足 1 秒')
                app.store.put('sorting',w,job)
            return dict(app.store.get('sorting',jid,w),skipped_short=True)
        if row and row['status']=='fault':raise Problem('此区间为四把旋转熄灯故障镜头')
        if row and row['status']!='pending':
            return dict(job,skipped_short=row.get('skip_reason')=='不足 1 秒')
        if body.get('decision')=='skip' and row:
            row['status']='skipped'
            return app.store.put('sorting',w,job)
        if body.get('decision')!='confirm':raise Problem('请选择确认或跳过')
        start,end = interval(body.get('start'),body.get('end'),source['duration'])
        if any(r['status']=='fault' and start<r['end'] and end>r['start'] for r in job['segments']):
            raise Problem('选区包含四把光剑旋转时的熄灯故障，请调整起止时间')
        if end < start + MIN_CLIP_SECONDS:return skip_short()
        labels = body.get('labels')
        categories = app.product(p).get('shot_categories',[])
        if (not isinstance(labels,list) or len(labels)>30 or any(not isinstance(x,str) or not 0<len(x)<=40
                or categories and x not in categories for x in labels) or categories and not labels):
            raise Problem('请选择当前产品的展示类别')
        for other in job['segments']:
            if other['status']=='confirmed' and start<other['end'] and end>other['start']:
                if (start,end,labels)==(other['start'],other['end'],other['labels']):return job
                raise Problem('该区间与已入库片段重叠')
        if not row:
            row=dict(id=uid(),reason='人工补段')
            job['segments'].append(row)
        if end > start + MAX_CLIP_SECONDS:
            pieces = split_pending([dict(row,start=start,end=end,labels=labels,status='pending')], source['sha256'])
            # A repeated manual submission may already have created these intervals.
            expected = {(piece['start'],piece['end']) for piece in pieces}
            present = {(item['start'],item['end']) for item in job['segments']
                       if 'start' in item and item['labels']==labels}
            if expected <= present:return app.store.get('sorting',jid,w)
            index = job['segments'].index(row)
            job['segments'][index:index+1] = pieces
            return app.store.put('sorting',w,job)
        aid = uid()
        shot = dict(id=uid(),asset_id=source['id'],asset_sha256=source['sha256'],start=start,end=end,
                    facts=row['reason'],human_confirmed=True,review_decision='keep')
        root = app.wroot(w)/'整理片段'
        root.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=app.wroot(w)) as tmp:
            exported = app.export_shots(w,[shot],Path(tmp),max_duration=MAX_CLIP_SECONDS)[0]
            clip = Path(exported['path'])
            info = probe(clip)
            duration = media_duration(info,'video')
            if duration < MIN_CLIP_SECONDS:return skip_short()
            if duration > MAX_CLIP_SECONDS:raise Problem('实际片段超过 4 秒，请缩短选区后重试')
            stream = next(x for x in info['streams'] if x['codec_type']=='video')
            doc = write_document(clip,exported['sha256'],complete=True,context={'visual_details':{'display_categories':labels}})
            dest = root / f'{Path(source["name"]).stem[:65]}-{start:.2f}-{end:.2f}-{aid[:8]}.mp4'
            with app.lock:
                library = next((l for l in app.store.all('library',w) if l['path']==str(root)),None)
                if not library:library=dict(id=uid(),workspace_id=w,path=str(root),name='整理片段',kind='prepared')
                asset=dict(id=aid,workspace_id=w,library_id=library['id'],kind='prepared',available=True,version=1,
                           name=dest.name,path=str(dest),sha256=exported['sha256'],duration=duration,
                           width=stream['width'],height=stream['height'],origin_sha256=source['sha256'],
                           origin_asset_id=source['id'],source_start=start,source_end=end,
                           user_category=dict(labels=labels,status='已确认类别',confirmed=True))
                shot.update(asset_id=aid,asset_sha256=asset['sha256'],start=0,end=duration,
                            safe_trim_ranges=[dict(start=0,end=duration)],visual_details={'display_categories':labels})
                row.update(start=start,end=end,labels=labels,status='confirmed',asset_id=aid)
                target_doc=document_path(dest)
                try:
                    clip.replace(dest)
                    Path(doc).replace(target_doc)
                    app.store.put_many(w,[('library',library),('asset',asset),('shot',shot),('sorting',job)])
                except Exception:
                    dest.unlink(missing_ok=True)
                    target_doc.unlink(missing_ok=True)
                    raise
        return job
