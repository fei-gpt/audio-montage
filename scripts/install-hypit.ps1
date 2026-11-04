param(
    [string]$Proxy = $env:HYPIT_PROXY,
    [switch]$NoProxy,
    [switch]$AllowInsecureTls
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $repo '.hypit-runtime'
$version = '0.3.1'

function Fail([string]$message) {
    Write-Error $message
    exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail '找不到 Node.js。请先安装 Node.js 22.15+。'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail '找不到 npm。请先安装 Node.js 22.15+。'
}

$nodeVersion = (& node --version).Trim().TrimStart('v')
try { $node = [version]$nodeVersion } catch { Fail "无法解析 Node.js 版本：$nodeVersion" }
$tooOld = ($node.Major -lt 22) -or (($node.Major -eq 22) -and ($node.Minor -lt 15))
if ($tooOld) {
    Fail "Hypit 0.3.1 需要 Node.js 22.15+，当前为 $nodeVersion。"
}

if (-not $NoProxy) {
    if (-not $Proxy) { $Proxy = 'http://127.0.0.1:7897' }
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
    Write-Host "使用代理：$Proxy"
}

$npmArgs = @(
    'install', '--prefix', $runtime, '--save-exact',
    '--registry', 'https://registry.npmjs.org',
    '--fetch-timeout', '30000', '--fetch-retries', '1',
    '@hypit/hypit@' + $version
)
if ($AllowInsecureTls) {
    $npmArgs += @('--strict-ssl=false')
    Write-Warning '本次 npm 安装关闭了严格 TLS 校验，仅用于兼容本机代理证书。'
}

Write-Host "安装 @hypit/hypit@$version 到 $runtime ..."
& npm @npmArgs
if ($LASTEXITCODE -ne 0) { Fail "Hypit 安装失败，npm 退出码：$LASTEXITCODE" }

$hypit = Join-Path $runtime 'node_modules\.bin\hypit.cmd'
if (-not (Test-Path $hypit)) { Fail "安装完成但找不到 Hypit CLI：$hypit" }
$reported = (& $hypit version).Trim()
if ($LASTEXITCODE -ne 0) { Fail 'Hypit CLI 启动失败。' }
if ($reported -notmatch [regex]::Escape($version)) {
    Fail "Hypit 版本校验失败：期望 $version，实际 $reported"
}

$manifest = [ordered]@{
    package = '@hypit/hypit'
    version = $version
    executable = $hypit
    node = $nodeVersion
    installed_at = (Get-Date).ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtime 'INSTALL-MANIFEST.json')
Write-Host "Hypit $version 安装并验证成功。"
Write-Host "工作台重启后会自动使用：$hypit"
