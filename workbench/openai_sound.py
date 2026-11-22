"""Generate a single experimental GPT audio sample for an editing workspace."""
import base64
import io
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from vision_api import api_key
from workbench.backend import Problem


def generate_sample(app, product, workspace, body):
    if not app.workspace(product, workspace)['assigned']:
        raise Problem('请先选择已分配的账号')
    if body.get('allow_paid') is not True:
        raise Problem('生成试听会使用 OpenAI API 额度，请先确认')
    prompt = body.get('description')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
        raise Problem('请填写 1 至 1500 字的音效说明')
    prompt = prompt.strip()
    try:
        request_id = uuid.UUID(str(body.get('request_id')))
    except ValueError:
        raise Problem('缺少有效的试听请求编号')
    ident = uuid.uuid5(uuid.NAMESPACE_URL, f'workbench:sound:{workspace}:{request_id}').hex
    with app.lock:
        try:
            previous = app.store.get('sound_attempt', ident, workspace)
        except Problem as exc:
            if exc.status != 404:
                raise
        else:
            if previous['description'] != prompt:
                raise Problem('该请求编号已用于另一段说明', 409)
            if previous.get('upload_id'):
                return {'id': previous['upload_id']}
            raise Problem('这次试听已经提交，请核对原调用记录', 409)
        key = api_key({'api_key_env':'OPENAI_API_KEY','api_key_file':str(app.root/'credentials.json')})
        if not key:
            raise Problem('尚未配置 OPENAI_API_KEY')
        attempt = dict(id=ident, description=prompt, status='submitted')
        app.store.put('sound_attempt', workspace, attempt)

    payload = dict(model='gpt-audio-1.5', modalities=['text','audio'], store=False,
                   audio=dict(voice='alloy', format='wav'),
                   messages=[dict(role='system', content='Return only the requested short nonverbal sound effect. No speech, vocal imitation, narration or music.'),
                             dict(role='user', content=prompt)])
    request = Request('https://api.openai.com/v1/chat/completions', data=json.dumps(payload).encode(),
                      headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urlopen(request, timeout=90) as response:
            audio = json.load(response)['choices'][0]['message']['audio']
        wav = base64.b64decode(audio['data'], validate=True)
        sound = app.editing.upload(product, workspace, 'GPT试听-'+request_id.hex[:8]+'.wav',
                                   'sound', io.BytesIO(wav), len(wav))
    except HTTPError as exc:
        app.store.put('sound_attempt', workspace, dict(attempt,status='http_error',code=exc.code))
        raise Problem(f'OpenAI 音频接口返回 HTTP {exc.code}，请核对密钥、模型权限和额度', 502) from exc
    except Exception as exc:
        app.store.put('sound_attempt', workspace, dict(attempt,status='unverified'))
        raise Problem('未取得可用的纯音效试听，请核对本次调用记录：'+str(exc)[:180], 502) from exc
    app.store.put('sound_attempt', workspace, dict(attempt,status='ready',upload_id=sound['id'],transcript=audio.get('transcript','')))
    return {'id': sound['id']}
