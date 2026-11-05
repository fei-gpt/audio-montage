"""Read-only, deterministic naming-based MP4/MP3 batch pairing."""
import hashlib,json
from pathlib import Path

def inspect_folder(root):
    groups={};snapshot=[];ignored=0
    for path in sorted(Path(root).iterdir(),key=lambda p:p.name):
        if path.suffix.lower() not in {'.mp4','.mp3'} or not path.is_file() or path.is_symlink():
            ignored+=1;continue
        stat=path.stat();snapshot.append((path.name,stat.st_size,stat.st_mtime_ns))
        groups.setdefault(path.stem.casefold(),{}).setdefault(path.suffix.lower(),[]).append(path.name)
    from workbench.editing import natural
    rows=[]
    for key,files in sorted(groups.items(),key=lambda item:natural(item[0])):
        videos=files.get('.mp4',[]);audios=files.get('.mp3',[])
        issue='文件名存在大小写或重名冲突' if len(videos)>1 or len(audios)>1 else ('缺少同名MP4' if not videos else '缺少同名MP3' if not audios else '')
        rows.append({'key':key,'videos':videos,'audios':audios,'paired':not issue,'issue':issue})
    digest=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False).encode()).hexdigest()
    return {'path':str(Path(root).resolve()),'snapshot':digest,'rows':rows,'paired_count':sum(r['paired'] for r in rows),'problem_count':sum(not r['paired'] for r in rows),'ignored_count':ignored}
