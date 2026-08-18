# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

project_root = Path.cwd().resolve().parents[1]
uploader_root = project_root / "apps" / "uploader"
parser_root = project_root / "packages" / "parser_core"
uploader_core_root = project_root / "packages" / "uploader_core"

for source_root in (uploader_root, parser_root, uploader_core_root):
    source_path = str(source_root)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

datas = [
    (str(uploader_root / "app" / "assets"), "app/assets"),
]

hiddenimports = collect_submodules("parser_core")
hiddenimports += collect_submodules("uploader_core")
hiddenimports += ["socksio"]

excludes = [
    "zstandard",
    "numpy",
    "numpy.libs",
    "PIL",
    "Pillow",
    "tkinter",
    "unittest",
    "pydoc",
    "setuptools",
    "distutils",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtPdf",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtOpenGL",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSensors",
    "PySide6.QtPositioning",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
]


a = Analysis(
    [str(uploader_root / "app" / "main.py")],
    pathex=[str(uploader_root), str(parser_root), str(uploader_core_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # httpx treats any importable `zstandard` namespace as full zstd support.
    # The Windows build host can contain only backend_c.pyd without __init__.py,
    # which yields a decoder object with no ZstdDecompressor at runtime.
    excludes=excludes,
    noarchive=False,
)

excluded_binaries = {
    "opengl32sw.dll",
    "qt6pdf.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmodels.dll",
    "qt6qmlworkerscript.dll",
    "qt6qmlmeta.dll",
    "qt6virtualkeyboard.dll",
    "qt6opengl.dll",
}
a.binaries = [x for x in a.binaries if not any(x[0].lower().endswith(eb) for eb in excluded_binaries)]

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
