@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=J:\MagicTool\Standalone\VideoCut\video_tool\venv\Scripts\python.exe"
set "LOG_FILE=%~dp0startup.log"

echo ============================== > "%LOG_FILE%"
echo Start time: %date% %time% >> "%LOG_FILE%"
echo Work dir: %cd% >> "%LOG_FILE%"
echo ============================== >> "%LOG_FILE%"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo Python: %PYTHON_EXE% >> "%LOG_FILE%"

if "%~1"=="--check" (
    "%PYTHON_EXE%" -c "from app.ui.main_window import MainWindow; print('launcher-check-ok')" >> "%LOG_FILE%" 2>&1
) else (
    "%PYTHON_EXE%" main.py >> "%LOG_FILE%" 2>&1
)

if errorlevel 1 (
    echo.
    echo Launch failed. See log:
    echo %LOG_FILE%
    echo.
    type "%LOG_FILE%"
    echo.
    pause
    exit /b 1
)

if "%~1"=="--check" (
    type "%LOG_FILE%"
) else (
    echo.
    echo App closed.
    echo Log: %LOG_FILE%
    pause
)

endlocal
