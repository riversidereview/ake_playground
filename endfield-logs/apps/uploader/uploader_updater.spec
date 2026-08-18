# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path.cwd().resolve().parents[1]
uploader_root = project_root / "apps" / "uploader"


a = Analysis(
    [str(uploader_root / "app" / "updater_main.py")],
    pathex=[str(uploader_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "sqlite3", "pydoc", "setuptools", "distutils"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EndfieldLogsUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(uploader_root / "app" / "assets" / "logo.ico"),
)
