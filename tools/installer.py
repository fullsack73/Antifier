import sys
import os
import platform
import subprocess
import shutil
import json
import argparse
import time
import socket
import webbrowser
from pathlib import Path
from typing import Dict, Optional, Tuple, List



def get_bundled_resource_path(relative_path: str) -> Path:
    """Get path to bundled resource file (for PyInstaller executables)
    
    When running from PyInstaller executable, files are extracted to sys._MEIPASS temp directory.
    Otherwise, use the normal path relative to the script.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running from source
        base_path = Path(__file__).parent.parent
    
    return base_path / relative_path


def get_npm_command() -> List[str]:
    """Get platform-specific npm command"""
    if platform.system() == "Windows":
        return ["npm.cmd"]
    return ["npm"]


class InstallerError(Exception):
    """Custom exception for installer errors"""
    pass


class PlatformInfo:
    """Encapsulates platform detection and configuration"""
    
    def __init__(self):
        self.system = platform.system()
        self.machine = platform.machine()
        self.python_version = platform.python_version()
        self.distribution = self._detect_linux_distribution()
    
    def _detect_linux_distribution(self) -> Optional[str]:
        """Detect Linux distribution for platform-specific package management"""
        if self.system != "Linux":
            return None
        
        try:
            # Try to read /etc/os-release
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    content = f.read()
                    if 'ubuntu' in content.lower() or 'debian' in content.lower():
                        return 'debian'
                    elif 'fedora' in content.lower() or 'rhel' in content.lower() or 'centos' in content.lower():
                        return 'redhat'
            
            # Fallback: check for package managers
            if shutil.which('apt'):
                return 'debian'
            elif shutil.which('yum') or shutil.which('dnf'):
                return 'redhat'
        except Exception:
            pass
        
        return 'unknown'
    
    def get_platform_name(self) -> str:
        """Return human-readable platform name"""
        if self.system == "Darwin":
            return "macOS"
        elif self.system == "Windows":
            return "Windows"
        elif self.system == "Linux":
            return f"Linux ({self.distribution})"
        return self.system
    
    def is_supported(self) -> bool:
        """Check if platform is supported"""
        return self.system in ["Darwin", "Windows", "Linux"]


class SystemValidator:
    """Validates system prerequisites and requirements"""
    
    def __init__(self, install_dir: Path):
        self.install_dir = install_dir
    
    def check_nodejs(self) -> Tuple[bool, Optional[str]]:
        """Check if Node.js is installed and return version"""
        try:
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return True, version
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return False, None
    
    def check_vite(self) -> bool:
        """Check if Vite is globally installed"""
        try:
            result = subprocess.run(
                get_npm_command() + ['list', '-g', 'vite'],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Vite is installed if it appears in the output
            return 'vite@' in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def install_vite(self) -> bool:
        """Install Vite globally"""
        print("📦 Installing Vite globally...")
        try:
            result = subprocess.run(
                get_npm_command() + ['install', '-g', 'vite'],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def check_python(self) -> Tuple[bool, Optional[str]]:
        """Check if Python 3.8+ is installed and return version"""
        for cmd in ['python3', 'python']:
            try:
                result = subprocess.run(
                    [cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version_str = result.stdout.strip()
                    # Extract version number (e.g., "Python 3.9.7" -> "3.9.7")
                    version = version_str.split()[1] if len(version_str.split()) > 1 else "0.0.0"
                    major, minor = map(int, version.split('.')[:2])
                    
                    if major == 3 and minor >= 8:
                        return True, version
            except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
                continue
        
        return False, None
    
    def check_disk_space(self, required_gb: float = 2.0) -> Tuple[bool, float]:
        """Check if sufficient disk space is available"""
        try:
            stat = shutil.disk_usage(self.install_dir)
            available_gb = stat.free / (1024 ** 3)
            return available_gb >= required_gb, available_gb
        except Exception:
            return False, 0.0
    
    def check_write_permissions(self) -> bool:
        """Check if we have write permissions in the installation directory"""
        test_file = self.install_dir / '.installer_permission_test'
        try:
            test_file.touch()
            test_file.unlink()
            return True
        except (PermissionError, OSError):
            return False
    
    def check_cpp_compiler(self) -> bool:
        """Check if C++ compiler is installed (Windows only)"""
        if platform.system() != "Windows":
            return True
            
        # method 1: check for cl.exe (Visual C++ compiler)
        if shutil.which('cl'):
            return True
            
        # method 2: check using vswhere
        try:
            program_files = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            vswhere = Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            
            if vswhere.exists():
                result = subprocess.run(
                    [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and result.stdout.strip():
                    return True
        except Exception:
            pass
            
        return False

    def install_cpp_compiler(self) -> bool:
        """Install Visual Studio Build Tools via winget"""
        print("📦 Installing Visual Studio Build Tools...")
        print("   This will open a UAC prompt. Please accept it.")
        
        try:
            # Check if winget is available
            if not shutil.which('winget'):
                print("❌ Error: winget not found. Please install Visual Studio Build Tools manually.")
                print("   Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/")
                return False
                
            # Install VS Build Tools with C++ workload
            # Microsoft.VisualStudio.2022.BuildTools is the ID
            cmd = [
                'winget', 'install',
                '--id', 'Microsoft.VisualStudio.2022.BuildTools',
                '--silent', 
                '--override', '--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
            ]
            
            print(f"   Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, shell=True)
            
            if result.returncode == 0:
                print("✅ Visual Studio Build Tools installed successfully")
                return True
            else:
                print(f"❌ Error: Installation failed with code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"❌ Error during installation: {e}")
            return False


class ConfigManager:
    """Manages installation configuration and metadata"""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
    
    def create_config(self, data: Dict) -> bool:
        """Create or update configuration file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"⚠️  Warning: Could not write config file: {e}")
            return False
    
    def read_config(self) -> Optional[Dict]:
        """Read existing configuration file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def update_config(self, updates: Dict) -> bool:
        """Update existing configuration with new values"""
        try:
            existing = self.read_config() or {}
            existing.update(updates)
            return self.create_config(existing)
        except Exception as e:
            print(f"⚠️  Warning: Could not update config file: {e}")
            return False


class VenvManager:
    """Manages Python virtual environment creation and activation"""
    
    def __init__(self, install_dir: Path, verbose: bool = False):
        self.install_dir = install_dir
        self.venv_path = install_dir / ".venv"
        self.verbose = verbose
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
    
    def create_venv(self) -> bool:
        """Create Python virtual environment"""
        print("\n📦 Creating Python virtual environment...")
        
        if self.venv_path.exists():
            print(f"  ⚠️  Virtual environment already exists at {self.venv_path}")
            return True
        
        try:
            # Use the current Python interpreter to create the venv
            python_cmd = sys.executable
            
            # If running as compiled executable (PyInstaller), we can't use sys.executable
            if getattr(sys, 'frozen', False):
                self.log("Running as frozen executable, searching for system Python...")
                found = False
                # Try python first on Windows as it's the standard command
                candidates = ['python', 'python3'] if platform.system() == "Windows" else ['python3', 'python']
                
                for cmd in candidates:
                    if shutil.which(cmd):
                        python_cmd = cmd
                        found = True
                        break
                
                if not found:
                    print("  ❌ Error: Could not find system Python to create virtual environment")
                    print("  Please ensure Python is installed and in your PATH")
                    return False

            self.log(f"Creating venv with: {python_cmd} -m venv {self.venv_path}")
            
            result = subprocess.run(
                [python_cmd, '-m', 'venv', str(self.venv_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"  ❌ Error creating venv: {result.stderr}")
                return False
            
            # Verify venv was created
            if not self.venv_path.exists():
                print("  ❌ Error: Virtual environment directory not created")
                return False
            
            print(f"  ✅ Virtual environment created at {self.venv_path}")
            return True
            
        except subprocess.TimeoutExpired:
            print("  ❌ Error: Venv creation timed out")
            return False
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False
    
    def get_activation_command(self) -> List[str]:
        """Get platform-specific venv activation command"""
        if platform.system() == "Windows":
            return [str(self.venv_path / "Scripts" / "python.exe")]
        else:
            return [str(self.venv_path / "bin" / "python")]
    
    def get_python_executable(self) -> Path:
        """Get path to Python executable in venv"""
        if platform.system() == "Windows":
            return self.venv_path / "Scripts" / "python.exe"
        else:
            return self.venv_path / "bin" / "python"
    
    def get_pip_command(self) -> List[str]:
        """Get platform-specific pip command within venv"""
        if platform.system() == "Windows":
            return [str(self.venv_path / "Scripts" / "pip.exe")]
        else:
            return [str(self.venv_path / "bin" / "pip")]


class PackageInstaller:
    """Manages package installation for Python and npm"""
    
    def __init__(self, install_dir: Path, venv_manager: VenvManager, verbose: bool = False):
        self.install_dir = install_dir
        self.venv_manager = venv_manager
        self.verbose = verbose
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
    
    def install_python_packages(self, requirements_file: Path, max_retries: int = 3) -> bool:
        """Install Python packages from requirements file with retry logic"""
        print(f"\n📦 Installing Python packages from {requirements_file.name}...")
        print("  ℹ️  This may take 15-30 minutes (TensorFlow, PyTorch are large packages)")
        print("  Please be patient - the installer is working...")
        
        if not requirements_file.exists():
            print(f"  ❌ Error: Requirements file not found: {requirements_file}")
            return False
        
        pip_cmd = self.venv_manager.get_pip_command()
        
        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"Attempt {attempt}/{max_retries}: Running pip install")
                
                # Use Popen to show real-time output instead of capture_output
                process = subprocess.Popen(
                    pip_cmd + ['install', '-r', str(requirements_file), '--progress-bar', 'on'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.install_dir),
                    bufsize=1
                )
                
                # Print output in real-time
                for line in process.stdout:
                    print(f"  {line.rstrip()}")
                
                return_code = process.wait(timeout=1800)  # 30 minutes timeout
                
                if return_code == 0:
                    print(f"  ✅ Python packages installed successfully")
                    return True
                else:
                    print(f"  ⚠️  Attempt {attempt} failed with return code {return_code}")
                    
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"  Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  Attempt {attempt} timed out")
                if attempt < max_retries:
                    print(f"  Retrying...")
            except Exception as e:
                print(f"  ⚠️  Attempt {attempt} error: {e}")
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    print(f"  Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        print(f"  ❌ Error: Failed to install Python packages after {max_retries} attempts")
        return False
    
    def install_npm_packages(self, max_retries: int = 3) -> bool:
        """Install npm packages with retry logic"""
        print(f"\n📦 Installing npm packages...")
        
        package_json = self.install_dir / "package.json"
        if not package_json.exists():
            print(f"  ❌ Error: package.json not found in {self.install_dir}")
            return False
        
        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"Attempt {attempt}/{max_retries}: Running npm install")
                
                result = subprocess.run(
                    get_npm_command() + ['install'],
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes timeout
                    cwd=str(self.install_dir)
                )
                
                if result.returncode == 0:
                    print(f"  ✅ npm packages installed successfully")
                    return True
                else:
                    print(f"  ⚠️  Attempt {attempt} failed: {result.stderr[:200]}")
                    
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"  Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  Attempt {attempt} timed out")
                if attempt < max_retries:
                    print(f"  Retrying...")
            except Exception as e:
                print(f"  ⚠️  Attempt {attempt} error: {e}")
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    print(f"  Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        print(f"  ❌ Error: Failed to install npm packages after {max_retries} attempts")
        return False
    
    def get_installed_python_packages(self) -> Dict[str, str]:
        """Get list of installed Python packages with versions"""
        try:
            pip_cmd = self.venv_manager.get_pip_command()
            result = subprocess.run(
                pip_cmd + ['list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return {pkg['name']: pkg['version'] for pkg in packages}
        except Exception as e:
            self.log(f"Error getting installed packages: {e}")
        
        return {}
    
    def get_installed_npm_packages(self) -> Dict[str, str]:
        """Get list of installed npm packages with versions"""
        try:
            package_lock = self.install_dir / "package-lock.json"
            if package_lock.exists():
                with open(package_lock, 'r') as f:
                    lock_data = json.load(f)
                    packages = lock_data.get('packages', {})
                    
                    # Extract top-level dependencies
                    result = {}
                    for pkg_path, pkg_info in packages.items():
                        if pkg_path.startswith('node_modules/'):
                            pkg_name = pkg_path.replace('node_modules/', '')
                            if '/' not in pkg_name or pkg_name.startswith('@'):
                                result[pkg_name] = pkg_info.get('version', 'unknown')
                    
                    return result
        except Exception as e:
            self.log(f"Error getting installed npm packages: {e}")
        
        return {}


class LauncherGenerator:
    """Generates platform-specific launcher scripts"""
    
    def __init__(self, install_dir: Path, platform_info: PlatformInfo, verbose: bool = False):
        self.install_dir = install_dir
        self.platform = platform_info
        self.verbose = verbose
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
    
    def generate_unix_launcher(self) -> Path:
        """Generate launcher script for macOS/Linux"""
        script_path = self.install_dir / "launch-antifier.sh"
        
        script_content = """#!/bin/bash

# Antifier Webapp Launcher (Unix)
# Auto-generated by installer

echo "🚀 Starting Antifier webapp..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment
echo "  Activating Python environment..."
source .venv/bin/activate

# Start Flask backend in background
echo "  Starting Flask backend..."
python src/backend/app.py > /dev/null 2>&1 &
FLASK_PID=$!

# Wait for Flask to be ready (check port 5000)
echo "  Waiting for backend to initialize..."
for i in {1..30}; do
    if nc -z localhost 5000 2>/dev/null; then
        echo "  ✅ Backend ready on port 5000"
        break
    fi
    sleep 1
done

# Start Vite frontend in background
echo "  Starting Vite frontend..."
npm run dev > /dev/null 2>&1 &
VITE_PID=$!

# Wait a moment for Vite to start
sleep 3

# Open browser
echo "  Opening browser..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:5173
else
    xdg-open http://localhost:5173
fi

echo ""
echo "✅ Antifier is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the servers"

# Wait for user interrupt
trap "kill $FLASK_PID $VITE_PID 2>/dev/null; exit" INT
wait
"""
        
        self.log(f"Writing Unix launcher script to {script_path}")
        script_path.write_text(script_content)
        
        # Make executable
        os.chmod(script_path, 0o755)
        self.log(f"Set executable permissions on {script_path}")
        
        return script_path
    
    def generate_windows_launcher(self) -> Path:
        """Generate launcher script for Windows"""
        script_path = self.install_dir / "launch-antifier.bat"
        
        script_content = """@echo off
REM Antifier Webapp Launcher (Windows)
REM Auto-generated by installer

echo Starting Antifier webapp...

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Activate virtual environment
echo   Activating Python environment...
call .venv\\Scripts\\activate.bat

REM Start Flask backend in new window
echo   Starting Flask backend...
start "Antifier Backend" /MIN cmd /c "python src\\backend\\app.py"

REM Wait for Flask to be ready
echo   Waiting for backend to initialize...
timeout /t 5 /nobreak >nul

REM Start Vite frontend in new window
echo   Starting Vite frontend...
start "Antifier Frontend" /MIN cmd /c "npm run dev"

REM Wait for Vite to start
timeout /t 3 /nobreak >nul

REM Open browser
echo   Opening browser...
start http://localhost:5173

echo.
echo Antifier is running!
echo   Frontend: http://localhost:5173
echo   Backend: http://localhost:5000
echo.
echo Close the terminal windows to stop the servers
pause
"""
        
        self.log(f"Writing Windows launcher script to {script_path}")
        script_path.write_text(script_content)
        
        return script_path
    
    def generate_launcher(self) -> Path:
        """Generate launcher script for current platform"""
        print("\n📝 Generating launcher script...")
        
        if self.platform.system == "Windows":
            script_path = self.generate_windows_launcher()
            print(f"  ✅ Created launch-antifier.bat")
        else:
            script_path = self.generate_unix_launcher()
            print(f"  ✅ Created launch-antifier.sh")
        
        return script_path


class WebappLauncher:
    """Launches the Flask backend and Vite frontend"""
    
    def __init__(self, install_dir: Path, platform_info: PlatformInfo, 
                 venv_manager: 'VenvManager', verbose: bool = False):
        self.install_dir = install_dir
        self.platform = platform_info
        self.venv_manager = venv_manager
        self.verbose = verbose
        self.flask_process = None
        self.vite_process = None
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
    
    def is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return False
            except OSError:
                return True
    
    def wait_for_port(self, port: int, timeout: int = 30) -> bool:
        """Wait for a port to be in use (service started)"""
        self.log(f"Waiting for port {port} to be ready...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_port_in_use(port):
                self.log(f"Port {port} is ready")
                return True
            time.sleep(1)
        
        self.log(f"Timeout waiting for port {port}")
        return False
    
    def start_flask_backend(self) -> bool:
        """Start Flask backend process"""
        print("  Starting Flask backend...")
        
        backend_script = self.install_dir / "src" / "backend" / "app.py"
        if not backend_script.exists():
            print(f"  ❌ Error: Backend script not found: {backend_script}")
            return False
        
        try:
            # Get Python executable from venv
            python_exe = self.venv_manager.get_python_executable()
            
            # Start Flask in background
            self.flask_process = subprocess.Popen(
                [str(python_exe), str(backend_script)],
                cwd=str(self.install_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.log(f"Flask process started with PID: {self.flask_process.pid}")
            
            # Wait for Flask to be ready
            if self.wait_for_port(5000, timeout=30):
                print("  ✅ Backend ready on port 5000")
                return True
            else:
                print("  ❌ Error: Backend failed to start on port 5000")
                return False
                
        except Exception as e:
            print(f"  ❌ Error starting Flask backend: {e}")
            return False
    
    def start_vite_frontend(self) -> bool:
        """Start Vite frontend process"""
        print("  Starting Vite frontend...")
        
        try:
            # Start Vite in background
            self.vite_process = subprocess.Popen(
                get_npm_command() + ['run', 'dev'],
                cwd=str(self.install_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.log(f"Vite process started with PID: {self.vite_process.pid}")
            
            # Wait for Vite to be ready
            time.sleep(3)  # Give Vite time to start
            
            if self.wait_for_port(5173, timeout=15):
                print("  ✅ Frontend ready on port 5173")
                return True
            else:
                print("  ⚠️  Frontend may still be starting (port 5173)")
                return True  # Continue anyway as Vite takes time
                
        except Exception as e:
            print(f"  ❌ Error starting Vite frontend: {e}")
            return False
    
    def open_browser(self):
        """Open default browser to webapp URL"""
        print("  Opening browser...")
        
        url = "http://localhost:5173"
        
        try:
            if self.platform.system == "Darwin":
                # macOS
                subprocess.run(['open', url], check=True)
            elif self.platform.system == "Windows":
                # Windows
                subprocess.run(['start', url], shell=True, check=True)
            else:
                # Linux
                subprocess.run(['xdg-open', url], check=True)
            
            self.log(f"Browser opened to {url}")
            
        except Exception as e:
            print(f"  ⚠️  Could not open browser automatically: {e}")
            print(f"  Please open {url} manually in your browser")
    
    def launch(self) -> bool:
        """Launch the complete webapp (backend + frontend + browser)"""
        print("\n🚀 Launching Antifier webapp...")
        
        # Start Flask backend
        if not self.start_flask_backend():
            return False
        
        # Start Vite frontend
        if not self.start_vite_frontend():
            return False
        
        # Open browser
        self.open_browser()
        
        print("\n✅ Antifier is running!")
        print(f"   Frontend: http://localhost:5173")
        print(f"   Backend: http://localhost:5000")
        print("\n   Use the generated launcher script for future runs:")
        
        if self.platform.system == "Windows":
            print(f"   .\\launch-antifier.bat")
        else:
            print(f"   ./launch-antifier.sh")
        
        return True


class Installer:
    """Main installer orchestration class"""
    
    def __init__(self, install_dir: Optional[Path] = None, verbose: bool = False):
        self.install_dir = install_dir or Path.cwd()
        self.verbose = verbose
        self.platform = PlatformInfo()
        self.validator = SystemValidator(self.install_dir)
        self.config_manager = ConfigManager(self.install_dir / 'config.json')
        self.venv_manager = VenvManager(self.install_dir, verbose)
        self.package_installer = PackageInstaller(self.install_dir, self.venv_manager, verbose)
        self.launcher_generator = LauncherGenerator(self.install_dir, self.platform, verbose)
        self.webapp_launcher = WebappLauncher(self.install_dir, self.platform, self.venv_manager, verbose)
    
    def print_banner(self):
        """Display installer banner"""
        print("=" * 60)
        print("  Antifier Webapp Installer")
        print("  Automated setup for complete webapp environment")
        print("=" * 60)
        print()
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[DEBUG] {message}")
    
    def validate_platform(self) -> bool:
        """Validate that platform is supported"""
        print(f"🔍 Detecting platform: {self.platform.get_platform_name()}")
        
        if not self.platform.is_supported():
            print(f"❌ Error: Unsupported platform '{self.platform.system}'")
            print("   Supported platforms: macOS, Windows, Linux")
            return False
        
        print(f"✅ Platform supported")
        return True
    
    def validate_prerequisites(self) -> bool:
        """Validate all system prerequisites"""
        print("\n🔍 Validating system prerequisites...")
        
        # Check Node.js
        print("  Checking Node.js installation...")
        nodejs_installed, nodejs_version = self.validator.check_nodejs()
        if not nodejs_installed:
            print("❌ Error: Node.js is not installed")
            print("   Please install Node.js from https://nodejs.org/")
            print("   Node.js is required to run the webapp frontend")
            return False
        print(f"  ✅ Node.js {nodejs_version} detected")
        
        # Note: Vite will be installed locally via npm install (no global installation needed)
        
        # Check Python
        print("  Checking Python installation...")
        python_installed, python_version = self.validator.check_python()
        if not python_installed:
            print("❌ Error: Python 3.8+ is not installed")
            self._print_python_install_instructions()
            return False
        print(f"  ✅ Python {python_version} detected")
        
        # Check disk space
        print("  Checking disk space...")
        has_space, available_gb = self.validator.check_disk_space()
        if not has_space:
            print(f"❌ Error: Insufficient disk space (available: {available_gb:.2f} GB, required: 2.0 GB)")
            return False
        print(f"  ✅ Sufficient disk space ({available_gb:.2f} GB available)")
        
        # Check write permissions
        print("  Checking write permissions...")
        has_permissions = self.validator.check_write_permissions()
        if not has_permissions:
            print(f"❌ Error: No write permissions in {self.install_dir}")
            print("   Please run the installer with appropriate permissions")
            return False
        print("  ✅ Write permissions verified")
        
        print("✅ All prerequisites validated")

        # Check C++ Compiler (Windows only)
        if self.platform.system == "Windows":
            print("  Checking C++ compiler...")
            if not self.validator.check_cpp_compiler():
                print("⚠️  Warning: C++ compiler not found")
                print("   Some Python packages (like pmdarima) require a C++ compiler to install.")
                
                print("\n❓ Do you want to install Visual Studio Build Tools? (y/n): ", end='')
                if input().strip().lower() in ['y', 'yes']:
                    if not self.validator.install_cpp_compiler():
                        print("⚠️  Compiler installation failed. You may need to install it manually.")
                        print("   https://visualstudio.microsoft.com/visual-cpp-build-tools/")
                else:
                    print("⚠️  Skipping compiler installation. Installation may fail.")
            else:
                print("  ✅ C++ compiler detected")
            
        return True
    
    def _print_python_install_instructions(self):
        """Print platform-specific Python installation instructions"""
        if self.platform.system == "Darwin":
            print("\n   For macOS:")
            print("   - Install via Homebrew: brew install python")
            print("   - Or download from: https://www.python.org/downloads/")
        elif self.platform.system == "Windows":
            print("\n   For Windows:")
            print("   - Download from: https://www.python.org/downloads/")
            print("   - Make sure to check 'Add Python to PATH' during installation")
        elif self.platform.system == "Linux":
            print("\n   For Linux:")
            if self.platform.distribution == "debian":
                print("   - Run: sudo apt update && sudo apt install python3 python3-pip python3-venv")
            elif self.platform.distribution == "redhat":
                print("   - Run: sudo dnf install python3 python3-pip")
            else:
                print("   - Use your distribution's package manager to install Python 3.8+")
    
    def create_metadata(self, nodejs_version: str, python_version: str, 
                       python_packages: Optional[Dict] = None, 
                       npm_packages: Optional[Dict] = None) -> Dict:
        """Create installation metadata"""
        from datetime import datetime
        
        metadata = {
            "installation_date": datetime.now().isoformat(),
            "platform": self.platform.get_platform_name(),
            "nodejs_version": nodejs_version,
            "python_version": python_version,
            "venv_location": str(self.install_dir / ".venv"),
            "last_update": datetime.now().isoformat()
        }
        
        if python_packages:
            metadata["python_packages"] = python_packages
        
        if npm_packages:
            metadata["npm_packages"] = npm_packages
        
        return metadata
    
    def extract_application_files(self) -> bool:
        """Extract bundled application files to installation directory"""
        print("\n📦 Extracting application files...")
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running from PyInstaller bundle - extract files
            bundle_dir = Path(sys._MEIPASS)
            
            # List of files/directories to extract
            items_to_extract = [
                'src',
                'public', 
                'package.json',
                'package-lock.json',
                'vite.config.js',
                'index.html',
                'eslint.config.js'
            ]

            # Find all CSV files in bundle
            csv_files = list(bundle_dir.glob('*.csv'))
            for csv_file in csv_files:
                 items_to_extract.append(csv_file.name)
            
            for item_name in items_to_extract:
                source = bundle_dir / item_name
                dest = self.install_dir / item_name
                
                if not source.exists():
                    self.log(f"Skipping {item_name} (not found in bundle)")
                    continue
                
                try:
                    if source.is_dir():
                        self.log(f"Copying directory: {item_name}")
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(source, dest)
                    else:
                        self.log(f"Copying file: {item_name}")
                        shutil.copy2(source, dest)
                    
                    print(f"  ✅ Extracted {item_name}")
                except Exception as e:
                    print(f"  ⚠️  Warning: Could not extract {item_name}: {e}")
            
            print("  ✅ Application files extracted")
            return True
        else:
            # Running from source - files already in place
            print("  ℹ️  Running from source, files already in place")
            return True
    
    def check_for_updates(self) -> bool:
        """Check if this is an update installation"""
        existing_config = self.config_manager.read_config()
        
        if not existing_config:
            return False
        
        print("\n🔍 Existing installation detected")
        print(f"  Installed on: {existing_config.get('installation_date', 'Unknown')}")
        print(f"  Last update: {existing_config.get('last_update', 'Unknown')}")
        print(f"  Python version: {existing_config.get('python_version', 'Unknown')}")
        print(f"  Node.js version: {existing_config.get('nodejs_version', 'Unknown')}")
        
        # Ask user if they want to update
        print("\n❓ Do you want to update the installation? (y/n): ", end='')
        response = input().strip().lower()
        
        return response in ['y', 'yes']
    
    def run(self) -> bool:
        """Execute complete installation process"""
        self.print_banner()
        
        # Step 1: Validate platform
        if not self.validate_platform():
            return False
        
        # Step 2: Validate prerequisites
        if not self.validate_prerequisites():
            return False
        
        # Step 3: Check for updates
        self.check_for_updates()
        
        # Step 4: Extract application files (if running from bundled executable)
        if not self.extract_application_files():
            print("\n⚠️  Warning: Could not extract all application files")
        
        # Step 5: Create virtual environment
        if not self.venv_manager.create_venv():
            return False
        
        # Step 6: Install Python packages
        requirements_file = get_bundled_resource_path("requirements-pypi.txt")
        if not requirements_file.exists():
            # Fallback: try install_dir location
            requirements_file = self.install_dir / "requirements-pypi.txt"
        
        if not self.package_installer.install_python_packages(requirements_file):
            print("\n⚠️  Warning: Python package installation failed")
            print("   You may need to install packages manually")
        
        # Step 7: Install npm packages
        if not self.package_installer.install_npm_packages():
            print("\n⚠️  Warning: npm package installation failed")
            print("   You may need to install packages manually")
        
        # Step 8: Get installed package versions
        print("\n📊 Collecting package information...")
        python_packages = self.package_installer.get_installed_python_packages()
        npm_packages = self.package_installer.get_installed_npm_packages()
        
        print(f"  ✅ Tracked {len(python_packages)} Python packages")
        print(f"  ✅ Tracked {len(npm_packages)} npm packages")
        
        # Step 9: Create/update configuration metadata
        print("\n📝 Updating installation metadata...")
        _, nodejs_version = self.validator.check_nodejs()
        _, python_version = self.validator.check_python()
        
        metadata = self.create_metadata(
            nodejs_version or "unknown",
            python_version or "unknown",
            python_packages,
            npm_packages
        )
        
        if self.config_manager.create_config(metadata):
            print("✅ Configuration file updated")
        
        # Step 10: Generate launcher script
        try:
            self.launcher_generator.generate_launcher()
        except Exception as e:
            print(f"⚠️  Warning: Could not generate launcher script: {e}")
        
        # Step 11: Launch webapp
        print("\n✅ Environment setup completed successfully!")
        print("\nLaunching webapp for the first time...")
        
        try:
            self.webapp_launcher.launch()
        except Exception as e:
            print(f"\n⚠️  Warning: Could not auto-launch webapp: {e}")
            print("\nYou can manually launch the webapp using:")
            if self.platform.system == "Windows":
                print("  .\\launch-antifier.bat")
            else:
                print("  ./launch-antifier.sh")
        
        return True


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description="Antifier Webapp Installer - Automated setup tool"
    )
    parser.add_argument(
        '--install-dir',
        type=Path,
        help='Installation directory (default: current directory)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    try:
        installer = Installer(
            install_dir=args.install_dir,
            verbose=args.verbose
        )
        
        success = installer.run()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
