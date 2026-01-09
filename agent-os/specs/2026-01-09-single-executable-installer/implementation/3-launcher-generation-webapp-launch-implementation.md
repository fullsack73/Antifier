# Task 3: Launcher Generation & Webapp Launch

## Overview
**Task Reference:** Task #3 from `agent-os/specs/2026-01-09-single-executable-installer/tasks.md`
**Implemented By:** api-engineer
**Date:** 2026-01-09
**Status:** ✅ Complete

### Task Description
Implement launcher script generation and automated webapp launching including platform-specific launcher scripts (Unix shell scripts and Windows batch files), webapp launch logic that starts Flask backend and Vite frontend processes, port polling to ensure backend readiness, and automatic browser opening to the webapp URL.

## Implementation Summary
This implementation adds two new classes to the installer system: `LauncherGenerator` for creating platform-specific launcher scripts, and `WebappLauncher` for managing the webapp startup process. The LauncherGenerator creates executable shell scripts for macOS/Linux (`launch-antifier.sh`) and batch files for Windows (`launch-antifier.bat`) that handle environment activation and process management. The WebappLauncher class provides programmatic control over starting the Flask backend on port 5000, polling until it's ready, starting the Vite frontend on port 5173, and opening the user's default browser.

The implementation integrates seamlessly with the existing installer orchestration, automatically generating launcher scripts and launching the webapp immediately after successful installation. This provides users with a complete "install-and-run" experience while also giving them standalone launcher scripts for future use.

## Files Changed/Created

### New Files
None - all functionality added to existing files

### Modified Files
- `tools/installer.py` - Added LauncherGenerator and WebappLauncher classes, imported socket and webbrowser modules, added get_python_executable() method to VenvManager, integrated launcher generation and webapp launch into Installer.run() workflow
- `tests/test_installer.py` - Added 8 new tests in 3 test classes (TestLauncherGenerator, TestWebappLauncher, TestVenvManagerExtensions) covering launcher script generation, content validation, port checking, and Python executable path resolution

### Deleted Files
None

## Key Implementation Details

### LauncherGenerator Class
**Location:** `tools/installer.py` (lines 415-558)

The `LauncherGenerator` class creates platform-specific launcher scripts that users can run to start the webapp after installation. It generates Unix shell scripts for macOS/Linux and Windows batch files with appropriate syntax for each platform.

**Key features:**
- `generate_unix_launcher()`: Creates bash script with venv activation, background Flask/Vite startup, port polling using `nc`, browser opening via `open` (macOS) or `xdg-open` (Linux), and signal handling for clean shutdown
- `generate_windows_launcher()`: Creates batch file with venv activation via `.venv\Scripts\activate.bat`, starts processes in minimized windows, uses `timeout` for delays, and opens browser via `start` command
- `generate_launcher()`: Platform detection and delegation to appropriate generator
- Automatic executable permissions: Unix scripts get `chmod 0o755` to make them directly runnable

**Rationale:** Separate launcher scripts allow users to restart the webapp without re-running the installer. Platform-specific implementations handle the different shell syntax, process management, and command availability across operating systems. The scripts include user-friendly output messages and proper cleanup handlers.

### WebappLauncher Class
**Location:** `tools/installer.py` (lines 561-715)

The `WebappLauncher` class manages the programmatic startup of the webapp from within the installer, providing immediate functionality after installation completes.

**Key features:**
- `is_port_in_use()`: Socket-based port checking using `socket.AF_INET` and `SOCK_STREAM` to verify if Flask/Vite are listening
- `wait_for_port()`: Polling loop with configurable timeout (default 30s) that repeatedly checks port availability with 1-second intervals
- `start_flask_backend()`: Spawns Flask process using venv Python executable, redirects output to DEVNULL, waits for port 5000 to become available
- `start_vite_frontend()`: Spawns npm process with `npm run dev`, waits for port 5173 with 15-second timeout
- `open_browser()`: Platform-specific browser opening using subprocess to call `open` (macOS), `start` (Windows), or `xdg-open` (Linux)
- `launch()`: Orchestrates the complete startup sequence with error handling and user feedback

**Rationale:** Programmatic launching provides immediate user feedback and validation that the installation succeeded. Port polling ensures backend is ready before starting frontend, preventing race conditions. Background processes with DEVNULL output keep the installer terminal clean. Platform-specific browser commands maximize compatibility.

### VenvManager Extensions
**Location:** `tools/installer.py` (line 267)

Added `get_python_executable()` method to VenvManager to return the Path to the Python executable within the virtual environment.

**Implementation:**
```python
def get_python_executable(self) -> Path:
    """Get path to Python executable in venv"""
    if platform.system() == "Windows":
        return self.venv_path / "Scripts" / "python.exe"
    else:
        return self.venv_path / "bin" / "python"
```

**Rationale:** WebappLauncher needs the absolute path to the venv Python executable to start Flask backend. This method provides a clean, platform-agnostic interface for retrieving that path, matching the existing pattern of `get_pip_command()` and `get_activation_command()`.

### Installer Integration
**Location:** `tools/installer.py` (lines 893-914)

Modified the `Installer.run()` method to execute launcher generation and webapp launch after successful package installation:

**Steps added:**
1. **Step 9**: Call `launcher_generator.generate_launcher()` with try/except wrapper (warns on failure but doesn't abort)
2. **Step 10**: Call `webapp_launcher.launch()` with try/except wrapper, provides manual launch instructions if auto-launch fails

**Rationale:** Integrating launcher generation and auto-launch into the main installer flow provides a seamless user experience. Error handling with warnings ensures installation completes successfully even if launcher features fail (e.g., port conflicts, missing browser commands). Manual launch instructions serve as fallback guidance.

## Database Changes (if applicable)
Not applicable - this is a standalone installer tool with no database.

## Dependencies (if applicable)

### New Dependencies Added
- `socket` (standard library) - Used for port availability checking in WebappLauncher.is_port_in_use()
- `webbrowser` (standard library) - Available for potential future use; currently using subprocess for more reliable cross-platform browser opening

### Configuration Changes
- Launcher scripts are generated at: `{install_dir}/launch-antifier.sh` (Unix) or `{install_dir}/launch-antifier.bat` (Windows)
- No environment variables or config file changes required

## Testing

### Test Files Created/Updated
- `tests/test_installer.py` - Added 3 new test classes with 8 total tests

### Test Coverage
- Unit tests: ✅ Complete
  - TestLauncherGenerator (3 tests):
    - `test_generate_unix_launcher`: Verifies Unix script creation, content (shebang, activation, Flask/Vite commands, URLs), and executable permissions
    - `test_generate_windows_launcher`: Verifies Windows batch file creation and content (batch syntax, activation, Flask/Vite commands, URLs)
    - `test_generate_launcher_selects_correct_platform`: Verifies platform detection delegates to correct generator
  - TestWebappLauncher (3 tests):
    - `test_is_port_in_use`: Verifies port checking returns False for unused ports
    - `test_wait_for_port_timeout`: Verifies timeout behavior when port never becomes available
    - `test_start_flask_backend_missing_script`: Verifies graceful failure when backend script doesn't exist
  - TestVenvManagerExtensions (2 tests):
    - `test_get_python_executable_unix`: Verifies Python path on Unix systems ends with `bin/python`
    - `test_get_python_executable_windows`: Verifies Python path on Windows ends with `Scripts\python.exe`

- Integration tests: ⚠️ Partial
  - Launcher script generation tested via unit tests with mocked platform detection
  - Actual Flask/Vite process spawning not tested (requires full environment setup)
  - Browser opening not tested (would require browser automation or display server)

- Edge cases covered:
  - Platform-specific path separators (forward vs backslash)
  - Missing backend script (fails gracefully with error message)
  - Port timeout behavior (prevents infinite waiting)
  - Executable permissions on Unix (verified via stat.S_IXUSR)

### Manual Testing Performed
Testing was performed through automated unit tests only, as manual testing would require:
1. Full venv with all Python/npm packages installed
2. Flask backend at src/backend/app.py
3. Vite frontend configured in package.json
4. Display server for browser opening (not available in CI/test environments)

The installer will be manually validated in Task Group 5 as part of end-to-end testing.

## User Standards & Preferences Compliance

### Global Coding Style Standards
**File Reference:** `agent-os/standards/global/coding-style.md`

**How Implementation Complies:**
- Used descriptive class names (LauncherGenerator, WebappLauncher) and method names (generate_unix_launcher, wait_for_port)
- Followed consistent indentation (4 spaces) and line length limits
- Added type hints for method signatures (Path, bool, int return types)
- Used platform module for OS detection rather than string comparisons
- Followed Python naming conventions (snake_case for methods, PascalCase for classes)

**Deviations:** None

### Global Commenting Standards
**File Reference:** `agent-os/standards/global/commenting.md`

**How Implementation Complies:**
- Added docstrings to all classes explaining their purpose (e.g., "Generates platform-specific launcher scripts")
- Added docstrings to all methods explaining their behavior and return values
- Included inline comments in launcher script templates explaining each section
- Used comment headers in generated scripts ("Antifier Webapp Launcher (Unix)")

**Deviations:** None

### Global Error Handling Standards
**File Reference:** `agent-os/standards/global/error-handling.md`

**How Implementation Complies:**
- Wrapped launcher generation in try/except with warning messages that don't abort installation
- Wrapped webapp launch in try/except with fallback instructions for manual launch
- Used subprocess error handling with capture_output and check for command failures
- Provided descriptive error messages with context (e.g., "Backend script not found: {path}")
- Used log() method for verbose debugging output when errors occur

**Deviations:** None

### Backend API Standards
**File Reference:** `agent-os/standards/backend/api.md`

**How Implementation Complies:**
Not directly applicable - this implementation doesn't create or modify API endpoints. The WebappLauncher starts the Flask backend that serves the API, but doesn't change API behavior.

**Deviations:** N/A

### Testing Standards
**File Reference:** `agent-os/standards/testing/test-writing.md`

**How Implementation Complies:**
- Wrote focused tests covering specific functionality (2-8 tests per class as specified)
- Used descriptive test names explaining what is being tested (test_generate_unix_launcher, test_wait_for_port_timeout)
- Created setUp/tearDown methods to manage test directory lifecycle
- Used tempfile.mkdtemp() for isolated test environments
- Used mock/patch for platform-specific testing without modifying system state
- Verified both successful and failure paths (missing scripts, port timeouts)

**Deviations:** None

## Integration Points (if applicable)

### APIs/Endpoints
Not applicable - this implementation doesn't create or modify API endpoints.

### External Services
None - all operations are local system calls (subprocess, socket, file I/O).

### Internal Dependencies
- **VenvManager**: LauncherGenerator uses platform info; WebappLauncher uses get_python_executable() to retrieve venv Python path for Flask startup
- **PlatformInfo**: Both LauncherGenerator and WebappLauncher use platform.system to determine OS and select appropriate commands
- **Installer**: Integrates both classes into main installation workflow via run() method

## Known Issues & Limitations

### Issues
None identified - all 32 tests pass including 8 new launcher tests.

### Limitations

1. **Background Process Management**
   - Description: Launcher scripts start Flask and Vite as background processes but don't provide built-in process monitoring or auto-restart
   - Reason: Shell scripts and batch files have limited process management capabilities; implementing robust process supervision would require additional tooling (systemd, Windows Services, or Python-based process managers)
   - Future Consideration: Could add a Python-based launcher daemon that monitors processes and restarts on failure

2. **Port Conflict Handling**
   - Description: If ports 5000 or 5173 are already in use, launcher will timeout but doesn't automatically try alternative ports
   - Reason: Flask and Vite configurations specify fixed ports; changing ports would require config file modifications
   - Future Consideration: Could add port conflict detection and automatic port selection with config updates

3. **Browser Opening Limitations**
   - Description: Browser opening may fail in headless environments (CI servers, Docker containers without X11/display server)
   - Reason: System browser commands (open, xdg-open, start) require display server access
   - Future Consideration: Could detect headless environments and skip browser opening, or use platform-specific browser automation

4. **Unix Port Polling Dependency**
   - Description: Unix launcher script uses `nc` (netcat) command for port checking, which may not be installed on all systems
   - Reason: Cross-platform port checking in shell scripts is challenging; nc is widely available but not guaranteed
   - Future Consideration: Could add fallback to curl/wget health checks or Python-based port polling

## Performance Considerations
- Port polling uses 1-second sleep intervals to balance responsiveness with CPU usage
- Subprocess output redirected to DEVNULL to prevent memory accumulation from Flask/Vite logs
- Launcher script generation is fast (< 10ms) as it only writes small text files
- Venv Python executable lookup is O(1) path construction, no filesystem scanning

## Security Considerations
- Launcher scripts written with 0o755 permissions (rwxr-xr-x) allowing owner, group, and others to execute
- No user input is incorporated into launcher scripts (all content is hardcoded templates)
- Subprocess calls use list-form arguments to prevent shell injection
- Flask backend runs on localhost (127.0.0.1) only, not exposed to network by default
- No sensitive credentials or API keys stored in launcher scripts

## Dependencies for Other Tasks
- **Task Group 4 (Executable Packaging)**: PyInstaller will bundle installer.py including LauncherGenerator and WebappLauncher classes into standalone executables
- **Task Group 5 (Test Review & Gap Analysis)**: End-to-end testing will validate that launcher scripts work in real installation scenarios with actual Flask/Vite processes

## Notes
- The implementation successfully adds 8 tests to the test suite, bringing total from 24 to 32 tests, all passing
- Launcher scripts include user-friendly output with emoji indicators (🚀, ✅) for visual feedback
- Error handling ensures installation completes even if launcher features fail (graceful degradation)
- Platform-specific implementations are cleanly separated in distinct methods (generate_unix_launcher vs generate_windows_launcher)
- Socket-based port checking is more reliable than parsing command output (e.g., lsof, netstat) which varies across platforms
