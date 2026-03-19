#!/usr/bin/env python3
# =============================================================================
# Observer Intelligence Platform - Build Script
# Version: 1.0.0
# Last Updated: 2026-02-02
# Authors: Mr Cat + Claude AI
# =============================================================================
#
# This script builds standalone executables for Observer using PyInstaller.
# The resulting executable runs without requiring Python to be installed.
#
# USAGE:
#   python build.py                    # Build for current platform
#   python build.py --onefile          # Single executable (slower startup)
#   python build.py --clean            # Clean build artifacts
#   python build.py --help             # Show help
#
# OUTPUT:
#   dist/Observer/                        # Directory with executable
#   dist/Observer-1.0.0-windows-x64.zip   # Packaged release (Windows)
#   dist/Observer-1.0.0-macos-x64.tar.gz  # Packaged release (macOS)
#   dist/Observer-1.0.0-linux-x64.tar.gz  # Packaged release (Linux)
#
# =============================================================================

import os
import sys
import shutil
import platform
import subprocess
import argparse
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================
APP_NAME = "Observer"
APP_VERSION = "1.0.0"
SPEC_FILE = "observer.spec"

# Files to include in the release package (in addition to PyInstaller output)
RELEASE_FILES = [
    ".env.example",
    "README.md",
    "QUICKSTART.md",
    "LICENSE",
    "CONFIGURATION.md",
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
class Colors:
    """Cross-platform color support"""
    HEADER = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    INFO = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def init_colors():
    """Enable ANSI colors on Windows"""
    if platform.system() == "Windows":
        os.system("")

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

def get_platform_info():
    """Get platform information for naming"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Normalize system name
    if system == "darwin":
        system = "macos"
    
    # Normalize architecture
    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "i386": "x86",
        "i686": "x86",
    }
    arch = arch_map.get(machine, machine)
    
    return system, arch

def run_command(cmd, description=None):
    """Run a command and handle errors"""
    if description:
        print_info(description)
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        return False
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}")
        return False

# =============================================================================
# BUILD FUNCTIONS
# =============================================================================
def check_pyinstaller():
    """Check if PyInstaller is installed"""
    try:
        import PyInstaller
        version = PyInstaller.__version__
        print_success(f"PyInstaller {version}")
        return True
    except ImportError:
        print_error("PyInstaller is not installed")
        print_info("Install with: pip install pyinstaller")
        return False

def clean_build():
    """Clean build artifacts"""
    print_info("Cleaning build artifacts...")
    
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = ["*.pyc", "*.pyo", "*.spec.bak"]
    
    for dir_name in dirs_to_clean:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print_success(f"Removed {dir_name}/")
    
    # Clean __pycache__ in subdirectories
    for pycache in Path(".").rglob("__pycache__"):
        shutil.rmtree(pycache)
    
    print_success("Build artifacts cleaned")

def build_executable(onefile=False):
    """Build the executable using PyInstaller"""
    print_header(f"Building {APP_NAME} v{APP_VERSION}")
    
    system, arch = get_platform_info()
    print_info(f"Platform: {system}-{arch}")
    
    # Check PyInstaller
    if not check_pyinstaller():
        return False
    
    # Check spec file exists
    if not Path(SPEC_FILE).exists():
        print_error(f"Spec file not found: {SPEC_FILE}")
        return False
    
    # Build command
    cmd = ["pyinstaller", SPEC_FILE, "--clean", "--noconfirm"]
    
    if onefile:
        print_info("Building single-file executable (this takes longer)...")
        # For onefile, we need to modify the spec or use command line
        cmd.extend(["--onefile"])
    
    # Run PyInstaller
    print_info("Running PyInstaller (this may take a few minutes)...")
    if not run_command(cmd):
        return False
    
    print_success("Build completed!")
    return True

def create_release_package():
    """Create a distributable release package"""
    print_header("Creating Release Package")
    
    system, arch = get_platform_info()
    
    # Determine output directory
    dist_dir = Path("dist") / APP_NAME
    if not dist_dir.exists():
        print_error(f"Build output not found: {dist_dir}")
        print_info("Run build first: python build.py")
        return False
    
    # Create release directory
    release_name = f"{APP_NAME}-{APP_VERSION}-{system}-{arch}"
    release_dir = Path("dist") / release_name
    
    # Clean and recreate
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)
    
    # Copy build output
    print_info("Copying build output...")
    for item in dist_dir.iterdir():
        dest = release_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    
    # Copy additional release files
    print_info("Adding release files...")
    for file_name in RELEASE_FILES:
        src = Path(file_name)
        if src.exists():
            shutil.copy2(src, release_dir / src.name)
            print_success(f"  Added {file_name}")
        else:
            print_warning(f"  Missing {file_name}")
    
    # Create data directory
    (release_dir / "data").mkdir(exist_ok=True)
    
    # Create archive
    print_info("Creating archive...")
    archive_base = Path("dist") / release_name
    
    if system == "windows":
        archive_path = shutil.make_archive(
            str(archive_base), "zip", "dist", release_name
        )
    else:
        archive_path = shutil.make_archive(
            str(archive_base), "gztar", "dist", release_name
        )
    
    # Get file size
    size_mb = Path(archive_path).stat().st_size / (1024 * 1024)
    
    print_success(f"Release package created: {archive_path}")
    print_info(f"Size: {size_mb:.1f} MB")
    
    return True

def show_instructions():
    """Show post-build instructions"""
    system, arch = get_platform_info()
    
    print_header("Build Complete!")
    print()
    print("Your standalone executable is ready in the dist/ directory.")
    print()
    print("To run Observer:")
    
    if system == "windows":
        print("  1. Extract the ZIP file")
        print("  2. Copy .env.example to .env and add your API keys")
        print("  3. Double-click Observer.exe")
    elif system == "macos":
        print("  1. Extract the tar.gz file:")
        print("     tar -xzf Observer-*.tar.gz")
        print("  2. Copy .env.example to .env and add your API keys")
        print("  3. Run: ./Observer")
    else:  # Linux
        print("  1. Extract the tar.gz file:")
        print("     tar -xzf Observer-*.tar.gz")
        print("  2. Copy .env.example to .env and add your API keys")
        print("  3. Run: ./Observer")
    
    print()
    print("Dashboard will be available at: http://localhost:8000")
    print()

# =============================================================================
# MAIN
# =============================================================================
def main():
    init_colors()
    
    parser = argparse.ArgumentParser(
        description=f"Build {APP_NAME} standalone executable"
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Create a single-file executable (slower startup)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts only"
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Create release package after build"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clean, build, and package"
    )
    
    args = parser.parse_args()
    
    print()
    print(f"{'='*60}")
    print(f" {APP_NAME} Build System v{APP_VERSION}")
    print(f"{'='*60}")
    
    if args.clean and not args.all:
        clean_build()
        return
    
    if args.all:
        clean_build()
        args.package = True
    
    # Build
    if build_executable(onefile=args.onefile):
        if args.package or args.all:
            create_release_package()
        show_instructions()
    else:
        print_error("Build failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
