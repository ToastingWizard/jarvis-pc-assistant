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

# Write a manifest of every bundled data file so the frozen app can verify
# at runtime (diagnostics.verify_bundled) that each one actually exists in
# sys._MEIPASS.  The manifest is bundled alongside the files it lists.
manifest_lines = []
for src, dest in data_files:
    rel = (Path(dest) / Path(src).name).as_posix()
    manifest_lines.append(rel)
_manifest_file = SPEC_DIR / "build" / "bundle-manifest.txt"
_manifest_file.parent.mkdir(parents=True, exist_ok=True)
_manifest_file.write_text("\n".join(sorted(manifest_lines)) + "\n", encoding="utf-8")
data_files.append((str(_manifest_file), "."))

a = Analysis(
    ["naitro_main.py"],
    pathex=[str(SPEC_DIR / "Python")],
    binaries=[],
    datas=data_files,
    hiddenimports=[
        "diagnostics",
        "naitro_reviewer",
        "http_server",
        "naitro_app",
        "app_launcher",
        "ai_client",
        "browser_agent",
        "browser_agent.agent",
        "browser_agent.executor",
        "browser_agent.memory",
        "browser_agent.planner",
        "browser_agent.search",
        "browser_agent.types",
        "browser_agent.validator",
        # pyttsx3 loads its platform driver dynamically via importlib,
        # which PyInstaller's static analyzer can't detect on its own.
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
        # FastAPI and uvicorn dependencies
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
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
    upx=False,
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
