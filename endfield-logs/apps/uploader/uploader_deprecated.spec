# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path.cwd().resolve().parents[1]
uploader_root = project_root / "apps" / "uploader"

datas = [
    (str(uploader_root / "app" / "assets"), "app/assets"),
]


a = Analysis(
    [str(uploader_root / "app" / "deprecated_main.py")],
    pathex=[str(uploader_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EndfieldLogsUploader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(uploader_root / "app" / "assets" / "logo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EndfieldLogsUploader",
)
