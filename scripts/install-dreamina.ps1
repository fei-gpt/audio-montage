param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $repoPath '.dreamina-runtime'
$cliPath = Join-Path $runtimePath 'dreamina.exe'
if (-not (Test-Path -LiteralPath $cliPath)) {
    if ($CheckOnly) { throw 'Official Dreamina CLI is not installed.' }
    New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $sourceUrl = 'https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_windows_amd64.exe'
    $partialPath = Join-Path $runtimePath 'dreamina.download'
    Invoke-WebRequest -UseBasicParsing -Uri $sourceUrl -OutFile $partialPath
    Move-Item -LiteralPath $partialPath -Destination $cliPath
    @{ source = $sourceUrl; sha256 = (Get-FileHash -LiteralPath $cliPath -Algorithm SHA256).Hash } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'installation.json') -Encoding UTF8
}
& $cliPath -h
if ($LASTEXITCODE -ne 0) { throw 'Dreamina CLI help verification failed.' }
Write-Host "Installed: $cliPath"
Write-Host 'No generation was submitted. Complete one-time login with:'
Write-Host "& '$cliPath' login"
