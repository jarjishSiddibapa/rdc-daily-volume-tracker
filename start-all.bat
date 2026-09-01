@echo off
setlocal EnableExtensions

rem Always run from the repository, including when Task Scheduler leaves
rem the optional "Start in" field empty.
cd /d "%~dp0"

if not exist "Logs" mkdir "Logs"
set "LAUNCH_LOG=Logs\launcher.log"
>>"%LAUNCH_LOG%" echo [%date% %time%] Launcher started.

if not exist ".env" (
    echo ERROR: .env was not found in %CD%
    echo Copy .env.example to .env and configure it before starting the app.
    >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: .env was not found.
    exit /b 2
)

if not exist "venv\Scripts\python.exe" (
    echo Creating the Python virtual environment...
    where py >nul 2>&1
    if errorlevel 1 (
        python -m venv venv
    ) else (
        py -3 -m venv venv
    )

    if not exist "venv\Scripts\python.exe" (
        echo ERROR: The virtual environment could not be created.
        >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: Virtual environment creation failed.
        exit /b 3
    )
)

"venv\Scripts\python.exe" -c "import flask, flask_compress, waitress" >nul 2>&1
if errorlevel 1 (
    echo Installing application dependencies...
    "venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Dependency installation failed. See the output above.
        >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: Dependency installation failed.
        exit /b 4
    )
)

set "PYTHONUNBUFFERED=1"
echo Starting RDC Daily Volume Tracker...
echo Keep this process running. Press Ctrl+C to stop it.
>>"%LAUNCH_LOG%" echo [%date% %time%] Starting server.py.

"venv\Scripts\python.exe" server.py >>"%LAUNCH_LOG%" 2>&1
set "APP_EXIT_CODE=%ERRORLEVEL%"

>>"%LAUNCH_LOG%" echo [%date% %time%] Server stopped with exit code %APP_EXIT_CODE%.
echo Server stopped with exit code %APP_EXIT_CODE%. See %LAUNCH_LOG% for details.
exit /b %APP_EXIT_CODE%
