"""Conservative local recovery of complete model responses; never infer missing values."""
import json,re,hashlib


def decode_response(raw):
    if not isinstance(raw,dict) or not raw.get('choices'):raise ValueError('响应缺少 choices，原始响应已缓存；不自动重试')
    choice=raw['choices'][0] if isinstance(raw['choices'][0],dict) else {}
    if choice.get('finish_reason') not in {'stop',None}:raise ValueError('模型响应未完整结束，原始响应已缓存；不修补截断结果')
    text=(choice.get('message') or {}).get('content')
    if not isinstance(text,str) or not text.strip():raise ValueError('模型返回空内容或不支持的格式，原始响应已缓存；不自动重试')
    text=text.strip();fenced=re.fullmatch(r'```[A-Za-z]*\s*\n(.*?)\n?```',text,re.S)
    if fenced:text=fenced.group(1).strip()
    try:return json.loads(text),None
    except json.JSONDecodeError as error:original=error
    # Only one narrowly identifiable omission: a string-ending quote before an
    # object closes in an array, followed by another named JSON field. The full
    # response must become strict JSON after inserting exactly that one quote.
    matches=list(re.finditer(r'(?<!["\\])}\s*\]\s*,\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:',text))
    recovered=[]
    if choice.get('finish_reason')=='stop' and len(matches)<=16:
        for match in matches:
            pos=match.start();candidate=text[:pos]+'"'+text[pos:]
            try:
                result=json.loads(candidate)
                if isinstance(result,dict):recovered.append((result,pos))
            except json.JSONDecodeError:pass
    if len(recovered)==1:
        result,pos=recovered[0]
        return result,{'method':'insert_one_string_closing_quote','offset':pos,'inserted':'"',
                       'original_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                       'original_error':original.msg,'original_error_offset':original.pos,
                       'paid_retry':False,'content_inferred':False}
    raise ValueError(f'模型返回的不是有效 JSON（{original.msg}，字符{original.pos}）；原文已缓存，无法安全本地恢复，不自动重试')
