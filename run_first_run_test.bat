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

if not exist "%ROOT%persona_llm_config.release.json" (
  echo Missing persona_llm_config.release.json
  pause
  exit /b 1
)

echo Launching isolated first-run test profile...
echo Profile: onboarding_test
echo This will not touch your normal main/test memory.
echo.
"%PYTHON%" "%ROOT%persona_bot_test.py" --profile onboarding_test --reset-profile
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo App exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
