"""Discover the bundled CPU ASR environment without changing global Python packages."""
import os,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from montage import read,save


def runtime():
    root=REPO/'.asr-runtime'
    return root/('Scripts/python.exe' if os.name=='nt' else 'bin/python'),root/'models/base'


def status():
    python,model=runtime()
    manifest=REPO/'.asr-runtime/installation.json'
    ready=manifest.is_file() and python.is_file() and all((model/name).is_file() for name in ('model.bin','config.json','tokenizer.json'))
    return {'ready':ready,'model':'base','backend':'faster-whisper','model_path':str(model) if ready else '',
            'installed':manifest.is_file(),'note':'本机CPU识别；字幕时间需人工核对' if ready else '本地识别环境待安装，可运行 scripts/install-asr.ps1'}


def transcribe(project,model,language,prompt):
    python,default_model=runtime()
    model=Path(model) if model else default_model
    if not python.is_file():raise ValueError('本地识别依赖未就绪，请运行 scripts/install-asr.ps1 安装，无需上传字幕')
    if not (model/'model.bin').is_file():raise ValueError('本地识别模型尚未就绪，请运行 scripts/install-asr.ps1 完成安装')
    root=Path(project);request=root/'audio/asr-request.json'
    # Full supplied copy can bias Whisper into inventing trailing words. Keep it
    # for comparison, while deriving transcript and timestamps from audio alone.
    save(request,{'project':str(root),'model':str(model),'language':language,'prompt':'','provided_script':prompt,'vad_filter':True})
    result=subprocess.run([str(python),str(Path(__file__).resolve()),str(request)],capture_output=True,
                          encoding='utf-8',errors='replace',timeout=1800)
    if result.returncode:raise ValueError('本地配音识别失败：'+(result.stderr or result.stdout)[-1200:])
    return read(root/'audio/timing.json')


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(REPO))
    from runtime_environment import configure
    configure()
    from types import SimpleNamespace
    from montage import transcribe as run
    run(SimpleNamespace(**read(sys.argv[1])))
