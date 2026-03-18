@echo off
REM =============================================================================
REM RYBAT Lite - Windows Quick Start
REM Version: 1.0.0
REM Last Updated: 2026-02-02
REM =============================================================================
REM
REM This script provides a simple way to start RYBAT on Windows.
REM For first-time setup, use install.ps1 instead.
REM
REM =============================================================================

title RYBAT Lite

echo.
echo =============================================================================
echo  RYBAT Lite v1.0.0
echo =============================================================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run the installer first:
    echo   PowerShell: .\install.ps1 -Dev
    echo.
    echo Or manually create virtual environment:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Check if .env exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo.
    if exist ".env.example" (
        echo Creating .env from template...
        copy ".env.example" ".env" >nul
        echo.
        echo IMPORTANT: Edit .env file with your database password before continuing!
        echo.
        echo Press any key to open .env in Notepad...
        pause >nul
        notepad .env
        echo.
        echo After editing, press any key to start RYBAT...
        pause >nul
    ) else (
        echo Please create .env file with your configuration.
        pause
        exit /b 1
    )
)

REM Activate virtual environment and start
echo Starting RYBAT Lite...
echo.
echo Dashboard will be available at: http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.
echo =============================================================================
echo.

call venv\Scripts\activate.bat
python main.py

REM If we get here, the server stopped
echo.
echo RYBAT Lite has stopped.
pause
