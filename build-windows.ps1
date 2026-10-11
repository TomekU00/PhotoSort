param([string]$Python = "python", [string]$Output = "$PSScriptRoot/dist")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python make-icon.py
if ($LASTEXITCODE) { throw 'Icon build failed' }
& $Python -m PyInstaller --noconfirm --clean --onedir --windowed --name PhotoSort --icon assets/photosort.ico --paths _vendor --add-data 'assets;assets' --add-data 'photosort;photosort' --collect-all exifread --collect-all pytz --distpath $Output --workpath build/gui exe_gui.py
if ($LASTEXITCODE) { throw 'GUI build failed' }
& $Python -m PyInstaller --noconfirm --clean --onefile --console --name PhotoSort-Terminal --icon assets/photosort.ico --paths _vendor --add-data 'photosort;photosort' --collect-all exifread --collect-all pytz --distpath "$Output/PhotoSort" --workpath build/terminal exe_terminal.py
if ($LASTEXITCODE) { throw 'Terminal build failed' }
