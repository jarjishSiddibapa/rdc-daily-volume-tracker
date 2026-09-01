@echo off
setlocal EnableExtensions

rem Always run from the repository, including when Task Scheduler leaves
rem the optional "Start in" field empty.
cd /d "%~dp0"

if not exist "Logs" mkdir "Logs"
set "LAUNCH_LOG=Logs\launcher.log"
>>"%LAUNCH_LOG%" echo [%date% %time%] Launcher started.

if not exist ".env" (
    if not exist ".env.example" (
        echo ERROR: Neither .env nor .env.example was found in %CD%
        >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: Environment template was not found.
        exit /b 2
    )

    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 (
        echo ERROR: .env could not be created from .env.example.
        >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: Environment file creation failed.
        exit /b 2
    )
    set "ENV_CREATED=1"
    echo Created .env from .env.example.
    >>"%LAUNCH_LOG%" echo [%date% %time%] Created .env from .env.example.
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

if defined ENV_CREATED (
    "venv\Scripts\python.exe" -c "from pathlib import Path; import secrets; p=Path('.env'); s=p.read_text(encoding='utf-8'); p.write_text(s.replace('replace-with-a-strong-random-hex-key', secrets.token_hex(32)), encoding='utf-8')"
    if errorlevel 1 (
        echo ERROR: A secure Flask secret could not be written to .env.
        >>"%LAUNCH_LOG%" echo [%date% %time%] ERROR: Flask secret generation failed.
        exit /b 5
    )
    echo Generated a strong FLASK_SECRET_KEY in .env.
    >>"%LAUNCH_LOG%" echo [%date% %time%] Generated FLASK_SECRET_KEY in .env.
)

findstr /C:"MYSQL_PASSWORD=your-mysql-password" ".env" >nul
if not errorlevel 1 (
    echo.
    echo SETUP REQUIRED: .env was created, but the MySQL placeholder is still present.
    echo Edit %CD%\.env and enter the production database settings, then run start-all.bat again.
    >>"%LAUNCH_LOG%" echo [%date% %time%] Setup paused: production MySQL settings are required.
    exit /b 6
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
