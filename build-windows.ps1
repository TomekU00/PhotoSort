param([string]$Python = "python", [string]$Output = "$PSScriptRoot/dist")
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows build requires Windows' }
$Output = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath (Join-Path $Output 'PhotoSort')) { throw 'Use a fresh output directory to avoid stale files' }
Set-Location -LiteralPath $PSScriptRoot
& $Python make-icon.py
if ($LASTEXITCODE) { throw 'Icon build failed' }
& $Python -m PyInstaller --noconfirm --clean --python-option 'X utf8' --onedir --windowed --name PhotoSort --icon assets/photosort.ico --paths _vendor --add-data 'assets;assets' --add-data 'photosort;photosort' --collect-all exifread --collect-all pytz --distpath $Output --workpath build/gui exe_gui.py
if ($LASTEXITCODE) { throw 'GUI build failed' }
& $Python -m PyInstaller --noconfirm --clean --python-option 'X utf8' --onefile --console --name PhotoSort-Terminal --icon assets/photosort.ico --paths _vendor --add-data 'photosort;photosort' --collect-all exifread --collect-all pytz --distpath "$Output/PhotoSort" --workpath build/terminal exe_terminal.py
if ($LASTEXITCODE) { throw 'Terminal build failed' }
