"""Local duration-only planning; never reads transcript text or calls a model."""
import math
import random
import re
from pathlib import Path

def available_frames_at_30fps(seconds):
    # ffprobe rounds durations to microseconds.
    return math.floor(seconds*30+0.00002)


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


def _batch_overlap_score(parts,history):
    """Each plan uses a source at most once in free selection mode."""
    current={p['asset_sha256']:p for p in parts}
    duration=sum(p['frames'] for p in parts)
    ratios=[]
    for other in history:
        shared=0
        for old in other:
            part=current.get(old['asset_sha256'])
            if part is not None:
                start=max(round(part['start']*30),round(old['start']*30))
                end=min(round(part['start']*30)+part['frames'],round(old['start']*30)+old['frames'])
                shared+=max(0,end-start)
        ratios.append(shared/min(duration,sum(p['frames'] for p in other)))
    endings=sum(parts[-1]['asset_sha256']==plan[-1]['asset_sha256'] for plan in history)
    return max(ratios,default=0),endings,sum(ratios)


def plan_by_duration(candidates, timeline, duration, used=(), max_nodes=20000, accept=None, seed=None, ending_counts=None, batch_counts=None,free_selection=False,batch_history=(),required_cuts=(),preferred_cuts=(),shot_priority=None,min_frames=1,prefer_full_slots=False,shot_allowed=None):
    rng=random.Random(seed)
    planned=batch_counts or {}
    usage_priority={
        c['asset_sha256']:(planned.get(c['asset_sha256'],0),c.get('usage_count',0))
        for c in candidates
    } if free_selection else {}
    total=math.ceil(duration*30-1e-7)
    cuts=set(required_cuts)
    boundaries=sorted(({min(total,max(0,math.ceil(s['end']*30-1e-7))) for s in timeline['segments']}|cuts|set(preferred_cuts)|{total})-{0})
    fixed=sorted(cuts|{total})
    retained=[]
    start=0
    for end in fixed:
        for boundary in boundaries:
            if start+min_frames<=boundary<=end-min_frames:
                retained.append(boundary)
                start=boundary
        retained.append(end)
        start=end
    boundaries=retained
    slot_starts=[0]+boundaries[:-1]
    budgets=[end-start for start,end in zip(slot_starts,boundaries)]
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
        frame=slot_starts[index]+budgets[index]-remaining
        for c in candidates:
            if shot_allowed and not shot_allowed(c['id'],frame):continue
            if remaining==budgets[index] and slot_starts[index] in cuts and parts and parts[-1]['asset_sha256']==c['asset_sha256']:
                continue
            if parts and ascending(parts[-1].get('source_name'),c.get('name')):continue
            if not free_selection and len(parts)>=2 and compact_number_run([parts[-2]['source_name'],parts[-1]['source_name'],c.get('name')]):continue
            choices=[(c['start'],c['frames'])]
            for r in c.get('safe_trim_ranges',[]):
                available_frames=available_frames_at_30fps(r['end']-r['start'])
                slack=max(0,available_frames-min(remaining,available_frames))
                offsets={rng.randint(0,slack) for _ in range(min(8,slack+1))}
                offsets.update(range(1,min(5,slack)+1))
                starts=[r['start']]+[r['start']+n/30 for n in offsets]+[x['end'] for x in occupied if x['asset_sha256']==c['asset_sha256'] and r['start']<=x['end']<r['end']]
                for start in starts:
                    frames=min(remaining,available_frames_at_30fps(r['end']-start))
                    choices.append((start,frames))
            for start,frames in set(choices):
                if not min_frames<=frames<=remaining or 0<remaining-frames<min_frames:continue
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
        if batch_counts and not free_selection:
            options.sort(key=lambda part: batch_counts.get(part['asset_sha256'],0))
        if free_selection:
            options.sort(key=lambda part:usage_priority[part['asset_sha256']])
            used_sources={p['asset_sha256'] for p in parts}
            options=[p for p in options if p['asset_sha256'] not in used_sources]
        if shot_priority:
            options.sort(key=lambda part:(shot_priority(part['shot_id'],frame,frame+part['frames']==total), prefer_full_slots and part['frames']!=remaining))
        for part in options:
            result=search(index,remaining-part['frames'],parts+[part],occupied+[part])
            if result is not None:return result
        return None
    result=search(0,budgets[0] if budgets else 0,[],list(used))
    if not result:
        if cuts:raise ValueError('现有素材无法同时满足必切时间点、时长和安全裁切要求，请核对切点或补充素材')
        raise ValueError('现有素材或安全裁切范围无法在搜索范围内匹配断句时长，请补充素材或确认安全裁切范围')
    if free_selection and batch_history:
        score=_batch_overlap_score(result,batch_history)
        for _ in range(12):
            if score==(0,0,0) or nodes>=max_nodes:break
            alternate=search(0,budgets[0],[],list(used))
            if not alternate:break
            alternate_score=_batch_overlap_score(alternate,batch_history)
            if alternate_score<score:
                result,score=alternate,alternate_score
    return {'parts':result,'matching_mode':'duration','gaps':[]}
