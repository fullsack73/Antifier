# Specification: Single Executable Installer

## Goal
Create platform-specific executable installers (macOS, Windows, Linux) that automate the complete setup of the FinanceIQ webapp, including Python environment creation, dependency installation, and post-installation launch, enabling users to run the application with a single executable.

## User Stories
- As a new user, I want to install the FinanceIQ webapp by running a single executable, so that I don't have to manually set up Python, install packages, or configure environments
- As a user with Node.js, I want the installer to validate my Node.js installation and set up Vite if needed, so that my system is ready to run the webapp
- As a user, I want the webapp to launch automatically after installation completes, so that I can start using it immediately
- As a user, I want to update dependencies by re-running the installer, so that I can keep the webapp up-to-date without manual intervention

## Core Requirements

### Functional Requirements
- Validate Node.js installation is present (prerequisite check)
- Check if Vite is globally installed and install it if missing
- Detect or install Python 3.x on the user's system
- Create isolated Python virtual environment (venv) for the webapp
- Install all Python packages from requirements-pypi.txt into the venv
- Install all frontend dependencies from package.json via npm
- Create platform-specific launcher scripts for easy future startups
- Generate configuration file tracking installation metadata (versions, paths, timestamps)
- Automatically launch the webapp (Flask backend + browser) after successful installation
- Support re-running installer for dependency updates

### Non-Functional Requirements
- CLI-based interface with clear progress messages and error handling
- Platform-specific implementations for macOS, Windows, and Linux
- Graceful error messages for missing prerequisites (Node.js)
- Network error handling for package downloads
- Permission checks and guidance for users
- Installation metadata persisted to JSON configuration file
- Self-contained executable that works without additional files (GitHub release ready)

## Visual Design
No visual assets provided - CLI-based terminal interface.

## Reusable Components

### Existing Code to Leverage
- **cache_warmer.py**: Reference for backend initialization patterns and startup sequences
- **app.py**: Flask application startup logic - reference for proper backend launch (line 1-50 shows imports and Flask initialization)
- **requirements-pypi.txt**: Source of truth for Python dependencies (62 packages)
- **package.json**: Source of truth for frontend dependencies (scripts at lines 6-10 show build commands)
- **README_old.md**: Documents current manual installation process (lines 52-82) showing:
  - Backend: `python src/backend/app.py` starts Flask on port 5000
  - Frontend: `npm run dev` starts Vite on port 5173
  - Two-step manual process that installer will automate

### New Components Required
- **Installer orchestration script**: New Python script to coordinate installation flow, system checks, and environment setup
- **Platform detection module**: Identify OS and execute platform-specific installation logic
- **Python installer**: Download and install Python on systems where it's missing (platform-specific methods)
- **Launcher script generator**: Create .sh (macOS/Linux) and .bat (Windows) scripts for future webapp launches
- **Configuration manager**: Generate and update JSON config file with installation metadata
- **PyInstaller build scripts**: Create executables for each platform from the orchestration script

## Technical Approach

### Installation Flow
1. **Prerequisite validation**:
   - Check Node.js/npm availability (exit if missing)
   - Check Vite global installation (install if missing with user notification)
   - Validate disk space and permissions

2. **Python setup**:
   - Detect Python 3.x installation
   - If missing, download and install using platform-specific method:
     - macOS: Recommend Homebrew or python.org installer
     - Windows: Download and execute official Python installer
     - Linux: Use apt/yum/dnf based on distribution
   - Create venv in webapp directory: `python -m venv .venv`

3. **Dependency installation**:
   - Activate venv
   - Install Python packages: `pip install -r requirements-pypi.txt`
   - Install frontend packages: `npm install`

4. **Post-installation setup**:
   - Generate launcher script:
     - macOS/Linux: Shell script activating venv, starting Flask, opening browser
     - Windows: Batch or PowerShell script with same functionality
   - Create config.json with metadata:
     - Installation date/time
     - Python version detected
     - Node.js version detected
     - Venv location path
     - Package versions installed
     - Last update timestamp

5. **Automatic launch**:
   - Execute Flask backend: Activate venv and run `python src/backend/app.py`
   - Wait for Flask initialization (port 5000)
   - Open default browser to `http://localhost:5173`
   - Execute frontend: `npm run dev` (Vite on port 5173)

### Build Process
- Use PyInstaller to create standalone executables for each platform
- Bundle installation orchestration script with dependencies
- Include requirements-pypi.txt and package.json in bundled resources
- Use PyInstaller's --onefile option to create single self-contained executable
- Embed all required files as resources within the executable
- Create separate builds: `financeiq-installer-macos`, `financeiq-installer-windows.exe`, `financeiq-installer-linux`

### Error Handling
- Missing Node.js: Display error message with installation instructions and exit
- Network failures: Retry with exponential backoff, provide offline troubleshooting guidance
- Permission errors: Detect and suggest running with elevated privileges
- Disk space: Check before installation and warn user if insufficient
- Invalid Python: Validate Python 3.x version (minimum 3.8+)

### Configuration File Structure
```json
{
  "installation_date": "2026-01-09T10:30:00Z",
  "python_version": "3.11.5",
  "nodejs_version": "20.10.0",
  "venv_location": "/path/to/webapp/.venv",
  "last_update": "2026-01-09T10:30:00Z",
  "packages": {
    "python": ["catboost==1.2.8", "flask==3.0.0", ...],
    "npm": ["react==19.0.0", "vite==6.1.0", ...]
  }
}
```

## Out of Scope
- GUI installer interface (CLI only for version 1)
- Automatic Node.js installation (user prerequisite)
- Background auto-update mechanism
- Telemetry or usage tracking
- Uninstaller utility
- Installation progress bars (text-based progress only)

## Success Criteria
- User can run single executable and have fully functional webapp within 10 minutes
- Installer executable is completely self-contained (no additional files required)
- Executable can be distributed via GitHub releases and run immediately
- Installer successfully validates Node.js and Vite installation
- Python venv created with all 62+ packages from requirements-pypi.txt installed
- Frontend dependencies installed from package.json
- Launcher script created and functional on target platform
- Configuration file generated with accurate metadata
- Webapp launches automatically and opens in browser after installation
- Installer can be re-run for updates without conflicts or errors
