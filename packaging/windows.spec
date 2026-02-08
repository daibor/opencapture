# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OpenCapture Windows .exe.

Capture is macOS-only; this build supports analysis commands on Windows:
    OpenCapture.exe --analyze today
    OpenCapture.exe --image screenshot.webp
    OpenCapture.exe --health-check

Build (on Windows):
    pip install pyinstaller
    pyinstaller packaging/windows.spec

Output:
    dist/OpenCapture/OpenCapture.exe
"""

import os

block_cipher = None

spec_dir = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.dirname(spec_dir)
src_dir = os.path.join(project_root, "src")

a = Analysis(
    [os.path.join(src_dir, "opencapture", "cli.py")],
    pathex=[src_dir],
    binaries=[],
    datas=[
        (os.path.join(src_dir, "opencapture", "config", "example.yaml"),
         os.path.join("opencapture", "config")),
    ],
    hiddenimports=[
        "opencapture",
        "opencapture.cli",
        "opencapture.auto_capture",
        "opencapture.config",
        "opencapture.llm_client",
        "opencapture.analyzer",
        "opencapture.report_generator",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude macOS-only modules that won't exist on Windows
    excludes=[
        "AppKit",
        "Quartz",
        "objc",
        "Foundation",
        "CoreFoundation",
        "pyobjc",
        "pyobjc_framework_Cocoa",
        "pyobjc_framework_Quartz",
        "opencapture.mic_capture",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenCapture",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI app, needs console
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OpenCapture",
)
