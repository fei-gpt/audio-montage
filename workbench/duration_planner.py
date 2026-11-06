"""Local duration-only planning; never reads transcript text or calls a model."""
import math
import random
import re
from pathlib import Path

def numeric_order(name):
    found=re.search(r"(\d+)$",Path(name or "").stem)
    return int(found[1]) if found else None

def ascending(previous,current):
    a=numeric_order(previous);b=numeric_order(current)
    return a is not None and b is not None and b==a+1


def compact_number_run(names):
    """Three successive different clips from five neighboring numbers in one series."""
    recent=[]
    for name in names:
        match=re.fullmatch(r'(.*?)(\d+)',Path(name or '').stem.casefold())
        if not match:
            recent.clear()
            continue
        prefix,number=match.groups()
        if recent and recent[-1][0]!=prefix:recent.clear()
        recent=(recent+[(prefix,int(number))])[-3:]
        numbers={n for _,n in recent}
        if len(numbers)==3 and max(numbers)-min(numbers)<=4:return True
    return False


def plan_by_duration(candidates, timeline, duration, used=(), max_nodes=20000, accept=None, seed=None, ending_counts=None, batch_counts=None,free_selection=False):
    rng=random.Random(seed)
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
        if index==len(budgets):return parts if accept is None or accept(parts) else None
        if remaining==0:return search(index+1,budgets[index+1] if index+1<len(budgets) else 0,parts,occupied)
        options=[]
        for c in candidates:
            if parts and ascending(parts[-1].get('source_name'),c.get('name')):continue
            if not free_selection and len(parts)>=2 and compact_number_run([parts[-2]['source_name'],parts[-1]['source_name'],c.get('name')]):continue
            choices=[(c['start'],c['frames'])]
            for r in c.get('safe_trim_ranges',[]):
                available_frames=math.floor((r['end']-r['start'])*30+1e-6)
                slack=max(0,available_frames-min(remaining,available_frames))
                offsets={rng.randint(0,slack) for _ in range(min(8,slack+1))}
                offsets.update(range(1,min(5,slack)+1))
                starts=[r['start']]+[r['start']+n/30 for n in offsets]+[x['end'] for x in occupied if x['asset_sha256']==c['asset_sha256'] and r['start']<=x['end']<r['end']]
                for start in starts:
                    frames=min(remaining,math.floor((r['end']-start)*30+1e-6))
                    choices.append((start,frames))
            for start,frames in set(choices):
                if not 0<frames<=remaining:continue
                end=start+frames/30
                if c.get('action_start') is not None and (start>c['action_start']+1e-6 or end<c['action_end']-1e-6):continue
                if overlap(c,start,end,occupied):continue
                part={'source_name':c.get('name',''),'shot_id':c['id'],'asset_sha256':c['asset_sha256'],'start':start,'end':end,'frames':frames,'reason':'从可用素材随机选取并匹配实际断句时长，不作语义匹配'}
                options.append(part)
        # Search all valid choices in random order, never filename/ID/length order.
        rng.shuffle(options)
        if ending_counts and index==len(budgets)-1:
            # Preserve random order among tied choices. Try alternatives before
            # finishing on a frequently used ending, including multi-shot fits.
            options.sort(key=lambda p: ending_counts.get(p['asset_sha256'],0) if p['frames']==remaining else 0)
        if batch_counts:
            options.sort(key=lambda part: batch_counts.get(part['asset_sha256'],0))
        if free_selection:
            counts={c['asset_sha256']:c.get('usage_count',0)+(batch_counts or {}).get(c['asset_sha256'],0) for c in candidates}
            options.sort(key=lambda part:counts[part['asset_sha256']])
            used_sources={p['asset_sha256'] for p in parts}
            options=[p for p in options if p['asset_sha256'] not in used_sources]
        for part in options:
            result=search(index,remaining-part['frames'],parts+[part],occupied+[part])
            if result is not None:return result
        return None
    result=search(0,budgets[0] if budgets else 0,[],list(used))
    if not result:raise ValueError('现有素材或安全裁切范围无法在搜索范围内匹配断句时长，请补充素材或确认安全裁切范围')
    return {'parts':result,'matching_mode':'duration','gaps':[]}
