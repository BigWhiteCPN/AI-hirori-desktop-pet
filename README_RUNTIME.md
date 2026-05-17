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

## 手动方式

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\tools\doctor.py
.\.venv\Scripts\python.exe .\persona_bot_test.py --profile main
```

## 首次配置

- API 模式：在 `persona_llm_config.json` 填 `api_key`，或设置 `DEEPSEEK_API_KEY`
- 本地 TTS：把 `tts_provider` 改成 `local`
- 默认本地 TTS 模型目录：`third_party/qwen_tts_model/`
- 默认参考音频和文本：`third_party/qwen_tts_refs/neutral.wav`、`third_party/qwen_tts_refs/neutral.txt`
- 默认语音识别是 `speech_provider = "doubao"`
- 如果改成 `speech_provider = "local"`，首次使用会自动下载本地识别模型

## 路径约定

- 仓库里的文档和脚本优先使用相对路径
- 项目内资源路径默认相对于仓库根目录
- 外部程序或外部项目路径只建议保存在你自己的 `persona_llm_config.json`

## 可选依赖

浏览器代理：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

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
