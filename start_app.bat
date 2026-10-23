@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================
echo           KeyMacro — Desktop Automation
echo ===================================================

:: 1. Check if venv or .venv already exists
if exist "venv\Scripts\python.exe" (
    echo [Info] Virtual environment detected (venv).
    echo [Launch] Starting KeyMacro...
    venv\Scripts\python.exe run_qt.py
    goto end
)
if exist ".venv\Scripts\python.exe" (
    echo [Info] Virtual environment detected (.venv).
    echo [Launch] Starting KeyMacro...
    .venv\Scripts\python.exe run_qt.py
    goto end
)

:: 2. Find Python on system (check 'python' then 'py')
set PY_CMD=
where python >nul 2>&1
if !errorlevel! equ 0 (
    set PY_CMD=python
) else (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        set PY_CMD=py
    )
)

if "%PY_CMD%"=="" (
    echo.
    echo [ERROR] Python is installed, but Windows cannot find it in PATH.
    echo.
    echo How to fix:
    echo 1. Open Windows Start menu and search: "Manage app execution aliases"
    echo    Turn OFF "App Installer (python.exe)" and "App Installer (python3.exe)"
    echo 2. Re-run your Python installer, click "Modify", and check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: 3. Create .venv and install requirements
echo [Setup] Creating virtual environment (.venv)...
%PY_CMD% -m venv .venv
if !errorlevel! neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [Setup] Installing required packages (PySide6, pynput, etc.)...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo [Launch] Starting KeyMacro...
.venv\Scripts\python.exe run_qt.py

:end
if %errorlevel% neq 0 (
    echo.
    echo App closed with an exit code: %errorlevel%
    pause
)
