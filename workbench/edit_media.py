"""Compose confirmed footage, narration, optional music and intact bookend clips.

Adapted from the legacy dashboard segmented renderer. No speed changes,
looping, aspect-ratio conversions or invented video frames are permitted.
"""
import math
import subprocess
from pathlib import Path
from montage import probe, portrait_geometry, media_duration, fingerprint, save


def run(args):
    return subprocess.run([str(x) for x in args],check=True,capture_output=True,timeout=3600)


def render(intro,audio,parts,folder,preview=False,keep_original_audio=False,check_cancel=lambda:None,
           clips=(),music=None,music_volume=.15):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    width,height=(360,640) if preview else (1080,1920)
    body_frames=math.ceil(media_duration(probe(audio),'audio')*30-1e-7)
    if sum(p['frames'] for p in parts)!=body_frames:raise ValueError('画面未覆盖完整配音时间轴')
    head=[c['path'] for c in clips if c['position']=='intro'];tail=[c['path'] for c in clips if c['position']=='outro']
    if intro:head.insert(0,str(intro))
    sequence=[];head_frames=0;tail_frames=0
    intro_audio_tail=None
    for role,files in [('intro',head),('outro',tail)]:
        for path in files:
            pi=probe(path);portrait_geometry(pi);seconds=media_duration(pi,'video')
            frames=math.ceil(seconds*30-1e-7)
            if any(s['codec_type']=='audio' for s in pi['streams']):
                audio_seconds=media_duration(pi,'audio')
                excess=audio_seconds-frames/30
                if role=='intro' and not sequence and intro and 0<excess<=min(.12,body_frames/30):
                    # Preserve short container/audio tails at the cut without extending video.
                    intro_audio_tail=(path,frames,excess)
                elif audio_seconds>seconds+.05:
                    raise ValueError('开头或结尾片段的音频长于画面，请先确认边界；不会自动补尾帧')
            if role=='intro':head_frames+=frames
            else:tail_frames+=frames
            sequence.append({'path':path,'start':0,'frames':frames,'role':role})
    sequence=[p for p in sequence if p['role']=='intro']+[dict(p,role='body') for p in parts]+[p for p in sequence if p['role']=='outro']
    expected=(head_frames+body_frames+tail_frames)/30
    paths=[Path(audio)]+[Path(p['path']) for p in sequence if 'path' in p]+([Path(music['path'])] if music else [])
    hashes={str(p):fingerprint(p) for p in paths};videos=[];sounds=[];bookend_audio=False
    for i,part in enumerate(sequence):
        if 'reference_gap' in part:
            if not preview:raise ValueError('参考时间轴仍有空缺，不能正式输出')
            check_cancel()
            out=folder/f'clip-{i:04}.mp4';sound=folder/f'sound-{i:04}.wav'
            frames=part['frames'];beat=int(part['reference_gap'])
            card=f"drawtext=text='SHOT {beat}  /  FOOTAGE NEEDED':fontcolor=white:fontsize=19:x=(w-tw)/2:y=(h-th)/2"
            run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',f'color=c=0x202630:s={width}x{height}:r=30',
                 '-vf',card,'-frames:v',frames,'-an','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p',out])
            run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',frames/30,sound])
            videos.append(out);sounds.append(sound)
            continue
        check_cancel();path=part['path'];start=part['start'];frames=part['frames'];pi=probe(path);portrait_geometry(pi)
        if start+frames/30>media_duration(pi,'video')+1/30+1e-6:raise ValueError('视频长度不足，不能循环或定格补齐')
        out=folder/f'clip-{i:04}.mp4';videos.append(out)
        zoom=part.get('zoom',1) if part['role']=='body' else 1
        if type(zoom) not in (int,float) or not math.isfinite(zoom) or not 1<=zoom<=1.05:raise ValueError('放大倍率无效')
        spatial=f'scale={width}:{height}'
        if zoom!=1:
            unit=max(width//9,math.floor((width/9)*zoom+1e-6))
            spatial=f'scale={unit*9}:{unit*16},crop={width}:{height}:(iw-ow)/2:(ih-oh)/2'
        run(['ffmpeg','-v','error','-nostdin','-n','-ss',start,'-i',path,'-map','0:v:0','-an',
             '-vf',f'fps=30,{spatial},setsar=1,setpts=PTS-STARTPTS','-frames:v',frames,
             '-c:v','libx264','-preset','fast','-pix_fmt','yuv420p',out])
        if int(next(s for s in probe(out)['streams'] if s['codec_type']=='video').get('nb_frames',0))!=frames:
            raise ValueError('源画面不足所需帧数，不补帧')
        sound=folder/f'sound-{i:04}.wav';sounds.append(sound)
        has_sound=any(s['codec_type']=='audio' for s in pi['streams'])
        if part['role']!='body':bookend_audio|=has_sound
        if has_sound and (part['role']!='body' or keep_original_audio):
            run(['ffmpeg','-v','error','-nostdin','-n','-ss',start,'-i',path,'-vn','-af',
                 f'aresample=48000:async=1:first_pts=0,apad,atrim=duration={frames/30}',
                 '-ar','48000','-ac','2',sound])
        else:
            run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',frames/30,sound])
    check_cancel()
    for name,files in [('video',videos),('original',sounds)]:
        (folder/(name+'.txt')).write_text(''.join(f"file '{p.name}'\n" for p in files),encoding='utf-8')
    cmd=['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',folder/'video.txt',
         '-i',audio,'-f','concat','-safe','0','-i',folder/'original.txt']
    filters=(f'[1:a:0]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,'
             f'apad,atrim=duration={body_frames/30},asetpts=PTS-STARTPTS,adelay={head_frames*1600}S:all=1,'
             f'apad,atrim=duration={expected}[voice];')
    mix='[2:a:0][voice]';count=2
    if music:
        cmd+=['-i',music['path']]
        filters+=(f'[3:a:0]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                  f'volume={music_volume},apad,atrim=duration={body_frames/30},asetpts=PTS-STARTPTS,'
                  f'adelay={head_frames*1600}S:all=1,apad,atrim=duration={expected}[music];')
        mix+='[music]';count+=1
    if intro_audio_tail:
        path,cut,excess=intro_audio_tail
        cmd+=['-i',path]
        stream=4 if music else 3
        filters+=(f'[{stream}:a:0]aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,'
                  f'atrim=start_sample={cut*1600},asetpts=PTS-STARTPTS,adelay={cut*1600}S:all=1[headtail];')
        mix+='[headtail]';count+=1
    filters+=mix+f'amix=inputs={count}:duration=first:normalize=0,alimiter=limit=0.98:level=false:latency=1[a]'
    out=folder/('preview.mp4' if preview else 'final.mp4')
    run(cmd+['-filter_complex',filters,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac',
             '-ar','48000','-t',expected,'-movflags','+faststart',out])
    check_cancel();oi=probe(out);portrait_geometry(oi)
    run(['ffmpeg','-v','error','-xerror','-nostdin','-i',out,'-f','null','-'])
    if abs(media_duration(oi,'video')-expected)>.05:raise ValueError('成片时长检查未通过')
    if any(fingerprint(p)!=h for p,h in hashes.items()):raise ValueError('输入文件在渲染期间发生变化')
    report={'duration':expected,'intro_seconds':head_frames/30,'body_seconds':body_frames/30,'outro_seconds':tail_frames/30,
            'width':width,'height':height,'fps':30,'sha256':fingerprint(out),'decode_checked':True,
            'source_files_unchanged':True,'intro_audio_preserved':bookend_audio,'bookends_preserved':True,
            'music_body_only':bool(music),'music_volume':music_volume if music else 0,'music_looped':False,
            'intro_audio_tail_seconds':intro_audio_tail[2] if intro_audio_tail else 0,
            'keep_original_audio':keep_original_audio,'human_reviewed':False}
    save(folder/'validation.json',report);return out,report
