param([switch]$CheckOnly, [string]$IndexUrl = 'https://pypi.org/simple', [string]$ModelEndpoint = 'https://huggingface.co')
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $repoPath '.asr-runtime'
$pythonPath = Join-Path $runtimePath 'Scripts\python.exe'
$modelPath = Join-Path $runtimePath 'models\base'
if ($CheckOnly) {
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'ASR Python is not installed.' }
    & $pythonPath -c "from faster_whisper import WhisperModel; WhisperModel(r'$modelPath', device='cpu', compute_type='int8', local_files_only=True); print('Local ASR ready')"
    if ($LASTEXITCODE -ne 0) { throw 'ASR verification failed.' }
    exit 0
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create ASR virtual environment.' }
}
& $pythonPath -m pip install --disable-pip-version-check --index-url $IndexUrl 'faster-whisper==1.2.1'
if ($LASTEXITCODE -ne 0) { throw 'Cannot install faster-whisper dependencies.' }
& $pythonPath (Join-Path $PSScriptRoot 'setup-asr-model.py') --output $modelPath --endpoint $ModelEndpoint
if ($LASTEXITCODE -ne 0) { throw 'Cannot finish local ASR model installation.' }
Write-Host 'Local multilingual CPU ASR installed. No paid API was called.'
