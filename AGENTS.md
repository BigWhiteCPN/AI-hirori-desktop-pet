# Codex Project Notes

This repository is the local `person_test_all` AI desktop pet project. It is a stateful Windows desktop app, not a simple script collection.

## Run

```powershell
.\setup_persona_bot_test.bat
.\run_persona_bot_test.bat
```

Use `setup_persona_bot_test.bat` for first-run setup and `run_persona_bot_test.bat` as the checked launcher.

## Shape

- `persona_bot_test.py` is the composition root and main entry point.
- `persona_pet/` contains the runtime modules and mixins.
- `Live2DDesktopPet` combines PyQt5 `QOpenGLWidget`, Live2D rendering, LLM chat, memory, speech/TTS, Godot bridge, room/city modes, inventory/economy, and agent capabilities.
- `persona_llm_config*.json` is local configuration; do not commit secrets. Only `persona_llm_config.release.json` is intended for the repo.
- `requirements_core.txt` is the minimal install; local TTS/ASR/OCR/browser features have separate requirement files.
- `outputs/`, `logs/`, `user_data_backups/`, and `third_party/` are runtime/local data.

## Important Modules

- `persona_pet/llm_client.py`: LLM calls and structured reply parsing.
- `persona_pet/llm_config.py`: defaults and config persistence.
- `persona_pet/memory.py`, `episodic_memory.py`: memory systems.
- `persona_pet/behavior.py`, `pet_render.py`: emotion, motion, Live2D render parameters.
- `persona_pet/speech.py`, `voicevox.py`, `qwen_tts_engine.py`: speech input, TTS, playback.
- `persona_pet/godot_bridge.py`: external Godot JSON bridge.
- `persona_pet/file_agent.py`, `browser_agent.py`: higher-risk agent actions.
- `persona_pet/room_mode.py`, `city_mode.py`, `city_dialogs.py`, `economy.py`, `items.py`, `supermarket.py`: room/city/gameplay systems.

## Rules For Changes

- Inspect `git status --short` before editing; this repo commonly has user changes.
- Keep edits scoped to the subsystem being changed.
- Avoid blocking operations on Qt UI paths. Follow existing controller, timer, and callback patterns.
- Be conservative with machine-specific absolute paths in defaults.
- Do not delete or rewrite assets, generated outputs, model files, or third-party engines unless explicitly asked.
- Treat file/browser agent code, path handling, local config, and API keys as security-sensitive.
- Preserve current profile behavior unless asked. GitHub/new-user startup now defaults to `RUN_PROFILE = "main"`.

## Encoding Rules

- Treat `persona_bot_test.py` and related Python/UI files as `UTF-8`.
- Do not trust mojibake shown in PowerShell or `cmd.exe` as the real source text.
- Never paste terminal-rendered乱码 back into source files.
- Before editing Chinese strings, read the real file contents through an explicit `UTF-8` path.
- After changing Chinese UI text, scan for mojibake markers such as `鎸`, `濂`, `閸`, `鍏`, `锛`, `銆`, `€`.
- If those markers appear in edited lines, fix the source text immediately before making further changes.
- Prefer syntax-only validation for Python text repairs when writing `__pycache__` is blocked by the environment.

## Validation

For Python changes, start with:

```powershell
.\.venv\Scripts\python.exe -m compileall persona_bot_test.py persona_pet
```

For GUI, audio, Live2D, TTS, browser automation, or Godot bridge work, note what could not be fully verified without launching external/runtime components.
