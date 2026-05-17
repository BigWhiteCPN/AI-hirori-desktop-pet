# person_test_all 运行说明

这个目录是桌宠项目的可运行工作区，入口文件是 `persona_bot_test.py`。

## 推荐启动方式

首次运行：

```powershell
.\setup_persona_bot_test.bat
```

日常启动：

```powershell
.\run_persona_bot_test.bat
```

## 我第一次接触时会怎么跑

如果我是第一次接触这个项目，我会先走最小路径：

1. Windows 上克隆仓库
2. 跑 `setup_persona_bot_test.bat`
3. 至少准备 `DEEPSEEK_API_KEY`
4. 如果没有本地 GPU TTS 条件，再准备 `VOLCENGINE_TTS_API_KEY`
5. 用 `run_persona_bot_test.bat` 启动

这样比一开始就折腾本地 TTS / 本地 ASR / browser agent 更稳。

## 手动方式

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_core.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\tools\doctor.py
.\.venv\Scripts\python.exe .\persona_bot_test.py --profile main
```

## 首次配置

- API 模式：在 `persona_llm_config.json` 填 `api_key`，或设置 `DEEPSEEK_API_KEY`
- 云端语音合成：设置 `VOLCENGINE_TTS_API_KEY`
- 本地 TTS：把 `tts_provider` 改成 `local`，并安装 `requirements_local_tts.txt`
- 默认本地 TTS 模型目录：`third_party/qwen_tts_model/`
- 默认参考音频和文本：`third_party/qwen_tts_refs/neutral.wav`、`third_party/qwen_tts_refs/neutral.txt`
- 默认语音识别是 `speech_provider = "doubao"`
- 如果改成 `speech_provider = "local"`，还需要安装 `requirements_local_asr.txt`

## 依赖分层

- `requirements_core.txt`：最小运行依赖
- `requirements_local_tts.txt`：本地 TTS
- `requirements_local_asr.txt`：本地 ASR
- `requirements_ocr.txt`：OCR Python 依赖
- `requirements_memory.txt`：向量记忆检索
- `requirements_browser_agent.txt`：browser agent
- `requirements_desktop_optional.txt`：keyring 等可选桌面依赖
- `requirements_runtime.txt`：兼容旧的一次性安装入口

## 可选依赖

浏览器代理：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

OCR：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_ocr.txt
```

另外还需要系统级 Tesseract。

## 路径约定

- 仓库里的文档和脚本优先使用相对路径
- 项目内资源路径默认相对于仓库根目录
- 外部程序或外部项目路径只建议保存在你自己的 `persona_llm_config.json`

## 自检

```powershell
.\.venv\Scripts\python.exe .\tools\doctor.py
```

## 本地生成文件

这些目录会在运行时自动生成，不适合提交：

- `logs/`
- `outputs/`
- `user_data_backups/`
- `__pycache__/`
