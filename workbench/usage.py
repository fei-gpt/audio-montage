"""Successful-output usage ledger, shared by content hash; never modifies videos."""
import json
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


def ledger(store, extra_paths=()):
    events = {}
    for task in store.all('edit_task'):
        if not task.get('output'):
            continue
        for sha in sources(store, task):
            events.setdefault(sha, {})[task['id']] = {'task_id': task['id'], 'batch_id': task['batch_id']}
    # Sidecars travel with footage; copying/renaming the same bytes cannot reset usage.
    paths = {(a['path'], a['sha256']) for a in store.all('asset')} | set(extra_paths)
    for path, sha in paths:
        doc = Path(str(path) + '.usage.json')
        if not doc.exists():
            continue
        data = json.loads(doc.read_text(encoding='utf-8-sig'))
        if data.get('schema') != SCHEMA or data.get('source_sha256') != sha:
            raise ValueError('引用记录与素材不一致，请核对：' + str(doc))
        entries = data.get('references')
        if not isinstance(entries, list) or any(not isinstance(e, dict) or not isinstance(e.get('task_id'), str) for e in entries):
            raise ValueError('引用记录格式无效，请核对：' + str(doc))
        events.setdefault(sha, {}).update({e['task_id']: e for e in entries})
    for folder in {Path(path).parent for path,sha in paths}:
        index=folder/'素材引用次数索引.json'
        if not index.exists():continue
        data=json.loads(index.read_text(encoding='utf-8-sig'))
        if data.get('schema')!='montage-library-usage-v1':raise ValueError('素材引用索引格式无效：'+str(index))
        for sha,item in data.get('素材',{}).items():
            entries=item.get('references',[])
            if not isinstance(entries,list) or any(not isinstance(e,dict) or not isinstance(e.get('task_id'),str) for e in entries):raise ValueError('素材引用索引记录无效')
            events.setdefault(sha,{}).update({e['task_id']:e for e in entries})
    return events


def check(store, task, batch):
    extra = [(c['path'], c['sha256']) for c in batch.get('clips', [])]
    if task.get('intro'):
        extra.append((task['intro'], task['intro_sha256']))
    events = ledger(store, extra)
    occupied = {}
    for other in store.all('edit_task'):
        if other['id'] == task['id'] or other.get('output'):
            continue
        if other.get('dedup_reserved') and other.get('status') in {'running', 'queued'}:
            for sha in sources(store, other):
                occupied.setdefault(sha, set()).add(other['id'])
    for sha in sources(store, task):
        count = len(set(events.get(sha, {})) - {task['id']})
        if count + len(occupied.get(sha, set())) >= LIMIT:
            raise ValueError('素材已达到3次引用上限或剩余次数已被输出任务占用，请更换片段：' + sha[:12])


def sync(store, only_shas=None):
    paths = {(a['path'], a['sha256']) for a in store.all('asset')}
    for task in store.all('edit_task'):
        if task.get('intro') and task.get('intro_sha256'):
            paths.add((task['intro'], task['intro_sha256']))
        batch = store.get('edit_batch', task['batch_id'], task['workspace_id'])
        paths.update((c['path'], c['sha256']) for c in batch.get('clips', []))
    events = ledger(store, paths)
    material_paths={(a['path'],a['sha256']) for a in store.all('asset')}
    paths=paths & material_paths
    if only_shas is not None:
        paths = {(p, sha) for p, sha in paths if sha in only_shas}
    written = 0
    errors = []
    for path, sha in sorted(paths):
        source = Path(path)
        try:
            if not source.is_file():
                continue
            if fingerprint(source) != sha:
                raise ValueError('源文件指纹变化，未写入引用记录')
            refs = sorted(events.get(sha, {}).values(), key=lambda e: e['task_id'])
            # Existing fixed-name per-video files remain compatible; no new
            # sidecar is created on each use. The folder index is authoritative.
            if Path(str(source)+'.usage.json').exists():save(Path(str(source) + '.usage.json'), {
                'schema': SCHEMA, 'source_sha256': sha, 'video_name': source.name,
                '引用次数': len(refs), '引用上限': LIMIT, '可继续引用': len(refs) < LIMIT,
                '计数说明': '按成功输出任务计数；同一成片多次选用本源文件只计1次；预览和失败不计。',
                'references': refs})
            written += 1
        except (OSError, ValueError) as exc:
            errors.append({'path': str(source), 'error': str(exc)})
    folders={Path(p).parent for p,sha in paths}
    indexes=0
    for folder in folders:
        if not folder.is_dir():continue
        try:
            entries={}
            for path,sha in material_paths:
                if Path(path).parent!=folder:continue
                refs=sorted(events.get(sha,{}).values(),key=lambda e:e['task_id'])
                item=entries.setdefault(sha,{'文件名':[],'引用次数':len(refs),'引用上限':LIMIT,'可继续引用':len(refs)<LIMIT,'references':refs})
                item['文件名'].append(Path(path).name)
            save(folder/'素材引用次数索引.json',{'schema':'montage-library-usage-v1','说明':'仅登记本素材目录原视频；按成功成片计数，预览失败不计；每次更新本文件。','素材':entries})
            indexes+=1
        except (OSError,ValueError) as exc:errors.append({'path':str(folder),'error':str(exc)})
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
