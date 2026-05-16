# person_test_all 运行说明

这个目录是桌宠项目的可运行工作区，入口文件是 `persona_bot_test.py`。

项目可以放在任意路径，不要求固定盘符。

## 运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\persona_bot_test.py
```

或运行 `run_persona_bot_test.bat`。

## 首次配置

- API 模型：填写 `persona_llm_config.json`，或设置 `DEEPSEEK_API_KEY`
- 本地 TTS：把 `tts_provider` 改成 `local`
- 如果使用默认项目目录结构，本地 TTS 模型放在 `third_party/qwen_tts_model/`
- 参考音频和文本放在 `third_party/qwen_tts_refs/neutral.wav` 与 `neutral.txt`
- 本地 TTS 按 `faster-qwen3-tts` 官方说明需要 Python 3.10+、PyTorch 2.5.1+、NVIDIA GPU 和 CUDA
- 语音识别默认是 `speech_provider = "doubao"`，不需要下载本地识别模型
- 如果改成 `speech_provider = "local"`，项目会在首次使用时自动下载并缓存 `SenseVoiceSmall` 相关模型

## 必要文件

- `hiyori_pro_zh/`：Live2D 模型
- `persona_pet/`：功能模块
- `assets/room/`：小屋背景和布局
- `assets/city_map/`：城市地图背景
- `persona_llm_config.release.json`：发布模板配置

## 本地模型下载

Hugging Face CLI：

```powershell
.\.venv\Scripts\python.exe -m pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base --local-dir .\third_party\qwen_tts_model
```

ModelScope：

```powershell
.\.venv\Scripts\python.exe -m pip install -U modelscope
modelscope download --model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir .\third_party\qwen_tts_model
```

## 本地生成物

这些目录会在运行时自动生成，不适合提交：

- `logs/`
- `outputs/`
- `user_data_backups/`
- `__pycache__/`
