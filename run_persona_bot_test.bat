@echo off
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"
set PYTHON=%ROOT%\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
  set PYTHON=%ROOT%..\.venv\Scripts\python.exe
)

if not exist "%PYTHON%" (
  echo Virtual environment not found.
  echo Run setup_persona_bot_test.bat first.
  pause
  exit /b 1
)

if not exist "%ROOT%persona_llm_config.json" if exist "%ROOT%persona_llm_config.release.json" (
  copy /Y "%ROOT%persona_llm_config.release.json" "%ROOT%persona_llm_config.json" >nul
  echo Created persona_llm_config.json from release template.
)

"%PYTHON%" "%ROOT%tools\doctor.py" --quick
if errorlevel 1 (
  echo.
  echo Environment check failed. Fix the issues above or rerun setup_persona_bot_test.bat.
  pause
  exit /b 1
)

"%PYTHON%" "%ROOT%persona_bot_test.py" --profile main
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo App exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
