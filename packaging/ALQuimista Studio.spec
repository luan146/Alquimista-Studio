# -*- mode: python ; coding: utf-8 -*-

import os

ROOT_DIR = os.path.abspath(os.path.join(SPECPATH, os.pardir))


a = Analysis(
    [os.path.join(ROOT_DIR, 'alquimista', '__main__.py')],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=[
        (os.path.join(ROOT_DIR, 'alquimista', 'ui', 'assets'), os.path.join('alquimista', 'ui', 'assets')),
        (os.path.join(ROOT_DIR, 'alquimista', 'ui', 'translations'), os.path.join('alquimista', 'ui', 'translations')),
        (os.path.join(ROOT_DIR, 'assets'), 'assets'),
    ],
    hiddenimports=[],
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
    name='ALQuimista Studio',
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
)
