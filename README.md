# AI Hirori Desktop Pet

Live2D desktop pet prototype with LLM chat, speech input, TTS, memory, proactive behavior, life-writing, and simple internal drive states.

## What is included

- `persona_bot_test.py` - main desktop pet application.
- `persona_pet/` - shared package modules for memory, safe file/browser helpers, lexicons, and prompt contracts.
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

## Local progress and privacy

Runtime progress is private and should not be committed:

- `outputs/memory/` - memories, relationship state, heart state, user profile.
- `outputs/life/` - diaries and novels.
- `persona_llm_config.json` - local API keys and service settings.
- `logs/`, screenshots, generated voice files.

These paths are ignored by git. Before updating code or switching branches, back up progress outside the repo:

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe tools\persona_progress.py backup
```

Backups are written to `user_data_backups/` by default. This folder is ignored by git, so it will not be committed. This backs up only memory and life progress, not API keys. For a safer long-term copy, pass `--backup-root` to write to an external disk or cloud folder.

Useful commands:

```powershell
# List backups
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe tools\persona_progress.py list

# Restore progress without overwriting existing files
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe tools\persona_progress.py restore user_data_backups\persona_progress_YYYYMMDD_HHMMSS.zip

# Restore and overwrite current local progress
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe tools\persona_progress.py restore user_data_backups\persona_progress_YYYYMMDD_HHMMSS.zip --force
```

Only use `--include-config` if you intentionally want to back up or restore `persona_llm_config.json`, because it may contain API keys.

## Code layout

`persona_bot_test.py` is still the compatible entry point. New standalone code should go under `persona_pet/` first, then be imported by the entry script. This keeps the app runnable while the original prototype file is gradually split into smaller modules.

Current extracted modules:

- `persona_pet/memory.py` - memory storage, retrieval, text cleanup, and boundary query helpers.
- `persona_pet/file_agent.py` - constrained local folder/docx/pptx creation.
- `persona_pet/browser_agent.py` - constrained browser automation wrapper.
- `persona_pet/agent_commands.py` - file/browser agent command confirmation mixin.
- `persona_pet/behavior.py` - emotion analysis, motion selection, Live2D parameter composition, and behavior controller.
- `persona_pet/llm_client.py` - LLM HTTP calls, reply parsing, retry fallback, and async chat events.
- `persona_pet/llm_config.py` - LLM and speech service defaults plus config file load/save helpers.
- `persona_pet/chat_advice.py` - chat screenshot OCR analysis controller and related PyQt UI.
- `persona_pet/chat_capture.py` - chat screenshot capture mixin.
- `persona_pet/heart.py` - INFP heart module, mood/status strip, and autonomous memory reflection that can write self-thoughts back into memory.
- `persona_pet/library_dialogs.py` - bookshelf UI for browsing generated diaries and novels.
- `persona_pet/life_system.py` - drive state, relationship state, interactions, diary/novel quotas.
- `persona_pet/life_writing.py` - background diary and novel writing controller.
- `persona_pet/pet_dialogue.py` - keyboard dialogue test and sentence playback mixin.
- `persona_pet/pet_interactions.py` - feed/pat/minigame reward feedback mixin.
- `persona_pet/pet_render.py` - Live2D rendering, subtitle bubble, resize, and drag handling mixin.
- `persona_pet/pet_workflow.py` - chat, speech input, memory writes, proactive chat, and voice-event workflow mixin.
- `persona_pet/physiology.py` - non-explicit body needs such as hunger, thirst, fatigue, sleepiness, comfort, stress, and closeness need.
- `persona_pet/room_mode.py` - room-mode layout, activity selection, and drawing mixin.
- `persona_pet/speech.py` - speech-input helper process wrapper, text cleanup, and barge-in monitor.
- `persona_pet/status_dialogs.py` - memory graph and drive status PyQt dialogs.
- `persona_pet/ui_dialogs.py` - low-coupling PyQt dialogs such as API settings and mini games.
- `persona_pet/user_profile.py` - heuristic user MBTI/profile estimator for adaptive reply behavior.
- `persona_pet/voicevox.py` - VOICEVOX/Volcengine TTS synthesis, playback events, and voice prosody helpers.
- `persona_pet/lexicon.py` - built-in relationship and boundary lexicons.
- `persona_pet/prompts.py` - LLM output-format prompt contracts.

## Controls

- `O` - toggle room mode. The room shows her current idle life state, such as writing, resting, walking, playing, or waiting.
- `Ctrl+O` - reload room assets and `assets/room/room_layout.json`.
- `D` - open the diary and novel bookshelf.
- `P` - intimacy cheat code: set the relationship to the highest intimacy stage.
- `R` - trigger a random idle motion.
- `ESC` - exit.

## Notes

This is an experimental local desktop pet project. Some features depend on local assets and external services that are not committed to GitHub.
