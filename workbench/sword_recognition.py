"""Suggest product categories for newly scanned lightplay and toy footage."""
import json
import math
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from hypit_adapter import _hypit_command, _json_output, _run
from montage import fingerprint
from product_display import FOUR_SWORD_FAULT_PROMPT, four_sword_fault
from recognition_schema import array, obj


def recognize(app,w,asset,product):
    from vision_api import call
    categories=product.get('shot_categories')
    if not categories:raise ValueError('产品缺少光剑类别标准，请先关联光剑产品资料')
    config=app.config()
    if config.get('provider')!='codex':raise ValueError('光剑自动归类需要配置 Codex 视觉识别服务')
    path=app.asset_path(w,asset['id'])
    duration=asset['duration']
    cli=_hypit_command(None)
    with TemporaryDirectory(prefix='sword-tiles-') as tmp:
        folder=Path(tmp)
        source=folder/('source'+path.suffix.lower())
        shutil.copyfile(path,source)
        if fingerprint(source)!=asset['sha256']:raise ValueError('取帧时素材版本发生变化，请重新扫描')
        probe=_json_output(_run([cli,'media','probe',source.name,'--json'],cwd=tmp,timeout=90))
        fps=float(probe['frameRate'])
        if not math.isfinite(fps) or fps<=0:raise ValueError('无法读取视频帧率')
        end=max(0,min(duration,float(probe['duration']))-1/fps)
        if end<=0:raise ValueError('可读取的视频帧太少')
        _run([cli,'media','tiles',source.name,'--start','0','--end',str(end),'--every',str(max(1/fps,end/47)),
              '--columns','3','--rows','3','--cell','440','--to','grids'],cwd=tmp,timeout=300)
        pages=sorted((folder/'grids').glob('*.jpg'))
        if not pages:raise ValueError('Hypit 未返回可读取的画面')
        labels={'type':'string','enum':categories}
        schema=obj(labels=array(labels),uncertain={'type':'boolean'},reason={'type':'string'},
                   rotation_ranges=array(obj(label=labels,light_out={'type':'boolean'},start={'type':'number'},end={'type':'number'})))
        prompt=('按图中时码顺序归类光剑素材。优先判断实际旋转的是单把剑绕指孔，还是四把剑连接同一中心旋转。'
                '多把同框、多人持剑、灯色或拖影条数不能证明四把合体。合体静置或仅调整摆姿不能算旋转。'
                '分别记录可辨认的旋转区间（秒），不能将前后静态段算入。如果结构或运动看不清，将 uncertain 设为 true。'
                '其他标签仅在该动作构成可独立剪用的展示时填写。明确没有旋转但有其他展示时可正常分类。'
                '没有可确定的类别时返回空标签。reason 用中文简述可见依据或不确定原因。可选类别为'
                +json.dumps(categories,ensure_ascii=False)+f'。素材总时长 {duration:.3f} 秒。')
        result=call(config,prompt+FOUR_SWORD_FAULT_PROMPT,[dict(time=0,path=str(page)) for page in pages],
                    app.wroot(w)/'sword-recognition'/asset['sha256'],True,output_schema=schema)
    tags=result['labels'];ranges=result['rotation_ranges']
    if (not isinstance(tags,list) or any(x not in categories for x in tags) or type(result['uncertain'])!=bool
            or not isinstance(ranges,list) or not isinstance(result['reason'],str)):
        raise ValueError('模型返回的标签或判断格式无效')
    from product_display import LIGHT_SWORD_ROTATIONS
    aliases=product.get('shot_category_aliases',{})
    rotation_labels={aliases.get(label,label) for group in LIGHT_SWORD_ROTATIONS.values() for label in group}
    for r in ranges:
        if (r['label'] not in tags or r['label'] not in rotation_labels
                or not all(type(r[k]) in (int,float) for k in ('start','end'))
                or not 0<=r['start']<r['end']<=duration+.001):raise ValueError('模型返回的旋转区间无效')
    if (rotation_labels.intersection(tags)-{r['label'] for r in ranges}):
        raise ValueError('旋转标签缺少可核对的动作时段')
    faults=[r for r in ranges if four_sword_fault([r['label']],r['light_out'],product)]
    return dict(fault_ranges=faults,labels=list(dict.fromkeys(tags)),ranges=ranges,reason=result['reason'][:500],
                status='unrecognized' if result['uncertain'] or not tags else 'suggested')


def run(app,p,w,aid,sha):
    with app.lock:
        a=app.store.get('asset',aid,w)
        if (not a['available'] or a['sha256']!=sha or a.get('user_category')
                or a.get('sword_recognition',{}).get('status')!='queued'):return
        a['sword_recognition']={'status':'running'}
        app.store.put('asset',w,a)
    try:
        result=recognize(app,w,a,app.product(p))
        app.asset_path(w,aid)
    except Exception as exc:
        result=dict(status='unrecognized',reason=str(exc)[:500] or type(exc).__name__,labels=[],ranges=[])
    with app.lock:
        current=app.store.get('asset',aid,w)
        if current['sha256']!=sha or current.get('user_category') or not current['available']:return
        if any(label not in app.product(p).get('shot_categories',[]) for label in result['labels']):
            result.update(status='unrecognized',reason='识别期间类别标准已更改，请核对',labels=[],ranges=[])
        current['sword_recognition']=result
        if result['labels']:
            current['category_review']=dict(labels=result['labels'],confirmed=False,status='Hypit 建议，待确认',evidence=result['reason'])
        app.store.put('asset',w,current)
