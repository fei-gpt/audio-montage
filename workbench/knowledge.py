"""Reuse product knowledge without re-reading source files or calling a model."""
import copy
import json


def merge_profiles(profiles):
    result={}
    for profile in profiles:
        if not profile:continue
        for key,value in profile.items():
            if isinstance(value,list):
                rows=result.setdefault(key,[])
                seen={json.dumps(x,sort_keys=True,ensure_ascii=False) for x in rows}
                for row in value:
                    identity=json.dumps(row,sort_keys=True,ensure_ascii=False)
                    if identity not in seen:rows.append(copy.deepcopy(row));seen.add(identity)
            elif key not in result:result[key]=copy.deepcopy(value)
    return result


def remap_profile(profile,mapping):
    def convert(value):
        if isinstance(value,list):return [convert(x) for x in value]
        if isinstance(value,dict):
            return {k:(mapping.get(v,v) if k in {'source_id','id'} and isinstance(v,str) else
                       [mapping.get(x,x) for x in v] if k=='references' and isinstance(v,list) else convert(v))
                    for k,v in value.items()}
        return value
    return convert(profile)
