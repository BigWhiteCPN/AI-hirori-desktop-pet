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

echo [3/4] Installing core dependencies...
"%VENV_PY%" -m pip install -U pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

"%VENV_PY%" -m pip install -r "%ROOT%requirements_core.txt"
if errorlevel 1 (
  echo Failed to install requirements_core.txt
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
echo Recommended cloud voice add-on:
echo   set DEEPSEEK_API_KEY=...
echo   set VOLCENGINE_TTS_API_KEY=...
echo.
echo Optional local TTS add-on:
echo   .\.venv\Scripts\python.exe -m pip install -r .\requirements_local_tts.txt
echo.
echo Optional local ASR add-on:
echo   .\.venv\Scripts\python.exe -m pip install -r .\requirements_local_asr.txt
echo.
echo Optional OCR add-on:
echo   .\.venv\Scripts\python.exe -m pip install -r .\requirements_ocr.txt
echo   Then install Tesseract on Windows.
echo.
echo Optional browser agent:
echo   .\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
echo   .\.venv\Scripts\python.exe -m playwright install chromium
echo.
if not "%DOCTOR_EXIT%"=="0" (
  echo Doctor reported blocking issues or warnings above. Fix them before launch.
)
pause
exit /b %DOCTOR_EXIT%
