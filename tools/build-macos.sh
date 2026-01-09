#!/bin/bash

# Build script for Antifier Installer - macOS
# Generates self-contained executable for macOS platform

set -e  # Exit on error

echo "========================================"
echo "  Antifier Installer Build - macOS"
echo "========================================"
echo ""

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ Error: PyInstaller is not installed"
    echo "   Install with: pip install pyinstaller"
    exit 1
fi

echo "✅ PyInstaller found"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/
echo ""

# Build executable using spec file
echo "🔨 Building macOS executable..."
pyinstaller --clean tools/installer.spec

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "Executable location:"
    echo "   $PROJECT_ROOT/dist/antifier-installer-macos"
    echo ""
    echo "File size:"
    ls -lh dist/antifier-installer-macos | awk '{print "   " $5}'
    echo ""
    echo "To test the executable:"
    echo "   ./dist/antifier-installer-macos --help"
else
    echo ""
    echo "❌ Build failed"
    exit 1
fi
