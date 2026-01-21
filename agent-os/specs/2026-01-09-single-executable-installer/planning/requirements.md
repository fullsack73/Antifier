# Spec Requirements: Single Executable Installer

## Initial Description
in order for a user to run this webapp in their local machine, they have to have python and all the modules at #file:requirements-pypi.txt plus the npm + vite.

i want to wrap this process in a single executable so all of the requirements are installed at single run of an exe.

## Requirements Discussion

### First Round Questions

**Q1: Target Operating System**
I assume you want to support macOS, Windows, and Linux with a single installer that auto-detects the OS and installs appropriate dependencies. Is that correct, or do you want separate executables for each platform?

**Answer:** let's seperate installation files for each OS

**Q2: Python Environment Management**
I'm thinking the installer should create an isolated Python environment (like a conda environment or venv) rather than modifying the user's global Python installation. This would avoid conflicts with existing Python packages. Should we go with conda (since you're using it) or a lighter venv approach?

**Answer:** venv approach should be better

**Q3: Node.js/npm Bundling**
I assume the installer should either bundle Node.js/npm or check if they're installed and offer to install them automatically. Would you prefer the installer to download Node.js during runtime if missing, or should it be fully bundled (larger file size but works offline)?

**Answer:** yeah, i will state that node.js is a neccesity. we should first check if user has node js installed, and if not we cancel the installation. if they have it, we should then check if they also got vite installed in it too. and if not, we run the install command with a notification to the user

**Q4: Installation Process**
I'm thinking the installer should:
- Check for Python (install if missing)
- Create isolated Python environment
- Install all pip packages from requirements-pypi.txt
- Check for Node.js/npm (install if missing)
- Run `npm install` for frontend dependencies
- Optionally create desktop shortcuts/launcher scripts

Does this flow work for you, or would you like a different sequence?

**Answer:** yeah you're right

**Q5: Installer Technology**
For creating the single executable, I'm assuming we should use PyInstaller or similar to bundle a Python script that orchestrates the installation. Alternatively, we could use platform-specific installers (InnoSetup for Windows, DMG for macOS, .deb/.rpm for Linux). Which approach do you prefer?

**Answer:** let's go with pyinstaller

**Q6: User Interaction**
Should the installer be GUI-based (with a visual installer window) or CLI-based (terminal prompts)? Or perhaps a hybrid where it opens a terminal with friendly prompts?

**Answer:** making it CLI based should be easier so let's go with that

**Q7: Post-Installation Launch**
After installation completes, should the installer automatically start the webapp (launch backend + open browser), or just complete and let users manually start it later via a launcher script?

**Answer:** we should automatically launch the webapp post-installation

**Q8: Configuration & Updates**
Should the installer create configuration files for easy updates later? For example, tracking installed versions and allowing users to run the installer again to update dependencies?

**Answer:** yes

**Q9: Scope Boundaries**
Are there any specific features you DON'T want in the first version? For example, auto-updates, telemetry, or installation progress bars might add complexity.

**Answer:** i don't have any at the moment

### Existing Code to Reference

**Similar Features Identified:**
- `cache_warmer.py` - Backend initialization script that could inform post-installation startup logic
- `requirements-pypi.txt` and `requirements.txt` - Existing dependency files to reference
- `package.json` - Frontend dependency configuration

No direct installer or setup scripts exist currently that need to be referenced.

### Follow-up Questions
None required - all requirements are clear.

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
Not applicable.

## Requirements Summary

### Functional Requirements

**Platform Support:**
- Create separate installer executables for macOS, Windows, and Linux
- Each installer tailored to its platform's conventions and paths

**Prerequisite Checking:**
- Check if Node.js is installed before proceeding
- If Node.js is not found, cancel installation with error message
- If Node.js is found, check if Vite is globally installed
- If Vite is not installed, run `npm install -g vite` with notification to user

**Python Environment Setup:**
- Check if Python 3.x is installed on system
- If Python is missing, install it (platform-appropriate method)
- Create isolated venv (Python virtual environment) for the webapp
- Activate venv and install all packages from requirements-pypi.txt

**Frontend Dependencies:**
- Run `npm install` to install all frontend dependencies from package.json
- Handle npm errors gracefully with user-friendly messages

**Post-Installation:**
- Create launcher scripts for easy future startup
- Create configuration file tracking installed versions and installation paths
- Automatically launch the webapp (start Flask backend + open browser to frontend)
- Provide user with confirmation of successful installation

**Update Support:**
- Save installation metadata to config file
- Allow installer to be run again for updates
- Detect existing installation and offer to update dependencies

### Reusability Opportunities
- Backend cache warming logic (cache_warmer.py) can inform startup sequence
- Existing dependency files (requirements-pypi.txt, package.json) are the source of truth
- Flask app startup logic (app.py) should be referenced for proper backend launch

### Scope Boundaries

**In Scope:**
- Platform-specific installers (3 separate executables)
- Python environment creation and dependency installation
- Node.js/Vite prerequisite validation
- Frontend dependency installation
- Automatic webapp launch after installation
- Configuration file for tracking installation
- Update capability via re-running installer
- CLI-based user interaction with clear progress messages

**Out of Scope:**
- GUI installer interface (CLI only for v1)
- Automatic Node.js installation (user must have it pre-installed)
- Auto-update mechanism (background updates)
- Telemetry or usage tracking
- Uninstaller tool
- Installation progress bars (simple text output is sufficient)

### Technical Considerations

**Build Tool:**
- Use PyInstaller to create standalone executables for each platform
- Bundle Python installer script with necessary installation logic

**Environment Isolation:**
- Use Python venv (not conda) for lighter weight and better portability
- Venv will be created in webapp directory or user-specified location

**Platform Differences:**
- macOS: Use homebrew or python.org installer for Python if missing
- Windows: Download and run official Python installer if missing
- Linux: Use apt/yum/dnf depending on distribution for Python if missing

**Error Handling:**
- Graceful failure messages for missing Node.js
- Network error handling for pip/npm package downloads
- Permission issues (suggest running with appropriate privileges)
- Disk space checks before installation

**Launcher Script Creation:**
- macOS/Linux: Shell script (.sh) that activates venv, starts Flask, opens browser
- Windows: Batch file (.bat) or PowerShell script for same functionality

**Configuration File:**
- JSON or YAML file storing:
  - Installation date
  - Python version used
  - Node.js version detected
  - Venv location
  - Installed package versions
  - Last update timestamp
