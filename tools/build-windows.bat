@echo off
REM Build script for Antifier Installer - Windows
REM Generates self-contained executable for Windows platform

echo ========================================
echo   Antifier Installer Build - Windows
echo ========================================
echo.

REM Check if PyInstaller is installed
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo Error: PyInstaller is not installed
    echo    Install with: pip install pyinstaller
    exit /b 1
)

echo PyInstaller found
echo.

REM Get script directory and project root
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
cd /d "%PROJECT_ROOT%"

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

REM Build executable using spec file
echo Building Windows executable...
pyinstaller --clean tools\installer.spec

if %errorlevel% equ 0 (
    echo.
    echo Build successful!
    echo.
    echo Executable location:
    echo    %PROJECT_ROOT%\dist\antifier-installer-windows.exe
    echo.
    echo To test the executable:
    echo    .\dist\antifier-installer-windows.exe --help
) else (
    echo.
    echo Build failed
    exit /b 1
)
