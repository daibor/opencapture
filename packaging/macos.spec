# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OpenCapture macOS .app bundle.

Build:
    pip install pyinstaller
    pyinstaller packaging/macos.spec

Output:
    dist/OpenCapture.app

Signing is handled by the release workflow (Developer ID + notarization).
For local testing, ad-hoc sign:
    codesign --force --deep --sign - dist/OpenCapture.app
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Resolve paths relative to spec file location
spec_dir = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.dirname(spec_dir)
src_dir = os.path.join(project_root, "src")

# Collect yaml package completely (PyInstaller 6 bundle layout can split it)
yaml_datas, yaml_binaries, yaml_hiddenimports = collect_all('yaml')

a = Analysis(
    [os.path.join(src_dir, "opencapture", "cli.py")],
    pathex=[src_dir],
    binaries=yaml_binaries,
    datas=[
        (os.path.join(src_dir, "opencapture", "config", "example.yaml"),
         os.path.join("opencapture", "config")),
    ] + yaml_datas,
    hiddenimports=[
        "opencapture",
        "opencapture.cli",
        "opencapture.auto_capture",
        "opencapture.mic_capture",
        "opencapture.config",
        "opencapture.llm_client",
        "opencapture.analyzer",
        "opencapture.report_generator",
        "pynput.keyboard._darwin",
        "pynput.mouse._darwin",
    ] + yaml_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
    disable_windowed_traceback=False,
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

app = BUNDLE(
    coll,
    name="OpenCapture.app",
    icon=None,
    bundle_identifier="com.opencapture.agent",
    info_plist={
        "CFBundleName": "OpenCapture",
        "CFBundleDisplayName": "OpenCapture",
        "CFBundleVersion": "0.0.0",
        "CFBundleShortVersionString": "0.0.0",
        "LSUIElement": True,  # No Dock icon
        # Usage descriptions required for hardened runtime
        "NSAppleEventsUsageDescription": "OpenCapture uses Apple Events for system integration.",
        "NSMicrophoneUsageDescription": "OpenCapture records microphone audio when enabled.",
        "NSScreenCaptureUsageDescription": "OpenCapture captures screenshots of user activity.",
        "NSAccessibilityUsageDescription": "OpenCapture monitors keyboard and mouse input.",
    },
)
