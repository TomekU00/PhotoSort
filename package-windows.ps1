param([string]$Python = 'python', [string]$Output = "$PSScriptRoot/dist")
$ErrorActionPreference = 'Stop'
$Output = [IO.Path]::GetFullPath($Output)
$version = & $Python -c "import importlib.metadata; print(importlib.metadata.version('photosort-tool'))"
if ($LASTEXITCODE -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid package version' }
$package = Join-Path $Output 'PhotoSort'
foreach ($required in @('PhotoSort.exe', 'PhotoSort-Terminal.exe', '_internal')) {
    if (!(Test-Path -LiteralPath (Join-Path $package $required))) { throw "Missing $required" }
}
foreach ($doc in @('README.md', 'CHANGELOG.md', 'TECHNICAL-DOCUMENTATION.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $doc) -Destination $package
}
$zip = Join-Path $Output "PhotoSort-$version-windows-x64.zip"
if (Test-Path -LiteralPath $zip) { throw 'Archive already exists; use a fresh output directory' }
Compress-Archive -LiteralPath $package -DestinationPath $zip
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($zip))" | Set-Content -Encoding ascii -LiteralPath "$zip.sha256"
Write-Host "Package: $zip"
