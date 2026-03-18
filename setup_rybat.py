#!/usr/bin/env python3
# =============================================================================
# RYBAT Intelligence Platform - Cross-Platform Setup Script
# Version: 1.0.0
# Last Updated: 2026-02-02
# Authors: Mr Cat + Claude AI
# =============================================================================
#
# This script works on Windows, macOS, and Linux!
#
# USAGE:
#   python setup_rybat.py
#   python setup_rybat.py --dev
#   python setup_rybat.py --check
#   python setup_rybat.py --help
#
# =============================================================================

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================
RYBAT_VERSION = "1.0.0"
PYTHON_MIN_VERSION = (3, 11)
VENV_DIR = "venv"

# =============================================================================
# COLORS (cross-platform)
# =============================================================================
class Colors:
    """Cross-platform color support"""
    
    @staticmethod
    def init():
        """Enable ANSI colors on Windows"""
        if platform.system() == "Windows":
            os.system("")  # Enable ANSI escape sequences
    
    HEADER = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    INFO = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{text}{Colors.RESET}")

def print_success(text):
    print(f"{Colors.SUCCESS}✓ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.ERROR}✗ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.INFO}ℹ {text}{Colors.RESET}")

# =============================================================================
# SYSTEM DETECTION
# =============================================================================
def get_system_info():
    """Get system information"""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "is_windows": platform.system() == "Windows",
        "is_macos": platform.system() == "Darwin",
        "is_linux": platform.system() == "Linux",
    }

def get_venv_python():
    """Get path to Python in virtual environment"""
    system = platform.system()
    if system == "Windows":
        return Path(VENV_DIR) / "Scripts" / "python.exe"
    else:
        return Path(VENV_DIR) / "bin" / "python"

def get_venv_pip():
    """Get path to pip in virtual environment"""
    system = platform.system()
    if system == "Windows":
        return Path(VENV_DIR) / "Scripts" / "pip.exe"
    else:
        return Path(VENV_DIR) / "bin" / "pip"

def get_venv_activate():
    """Get activation command for virtual environment"""
    system = platform.system()
    if system == "Windows":
        return f".\\{VENV_DIR}\\Scripts\\activate"
    else:
        return f"source {VENV_DIR}/bin/activate"

# =============================================================================
# PREREQUISITES CHECK
# =============================================================================
def check_python_version():
    """Check if Python version meets requirements"""
    current = (sys.version_info.major, sys.version_info.minor)
    if current >= PYTHON_MIN_VERSION:
        print_success(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return True
    else:
        print_error(f"Python {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}+ required, found {current[0]}.{current[1]}")
        return False

def check_pip():
    """Check if pip is available"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], 
                      capture_output=True, check=True)
        print_success("pip available")
        return True
    except subprocess.CalledProcessError:
        print_error("pip is not available")
        print_info("Install with: python -m ensurepip")
        return False

def check_venv_module():
    """Check if venv module is available"""
    try:
        import venv
        print_success("venv module available")
        return True
    except ImportError:
        print_error("venv module not available")
        if platform.system() == "Linux":
            print_info("Install with: sudo apt install python3-venv")
        return False

def check_docker():
    """Check if Docker is available"""
    try:
        result = subprocess.run(["docker", "--version"], 
                               capture_output=True, check=True)
        version = result.stdout.decode().strip()
        print_success(f"Docker: {version}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("Docker not available (optional)")
        return False

def check_prerequisites():
    """Run all prerequisite checks"""
    print_info("Checking prerequisites...")
    print()
    
    checks = [
        check_python_version(),
        check_pip(),
        check_venv_module(),
    ]
    
    # Docker is optional
    check_docker()
    
    print()
    if all(checks):
        print_success("All required prerequisites satisfied")
        return True
    else:
        print_error("Some prerequisites are missing")
        return False

# =============================================================================
# INSTALLATION
# =============================================================================
def create_virtual_environment():
    """Create Python virtual environment"""
    print_info("Creating virtual environment...")
    
    try:
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
        print_success("Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False

def install_dependencies():
    """Install Python dependencies"""
    print_info("Installing dependencies (this may take a few minutes)...")
    
    pip_path = get_venv_pip()
    
    try:
        # Upgrade pip first
        subprocess.run([str(pip_path), "install", "--upgrade", "pip"], 
                      check=True, capture_output=True)
        
        # Install requirements
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"], 
                      check=True)
        print_success("Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def setup_configuration():
    """Setup configuration files"""
    print_info("Setting up configuration...")
    
    # Create .env from example
    if not Path(".env").exists():
        if Path(".env.example").exists():
            shutil.copy(".env.example", ".env")
            print_warning(".env file created from template")
            print_warning("IMPORTANT: Edit .env with your API keys!")
        else:
            print_warning(".env.example not found, skipping .env creation")
    else:
        print_info(".env file already exists")
    
    # Create data directory
    Path("data").mkdir(exist_ok=True)
    print_success("Data directory ready")
    
    return True

def create_start_scripts():
    """Create platform-specific start scripts"""
    system = platform.system()
    
    if system == "Windows":
        # start.bat already provided
        print_info("Use start.bat to launch RYBAT")
    else:
        # Create Unix start script
        start_script = f"""#!/bin/bash
# RYBAT Start Script
cd "$(dirname "$0")"
source {VENV_DIR}/bin/activate
python main.py
"""
        script_path = Path("start.sh")
        script_path.write_text(start_script)
        script_path.chmod(0o755)
        print_success("Created start.sh")

def install_development():
    """Run development installation"""
    print_header("Installing RYBAT in Development Mode")
    print()
    
    if not check_prerequisites():
        return False
    
    print()
    
    if not create_virtual_environment():
        return False
    
    if not install_dependencies():
        return False
    
    if not setup_configuration():
        return False
    
    create_start_scripts()
    
    # Print success message
    print()
    print_header("Installation Complete!")
    print()
    
    system_info = get_system_info()
    activate_cmd = get_venv_activate()
    
    print("Next steps:")
    print()
    print(f"  1. Edit .env file with your API keys:")
    if system_info["is_windows"]:
        print("     notepad .env")
    else:
        print("     nano .env")
    print()
    print("  2. Activate virtual environment:")
    print(f"     {activate_cmd}")
    print()
    print("  3. Start RYBAT:")
    if system_info["is_windows"]:
        print("     python main.py")
        print("     (or double-click start.bat)")
    else:
        print("     python main.py")
        print("     (or run ./start.sh)")
    print()
    print("  4. Open dashboard:")
    print("     http://localhost:8000")
    print()
    
    return True

# =============================================================================
# SYSTEM INFO DISPLAY
# =============================================================================
def show_system_info():
    """Display system information"""
    info = get_system_info()
    
    print_header("System Information")
    print()
    print(f"  Operating System: {info['os']} {info['os_release']}")
    print(f"  Architecture:     {info['arch']}")
    print(f"  Python Version:   {info['python']}")
    print()

# =============================================================================
# HELP
# =============================================================================
def show_help():
    """Display help message"""
    print(f"""
RYBAT Intelligence Platform - Cross-Platform Setup Script v{RYBAT_VERSION}

Usage: python setup_rybat.py [OPTIONS]

Options:
  --dev, -d      Development mode (create venv, install deps)
  --check, -c    Check prerequisites only
  --info, -i     Show system information
  --help, -h     Show this help message

Examples:
  python setup_rybat.py              # Interactive mode
  python setup_rybat.py --dev        # Quick development setup
  python setup_rybat.py --check      # Verify system requirements

Supported Platforms:
  ✓ Windows 10/11
  ✓ macOS 12+ (Monterey and later)
  ✓ Linux (Ubuntu 22.04+, Debian 12+, etc.)
""")

# =============================================================================
# MAIN
# =============================================================================
def main():
    """Main entry point"""
    Colors.init()
    
    print()
    print_header(f"RYBAT Intelligence Platform - Setup v{RYBAT_VERSION}")
    print()
    
    # Parse arguments
    args = sys.argv[1:]
    
    if "--help" in args or "-h" in args:
        show_help()
        return
    
    if "--info" in args or "-i" in args:
        show_system_info()
        return
    
    if "--check" in args or "-c" in args:
        show_system_info()
        check_prerequisites()
        return
    
    if "--dev" in args or "-d" in args:
        show_system_info()
        install_development()
        return
    
    # Interactive mode
    show_system_info()
    
    print("Select installation mode:")
    print()
    print("  1) Development (recommended for most users)")
    print("  2) Check prerequisites only")
    print("  3) Show help")
    print()
    
    try:
        choice = input("Enter choice [1-3]: ").strip()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return
    
    print()
    
    if choice == "1":
        install_development()
    elif choice == "2":
        check_prerequisites()
    elif choice == "3":
        show_help()
    else:
        print_error("Invalid choice")

if __name__ == "__main__":
    main()
