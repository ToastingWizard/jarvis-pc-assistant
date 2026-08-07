$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ReactDir = Join-Path $PSScriptRoot "web\react-ui"
$ReactIndex = Join-Path $ReactDir "dist\index.html"
$SpecFile = Join-Path $PSScriptRoot "NaiTRO.spec"

Write-Host "==> Building React UI..."
Push-Location $ReactDir
try {
    if (-not (Test-Path "node_modules")) {
        npm install
    }
    npm run build
} finally {
    Pop-Location
}

if (-not (Test-Path $ReactIndex)) {
    throw "React build failed - expected $ReactIndex"
}

$content = Get-Content $ReactIndex -Raw -Encoding UTF8
if ($content -notmatch "NaiTRO OS") {
    throw "React build at $ReactIndex does not look like the NaiTRO OS frontend."
}

Write-Host "==> Cleaning previous PyInstaller output..."
foreach ($dir in @("build", "dist")) {
    $path = Join-Path $PSScriptRoot $dir
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
    }
}

Write-Host "==> Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

Write-Host "==> Building NaiTRO.exe..."
python -m PyInstaller $SpecFile --noconfirm --clean

$ExePath = Join-Path $PSScriptRoot "dist\NaiTRO.exe"
if (-not (Test-Path $ExePath)) {
    throw "Build failed - $ExePath was not created."
}

Write-Host ""
Write-Host "Build complete: $ExePath"
