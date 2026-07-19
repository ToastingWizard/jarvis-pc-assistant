# -*- mode: python ; coding: utf-8 -*-

import sys

block_cipher = None

icon_file = ['assets/NaiTRO.ico'] if sys.platform.startswith('win') else None
data_files = [('assets/NaiTRO.ico', '.')] if sys.platform.startswith('win') else []

a = Analysis(
    ['Python/naitro_app.py'],
    pathex=[],
    binaries=[],
    datas=data_files,
    hiddenimports=['naitro_reviewer'],
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
    name='NaiTRO',
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
