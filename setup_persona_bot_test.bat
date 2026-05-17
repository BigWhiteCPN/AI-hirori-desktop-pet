@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "BOOTSTRAP=python"
where py >nul 2>nul
if not errorlevel 1 set "BOOTSTRAP=py -3"

echo [1/4] Checking Python launcher...
%BOOTSTRAP% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found.
  echo Install Python 3.10+ first, then run this script again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [2/4] Creating virtual environment...
  %BOOTSTRAP% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
) else (
  echo [2/4] Virtual environment already exists.
)

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

echo [3/4] Installing runtime dependencies...
"%VENV_PY%" -m pip install -U pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

"%VENV_PY%" -m pip install -r "%ROOT%requirements_runtime.txt"
if errorlevel 1 (
  echo Failed to install requirements_runtime.txt
  pause
  exit /b 1
)

if not exist "%ROOT%persona_llm_config.json" (
  echo [4/4] Creating persona_llm_config.json from release template...
  copy /Y "%ROOT%persona_llm_config.release.json" "%ROOT%persona_llm_config.json" >nul
) else (
  echo [4/4] Keeping existing persona_llm_config.json
)

echo Running doctor checks...
"%VENV_PY%" "%ROOT%tools\doctor.py"
set "DOCTOR_EXIT=%ERRORLEVEL%"

echo.
echo Setup finished.
echo Main launch command:
echo   .\.venv\Scripts\python.exe .\persona_bot_test.py --profile main
echo.
echo Optional browser agent:
echo   .\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
echo.
if not "%DOCTOR_EXIT%"=="0" (
  echo Doctor reported blocking issues or warnings above. Fix them before launch.
)
pause
exit /b %DOCTOR_EXIT%
