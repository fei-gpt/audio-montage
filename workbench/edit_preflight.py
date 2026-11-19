"""Inspect the current inputs and source ranges without changing the reviewed edit."""
from pathlib import Path

from montage import fingerprint
from workbench.backend import Problem
from workbench.duration_planner import available_frames_at_30fps
from workbench.reference import fit_beat, span_key
from workbench.usage import usage_issue, usage_snapshot


def inspect_edit(edit,b,t,*,options=False,selected_ids=None):
    fixed=[]
    issues=[]
    inputs=[t.get('audio'),t.get('intro'),(b.get('reference') or {}).get('path'),
            (b.get('music') or {}).get('path'),*[c['path'] for c in b.get('clips',[])]]
    for path in inputs:
        if path and not Path(path).is_file():fixed.append('找不到输入文件：'+str(path))
    if not fixed:
        try:edit.check_inputs(b,t)
        except (OSError,ValueError,Problem) as error:fixed.append(str(error))
    parts=(t.get('plan') or {}).get('parts',[])
    if not parts:return dict(fixed=fixed,issues=issues)
    snapshot=usage_snapshot(edit.store,t,b)
    for sha,name in [(t.get('intro_sha256'),t.get('intro')),*[(c['sha256'],c['name']) for c in b.get('clips',[])]]:
        if sha:
            message=usage_issue(snapshot,t['id'],sha,None)
            if message:fixed.append(f'{name} · {message}')
    assets={a['id']:a for a in edit.app.visible_assets(t['workspace_id'])}
    minimum=min((max(1,available_frames_at_30fps(a['duration'])) for a in assets.values() if a.get('duration',0)>0),default=1)
    for index,part in enumerate(parts):
        sha=part['asset_sha256']
        asset=assets.get(part['asset_id'])
        start=round(part['start']*30)
        reason=usage_issue(snapshot,t['id'],sha,[start,start+part['frames']])
        try:
            if not asset or asset['sha256']!=sha or fingerprint(Path(asset['path']))!=sha:
                reason='原素材已失效或版本已变化'
        except OSError:reason='无法读取原素材'
        if part['frames']<minimum:reason=f'当前镜头 {part["frames"]} 帧，素材库下限 {minimum} 帧，需要调整时长'
        if reason:
            issues.append(dict(index=index,name=part.get('source_name') or part['shot_id'],reason=reason,
                               replaceable=part['frames']>=minimum))
    if options and issues and not fixed:
        from workbench.editing import source_group,shot_request_matches, shot_request_satisfied, contains_category
        from workbench.duration_planner import ascending
        rules=edit.task_batch(b,t)['rules']
        reference=b['rules'].get('reference_matching')==2
        kept={source_group(part) for part in parts}
        problem_indices={issue['index'] for issue in issues}
        if edit.distinct_batch_sources(b):
            kept.update(source_group(part) for peer in edit.tasks(t['workspace_id'],b['id'])
                        if peer['id']!=t['id'] and peer['status']!='cancelled' for part in (peer.get('plan') or {}).get('parts',[]))
        originals={parts[i]['asset_id'] for i in problem_indices}
        eligible={key:a for key,a in assets.items() if key in originals or (a.get('origin_sha256') or a['sha256']) not in kept}
        library=[] if reference else edit.candidates(t['product_id'],t['workspace_id'],b['rules'].get('analysis_mode'),
            b['rules'].get('use_prepared_files',False),active_versions=b['rules'].get('matching_mode','semantic')=='semantic',
            allow_prepared_trim=edit.rhythm_trim_enabled(b),usage=snapshot[0],visible=eligible,
            shot_ids=selected_ids,browsing=selected_ids is None)
        by_id={c['id']:c for c in library}
        for issue in issues:
            i=issue['index']
            original=parts[i]
            choices=[]
            if reference:
                rows=t.get('reference_choices') or []
                for alt in rows[i] if i<len(rows) else []:
                    if ((t.get('reference_verdicts') or {}).get(span_key(alt),{}).get('verdict')=='different_shoot'
                            and assets.get(alt['asset_id'],{}).get('sha256')==alt['asset_sha256']):
                        choices.append(alt)
            else:
                last=i==len(parts)-1
                requests=[r for r in rules.get('shot_requests',[]) if shot_request_matches(
                    r,i+1,round(original['timeline_start']*30),last)]
                old_labels=set(by_id.get(original['shot_id'],{}).get('confirmed_categories',[]))
                for c in library:
                    if source_group(c) in kept or contains_category(c,rules.get('excluded_shot_categories',[])):continue
                    if any(contains_category(c,r['excluded']) or not r['preferred'] and not shot_request_satisfied(r,c) for r in requests):continue
                    if i and i-1 not in problem_indices and ascending(parts[i-1]['source_name'],c['name']):continue
                    if not last and i+1 not in problem_indices and ascending(c['name'],parts[i+1]['source_name']):continue
                    start,frames=fit_beat(c,original['frames']/30)
                    choices.append(dict(shot_id=c['id'],source_name=c['name'],asset_sha256=c['asset_sha256'],
                                        start=start,frames=frames,reason='人工选择的等长替换镜头'))
                choices.sort(key=lambda x:(-len(old_labels.intersection(by_id[x['shot_id']].get('confirmed_categories',[]))),x['source_name']))
            issue['options']=[]
            for alt in choices:
                sha=alt['asset_sha256']
                start=round(alt['start']*30)
                asset_id=alt.get('asset_id') or by_id[alt['shot_id']]['asset_id']
                group=assets.get(asset_id,{}).get('origin_sha256') or sha
                if (issue['replaceable'] and group not in kept and alt['frames']==original['frames'] and
                        not usage_issue(snapshot,t['id'],sha,[start,start+alt['frames']])):
                    record=assets.get(asset_id,{})
                    categories=record.get('user_category') or record.get('category_review') or {}
                    issue['options'].append(dict(alt,asset_id=asset_id,labels=categories.get('labels',[]) if categories.get('confirmed') else []))
    return dict(fixed=fixed,issues=issues)
