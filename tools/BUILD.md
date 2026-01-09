# Building Antifier Installer Executables

This document describes how to build self-contained executable installers for the Antifier webapp across different platforms (macOS, Windows, Linux).

## Overview

The Antifier installer is packaged using [PyInstaller](https://pyinstaller.org/) to create single-file executables that can be distributed via GitHub releases. These executables are completely self-contained and do not require Python or any other dependencies to be pre-installed on the target system.

**Generated Executables:**
- macOS: `antifier-installer-macos`
- Windows: `antifier-installer-windows.exe`
- Linux: `antifier-installer-linux`

## Prerequisites

### Required Software

All platforms require:
- **Python 3.8+** with pip (for building only, not required to run the executable)
- **PyInstaller 5.0+**: Install with `pip install pyinstaller`

### Platform-Specific Requirements

**macOS:**
- Xcode Command Line Tools (for code signing support)
- Install with: `xcode-select --install`

**Windows:**
- No additional requirements beyond Python and PyInstaller

**Linux:**
- Standard build tools (gcc, make)
- Usually pre-installed or available via package manager

## Building Executables

### Quick Start

Each platform has a dedicated build script that handles the complete build process:

**macOS:**
```bash
./tools/build-macos.sh
```

**Windows:**
```cmd
tools\build-windows.bat
```

**Linux:**
```bash
./tools/build-linux.sh
```

### Build Process Details

The build scripts perform the following steps:

1. **Verify PyInstaller Installation**
   - Checks if PyInstaller is available
   - Exits with error message if not found

2. **Clean Previous Builds**
   - Removes `build/` and `dist/` directories
   - Ensures fresh build without cached artifacts

3. **Run PyInstaller**
   - Uses `tools/installer.spec` configuration file
   - Bundles all dependencies into a single executable
   - Includes data files (requirements-pypi.txt, package.json)
   - Creates platform-specific executable name

4. **Report Build Results**
   - Displays executable location
   - Shows file size
   - Provides command to test the executable

### Build Output

Successful builds create the following structure:

```
portfolio-project/
├── build/              # Temporary build artifacts (can be deleted)
│   └── installer/      # Analysis and compilation cache
├── dist/               # Final executable output
│   └── antifier-installer-{platform}[.exe]
└── tools/
    └── installer.spec  # PyInstaller configuration
```

**Important:** Only the file in `dist/` is needed for distribution. The `build/` directory can be safely deleted.

## Testing Built Executables

### Basic Functionality Test

Test that the executable runs and shows help:

```bash
# macOS/Linux
./dist/antifier-installer-macos --help
./dist/antifier-installer-linux --help

# Windows
.\dist\antifier-installer-windows.exe --help
```

Expected output:
```
usage: antifier-installer-{platform} [-h] [--install-dir INSTALL_DIR] [--verbose]

Antifier Webapp Installer - Automated setup tool

options:
  -h, --help            show this help message and exit
  --install-dir INSTALL_DIR
                        Installation directory (default: current directory)
  --verbose             Enable verbose logging
```

### Verify Self-Contained Execution

Test that the executable runs from a different directory (proving it's self-contained):

```bash
# macOS/Linux
cd /tmp
/path/to/portfolio-project/dist/antifier-installer-macos --help

# Windows
cd C:\Temp
C:\path\to\portfolio-project\dist\antifier-installer-windows.exe --help
```

### Test on Clean System

For thorough testing, run the executable on a system that doesn't have:
- Python installed
- Node.js installed (to test prerequisite detection)
- Any development tools

The installer should:
1. Detect the platform correctly
2. Check for prerequisites (Node.js, Python)
3. Display appropriate error messages if prerequisites are missing
4. Guide the user to install missing prerequisites

## PyInstaller Configuration

### Spec File (`tools/installer.spec`)

The PyInstaller spec file defines how the executable is built:

**Key Configuration:**
- **Entry Point:** `tools/installer.py`
- **Bundled Data Files:**
  - `requirements-pypi.txt` - Python package requirements
  - `package.json` - Node.js package requirements
- **Mode:** One-file (`--onefile`) for single executable output
- **Console Mode:** Enabled for terminal-based installer UI
- **UPX Compression:** Enabled to reduce executable size
- **Platform Detection:** Automatically sets executable name based on build platform

### Customizing the Build

To modify the build configuration, edit `tools/installer.spec`:

**Add more data files:**
```python
datas = [
    (str(project_root / 'requirements-pypi.txt'), '.'),
    (str(project_root / 'package.json'), '.'),
    (str(project_root / 'your-file.txt'), '.'),  # Add here
]
```

**Add hidden imports (if modules aren't detected):**
```python
hiddenimports=['your.module.name']
```

**Disable UPX compression (if causing issues):**
```python
upx=False
```

## Troubleshooting

### Issue: "PyInstaller not found"

**Symptoms:**
```
Error: PyInstaller is not installed
```

**Solution:**
```bash
pip install pyinstaller
```

### Issue: "Module not found" at runtime

**Symptoms:**
Executable builds successfully but crashes with `ModuleNotFoundError` when run.

**Solution:**
Add missing module to `hiddenimports` in `installer.spec`:
```python
hiddenimports=['missing.module.name']
```

### Issue: "Data file not found" at runtime

**Symptoms:**
Executable cannot find `requirements-pypi.txt` or `package.json`.

**Solution:**
1. Verify files are listed in `datas` in `installer.spec`
2. Use `sys._MEIPASS` in code to access bundled files:
```python
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    # Running as executable
    base_path = Path(sys._MEIPASS)
else:
    # Running as script
    base_path = Path(__file__).parent
```

### Issue: Large executable size

**Symptoms:**
Executable is larger than expected (>50MB).

**Possible Causes:**
- Unnecessary dependencies bundled
- UPX compression disabled or not working

**Solutions:**
1. **Enable UPX compression** (if disabled):
   ```python
   upx=True
   ```

2. **Exclude unnecessary modules:**
   ```python
   excludes=['tkinter', 'matplotlib', 'PyQt5']
   ```

3. **Use virtual environment** to minimize dependencies:
   ```bash
   python -m venv build_env
   source build_env/bin/activate  # or build_env\Scripts\activate on Windows
   pip install pyinstaller
   ./tools/build-macos.sh
   ```

### Issue: Antivirus flags executable as suspicious

**Symptoms:**
Windows Defender or other antivirus software blocks the executable.

**Explanation:**
PyInstaller executables are sometimes flagged as suspicious because they use self-extracting archive techniques. This is a false positive.

**Solutions:**
1. **Add to antivirus exclusions** during testing
2. **Code signing** (recommended for production):
   - macOS: `codesign -s "Developer ID" dist/antifier-installer-macos`
   - Windows: Use signtool.exe with a code signing certificate

### Issue: Build fails on macOS with codesign error

**Symptoms:**
```
error: The specified item could not be found in the keychain.
```

**Solution:**
PyInstaller attempts to code sign by default. Disable during development:
```python
codesign_identity=None
```

For production builds, obtain a Developer ID certificate from Apple.

### Issue: Permission denied when running executable

**Symptoms (Unix):**
```
bash: ./antifier-installer-macos: Permission denied
```

**Solution:**
Make executable:
```bash
chmod +x dist/antifier-installer-macos
```

## Distribution via GitHub Releases

### Upload Process

1. **Build executables on each platform:**
   - Build macOS executable on macOS machine
   - Build Windows executable on Windows machine
   - Build Linux executable on Linux machine

2. **Create GitHub Release:**
   ```bash
   # Tag the release
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

3. **Upload executables to release:**
   - `antifier-installer-macos`
   - `antifier-installer-windows.exe`
   - `antifier-installer-linux`

### Release Notes Template

```markdown
## Antifier Installer v1.0.0

Self-contained installers for macOS, Windows, and Linux.

### Downloads

- **macOS:** [antifier-installer-macos](link)
- **Windows:** [antifier-installer-windows.exe](link)
- **Linux:** [antifier-installer-linux](link)

### Usage

Download the appropriate installer for your platform and run:

**macOS/Linux:**
```bash
chmod +x antifier-installer-{platform}
./antifier-installer-{platform}
```

**Windows:**
```cmd
antifier-installer-windows.exe
```

### Prerequisites

The installer will check for and help you install:
- Node.js (required)
- Python 3.8+ (required)
- Vite (automatically installed if missing)
```

## Build Automation (CI/CD)

### GitHub Actions Example

To automate builds across all platforms using GitHub Actions:

```yaml
name: Build Installers

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    strategy:
      matrix:
        os: [macos-latest, windows-latest, ubuntu-latest]
    
    runs-on: ${{ matrix.os }}
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install PyInstaller
        run: pip install pyinstaller
      
      - name: Build (macOS)
        if: runner.os == 'macOS'
        run: ./tools/build-macos.sh
      
      - name: Build (Windows)
        if: runner.os == 'Windows'
        run: tools\build-windows.bat
      
      - name: Build (Linux)
        if: runner.os == 'Linux'
        run: ./tools/build-linux.sh
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: installer-${{ runner.os }}
          path: dist/*
```

## Additional Resources

- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [PyInstaller Spec File Reference](https://pyinstaller.org/en/stable/spec-files.html)
- [Code Signing Guide (macOS)](https://developer.apple.com/support/code-signing/)
- [Code Signing Guide (Windows)](https://docs.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools)

## Support

For build issues or questions:
1. Check this troubleshooting guide
2. Review PyInstaller logs in `build/installer/warn-installer.txt`
3. Open an issue on GitHub with build logs
