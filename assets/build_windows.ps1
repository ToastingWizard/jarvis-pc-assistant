$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller .\NaiTRO.spec --noconfirm

Write-Host ""
Write-Host "Build complete: $PSScriptRoot\dist\NaiTRO.exe"
