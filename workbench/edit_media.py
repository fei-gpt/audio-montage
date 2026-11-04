"""Segmented composition adapted from the legacy dashboard production renderer.

The introduction retains its sound; body footage is silent unless requested.
No looping, padding, speed changes, or aspect-ratio conversions are permitted.
"""
import math
import subprocess
from pathlib import Path
from montage import probe, portrait_geometry, media_duration, fingerprint, save


def run(args):
    return subprocess.run([str(x) for x in args],check=True,capture_output=True,timeout=3600)


def render(intro, audio, parts, folder, preview=False, keep_original_audio=False, check_cancel=lambda:None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    width,height=(360,640) if preview else (1080,1920)
    info=probe(intro);portrait_geometry(info)
    intro_duration=media_duration(info,'video');audio_duration=media_duration(probe(audio),'audio')
    intro_sound=any(s['codec_type']=='audio' for s in info['streams'])
    if intro_sound and media_duration(info,'audio')>intro_duration+.05:
        raise ValueError('前段音频长于画面，请先确认音画边界；不会自动补尾帧')
    head_frames=math.ceil(intro_duration*30-1e-7)
    body_frames=math.ceil(audio_duration*30-1e-7)
    if sum(p['frames'] for p in parts)!=body_frames:raise ValueError('后段画面未覆盖完整配音时间轴')
    paths=[Path(intro),Path(audio)]+[Path(p['path']) for p in parts]
    hashes={str(p):fingerprint(p) for p in paths}
    clips=[];sounds=[]
    for i,(path,start,frames) in enumerate([(intro,0,head_frames)]+[(p['path'],p['start'],p['frames']) for p in parts]):
        check_cancel();pi=probe(path);portrait_geometry(pi)
        if start+frames/30>media_duration(pi,'video')+1/30+1e-6:raise ValueError('视频长度不足，不能循环或定格补齐')
        out=folder/f'clip-{i:04}.mp4';clips.append(out)
        run(['ffmpeg','-v','error','-nostdin','-n','-ss',start,'-i',path,'-map','0:v:0','-an',
             '-vf',f'fps=30,scale={width}:{height},setsar=1,setpts=PTS-STARTPTS','-frames:v',frames,
             '-c:v','libx264','-preset','fast','-pix_fmt','yuv420p',out])
        actual=next(s for s in probe(out)['streams'] if s['codec_type']=='video')
        if int(actual.get('nb_frames',0))!=frames:raise ValueError('源画面不足所需帧数，不补帧')
        sound=folder/f'sound-{i:04}.wav';sounds.append(sound)
        if (i==0 or keep_original_audio) and any(s['codec_type']=='audio' for s in pi['streams']):
            run(['ffmpeg','-v','error','-nostdin','-n','-ss',start,'-i',path,'-vn','-af',
                 f'aresample=48000:async=1:first_pts=0,apad,atrim=duration={frames/30}',
                 '-ar','48000','-ac','2',sound])
        else:
            run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                 '-t',frames/30,sound])
    check_cancel()
    video_list=folder/'video.txt';video_list.write_text(''.join(f"file '{p.name}'\n" for p in clips),encoding='utf-8')
    body_list=folder/'body.txt';body_list.write_text(''.join(f"file '{p.name}'\n" for p in sounds[1:]),encoding='utf-8')
    cmd=['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',video_list,
         '-i',sounds[0],'-i',audio]
    filters=f'[2:a:0]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={body_frames/30},asetpts=PTS-STARTPTS[voice];'
    if keep_original_audio:
        cmd+=['-f','concat','-safe','0','-i',body_list]
        filters+='[voice][3:a:0]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98:latency=1[body];'
    else:filters+='[voice]anull[body];'
    filters+='[1:a:0][body]concat=n=2:v=0:a=1[a]'
    out=folder/('preview.mp4' if preview else 'final.mp4');expected=(head_frames+body_frames)/30
    run(cmd+['-filter_complex',filters,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac',
             '-ar','48000','-t',expected,'-movflags','+faststart',out])
    check_cancel();oi=probe(out);portrait_geometry(oi)
    run(['ffmpeg','-v','error','-xerror','-nostdin','-i',out,'-f','null','-'])
    if abs(media_duration(oi,'video')-expected)>.05:raise ValueError('成片时长检查未通过')
    if any(fingerprint(p)!=h for p,h in hashes.items()):raise ValueError('输入文件在渲染期间发生变化')
    report={'duration':expected,'intro_seconds':head_frames/30,'body_seconds':body_frames/30,
            'width':width,'height':height,'fps':30,'sha256':fingerprint(out),'decode_checked':True,
            'source_files_unchanged':True,'intro_audio_preserved':intro_sound,
            'keep_original_audio':keep_original_audio,'human_reviewed':False}
    save(folder/'validation.json',report)
    return out,report
