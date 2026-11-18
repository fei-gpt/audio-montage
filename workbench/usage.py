"""Successful-output usage ledger, shared by content hash; never modifies videos."""
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from montage import save, fingerprint

LIMIT = 3
SCHEMA = 'montage-source-usage-v1'


def sources(store, task):
    result = {p['asset_sha256'] for p in task.get('plan', {}).get('parts', [])}
    if task.get('intro_sha256'):
        result.add(task['intro_sha256'])
    batch = store.get('edit_batch', task['batch_id'], task['workspace_id'])
    result.update(c['sha256'] for c in batch.get('clips', []))
    return result


def task_ranges(store, task, *, batch=None):
    ranges={}
    for part in task.get('plan',{}).get('parts',[]):
        interval=[round(part['start']*30),round(part['start']*30)+part['frames']]
        ranges.setdefault(part['asset_sha256'],[]).append(interval)
    if batch is None:batch=store.get('edit_batch',task['batch_id'],task['workspace_id'])
    for sha in [task.get('intro_sha256'),*(c['sha256'] for c in batch.get('clips',[]))]:
        if sha:ranges[sha]=None
    return ranges


def overlapping_uses(entries, interval):
    return sum(interval is None or not entry.get('ranges') or any(
        start<interval[1] and interval[0]<end for start,end in entry['ranges'])
        for entry in entries)


def references(record):
    entries=record.get('references') if isinstance(record,dict) else None
    if not isinstance(entries,list):raise ValueError('引用记录格式无效')
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('task_id'),str):raise ValueError('引用任务记录无效')
        ranges=entry.get('ranges')
        if ranges is not None and (not isinstance(ranges,list) or any(
            not isinstance(span,list) or len(span)!=2 or not all(type(n) is int for n in span)
            or not 0<=span[0]<span[1] for span in ranges)):
            raise ValueError('引用区间格式无效')
    return entries


@dataclass
class UsageRecords:
    events: dict
    errors: dict
    folder_items: dict

    def require(self,hashes):
        for sha in hashes:
            if sha in self.errors:raise ValueError(self.errors[sha])


def read_ledger(store, extra_paths=(), *, workspace=None):
    events = {}
    batches = {}
    for task in store.all('edit_task'):
        if not task.get('output'):
            continue
        key=(task['workspace_id'],task['batch_id'])
        if key not in batches:
            batches[key]=store.get('edit_batch',task['batch_id'],task['workspace_id'])
        for sha,ranges in task_ranges(store,task,batch=batches[key]).items():
            events.setdefault(sha,{})[task['id']]={'task_id':task['id'],'batch_id':task['batch_id'],'ranges':ranges}
    # Sidecars travel with footage; copying/renaming the same bytes cannot reset usage.
    assets=store.all('asset') if workspace is None else store.all('asset',workspace)
    by_path={Path(a['path']):a for a in assets}
    paths=defaultdict(set)
    for path,sha in extra_paths:paths[Path(path)].add(sha)
    for path,a in by_path.items():paths[path].add(a['sha256'])
    folders=defaultdict(set)
    for path,shas in paths.items():folders[path.parent].update(shas)
    issues={}
    folder_items={}
    for folder,shas in folders.items():
        index=folder/'素材引用次数索引.json'
        try:
            data=json.loads(index.read_text(encoding='utf-8-sig'))
            if not isinstance(data,dict) or data.get('schema')!='montage-library-usage-v1' or not isinstance(data.get('素材'),dict):
                raise ValueError('素材引用索引格式无效')
            items=data['素材']
            for item in items.values():
                if isinstance(item,dict) and 'references' not in item and not item.get('引用次数'):
                    item['references']=[]
                references(item)
                for key in ('文件名','历史文件名'):
                    names=item.get(key,[])
                    if not isinstance(names,list) or not all(isinstance(name,str) for name in names):
                        raise ValueError('引用索引文件名格式无效')
            folder_items[folder]=items
        except FileNotFoundError:folder_items[folder]={}
        except (OSError,ValueError) as exc:
            issues.update(dict.fromkeys(shas,f'{index}：{exc}'))
    old_shots=None
    for path,shas in paths.items():
        doc=Path(str(path)+'.usage.json')
        try:
            data=json.loads(doc.read_text(encoding='utf-8-sig'))
            if not isinstance(data,dict) or data.get('schema')!=SCHEMA:raise ValueError('引用记录格式无效')
            sha=data.get('source_sha256')
            if not isinstance(sha,str):raise ValueError('引用记录缺少来源指纹')
            asset=by_path.get(path)
            if sha not in shas or (asset and sha!=asset['sha256']):
                items=folder_items.get(path.parent,{})
                item=items.get(sha,{})
                names=item.get('文件名',[])+item.get('历史文件名',[])
                verified=asset and asset.get('replaced_source') and (
                    sha in asset.get('previous_hashes',[]) or path.name in names)
                if not verified and asset and asset.get('replaced_source'):
                    # Older catalogs recorded the replaced hash on the discarded shots.
                    if old_shots is None:
                        old_shots={(s.get('asset_id'),s.get('asset_sha256')) for s in store.all('shot',workspace) if s.get('stale')}
                    verified=(asset['id'],sha) in old_shots
                if not verified:raise ValueError('引用记录与素材不一致，请核对')
                item=items.setdefault(sha,{'文件名':[],'references':[]})
                previous_names=item.setdefault('历史文件名',[])
                if path.name not in previous_names:previous_names.append(path.name)
            for entry in references(data):
                events.setdefault(sha,{}).setdefault(entry['task_id'],entry)
        except FileNotFoundError:continue
        except (OSError,ValueError) as exc:
            issues.update(dict.fromkeys(shas,f'{exc}：{doc}'))
    for items in folder_items.values():
        for sha,item in items.items():
            for entry in item['references']:events.setdefault(sha,{}).setdefault(entry['task_id'],entry)
    return UsageRecords(events,issues,folder_items)


def ledger(store, extra_paths=(), *, workspace=None):
    records=read_ledger(store,extra_paths,workspace=workspace)
    records.require(records.errors)
    return records.events


def check(store, task, batch):
    extra = [(c['path'], c['sha256']) for c in batch.get('clips', [])]
    if task.get('intro'):
        extra.append((task['intro'], task['intro_sha256']))
    records = read_ledger(store, extra, workspace=task['workspace_id'])
    ranges_by_source=task_ranges(store,task,batch=batch)
    records.require(ranges_by_source)
    occupied = {}
    for other in store.all('edit_task'):
        if other['id'] == task['id'] or other.get('output'):
            continue
        if other.get('dedup_reserved') and other.get('status') in {'running', 'queued'}:
            for sha,ranges in task_ranges(store,other).items():
                occupied.setdefault(sha,[]).append({'ranges':ranges})
    for sha,ranges in ranges_by_source.items():
        entries=[e for tid,e in records.events.get(sha,{}).items() if tid!=task['id']]
        entries.extend(occupied.get(sha,[]))
        if any(overlapping_uses(entries,interval)>=LIMIT for interval in ranges or [None]):
            raise ValueError('素材区间已达到3次引用上限或剩余次数已被输出任务占用，请更换片段：'+sha[:12])


def sync(store, only_shas=None, *, workspace=None):
    assets=store.all('asset') if workspace is None else store.all('asset',workspace)
    tasks=store.all('edit_task') if workspace is None else store.all('edit_task',workspace)
    paths = set()
    batches=set()
    for task in tasks:
        if task.get('intro') and task.get('intro_sha256'):
            paths.add((task['intro'], task['intro_sha256']))
        batches.add((task['workspace_id'],task['batch_id']))
    for scope,bid in batches:
        batch = store.get('edit_batch',bid,scope)
        paths.update((c['path'], c['sha256']) for c in batch.get('clips', []))
    records=read_ledger(store,paths,workspace=workspace)
    folders=defaultdict(dict)
    for asset in assets:
        file=Path(asset['path'])
        folders[file.parent][file]=asset['sha256']
    written=0
    indexes=0
    errors=[]
    for folder,files in folders.items():
        selected={f:sha for f,sha in files.items() if only_shas is None or sha in only_shas}
        if not selected or not folder.is_dir():continue
        if folder not in records.folder_items:
            errors.append({'path':str(folder),'error':records.errors[next(iter(selected.values()))]})
            continue
        entries=dict(records.folder_items[folder])
        names=defaultdict(list)
        for file,sha in sorted(files.items()):names[sha].append(file.name)
        for sha in names.keys()|entries.keys():
            if sha in records.errors:continue
            refs=sorted(records.events.get(sha,{}).values(),key=lambda e:e['task_id'])
            if sha not in names and not refs:
                entries.pop(sha,None)
                continue
            item=entries.setdefault(sha,{})
            item.update({'引用次数':len(refs),'引用上限':LIMIT,'可继续引用':len(refs)<LIMIT,'references':refs})
            previous_names=set(item.get('文件名',[])+item.get('历史文件名',[]))-set(names.get(sha,[]))
            if previous_names:item['历史文件名']=sorted(previous_names)
            else:item.pop('历史文件名',None)
            item['文件名']=names.get(sha,[])
        # Save the old hash's portable history before replacing any per-file sidecar.
        try:
            save(folder/'素材引用次数索引.json',{'schema':'montage-library-usage-v1','说明':'按源文件指纹登记成功成片引用，保留已替换版本的历史记录。','素材':entries})
            indexes+=1
        except (OSError,ValueError) as exc:
            errors.append({'path':str(folder),'error':str(exc)})
            continue
        for file,sha in selected.items():
            try:
                records.require([sha])
                if not file.is_file():continue
                if fingerprint(file)!=sha:raise ValueError('源文件指纹变化，未写入引用记录')
                sidecar=Path(str(file)+'.usage.json')
                if sidecar.exists():
                    item=entries[sha]
                    save(sidecar,{'schema':SCHEMA,'source_sha256':sha,'video_name':file.name,
                                  '引用次数':item['引用次数'],'引用上限':LIMIT,'可继续引用':item['可继续引用'],
                                  '计数说明':'按成功成片计数，同一成片引用本素材只计一次。','references':item['references']})
                written+=1
            except (OSError,ValueError) as exc:errors.append({'path':str(file),'error':str(exc)})
    return {'written': written,'indexes':indexes, 'errors': errors}


if __name__ == '__main__':
    import argparse
    from workbench.backend import Store
    parser = argparse.ArgumentParser(description='从已有成功成片回填源视频引用文档，不启动处理任务')
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[1] / '.workbench-data')
    args = parser.parse_args()
    if not (args.data / 'catalog.sqlite').is_file():
        parser.error('已有工作台数据库不存在，不创建空数据目录')
    print(json.dumps(sync(Store(args.data)), ensure_ascii=True))
