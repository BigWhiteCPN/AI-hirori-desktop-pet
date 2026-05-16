# GitHub 发布与本地配置说明

这份说明用于把项目上传到 GitHub，同时避免提交本地记忆、密钥、模型权重和运行缓存。

## 推荐上传内容

- 源码：`persona_bot_test.py`、`persona_pet/`、`tools/`、`tests/`
- 运行说明：`README.md`、`README_RUNTIME.md`、`RELEASE_USAGE.txt`、`docs/`
- 轻量资源：`assets/`、`hiyori_pro_zh/`
- 依赖清单：`requirements_runtime.txt`、`requirements_browser_agent.txt`
- 示例配置：`persona_llm_config.release.json`、`.env.example`

## 不要上传

- 本地记忆和运行产物：`outputs/`、`logs/`、`user_data_backups/`
- 本地配置和密钥：`persona_llm_config.json`、`persona_llm_config.test.json`、`.env`
- 大模型和第三方本地引擎：`third_party/`、`.venv/`
- 打包产物和缓存：`build/`、`dist/`、`__pycache__/`、`Microsoft/`

## 路径原则

- 仓库不要写死 `<drive>:\...` 这类机器专属路径
- 文档命令优先使用相对路径，例如 `.\.venv\Scripts\python.exe`
- 本地专属路径放进 `persona_llm_config.json`，不要放进公开模板和 README

## 新用户运行方式

```powershell
git clone https://github.com/BigWhiteCPN/AI-hirori-desktop-pet.git
cd AI-hirori-desktop-pet
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\persona_bot_test.py
```

浏览器代理能力是可选项：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

## API 模型

- 设置环境变量 `DEEPSEEK_API_KEY`，或在 `persona_llm_config.json` 中填写 `api_key`
- 如使用豆包/火山语音服务，再设置 `DOUBAO_ASR_API_KEY` 和 `VOLCENGINE_TTS_API_KEY`

## 本地 TTS 模型

项目里的本地 TTS 基于 `faster-qwen3-tts`，`Qwen/Qwen3-TTS-12Hz-0.6B-Base` 和 `Qwen/Qwen3-TTS-12Hz-1.7B-Base` 都可以用。

环境前提：

- Python 3.10+
- PyTorch 2.5.1+
- NVIDIA GPU
- 可用的 CUDA 环境

### 自动下载

如果运行环境能访问 Hugging Face，可以直接在 `persona_llm_config.json` 中设置：

```json
{
  "tts_provider": "local",
  "qwen_tts_model_path": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
}
```

### 手动下载

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

参考来源：

- Qwen `qwen-tts` PyPI 页面提供了 Hugging Face / ModelScope 下载命令
- Hugging Face 模型页 `Qwen/Qwen3-TTS-12Hz-1.7B-Base` 说明了这个模型支持参考音频语音克隆

### 默认目录

如果按项目默认目录放置文件，可以少配很多参数：

- 模型目录：`third_party/qwen_tts_model/`
- 参考音频：`third_party/qwen_tts_refs/neutral.wav`
- 参考文本：`third_party/qwen_tts_refs/neutral.txt`

此时只需要把 `tts_provider` 改成 `local`，其余本地 TTS 路径字段可以继续留空。

## 本地语音识别

当前项目默认语音识别是云端豆包：

- `speech_provider = "doubao"`

这种模式不需要下载本地语音识别模型。

如果改成：

- `speech_provider = "local"`

项目会使用 `FunASR + iic/SenseVoiceSmall`，并在首次加载时自动下载并缓存相关模型文件。

当前代码这条本地 ASR 路径不是 `faster-whisper`。

## 上传前检查

```powershell
git status --short --ignored
```

确认 `persona_llm_config.json`、`persona_llm_config.test.json`、`outputs/`、`logs/`、`third_party/` 没有出现在待提交列表里，再提交和推送。
