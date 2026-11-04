param(
    [string]$Proxy = $env:HYPIT_PROXY,
    [switch]$NoProxy,
    [switch]$AllowInsecureTls,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $repo '.hypit-runtime'
$version = '0.3.1'

function Fail([string]$message) {
    [Console]::Error.WriteLine($message)
    exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail 'Node.js is missing. Install Node.js 22.15 or newer.'
}
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    Fail 'npm.cmd is missing. Install Node.js with npm.'
}

$nodeVersion = (& node --version).Trim().TrimStart('v')
$nodeParts = $nodeVersion.Split('.')
if ($nodeParts.Count -lt 2) { Fail "Invalid Node.js version: $nodeVersion" }
$nodeMajor = [int]$nodeParts[0]
$nodeMinor = [int]$nodeParts[1]
$tooOld = ($nodeMajor -lt 22) -or (($nodeMajor -eq 22) -and ($nodeMinor -lt 15))
if ($tooOld) {
    Fail "Hypit requires Node.js 22.15 or newer. Found: $nodeVersion"
}

if (-not $NoProxy) {
    if (-not $Proxy) { $Proxy = 'http://127.0.0.1:7897' }
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
    Write-Host "Proxy: $Proxy"
}

$npmArgs = @(
    'install', '--prefix', $runtime, '--save-exact',
    '--registry', 'https://registry.npmjs.org',
    '--fetch-timeout', '30000', '--fetch-retries', '1',
    ("@hypit/hypit@" + $version)
)
if ($AllowInsecureTls) {
    $npmArgs += @('--strict-ssl=false')
    Write-Warning 'TLS certificate verification is disabled for this npm invocation.'
}

if ($CheckOnly) {
    Write-Host "Preflight OK. Node: $nodeVersion"
    Write-Host "Package: @hypit/hypit@$version"
    Write-Host "Target: $runtime"
    exit 0
}
Write-Host "Installing @hypit/hypit@$version into $runtime ..."
& $npmCommand.Source @npmArgs
if ($LASTEXITCODE -ne 0) { Fail "npm installation failed. Exit code: $LASTEXITCODE" }

$hypit = Join-Path $runtime 'node_modules\.bin\hypit.cmd'
if (-not (Test-Path $hypit)) { Fail "Hypit CLI is missing: $hypit" }
$reported = (& $hypit version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { Fail 'Hypit CLI failed to start.' }
$packageFile = Join-Path $runtime 'node_modules\@hypit\hypit\package.json'
$installedVersion = (Get-Content -Raw -Encoding UTF8 $packageFile | ConvertFrom-Json).version
if ($installedVersion -ne $version) {
    Fail "Version mismatch. Expected: $version. Installed: $installedVersion"
}

$manifest = [ordered]@{
    package = '@hypit/hypit'
    version = $version
    executable = $hypit
    node = $nodeVersion
    installed_at = (Get-Date).ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtime 'INSTALL-MANIFEST.json')
Write-Host "Hypit $version installed and verified. CLI: $reported"
Write-Host "Restart the workbench to use: $hypit"
