# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

SPEC_DIR = Path(SPECPATH)
REACT_DIST = SPEC_DIR / "web" / "react-ui" / "dist"
REACT_INDEX = REACT_DIST / "index.html"
CONFIG_EXAMPLE = SPEC_DIR / "config" / "config.example.json"

if not REACT_INDEX.is_file():
    raise SystemExit(
        f"React UI build missing at {REACT_INDEX}.\n"
        "Build it first:\n"
        "  cd web/react-ui\n"
        "  npm install\n"
        "  npm run build"
    )

# Recursively bundle EVERY file under dist/ (JS bundles, CSS, assets/, etc.),
# not just index.html — a single-file tuple only copies that one file.
data_files = [
    (str(f), str(f.parent.relative_to(SPEC_DIR)))
    for f in REACT_DIST.rglob("*")
    if f.is_file()
]
if CONFIG_EXAMPLE.is_file():
    data_files.append((str(CONFIG_EXAMPLE), "config"))

if sys.platform.startswith("win"):
    icon_path = SPEC_DIR / "assets" / "NaiTRO.ico"
    if icon_path.is_file():
        data_files.append((str(icon_path), "."))
    icon_file = [str(icon_path)] if icon_path.is_file() else None
else:
    icon_file = None

a = Analysis(
    ["Python/naitro_app.py"],
    pathex=[str(SPEC_DIR / "Python")],
    binaries=[],
    datas=data_files,
    hiddenimports=[
        "naitro_reviewer",
        "webview_ui",
        # pyttsx3 loads its platform driver dynamically via importlib,
        # which PyInstaller's static analyzer can't detect on its own.
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NaiTRO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
