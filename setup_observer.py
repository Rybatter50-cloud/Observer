#!/usr/bin/env python3
# =============================================================================
# Observer Intelligence Platform - Cross-Platform Setup Script
# Version: 1.0.0
# Last Updated: 2026-02-02
# Authors: Mr Cat + Claude AI
# =============================================================================
#
# This script works on Windows, macOS, and Linux!
#
# USAGE:
#   python setup_observer.py
#   python setup_observer.py --dev
#   python setup_observer.py --check
#   python setup_observer.py --help
#
# =============================================================================

import os
import re
import secrets
import sys
import subprocess
import shutil
import platform
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================
Observer_VERSION = "1.0.0"
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

def check_postgres():
    """Check if PostgreSQL client is available"""
    try:
        result = subprocess.run(["psql", "--version"],
                               capture_output=True, check=True)
        version = result.stdout.decode().strip()
        print_success(f"PostgreSQL: {version}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("PostgreSQL client (psql) not found")
        if platform.system() == "Linux":
            print_info("Install with: sudo apt install postgresql postgresql-client")
        elif platform.system() == "Darwin":
            print_info("Install with: brew install postgresql")
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

    # PostgreSQL and Docker are checked but not required to proceed
    check_postgres()
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

# =============================================================================
# DATABASE SETUP
# =============================================================================
DB_NAME = "observer"
DB_USER = "observer"

def _run_psql(sql, method, database="postgres"):
    """Execute SQL via psql using the given connection method.

    method is either:
      ("sudo",)                          — sudo -u postgres psql
      ("credentials", user, password)    — psql -U user -h localhost (with PGPASSWORD)
    """
    if method[0] == "sudo":
        cmd = ["sudo", "-u", "postgres", "psql", "-d", database,
               "-tAc", sql]
        env = None
    else:
        _, user, password = method
        cmd = ["psql", "-U", user, "-h", "localhost", "-d", database,
               "-tAc", sql]
        env = {**os.environ, "PGPASSWORD": password}

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def _get_psql_method():
    """Determine how to connect to PostgreSQL as superuser.

    Try sudo -u postgres first; fall back to prompting for credentials.
    """
    # Try sudo -u postgres (may prompt for the user's own sudo password)
    try:
        result = subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-tAc", "SELECT 1"],
            capture_output=False, text=True, timeout=30,
            stdout=subprocess.PIPE,
        )
        if result.returncode == 0 and "1" in (result.stdout or ""):
            print_success("PostgreSQL access via sudo")
            return ("sudo",)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to credentials
    print_info("sudo access to postgres not available — enter admin credentials")
    try:
        pg_user = input("  PostgreSQL superuser [postgres]: ").strip() or "postgres"
        import getpass
        pg_pass = getpass.getpass(f"  Password for {pg_user}: ")
    except KeyboardInterrupt:
        print()
        return None

    result = _run_psql("SELECT 1", ("credentials", pg_user, pg_pass))
    if result.returncode == 0 and "1" in result.stdout:
        print_success(f"PostgreSQL access via {pg_user}")
        return ("credentials", pg_user, pg_pass)

    print_error(f"Could not connect as {pg_user}")
    if result.stderr:
        print_error(result.stderr.strip())
    return None


def setup_database():
    """Create PostgreSQL user, database, and update .env with credentials."""
    print_header("PostgreSQL Database Setup")
    print()

    # Check if psql is available
    try:
        subprocess.run(["psql", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("psql not found — skipping database setup")
        print_info("Create the database manually and update DATABASE_URL in .env")
        return False

    # Check if .env already has a real password (not CHANGEME)
    env_path = Path(".env")
    if env_path.exists():
        env_text = env_path.read_text()
        if "CHANGEME" not in env_text and "DATABASE_URL=" in env_text:
            print_info("DATABASE_URL already configured in .env")
            try:
                reconfigure = input("  Reconfigure database? [y/N]: ").strip().lower()
            except KeyboardInterrupt:
                print()
                reconfigure = "n"
            if reconfigure != "y":
                print_info("Skipping database setup")
                return True

    # Get superuser connection method
    method = _get_psql_method()
    if method is None:
        print_warning("Skipping database setup — configure manually in .env")
        return False

    print()

    # Generate password
    generated_password = secrets.token_urlsafe(18)
    print_info(f"Generated password: {generated_password}")
    try:
        custom = input("  Press Enter to accept, or type a custom password: ").strip()
    except KeyboardInterrupt:
        print()
        return False
    password = custom if custom else generated_password

    print()

    # Create role (or update password if it exists)
    safe_pw = password.replace("'", "''")
    create_role_sql = (
        f"DO $$ BEGIN "
        f"CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{safe_pw}'; "
        f"EXCEPTION WHEN duplicate_object THEN "
        f"ALTER ROLE {DB_USER} WITH PASSWORD '{safe_pw}'; "
        f"END $$;"
    )
    result = _run_psql(create_role_sql, method)
    if result.returncode != 0:
        print_error(f"Failed to create database user: {result.stderr.strip()}")
        return False
    print_success(f"Database user '{DB_USER}' ready")

    # Create database if it doesn't exist
    check_db = _run_psql(
        f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'", method
    )
    if "1" not in (check_db.stdout or ""):
        result = _run_psql(f"CREATE DATABASE {DB_NAME} OWNER {DB_USER}", method)
        if result.returncode != 0:
            print_error(f"Failed to create database: {result.stderr.strip()}")
            return False
        print_success(f"Database '{DB_NAME}' created")
    else:
        # Ensure ownership
        _run_psql(f"ALTER DATABASE {DB_NAME} OWNER TO {DB_USER}", method)
        print_success(f"Database '{DB_NAME}' already exists")

    # Enable pg_trgm extension
    result = _run_psql("CREATE EXTENSION IF NOT EXISTS pg_trgm", method, database=DB_NAME)
    if result.returncode != 0:
        print_warning(f"Could not enable pg_trgm: {result.stderr.strip()}")
        print_info("pg_trgm is required for sanctions screening — enable it manually")
    else:
        print_success("pg_trgm extension enabled")

    # Update .env with the real DATABASE_URL
    db_url = f"postgresql://{DB_USER}:{password}@localhost:5432/{DB_NAME}"
    if env_path.exists():
        env_text = env_path.read_text()
        env_text = re.sub(
            r"^DATABASE_URL=.*$",
            f"DATABASE_URL={db_url}",
            env_text,
            flags=re.MULTILINE,
        )
        env_path.write_text(env_text)
    print_success("DATABASE_URL updated in .env")

    print()
    return True


def download_nllb_model():
    """Download and convert the NLLB translation model."""
    print_info("Setting up NLLB translation model...")

    model_dir = Path("models") / "nllb-200-distilled-600M-ct2"
    model_bin = model_dir / "model.bin"
    sp_model = model_dir / "sentencepiece.bpe.model"

    if model_bin.exists() and sp_model.exists():
        size_mb = model_bin.stat().st_size / (1024 * 1024)
        print_success(f"NLLB model already installed ({size_mb:.0f} MB)")
        return True

    print_info("NLLB model not found — downloading and converting...")
    print_info("This requires transformers and torch (build-time only, ~2 GB download)")
    print()

    pip_path = get_venv_pip()
    python_path = get_venv_python()

    # Install build-time dependencies
    try:
        print_info("Installing build dependencies (transformers, torch)...")
        subprocess.run(
            [str(pip_path), "install", "transformers", "torch", "huggingface_hub"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print_warning(f"Could not install build dependencies: {e}")
        print_info("You can install the model manually later:")
        print_info("  python scripts/download_nllb.py")
        return False

    # Run the download script
    try:
        subprocess.run(
            [str(python_path), "scripts/download_nllb.py"],
            check=True,
        )
    except subprocess.CalledProcessError:
        print_warning("NLLB model download/conversion failed")
        print_info("You can retry later: python scripts/download_nllb.py")
        return False

    # Uninstall build-time dependencies to save space
    print_info("Removing build-time dependencies (transformers, torch)...")
    try:
        subprocess.run(
            [str(pip_path), "uninstall", "-y", "transformers", "torch"],
            capture_output=True,
        )
        print_success("Build dependencies removed (saves ~2 GB)")
    except subprocess.CalledProcessError:
        print_warning("Could not auto-remove build deps — run manually:")
        print_info("  pip uninstall transformers torch")

    if model_bin.exists():
        size_mb = model_bin.stat().st_size / (1024 * 1024)
        print_success(f"NLLB model installed ({size_mb:.0f} MB)")
        return True

    return False


def create_start_scripts():
    """Create platform-specific start scripts"""
    system = platform.system()
    
    if system == "Windows":
        # start.bat already provided
        print_info("Use start.bat to launch Observer")
    else:
        # Create Unix start script
        start_script = f"""#!/bin/bash
# Observer Start Script
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
    print_header("Installing Observer in Development Mode")
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

    setup_database()

    download_nllb_model()

    create_start_scripts()

    # Print success message
    print()
    print_header("Installation Complete!")
    print()

    system_info = get_system_info()
    activate_cmd = get_venv_activate()

    print("Next steps:")
    print()
    print("  1. Activate virtual environment:")
    print(f"     {activate_cmd}")
    print()
    print("  2. Start Observer:")
    if system_info["is_windows"]:
        print("     python main.py")
        print("     (or double-click start.bat)")
    else:
        print("     python main.py")
        print("     (or run ./start.sh)")
    print()
    print("  3. Open dashboard:")
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
Observer Intelligence Platform - Cross-Platform Setup Script v{Observer_VERSION}

Usage: python setup_observer.py [OPTIONS]

Options:
  --dev, -d      Development mode (create venv, install deps)
  --check, -c    Check prerequisites only
  --info, -i     Show system information
  --help, -h     Show this help message

Examples:
  python setup_observer.py              # Interactive mode
  python setup_observer.py --dev        # Quick development setup
  python setup_observer.py --check      # Verify system requirements

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
    print_header(f"Observer Intelligence Platform - Setup v{Observer_VERSION}")
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
