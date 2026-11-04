param([Parameter(Mandatory=$true)][string]$SourceDirectory)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $repo '.media-runtime\bin'
$source = (Resolve-Path -LiteralPath $SourceDirectory).Path
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
    $file = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing: $file" }
    $versionText = & $file -version
    if ($LASTEXITCODE -ne 0) { throw "Cannot run: $file" }
    $versionText | Select-Object -First 1
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
$encoderText = & (Join-Path $source 'ffmpeg.exe') -hide_banner -encoders 2>&1 | Out-String
if ($encoderText -notmatch '\blibx264\b') { throw 'FFmpeg must include the libx264 encoder.' }
$records = @()
$names = @('ffmpeg.exe', 'ffprobe.exe') + @(Get-ChildItem -LiteralPath $source -Filter '*.dll' -File | ForEach-Object { $_.Name })
foreach ($name in $names) {
    $file = Join-Path $source $name
    $dest = Join-Path $target $name
    if (Test-Path -LiteralPath $dest) {
        if ((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $file).Hash) {
            throw "Existing tool differs; preserve it and choose another runtime: $dest"
        }
    } else { Copy-Item -LiteralPath $file -Destination $dest }
    $records += @{name=$name; source=$file; sha256=(Get-FileHash -LiteralPath $dest).Hash}
}
@{tools=$records; installed_at=(Get-Date).ToString('o')} | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $repo '.media-runtime\INSTALL-MANIFEST.json')
Write-Host "Project media tools installed: $target"
