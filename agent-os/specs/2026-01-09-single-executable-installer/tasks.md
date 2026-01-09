# Task Breakdown: Single Executable Installer

## Overview
Total Tasks: 3 major task groups
Assigned roles: api-engineer, testing-engineer
Note: This spec focuses on Python scripting and build tooling rather than database or UI work

## Task List

### Core Installer Script

#### Task Group 1: Installer Orchestration & System Validation
**Assigned implementer:** api-engineer
**Dependencies:** None

- [ ] 1.0 Complete installer orchestration script
  - [ ] 1.1 Write 2-8 focused tests for installer core functionality
    - Test platform detection (OS identification)
    - Test Node.js validation (presence check)
    - Test Vite check and installation logic
    - Test Python detection logic
    - Test configuration file generation and parsing
    - Limit to 2-8 critical tests maximum
  - [ ] 1.2 Create main installer script (`tools/installer.py`)
    - Implement CLI interface with progress messages
    - Add command-line argument parsing for installation options
    - Create main installation flow orchestration
    - Reference: `cache_warmer.py` for initialization patterns
  - [ ] 1.3 Implement platform detection module
    - Detect macOS, Windows, or Linux
    - Identify Linux distribution (Ubuntu/Debian, RHEL/Fedora, etc.)
    - Return platform-specific configuration
  - [ ] 1.4 Implement Node.js/Vite validation
    - Check Node.js installation via `node --version`
    - Exit with error message if Node.js not found
    - Check Vite global installation via `npm list -g vite`
    - Install Vite globally if missing with user notification
  - [ ] 1.5 Implement Python detection and installation
    - Check for Python 3.x via `python --version` or `python3 --version`
    - Validate Python version is 3.8 or higher
    - If missing, trigger platform-specific Python installer:
      - macOS: Display instructions for Homebrew or python.org
      - Windows: Download and execute Python installer
      - Linux: Use apt/yum/dnf based on distribution
  - [ ] 1.6 Implement disk space and permission checks
    - Validate sufficient disk space (estimate 2GB minimum)
    - Check write permissions in installation directory
    - Provide clear error messages if checks fail
  - [ ] 1.7 Ensure installer core tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify platform detection works correctly
    - Verify prerequisite checks function properly
    - Do NOT run entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 pass
- Platform detection identifies OS correctly
- Node.js validation exits gracefully if not found
- Vite installation works when missing
- Python detection and version validation works
- Disk space and permission checks function properly

### Environment Setup & Dependencies

#### Task Group 2: Virtual Environment & Package Installation
**Assigned implementer:** api-engineer
**Dependencies:** Task Group 1

- [ ] 2.0 Complete environment setup and dependency installation
  - [ ] 2.1 Write 2-8 focused tests for environment setup
    - Test venv creation process
    - Test pip package installation with mock packages
    - Test npm package installation with mock packages
    - Test error handling for network failures
    - Test error handling for corrupted requirements files
    - Limit to 2-8 critical tests maximum
  - [ ] 2.2 Implement Python venv creation
    - Create `.venv` directory in webapp root
    - Execute `python -m venv .venv` with error handling
    - Verify venv creation success
  - [ ] 2.3 Implement Python package installation
    - Activate venv (platform-specific activation)
    - Install pip packages from `requirements-pypi.txt`
    - Parse and display installation progress
    - Handle network errors with retry logic (exponential backoff)
    - Log installed package versions to config
  - [ ] 2.4 Implement frontend dependency installation
    - Run `npm install` in webapp root
    - Display npm installation progress
    - Handle network errors with retry logic
    - Log installed package versions from package-lock.json
  - [ ] 2.5 Implement configuration file management
    - Create `config.json` in webapp root or `.installer/` directory
    - Store installation metadata:
      - Installation date/time (ISO format)
      - Python version used
      - Node.js version detected
      - Venv location (absolute path)
      - Installed package versions (Python + npm)
      - Last update timestamp
    - Reference config.json structure from spec
  - [ ] 2.6 Implement update detection logic
    - Read existing config.json if present
    - Compare installed versions with current requirements
    - Offer to update outdated packages
    - Preserve user data during updates
  - [ ] 2.7 Ensure environment setup tests pass
    - Run ONLY the 2-8 tests written in 2.1
    - Verify venv creation works
    - Verify package installation logic handles errors
    - Do NOT run entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 2.1 pass
- Venv created successfully in webapp directory
- All Python packages from requirements-pypi.txt install correctly
- All npm packages from package.json install correctly
- Configuration file generated with accurate metadata
- Update logic detects existing installation and offers updates

### Launcher Scripts & Post-Installation

#### Task Group 3: Launcher Generation & Webapp Launch
**Assigned implementer:** api-engineer
**Dependencies:** Task Group 2

- [ ] 3.0 Complete launcher generation and post-installation
  - [ ] 3.1 Write 2-8 focused tests for launcher functionality
    - Test launcher script generation for each platform
    - Test launcher script content validation
    - Test webapp launch sequence logic
    - Test browser opening logic
    - Limit to 2-8 critical tests maximum
  - [ ] 3.2 Create launcher script generator
    - Generate platform-specific launcher scripts:
      - macOS/Linux: `launch-financeiq.sh`
      - Windows: `launch-financeiq.bat`
    - Make scripts executable (chmod +x on Unix)
    - Store scripts in webapp root
  - [ ] 3.3 Implement macOS/Linux launcher script
    - Shell script that:
      - Activates venv: `source .venv/bin/activate`
      - Starts Flask backend: `python src/backend/app.py &`
      - Waits for Flask to initialize (check port 5000)
      - Starts frontend: `npm run dev &`
      - Opens browser to `http://localhost:5173`
      - Reference: README_old.md lines 52-82 for startup commands
  - [ ] 3.4 Implement Windows launcher script
    - Batch/PowerShell script that:
      - Activates venv: `.venv\Scripts\activate.bat`
      - Starts Flask backend in new window
      - Starts frontend in new window
      - Opens browser to `http://localhost:5173`
  - [ ] 3.5 Implement post-installation launcher
    - After successful installation, automatically:
      - Execute generated launcher script
      - Display success message with URLs
      - Provide instructions for future manual launches
  - [ ] 3.6 Implement webapp launch logic
    - Start Flask backend process
    - Poll port 5000 until Flask is ready (max 30s timeout)
    - Start Vite frontend process
    - Open default browser using platform-specific command:
      - macOS: `open http://localhost:5173`
      - Linux: `xdg-open http://localhost:5173`
      - Windows: `start http://localhost:5173`
  - [ ] 3.7 Ensure launcher tests pass
    - Run ONLY the 2-8 tests written in 3.1
    - Verify launcher scripts generate correctly for each platform
    - Verify launch sequence logic is sound
    - Do NOT run entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 3.1 pass
- Launcher scripts generated for appropriate platform
- Launcher scripts have correct permissions (executable on Unix)
- Webapp launches automatically after installation
- Flask backend starts on port 5000
- Vite frontend starts on port 5173
- Browser opens to correct URL
- User receives clear success message and usage instructions

### PyInstaller Build Configuration

#### Task Group 4: Executable Packaging
**Assigned implementer:** api-engineer
**Dependencies:** Task Groups 1-3

- [ ] 4.0 Complete PyInstaller build configuration
  - [ ] 4.1 Create PyInstaller spec file
    - Define entry point: `tools/installer.py`
    - Include data files: `requirements-pypi.txt`, `package.json`
    - Configure one-file bundling with --onefile option
    - Embed all resources within executable (no external data files)
    - Set appropriate console mode
    - Ensure executable is self-contained for GitHub release distribution
  - [ ] 4.2 Create build scripts for each platform
    - `build-macos.sh`: Build script for macOS executable
    - `build-windows.bat`: Build script for Windows executable
    - `build-linux.sh`: Build script for Linux executable
  - [ ] 4.3 Configure platform-specific builds
    - macOS: Generate `financeiq-installer-macos` executable
    - Windows: Generate `financeiq-installer-windows.exe` executable
    - Linux: Generate `financeiq-installer-linux` executable
  - [ ] 4.4 Test executable builds
    - Build each platform executable
    - Verify executables run without errors
    - Verify bundled resources are accessible
    - Test on clean systems (no Python installed)
  - [ ] 4.5 Create build documentation
    - Document build process in `tools/BUILD.md`
    - Include prerequisites for building
    - Include build commands for each platform
    - Document troubleshooting common build issues

**Acceptance Criteria:**
- PyInstaller spec file created and configured with --onefile option
- Build scripts created for all three platforms
- Executables build successfully for each platform
- Executables are completely self-contained (single file, no dependencies)
- Executables run on clean systems without Python
- Bundled resources (requirements files) are accessible from within executable
- Executables can be uploaded to GitHub releases and run immediately
- Build documentation is clear and complete

### Testing

#### Task Group 5: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-4

- [ ] 5.0 Review existing tests and fill critical gaps only
  - [ ] 5.1 Review tests from Task Groups 1-3
    - Review the 2-8 tests written for installer core (Task 1.1)
    - Review the 2-8 tests written for environment setup (Task 2.1)
    - Review the 2-8 tests written for launcher functionality (Task 3.1)
    - Total existing tests: approximately 6-24 tests
  - [ ] 5.2 Analyze test coverage gaps for installer feature only
    - Identify critical installation workflows lacking test coverage
    - Focus on integration between task groups
    - Focus on end-to-end installation scenarios
    - Prioritize error handling paths (network failures, permission issues)
    - Do NOT assess entire application test coverage
  - [ ] 5.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new integration tests for critical gaps:
      - Full installation flow end-to-end test (happy path)
      - Installation with missing Python test
      - Installation with insufficient permissions test
      - Update/re-installation flow test
      - Network failure during pip installation test
      - Network failure during npm installation test
      - Invalid requirements file test
      - Launcher script execution test
    - Do NOT write comprehensive coverage for all edge cases
    - Skip performance tests unless business-critical
  - [ ] 5.4 Run installer feature tests only
    - Run ONLY tests related to installer feature (tests from 1.1, 2.1, 3.1, and 5.3)
    - Expected total: approximately 16-34 tests maximum
    - Do NOT run entire application test suite
    - Verify critical installation workflows pass

**Acceptance Criteria:**
- All installer feature tests pass (approximately 16-34 tests total)
- Critical installation workflows are covered
- No more than 10 additional tests added by testing-engineer
- Testing focused exclusively on installer feature requirements
- Error handling paths have adequate coverage

## Execution Order

Recommended implementation sequence:
1. Core Installer Script (Task Group 1) - Platform detection and prerequisite validation
2. Environment Setup & Dependencies (Task Group 2) - Venv creation and package installation
3. Launcher Scripts & Post-Installation (Task Group 3) - Script generation and webapp launch
4. PyInstaller Build Configuration (Task Group 4) - Executable packaging
5. Test Review & Gap Analysis (Task Group 5) - Integration testing and validation

## Notes

- This spec is unusual in that it doesn't require database-engineer or ui-designer roles
- All work is Python scripting, system integration, and build tooling
- The api-engineer role is suitable for this work as it involves orchestration logic and system integration
- Testing should focus on installation scenarios rather than application functionality
- Manual testing on clean VMs or containers for each platform is recommended
- Consider creating a test matrix for platform-specific behaviors
