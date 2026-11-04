"""Reuse product knowledge without re-reading source files or calling a model."""
import copy
import json
import io
import zipfile


def knowledge_archive(product):
    profile=product.get('profile') or {}
    text=[f"# {product['name']} · 产品文字语料包", '', '已保存的理解结论；宣传主张、未知项和冲突均按原记录保留。', '']
    for key,label in [('appearance','外观'),('claims','来源宣传主张'),('demonstrations','展示方式'),('unknowns','未知项'),('conflicts','冲突')]:
        text.extend(['## '+label,''])
        text.extend('- '+(row if isinstance(row,str) else row.get('text',json.dumps(row,ensure_ascii=False))) for row in profile.get(key,[]))
        text.append('')
    payload={'format':'audio-montage-knowledge-v1','name':product['name'],'profile':profile}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('product-knowledge.md','\n'.join(text).encode('utf-8'))
        archive.writestr('product-knowledge.json',json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8'))
    return output.getvalue()


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
