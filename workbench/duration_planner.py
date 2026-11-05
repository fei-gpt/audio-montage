"""Local duration-only planning; never reads transcript text or calls a model."""
import math

def plan_by_duration(candidates, timeline, duration, used=(), max_nodes=20000):
    total=math.ceil(duration*30-1e-7)
    boundaries=sorted({min(total,max(0,math.ceil(s['end']*30-1e-7))) for s in timeline['segments']}|{total})
    budgets=[];previous=0
    for boundary in boundaries:
        if boundary>previous:budgets.append(boundary-previous);previous=boundary
    nodes=0
    def overlap(c,start,end,occupied):
        return any(c['asset_sha256']==x['asset_sha256'] and min(end,x['end'])-max(start,x['start'])>1e-6 for x in occupied)
    def search(index,remaining,parts,occupied):
        nonlocal nodes
        nodes+=1
        if nodes>max_nodes:return None
        if index==len(budgets):return parts
        if remaining==0:return search(index+1,budgets[index+1] if index+1<len(budgets) else 0,parts,occupied)
        options=[]
        for c in candidates:
            choices=[(c['start'],c['frames'])]
            for r in c.get('safe_trim_ranges',[]):
                starts=[r['start']]+[x['end'] for x in occupied if x['asset_sha256']==c['asset_sha256'] and r['start']<=x['end']<r['end']]
                for start in starts:
                    frames=min(remaining,math.floor((r['end']-start)*30+1e-6))
                    choices.append((start,frames))
            for start,frames in set(choices):
                if not 0<frames<=remaining:continue
                end=start+frames/30
                if c.get('action_start') is not None and (start>c['action_start']+1e-6 or end<c['action_end']-1e-6):continue
                if overlap(c,start,end,occupied):continue
                part={'shot_id':c['id'],'asset_sha256':c['asset_sha256'],'start':start,'end':end,'frames':frames,'reason':'按实际断句时长匹配，不作语义匹配'}
                options.append(part)
        options.sort(key=lambda x:(x['frames']!=remaining,-x['frames'],x['shot_id']))
        for part in options:
            result=search(index,remaining-part['frames'],parts+[part],occupied+[part])
            if result is not None:return result
        return None
    result=search(0,budgets[0] if budgets else 0,[],list(used))
    if not result:raise ValueError('现有素材或安全裁切范围无法在搜索范围内匹配断句时长，请补充素材或确认安全裁切范围')
    return {'parts':result,'matching_mode':'duration','gaps':[]}
