# AI Hirori Desktop Pet

Live2D desktop pet prototype with LLM chat, speech input, TTS, memory, proactive behavior, life-writing, and simple internal drive states.

## What is included

- `persona_bot_test.py` - main desktop pet application.
- `persona_speech_input_once.py` - isolated speech-recognition helper process.
- `hiyori_pro_zh/` - Live2D runtime assets required by the app.
- `persona_llm_config.release.json` - safe configuration template.
- `requirements_runtime.txt` - minimal runtime dependency list used by this project snapshot.
- `run_persona_bot_test.bat` - local launcher for the original development layout.

## What is not included

Large or local-only runtime artifacts are intentionally excluded:

- `third_party/` local VOICEVOX and faster-whisper assets.
- `outputs/` memory, generated voice, diary, and novel files.
- `logs/` runtime logs.
- `build/` and `dist_fixed/` PyInstaller artifacts.
- `persona_llm_config.json` local config with real API keys.

The removed local files were archived outside this repository at `E:\PythonProject1\person_test_all_old` on the original development machine.

## Configuration

Copy the release template before local use:

```powershell
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
```

Then fill keys locally or use environment variables:

```powershell
$env:DEEPSEEK_API_KEY="your_key"
$env:DOUBAO_ASR_API_KEY="your_key"
```

Do not commit `persona_llm_config.json`.

## Run

Original local layout:

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe E:\PythonProject1\pythonProject_1\person_test_all\persona_bot_test.py
```

Or:

```powershell
.\run_persona_bot_test.bat
```

## Notes

This is an experimental local desktop pet project. Some features depend on local assets and external services that are not committed to GitHub.
