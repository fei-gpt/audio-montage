"""Read-only reconstruction of a task's evidence and account-scoped regression cases."""
from asset_index import digest_json
from montage import read
from workbench.backend import Problem
from workbench.reference import span_key

STAGES = ('reference', 'recognition', 'ranking', 'trim')
SCOPES = ('shot', 'product', 'general')


def optional(path, default):
    return read(path) if path.is_file() else default


def diagnose(app, p, w, bid, tid):
    batch = app.editing.batch(p, w, bid)
    task = app.store.get('edit_task', tid, w)
    if task['batch_id'] != bid or not batch.get('reference'):
        raise Problem('找不到该账号和批次的参考任务', 404)
    root = app.editing.folder(w, bid)/tid
    stock = optional(root/'reference-stock.json', {})
    proposal = optional(root/'proposal.json', {})
    if not isinstance(proposal,dict):proposal={}
    audits = optional(root/'reference-verdicts.json', task.get('reference_verdicts', {}))
    plan = task.get('plan') or {}
    preview = task.get('output') or task.get('preview') or {}
    rendered = bool(preview and preview.get('plan_revision') == task.get('plan_revision'))
    intro = preview.get('report', {}).get('intro_seconds', 0)
    slots = {}
    for file in sorted((root/'api-cache').glob('slots-*.json')):
        for group in read(file).get('slots', []):
            slots[group['reference_beat']] = group
    shortlist = optional(root/'reference-shortlist.json', [])
    cases = [c for c in app.store.all('reference_case', w)
             if c['source_sha256'] == batch['reference']['sha256']]
    rows = []
    for index, beat in enumerate((task.get('reference_analysis') or {}).get('beats', []), 1):
        candidates = {}
        def entry(key):
            if key not in candidates:
                candidates[key] = dict(stock.get(key, {}), shot_id=key)
            return candidates[key]
        slot=slots.get(index,{})
        for rank, choice in enumerate(slot.get('choices', []), 1):
            entry(choice['id'])['rank'] = rank
        for part in proposal.get('parts') or []:
            if not isinstance(part,dict) or part.get('reference_beat') != index:
                continue
            alternatives=part.get('alternatives')
            for alt in [part, *(alternatives if isinstance(alternatives,list) else [])]:
                if isinstance(alt,dict) and isinstance(alt.get('shot_id'),str):
                    entry(alt['shot_id'])['recommendation'] = alt.get('reason','')
        for row in shortlist:
            for part in row:
                if part.get('reference_beat') == index:
                    c = entry(part['shot_id'])
                    c.setdefault('name', part['source_name'])
                    c['audit'] = audits.get(span_key(part))
        selected = []
        for part in plan.get('parts', []):
            if part.get('reference_beat') != index:
                continue
            c = entry(part['shot_id'])
            c.setdefault('name', part['source_name'])
            item = {k:part[k] for k in ('shot_id','source_name','asset_sha256','start','end',
                    'timeline_start','timeline_end','reason','analysis_version') if k in part}
            if rendered:
                item['rendered_interval'] = [intro + part['timeline_start'], intro + part['timeline_end']]
            selected.append(item)
        notes = [g['reason'] for g in proposal.get('gaps') or [] if isinstance(g,dict)
                 and g.get('reference_beat') == index and isinstance(g.get('reason'),str)]
        rows.append(dict(index=index,reference=beat,candidates=list(candidates.values()),selected=selected,
                         gaps=[g for g in plan.get('reference_gaps',[]) if g['beat']==index], notes=notes,
                         excluded=[dict(name=stock.get(key,{}).get('name',key),reason=reason)
                                   for key,reason in slot.get('excluded',[])],
                         cases=[c['id'] for c in cases if c['reference']['start'] < beat['end']
                                and c['reference']['end'] > beat['start']]))
    result = dict(task_id=tid, reference_sha256=batch['reference']['sha256'], plan_revision=task.get('plan_revision'),
                  media_sha256=preview.get('sha256') if rendered else None, rows=rows,
                  screen=task.get('reference_screen'), error=task.get('error'), cases=cases)
    result['revision'] = digest_json({k:v for k,v in result.items() if k!='cases'} | {
        'rows':[{k:v for k,v in row.items() if k!='cases'} for row in rows]})
    return result


def record(app,p,w,bid,tid,op,body):
    with app.lock:
        report=diagnose(app,p,w,bid,tid)
        if body.get('revision') != report['revision']:
            raise Problem('画面、方案或证据已更新，请重新打开诊断',409)
        index=body.get('beat')
        if type(index)!=int or not 1<=index<=len(report['rows']):
            raise Problem('参考段号无效')
        row=report['rows'][index-1]
        if op=='checks':
            case=app.store.get('reference_case',body.get('case_id'),w)
            outcome=body.get('outcome')
            if case['id'] not in row['cases'] or outcome not in ('pass','fail'):
                raise Problem('样本不属于该参考片区间或核对结果无效')
            check=dict(task_id=tid,revision=report['revision'],beat=index,outcome=outcome,
                       media_sha256=report['media_sha256'])
            if not case['checks'] or check != case['checks'][-1]:case['checks'].append(check)
            return app.store.put('reference_case',w,case)
        expected=body.get('expected')
        if (body.get('stage') not in STAGES or body.get('scope') not in SCOPES
                or not isinstance(expected,str) or not 0<len(expected.strip())<=2000):
            raise Problem('请选择首次出错步骤、适用范围，并填写正确判断（最多2000字）')
        shot_id=body.get('shot_id')
        target=next((c for c in row['candidates'] if c['shot_id']==shot_id),None)
        if shot_id and target is None:raise Problem('指定的候选不属于本次参考段')
        case=dict(target=target,product_id=p,workspace_id=w,batch_id=bid,task_id=tid,beat=index,
                  source_sha256=report['reference_sha256'],reference=row['reference'],
                  evidence={k:row[k] for k in ('selected','candidates','gaps','notes','excluded')},
                  revision=report['revision'],media_sha256=report['media_sha256'],
                  stage=body['stage'],scope=body['scope'],expected=expected.strip())
        case['id']=digest_json(case)
        existing=next((x for x in report['cases'] if x['id']==case['id']),None)
        return existing or app.store.put('reference_case',w,dict(case,checks=[]))
