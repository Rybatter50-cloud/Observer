# =============================================================================
# Observer Lite - Windows Installation Script (PowerShell)
# Version: 1.0.0
# Last Updated: 2026-03-18
# Authors: Mr Cat + Claude AI
# =============================================================================
#
# USAGE:
#   1. Open PowerShell as Administrator (recommended)
#   2. Navigate to Observer directory
#   3. Run: .\install.ps1
#
# EXECUTION POLICY:
#   If you get an execution policy error, run:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# =============================================================================

param(
    [switch]$Dev,
    [switch]$Docker,
    [switch]$Help
)

# =============================================================================
# CONFIGURATION
# =============================================================================
$Observer_VERSION = "1.0.0"
$PYTHON_MIN_VERSION = [Version]"3.11"
$VENV_DIR = "venv"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
function Write-Header {
    Write-Host ""
    Write-Host "=============================================================================" -ForegroundColor Blue
    Write-Host " Observer Lite - Windows Installer v$Observer_VERSION" -ForegroundColor Blue
    Write-Host "=============================================================================" -ForegroundColor Blue
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-WarnMsg {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

function Get-PythonVersion {
    try {
        $versionOutput = & python --version 2>&1
        if ($versionOutput -match "Python (\d+\.\d+)") {
            return [Version]$Matches[1]
        }
    } catch {}
    return $null
}

function Show-Help {
    Write-Host "Observer Lite - Windows Installation Script"
    Write-Host ""
    Write-Host "Usage: .\install.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Dev       Development mode (install in current directory)"
    Write-Host "  -Docker    Docker mode (build container image)"
    Write-Host "  -Help      Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\install.ps1 -Dev      # Local development"
    Write-Host "  .\install.ps1 -Docker   # Docker deployment"
    Write-Host ""
}

# =============================================================================
# PREREQUISITES CHECK
# =============================================================================
function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check Python
    if (-not (Test-Command "python")) {
        Write-ErrorMsg "Python is not installed or not in PATH"
        Write-Info "Download Python 3.11+: https://www.python.org/downloads/"
        Write-Info "IMPORTANT: Check 'Add Python to PATH' during installation"
        return $false
    }
    
    # Check Python version
    $pythonVersion = Get-PythonVersion
    if ($null -eq $pythonVersion) {
        Write-ErrorMsg "Could not determine Python version"
        return $false
    }
    
    if ($pythonVersion -lt $PYTHON_MIN_VERSION) {
        Write-ErrorMsg "Python $PYTHON_MIN_VERSION or higher is required"
        Write-Info "Current version: $pythonVersion"
        return $false
    }
    Write-Success "Python $pythonVersion"
    
    # Check pip
    if (-not (Test-Command "pip")) {
        Write-ErrorMsg "pip is not installed"
        Write-Info "Install pip: python -m ensurepip"
        return $false
    }
    Write-Success "pip available"

    # Check PostgreSQL
    if (-not (Test-Command "psql")) {
        Write-WarnMsg "PostgreSQL (psql) not found in PATH"
        Write-Info "Observer Lite requires PostgreSQL 14+ with pg_trgm extension"
        Write-Info "Download: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads"
        Write-Info "During install, ensure 'Command Line Tools' is selected"
        Write-Host ""
    } else {
        Write-Success "PostgreSQL available"
    }

    Write-Success "All prerequisites satisfied"
    Write-Host ""
    return $true
}

# =============================================================================
# INSTALLATION MODES
# =============================================================================
function Install-Development {
    Write-Info "Installing in DEVELOPMENT mode..."
    
    # Create virtual environment
    Write-Info "Creating virtual environment..."
    python -m venv $VENV_DIR
    if (-not $?) {
        Write-ErrorMsg "Failed to create virtual environment"
        return
    }
    Write-Success "Virtual environment created"
    
    # Activate and install dependencies
    Write-Info "Installing dependencies..."
    & ".\$VENV_DIR\Scripts\pip.exe" install --upgrade pip
    & ".\$VENV_DIR\Scripts\pip.exe" install -r requirements.txt
    if (-not $?) {
        Write-ErrorMsg "Failed to install dependencies"
        return
    }
    Write-Success "Dependencies installed"
    
    # Create .env from example if not exists
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-WarnMsg ".env file created from template - EDIT DATABASE_URL PASSWORD!"
        }
    } else {
        Write-Info ".env file already exists"
    }
    
    # Create data directory
    if (-not (Test-Path "data")) {
        New-Item -ItemType Directory -Path "data" | Out-Null
    }
    Write-Success "Data directory created"
    
    # Download NLLB translation model
    Write-Info "Setting up NLLB translation model..."
    $modelBin = "models\nllb-200-distilled-600M-ct2\model.bin"
    $spModel = "models\nllb-200-distilled-600M-ct2\sentencepiece.bpe.model"
    if ((Test-Path $modelBin) -and (Test-Path $spModel)) {
        Write-Success "NLLB model already installed"
    } else {
        Write-Info "Installing build dependencies (transformers, torch)..."
        & ".\$VENV_DIR\Scripts\pip.exe" install transformers torch huggingface_hub
        if ($?) {
            Write-Info "Downloading and converting NLLB model (this may take a few minutes)..."
            & ".\$VENV_DIR\Scripts\python.exe" scripts\download_nllb.py
            if ($?) {
                Write-Success "NLLB model installed"
                Write-Info "Removing build dependencies (transformers, torch)..."
                & ".\$VENV_DIR\Scripts\pip.exe" uninstall -y transformers torch 2>$null
            } else {
                Write-WarnMsg "NLLB model download failed — you can retry later:"
                Write-Info "  python scripts\download_nllb.py"
            }
        } else {
            Write-WarnMsg "Could not install build dependencies"
            Write-Info "Install the model manually: python scripts\download_nllb.py"
        }
    }

    # Create start script
    $startScript = @"
@echo off
echo Starting Observer Lite...
call venv\Scripts\activate.bat
python main.py
pause
"@
    Set-Content -Path "start.bat" -Value $startScript
    Write-Success "Created start.bat"
    
    # Print instructions
    Write-Host ""
    Write-Success "Development installation complete!"
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Edit .env file with your database password:"
    Write-Host "     notepad .env"
    Write-Host ""
    Write-Host "  2. Start Observer Lite (Option A - Double-click):"
    Write-Host "     start.bat"
    Write-Host ""
    Write-Host "  3. Start Observer Lite (Option B - Command line):"
    Write-Host "     .\venv\Scripts\activate"
    Write-Host "     python main.py"
    Write-Host ""
    Write-Host "  4. Open dashboard:"
    Write-Host "     http://localhost:8000"
    Write-Host ""
}

function Install-Docker {
    Write-Info "Installing with DOCKER..."
    
    # Check Docker
    if (-not (Test-Command "docker")) {
        Write-ErrorMsg "Docker is not installed"
        Write-Info "Install Docker Desktop: https://www.docker.com/products/docker-desktop"
        return
    }
    
    # Check if Docker is running
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Docker is not running"
        Write-Info "Please start Docker Desktop"
        return
    }
    Write-Success "Docker is running"
    
    # Create .env from example if not exists
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-WarnMsg ".env file created - EDIT WITH YOUR API KEYS!"
        }
    }
    
    # Build image
    Write-Info "Building Docker image (this may take a few minutes)..."
    docker build -t "observer:$Observer_VERSION" .
    if (-not $?) {
        Write-ErrorMsg "Failed to build Docker image"
        return
    }
    Write-Success "Docker image built"
    
    # Print instructions
    Write-Host ""
    Write-Success "Docker installation complete!"
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Edit configuration:"
    Write-Host "     notepad .env"
    Write-Host ""
    Write-Host "  2. Start with docker-compose:"
    Write-Host "     docker-compose up -d"
    Write-Host ""
    Write-Host "  3. Or run directly:"
    Write-Host "     docker run -d --name observer -p 8000:8000 -v ${PWD}\.env:/app/.env:ro observer:$Observer_VERSION"
    Write-Host ""
    Write-Host "  4. View logs:"
    Write-Host "     docker logs -f observer"
    Write-Host ""
    Write-Host "  5. Open dashboard:"
    Write-Host "     http://localhost:8000"
    Write-Host ""
}

# =============================================================================
# MAIN
# =============================================================================
function Main {
    Write-Header
    
    if ($Help) {
        Show-Help
        return
    }
    
    if ($Docker) {
        Install-Docker
        return
    }
    
    if ($Dev) {
        if (Test-Prerequisites) {
            Install-Development
        }
        return
    }
    
    # Interactive mode
    Write-Host "Select installation mode:"
    Write-Host ""
    Write-Host "  1) Development (local directory, recommended for testing)"
    Write-Host "  2) Docker (containerized deployment)"
    Write-Host ""
    $choice = Read-Host "Enter choice [1-2]"
    Write-Host ""
    
    switch ($choice) {
        "1" {
            if (Test-Prerequisites) {
                Install-Development
            }
        }
        "2" {
            Install-Docker
        }
        default {
            Write-ErrorMsg "Invalid choice"
        }
    }
}

# Run main
Main
