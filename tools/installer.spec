# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Antifier Webapp Installer
Generates self-contained executable for distribution via GitHub releases
"""

import sys
from pathlib import Path

# Determine platform-specific executable name
if sys.platform == 'darwin':
    exe_name = 'antifier-installer-macos'
elif sys.platform == 'win32':
    exe_name = 'antifier-installer-windows'
else:  # Linux and other Unix
    exe_name = 'antifier-installer-linux'

# Get project root directory
project_root = Path(SPECPATH).parent

# Data files to include in the executable
# Bundle the entire application (src/, package.json, etc.)
datas = [
    (str(project_root / 'requirements-pypi.txt'), '.'),
    (str(project_root / 'package.json'), '.'),
    (str(project_root / 'package-lock.json'), '.'),
    (str(project_root / 'vite.config.js'), '.'),
    (str(project_root / 'index.html'), '.'),
    (str(project_root / 'eslint.config.js'), '.'),
    (str(project_root / 'src'), 'src'),  # Bundle entire src directory
    (str(project_root / 'public'), 'public'),  # Bundle public directory
]

block_cipher = None

a = Analysis(
    [str(project_root / 'tools' / 'installer.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
