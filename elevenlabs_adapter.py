"""Explicit, cached ElevenLabs requests. Credentials are environment-only."""
import base64
import hashlib
import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from montage import (read, save, fingerprint, probe, media_duration, check_segments,
                     phrases, export_srt, init, number)

API = 'https://api.elevenlabs.io/v1/'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(root, endpoint, fields, audio, allow_paid):
    signature = {'endpoint': endpoint, 'fields': fields,
                 'audio_sha256': fingerprint(audio) if audio else None}
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    folder = root / 'audio/elevenlabs-cache'
    result_path = folder / (digest + '.json')
    receipt = folder / (digest + '.request.json')
    if result_path.exists():
        return read(result_path), digest
    if not allow_paid:
        raise ValueError('新请求将向 ElevenLabs 发送文稿或音频并可能计费；明确接受后添加 --allow-paid。未发送请求。')
    if receipt.exists():
        raise ValueError('此请求已有尝试记录但无完整结果，可能已计费；请先核查 ElevenLabs，再手动归档 request.json 后重试。')
    key = os.environ.get('ELEVENLABS_API_KEY')
    if not key:
        raise ValueError('请设置 ELEVENLABS_API_KEY 环境变量，不要把密钥写入项目')
    if audio:
        boundary = uuid.uuid4().hex
        chunks = []
        for name, value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        mime = mimetypes.guess_type(str(audio))[0] or 'application/octet-stream'
        chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio{audio.suffix}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
                   audio.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
        body, content_type = b''.join(chunks), 'multipart/form-data; boundary=' + boundary
    else:
        body, content_type = json.dumps(fields).encode(), 'application/json'
    save(receipt, {'signature': signature, 'status': 'attempted', 'automatic_retry': False})
    req = urllib.request.Request(API + endpoint, data=body,
                                 headers={'xi-api-key': key, 'Content-Type': content_type})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'ElevenLabs HTTP {exc.code}；未自动重试，请检查权限、余额及请求记录。') from None
    except (OSError, ValueError) as exc:
        raise ValueError('ElevenLabs 请求未取得完整响应；可能已计费，保留请求记录且不自动重试。') from None
    save(result_path, result)
    save(receipt, {'signature': signature, 'status': 'received', 'automatic_retry': False})
    return result, digest


def aligned_words(result, mode, language):
    if mode == 'tts':
        alignment = result.get('normalized_alignment') or result.get('alignment')
        if not alignment:
            raise ValueError('响应缺少时间对齐；原始响应已缓存，不自动重新计费')
        chars = alignment['characters']
        starts, ends = alignment['character_start_times_seconds'], alignment['character_end_times_seconds']
        if not len(chars) == len(starts) == len(ends):
            raise ValueError('字符时间戳长度不一致')
        units = [{'text': c, 'start': a, 'end': b} for c, a, b in zip(chars, starts, ends)]
    else:
        units = [{'text': w['text'], 'start': w['start'], 'end': w['end']}
                 for w in result.get('words', []) if w.get('type', 'word') in {'word', 'spacing'}]
    words, pending = [], []
    for unit in units:
        if not number(unit['start']) or not number(unit['end']) or unit['end'] < unit['start']:
            raise ValueError('服务返回了无效时间戳')
        if mode == 'tts' and language != 'zh':
            if unit['text'].isspace():
                if pending:
                    words.append({'text': ''.join(w['text'] for w in pending) + ' ',
                                  'start': pending[0]['start'], 'end': pending[-1]['end']})
                    pending = []
            else:
                pending.append(unit)
        else:
            unit = dict(unit)
            if language != 'zh' and not unit['text'].endswith(' '):
                unit['text'] += ' '
            words.append(unit)
    if pending:
        words.append({'text': ''.join(w['text'] for w in pending), 'start': pending[0]['start'], 'end': pending[-1]['end']})
    if not words:
        raise ValueError('没有可用文字时间戳')
    return words


def execute(args):
    root = Path(args.project).resolve()
    timing_path = root / 'audio/timing.json'
    if timing_path.exists():
        raise ValueError('项目已有时间轴；请建立新项目，避免使现有编排失效。未发送请求。')
    script = Path(args.script).read_text(encoding='utf-8-sig').strip() if args.script else None
    if args.mode in {'tts', 'align'} and not script:
        raise ValueError('需要非空的 --script 文稿文件')
    if args.mode == 'tts':
        existing = read(root / 'project.json') if (root / 'project.json').exists() else None
        if existing and not existing.get('elevenlabs_tts_request'):
            raise ValueError('配音生成请使用新项目目录')
        voice = args.voice or os.environ.get('ELEVENLABS_VOICE_ID')
        if not voice:
            raise ValueError('需要 --voice 或 ELEVENLABS_VOICE_ID')
        fields = {'text': script, 'model_id': args.model or os.environ.get('ELEVENLABS_TTS_MODEL', 'eleven_multilingual_v2')}
        if args.language != 'auto':
            fields['language_code'] = args.language
        result, digest = request(root, 'text-to-speech/' + urllib.parse.quote(voice, safe='') + '/with-timestamps', fields, None, args.allow_paid)
        audio = root / 'audio/generated.mp3'
        audio.parent.mkdir(parents=True, exist_ok=True)
        if existing and existing['elevenlabs_tts_request'] != digest:
            raise ValueError('生成参数已改变，请使用新项目目录；已有缓存保留')
        if not existing:
            audio.write_bytes(base64.b64decode(result['audio_base64'], validate=True))
            init(SimpleNamespace(project=str(root), audio=str(audio), width=1080, height=1920,
                                 fps=30, language=args.language, keep_original_audio=False))
            config = read(root / 'project.json')
            config['elevenlabs_tts_request'] = digest
            save(root / 'project.json', config)
        elif fingerprint(audio) != existing['audio_sha256']:
            raise ValueError('已生成配音被修改，请使用新项目')
    else:
        config = read(root / 'project.json')
        audio = Path(config['audio'])
        if config.get('audio_sha256') != fingerprint(audio):
            raise ValueError('项目配音已改变，不能沿用时间轴')
        if args.mode == 'align':
            endpoint, fields = 'forced-alignment', {'text': script}
        else:
            endpoint = 'speech-to-text'
            fields = {'model_id': args.model or os.environ.get('ELEVENLABS_STT_MODEL', 'scribe_v2'),
                      'timestamps_granularity': 'word', 'tag_audio_events': 'false'}
            if args.language != 'auto':
                fields['language_code'] = args.language
        result, digest = request(root, endpoint, fields, audio, args.allow_paid)
    config = read(root / 'project.json')
    language = result.get('language_code') or args.language
    words = aligned_words(result, args.mode, language)
    segments = phrases([{'start': words[0]['start'], 'end': words[-1]['end'],
                         'text': ''.join(w['text'] for w in words), 'words': words}], language=language)
    check_segments(segments, media_duration(probe(audio), 'audio'))
    provenance = {'provider': 'elevenlabs', 'mode': args.mode, 'request_hash': digest,
                  'audio_sha256': fingerprint(audio)}
    save(root / 'audio/raw-transcript.json', {'words': words, 'provenance': provenance})
    save(timing_path, {'segments': segments, 'language': language, 'reviewed': False,
                       'provenance': provenance, 'note': '服务返回时间戳，仍需实际核对文案与边界。'})
    export_srt(root, segments)
    print('已保存配音时间轴与字幕；核对后可继续 build-plan 和选片，不需重复转写。')


def register(sub):
    p = sub.add_parser('elevenlabs', help='ElevenLabs 配音、转写或强制对齐')
    p.add_argument('project'); p.add_argument('--mode', choices=['tts', 'transcribe', 'align'], required=True)
    p.add_argument('--script'); p.add_argument('--voice'); p.add_argument('--model')
    p.add_argument('--language', choices=['auto', 'en', 'es', 'zh'], default='auto')
    p.add_argument('--allow-paid', action='store_true')
    p.set_defaults(func=execute)
