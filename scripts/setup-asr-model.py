"""Explicit installer only. Runtime jobs never download models or use HF credentials."""
import argparse,hashlib,json,os
from pathlib import Path

os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS']='1'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--endpoint',default='https://huggingface.co');args=parser.parse_args()
    os.environ['HF_ENDPOINT']=args.endpoint
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
    from huggingface_hub import HfApi,snapshot_download
    info=HfApi(token=False).model_info('Systran/faster-whisper-base')
    snapshot_download('Systran/faster-whisper-base',revision=info.sha,local_dir=str(root),token=False,
                      allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
    from faster_whisper import WhisperModel
    WhisperModel(str(root),device='cpu',compute_type='int8',local_files_only=True)
    manifest={'repository':'Systran/faster-whisper-base','endpoint':args.endpoint,'revision':info.sha,'backend':'faster-whisper==1.2.1',
              'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.iterdir() if f.is_file()}}
    (root.parents[1]/'installation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Multilingual base model installed and loaded locally.')
