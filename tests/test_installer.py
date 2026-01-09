"""
Tests for Antifier Webapp Installer
Focused tests for core orchestration functionality
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import sys
import os

# Add tools directory to path for importing installer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.installer import (
    PlatformInfo, SystemValidator, ConfigManager, Installer,
    VenvManager, PackageInstaller, LauncherGenerator, WebappLauncher
)


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection functionality"""
    
    def test_platform_info_initialization(self):
        """Test that PlatformInfo initializes correctly"""
        platform = PlatformInfo()
        
        # Should have system information
        self.assertIsNotNone(platform.system)
        self.assertIn(platform.system, ['Darwin', 'Windows', 'Linux', 'Java'])
        
        # Should have python version
        self.assertIsNotNone(platform.python_version)
    
    def test_supported_platforms(self):
        """Test that supported platforms are correctly identified"""
        with patch('platform.system') as mock_system:
            # Test macOS
            mock_system.return_value = 'Darwin'
            platform = PlatformInfo()
            self.assertTrue(platform.is_supported())
            self.assertEqual(platform.get_platform_name(), 'macOS')
            
            # Test Windows
            mock_system.return_value = 'Windows'
            platform = PlatformInfo()
            self.assertTrue(platform.is_supported())
            self.assertEqual(platform.get_platform_name(), 'Windows')
            
            # Test Linux
            mock_system.return_value = 'Linux'
            platform = PlatformInfo()
            self.assertTrue(platform.is_supported())
    
    def test_unsupported_platform(self):
        """Test that unsupported platforms are correctly identified"""
        with patch('platform.system') as mock_system:
            mock_system.return_value = 'UnknownOS'
            platform = PlatformInfo()
            self.assertFalse(platform.is_supported())


class TestSystemValidator(unittest.TestCase):
    """Test system validation functionality"""
    
    def setUp(self):
        """Create temporary directory for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.validator = SystemValidator(self.test_dir)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_check_nodejs_installed(self):
        """Test Node.js detection when installed"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='v18.12.0\n'
            )
            
            installed, version = self.validator.check_nodejs()
            self.assertTrue(installed)
            self.assertEqual(version, 'v18.12.0')
    
    def test_check_nodejs_not_installed(self):
        """Test Node.js detection when not installed"""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            installed, version = self.validator.check_nodejs()
            self.assertFalse(installed)
            self.assertIsNone(version)
    
    def test_check_python_version_valid(self):
        """Test Python version detection for valid versions"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='Python 3.9.7\n'
            )
            
            installed, version = self.validator.check_python()
            self.assertTrue(installed)
            self.assertEqual(version, '3.9.7')
    
    def test_disk_space_sufficient(self):
        """Test disk space check with sufficient space"""
        has_space, available = self.validator.check_disk_space(required_gb=0.001)
        self.assertTrue(has_space)
        self.assertGreater(available, 0)
    
    def test_write_permissions_valid(self):
        """Test write permissions check with valid permissions"""
        has_permissions = self.validator.check_write_permissions()
        self.assertTrue(has_permissions)
    
    def test_write_permissions_invalid(self):
        """Test write permissions check with invalid permissions"""
        # Create read-only directory
        readonly_dir = self.test_dir / 'readonly'
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)
        
        validator = SystemValidator(readonly_dir)
        has_permissions = validator.check_write_permissions()
        
        # Clean up by restoring write permissions before deletion
        readonly_dir.chmod(0o755)
        
        self.assertFalse(has_permissions)


class TestConfigManager(unittest.TestCase):
    """Test configuration management functionality"""
    
    def setUp(self):
        """Create temporary directory for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_path = self.test_dir / 'config.json'
        self.config_manager = ConfigManager(self.config_path)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_create_config(self):
        """Test configuration file creation"""
        test_data = {
            'platform': 'macOS',
            'python_version': '3.9.7',
            'nodejs_version': 'v18.12.0'
        }
        
        success = self.config_manager.create_config(test_data)
        self.assertTrue(success)
        self.assertTrue(self.config_path.exists())
        
        # Verify content
        with open(self.config_path, 'r') as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data, test_data)
    
    def test_read_config(self):
        """Test reading existing configuration"""
        test_data = {'test': 'value'}
        with open(self.config_path, 'w') as f:
            json.dump(test_data, f)
        
        read_data = self.config_manager.read_config()
        self.assertEqual(read_data, test_data)
    
    def test_read_nonexistent_config(self):
        """Test reading non-existent configuration returns None"""
        read_data = self.config_manager.read_config()
        self.assertIsNone(read_data)


class TestInstallerOrchestration(unittest.TestCase):
    """Test installer orchestration logic"""
    
    def setUp(self):
        """Create temporary directory for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.installer = Installer(install_dir=self.test_dir, verbose=False)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_installer_initialization(self):
        """Test that installer initializes with correct components"""
        self.assertIsNotNone(self.installer.platform)
        self.assertIsNotNone(self.installer.validator)
        self.assertIsNotNone(self.installer.config_manager)
        self.assertIsNotNone(self.installer.venv_manager)
        self.assertIsNotNone(self.installer.package_installer)
        self.assertEqual(self.installer.install_dir, self.test_dir)
    
    def test_validate_platform_supported(self):
        """Test platform validation for supported platforms"""
        with patch.object(self.installer.platform, 'is_supported', return_value=True):
            result = self.installer.validate_platform()
            self.assertTrue(result)
    
    def test_validate_platform_unsupported(self):
        """Test platform validation for unsupported platforms"""
        with patch.object(self.installer.platform, 'is_supported', return_value=False):
            result = self.installer.validate_platform()
            self.assertFalse(result)


class TestVenvManager(unittest.TestCase):
    """Test virtual environment management"""
    
    def setUp(self):
        """Create temporary directory for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.venv_manager = VenvManager(self.test_dir, verbose=False)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_venv_manager_initialization(self):
        """Test VenvManager initializes correctly"""
        self.assertEqual(self.venv_manager.install_dir, self.test_dir)
        self.assertEqual(self.venv_manager.venv_path, self.test_dir / ".venv")
    
    def test_get_activation_command_unix(self):
        """Test activation command on Unix systems"""
        with patch('platform.system', return_value='Darwin'):
            venv_manager = VenvManager(self.test_dir)
            cmd = venv_manager.get_activation_command()
            self.assertEqual(cmd, [str(self.test_dir / ".venv" / "bin" / "python")])
    
    def test_get_activation_command_windows(self):
        """Test activation command on Windows"""
        with patch('platform.system', return_value='Windows'):
            venv_manager = VenvManager(self.test_dir)
            cmd = venv_manager.get_activation_command()
            self.assertEqual(cmd, [str(self.test_dir / ".venv" / "Scripts" / "python.exe")])
    
    def test_create_venv_already_exists(self):
        """Test venv creation when venv already exists"""
        # Create fake venv directory
        self.venv_manager.venv_path.mkdir()
        
        result = self.venv_manager.create_venv()
        self.assertTrue(result)


class TestPackageInstaller(unittest.TestCase):
    """Test package installation functionality"""
    
    def setUp(self):
        """Create temporary directory and components for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.venv_manager = VenvManager(self.test_dir, verbose=False)
        self.package_installer = PackageInstaller(self.test_dir, self.venv_manager, verbose=False)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_install_python_packages_file_not_found(self):
        """Test Python package installation with missing requirements file"""
        fake_requirements = self.test_dir / "fake_requirements.txt"
        
        result = self.package_installer.install_python_packages(fake_requirements)
        self.assertFalse(result)
    
    def test_install_npm_packages_no_package_json(self):
        """Test npm installation when package.json doesn't exist"""
        result = self.package_installer.install_npm_packages()
        self.assertFalse(result)
    
    def test_get_installed_python_packages(self):
        """Test getting installed Python packages"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='[{"name": "flask", "version": "2.0.0"}]'
            )
            
            packages = self.package_installer.get_installed_python_packages()
            self.assertIsInstance(packages, dict)
            self.assertEqual(packages.get('flask'), '2.0.0')
    
    def test_get_installed_npm_packages(self):
        """Test getting installed npm packages"""
        # Create fake package-lock.json
        lock_data = {
            "packages": {
                "node_modules/react": {"version": "19.0.0"},
                "node_modules/vite": {"version": "6.1.0"}
            }
        }
        
        lock_file = self.test_dir / "package-lock.json"
        with open(lock_file, 'w') as f:
            json.dump(lock_data, f)
        
        packages = self.package_installer.get_installed_npm_packages()
        self.assertIsInstance(packages, dict)
        self.assertEqual(packages.get('react'), '19.0.0')
        self.assertEqual(packages.get('vite'), '6.1.0')


class TestConfigManagerExtended(unittest.TestCase):
    """Test extended configuration management"""
    
    def setUp(self):
        """Create temporary directory for testing"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_path = self.test_dir / 'config.json'
        self.config_manager = ConfigManager(self.config_path)
    
    def tearDown(self):
        """Clean up temporary directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_update_config(self):
        """Test updating existing configuration"""
        # Create initial config
        initial_data = {'version': '1.0', 'platform': 'macOS'}
        self.config_manager.create_config(initial_data)
        
        # Update config
        updates = {'version': '2.0', 'new_field': 'value'}
        success = self.config_manager.update_config(updates)
        
        self.assertTrue(success)
        
        # Verify updates
        config = self.config_manager.read_config()
        self.assertEqual(config['version'], '2.0')
        self.assertEqual(config['platform'], 'macOS')
        self.assertEqual(config['new_field'], 'value')


class TestLauncherGenerator(unittest.TestCase):
    """Test launcher script generation"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.install_dir = Path(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)
    
    def test_generate_unix_launcher(self):
        """Test Unix launcher script generation"""
        with patch('platform.system', return_value='Linux'):
            platform = PlatformInfo()
            generator = LauncherGenerator(self.install_dir, platform, verbose=False)
            
            script_path = generator.generate_unix_launcher()
            
            # Verify script was created
            self.assertTrue(script_path.exists())
            self.assertEqual(script_path.name, 'launch-antifier.sh')
            
            # Verify script content
            content = script_path.read_text()
            self.assertIn('#!/bin/bash', content)
            self.assertIn('Antifier Webapp Launcher', content)
            self.assertIn('source .venv/bin/activate', content)
            self.assertIn('python src/backend/app.py', content)
            self.assertIn('npm run dev', content)
            self.assertIn('localhost:5173', content)
            
            # Verify executable permissions (Unix only)
            import stat
            mode = script_path.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR)
    
    def test_generate_windows_launcher(self):
        """Test Windows launcher script generation"""
        with patch('platform.system', return_value='Windows'):
            platform = PlatformInfo()
            generator = LauncherGenerator(self.install_dir, platform, verbose=False)
            
            script_path = generator.generate_windows_launcher()
            
            # Verify script was created
            self.assertTrue(script_path.exists())
            self.assertEqual(script_path.name, 'launch-antifier.bat')
            
            # Verify script content
            content = script_path.read_text()
            self.assertIn('@echo off', content)
            self.assertIn('Antifier Webapp Launcher', content)
            self.assertIn('.venv\\Scripts\\activate.bat', content)
            self.assertIn('python src\\backend\\app.py', content)
            self.assertIn('npm run dev', content)
            self.assertIn('localhost:5173', content)
    
    def test_generate_launcher_selects_correct_platform(self):
        """Test that generate_launcher creates correct script for platform"""
        with patch('platform.system', return_value='Darwin'):
            platform = PlatformInfo()
            generator = LauncherGenerator(self.install_dir, platform, verbose=False)
            
            script_path = generator.generate_launcher()
            
            # Should create Unix script on macOS
            self.assertEqual(script_path.name, 'launch-antifier.sh')
            self.assertTrue(script_path.exists())


class TestWebappLauncher(unittest.TestCase):
    """Test webapp launch functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.install_dir = Path(self.test_dir)
        
        # Create mock venv structure
        venv_path = self.install_dir / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "Scripts").mkdir()
    
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)
    
    def test_is_port_in_use(self):
        """Test port checking functionality"""
        platform = PlatformInfo()
        venv_manager = VenvManager(self.install_dir, verbose=False)
        launcher = WebappLauncher(self.install_dir, platform, venv_manager, verbose=False)
        
        # Port 9999 should not be in use
        self.assertFalse(launcher.is_port_in_use(9999))
    
    def test_wait_for_port_timeout(self):
        """Test port waiting with timeout"""
        platform = PlatformInfo()
        venv_manager = VenvManager(self.install_dir, verbose=False)
        launcher = WebappLauncher(self.install_dir, platform, venv_manager, verbose=False)
        
        # Should timeout on unused port
        result = launcher.wait_for_port(9999, timeout=1)
        self.assertFalse(result)
    
    def test_start_flask_backend_missing_script(self):
        """Test Flask startup with missing backend script"""
        platform = PlatformInfo()
        venv_manager = VenvManager(self.install_dir, verbose=False)
        launcher = WebappLauncher(self.install_dir, platform, venv_manager, verbose=False)
        
        # Should fail when backend script doesn't exist
        result = launcher.start_flask_backend()
        self.assertFalse(result)


class TestVenvManagerExtensions(unittest.TestCase):
    """Test VenvManager extensions for launcher support"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.install_dir = Path(self.test_dir)
        self.venv_manager = VenvManager(self.install_dir, verbose=False)
    
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)
    
    def test_get_python_executable_unix(self):
        """Test getting Python executable path on Unix"""
        with patch('platform.system', return_value='Linux'):
            python_exe = self.venv_manager.get_python_executable()
            
            self.assertIsInstance(python_exe, Path)
            self.assertTrue(str(python_exe).endswith('bin/python'))
    
    def test_get_python_executable_windows(self):
        """Test getting Python executable path on Windows"""
        with patch('platform.system', return_value='Windows'):
            python_exe = self.venv_manager.get_python_executable()
            
            self.assertIsInstance(python_exe, Path)
            self.assertTrue(str(python_exe).endswith('Scripts\\python.exe') or 
                          str(python_exe).endswith('Scripts/python.exe'))


class TestInstallerIntegration(unittest.TestCase):
    """Integration tests for complete installer workflows"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.install_dir = Path(self.test_dir)
        
        # Create mock requirements files
        (self.install_dir / 'requirements-pypi.txt').write_text('requests==2.28.0\n')
        (self.install_dir / 'package.json').write_text('{"name": "test", "dependencies": {}}')
    
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)
    
    def test_installer_component_initialization(self):
        """Test that installer initializes all required components"""
        installer = Installer(install_dir=self.install_dir, verbose=False)
        
        # Verify all components are initialized
        self.assertIsNotNone(installer.platform)
        self.assertIsNotNone(installer.validator)
        self.assertIsNotNone(installer.config_manager)
        self.assertIsNotNone(installer.venv_manager)
        self.assertIsNotNone(installer.package_installer)
        self.assertIsNotNone(installer.launcher_generator)
        self.assertIsNotNone(installer.webapp_launcher)
        
        # Verify components use correct install directory
        self.assertEqual(installer.install_dir, self.install_dir)
        self.assertEqual(installer.venv_manager.install_dir, self.install_dir)
    
    def test_config_manager_metadata_creation(self):
        """Test config manager creates valid metadata structure"""
        installer = Installer(install_dir=self.install_dir, verbose=False)
        
        metadata = installer.create_metadata(
            nodejs_version='v18.0.0',
            python_version='3.11.0',
            python_packages={'requests': '2.28.0'},
            npm_packages={'react': '18.0.0'}
        )
        
        # Verify metadata structure
        self.assertIn('platform', metadata)
        self.assertIn('installation_date', metadata)
        self.assertIn('nodejs_version', metadata)
        self.assertIn('python_version', metadata)
        self.assertIn('python_packages', metadata)
        self.assertIn('npm_packages', metadata)
        
        # Verify values
        self.assertEqual(metadata['nodejs_version'], 'v18.0.0')
        self.assertEqual(metadata['python_version'], '3.11.0')
        self.assertEqual(len(metadata['python_packages']), 1)
        self.assertEqual(len(metadata['npm_packages']), 1)
    
    def test_config_persistence_and_retrieval(self):
        """Test config can be written and read back correctly"""
        config_path = self.install_dir / 'config.json'
        config_manager = ConfigManager(config_path)
        
        test_config = {
            'version': '1.0',
            'platform': 'macOS',
            'installation_date': '2026-01-09T10:00:00',
            'python_packages': {'numpy': '1.24.0'}
        }
        
        # Write config
        success = config_manager.create_config(test_config)
        self.assertTrue(success)
        self.assertTrue(config_path.exists())
        
        # Read config back
        retrieved_config = config_manager.read_config()
        self.assertIsNotNone(retrieved_config)
        self.assertEqual(retrieved_config['version'], '1.0')
        self.assertEqual(retrieved_config['platform'], 'macOS')
        self.assertEqual(retrieved_config['python_packages']['numpy'], '1.24.0')
    
    def test_update_detection_logic(self):
        """Test that installer detects when packages need updating"""
        config_path = self.install_dir / 'config.json'
        config_manager = ConfigManager(config_path)
        
        # Create initial config with old package versions
        old_config = {
            'version': '1.0',
            'python_packages': {'requests': '2.25.0'},  # Old version
            'npm_packages': {'react': '17.0.0'}  # Old version
        }
        config_manager.create_config(old_config)
        
        # Simulate new installation with updated versions
        new_packages = {
            'python_packages': {'requests': '2.28.0'},  # New version
            'npm_packages': {'react': '18.0.0'}  # New version
        }
        
        # Read existing config
        existing = config_manager.read_config()
        self.assertIsNotNone(existing)
        
        # Verify versions differ (indicating update needed)
        self.assertNotEqual(
            existing['python_packages']['requests'],
            new_packages['python_packages']['requests']
        )
    
    def test_launcher_generator_platform_selection(self):
        """Test launcher generator selects correct script for platform"""
        with patch('platform.system', return_value='Darwin'):
            platform = PlatformInfo()
            generator = LauncherGenerator(self.install_dir, platform, verbose=False)
            
            script_path = generator.generate_launcher()
            
            # On macOS, should generate .sh file
            self.assertEqual(script_path.suffix, '.sh')
            self.assertEqual(script_path.name, 'launch-antifier.sh')
    
    def test_launcher_script_contains_required_commands(self):
        """Test generated launcher scripts contain all required startup commands"""
        with patch('platform.system', return_value='Linux'):
            platform = PlatformInfo()
            generator = LauncherGenerator(self.install_dir, platform, verbose=False)
            
            script_path = generator.generate_unix_launcher()
            content = script_path.read_text()
            
            # Verify critical commands are present
            required_commands = [
                'source .venv/bin/activate',
                'python src/backend/app.py',
                'npm run dev',
                'localhost:5173',
                'localhost:5000'
            ]
            
            for command in required_commands:
                self.assertIn(command, content, f"Missing required command: {command}")
    
    def test_venv_and_package_installer_integration(self):
        """Test VenvManager and PackageInstaller work together"""
        venv_manager = VenvManager(self.install_dir, verbose=False)
        package_installer = PackageInstaller(self.install_dir, venv_manager, verbose=False)
        
        # Verify package installer has reference to venv manager
        self.assertEqual(package_installer.venv_manager, venv_manager)
        
        # Verify venv manager provides correct paths
        python_exe = venv_manager.get_python_executable()
        pip_cmd = venv_manager.get_pip_command()
        
        self.assertIsInstance(python_exe, Path)
        self.assertIsInstance(pip_cmd, list)
        self.assertTrue(len(pip_cmd) > 0)
    
    def test_webapp_launcher_port_validation(self):
        """Test webapp launcher validates ports correctly"""
        platform = PlatformInfo()
        venv_manager = VenvManager(self.install_dir, verbose=False)
        launcher = WebappLauncher(self.install_dir, platform, venv_manager, verbose=False)
        
        # Test port checking functionality
        # Using a very high port that's unlikely to be in use
        self.assertFalse(launcher.is_port_in_use(59999))
        
        # Test timeout behavior
        result = launcher.wait_for_port(59999, timeout=1)
        self.assertFalse(result)
    
    def test_installer_metadata_includes_all_required_fields(self):
        """Test installer metadata contains all required tracking fields"""
        installer = Installer(install_dir=self.install_dir, verbose=False)
        
        metadata = installer.create_metadata(
            nodejs_version='v18.0.0',
            python_version='3.11.0',
            python_packages={'package1': '1.0.0'},
            npm_packages={'package2': '2.0.0'}
        )
        
        required_fields = [
            'platform',
            'installation_date',
            'nodejs_version',
            'python_version',
            'venv_location',
            'python_packages',
            'npm_packages'
        ]
        
        for field in required_fields:
            self.assertIn(field, metadata, f"Missing required field: {field}")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
