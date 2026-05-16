# AI Hiyori Desktop Pet

这是一个本地运行的 Live2D AI 桌宠项目，包含对话、语音输入、TTS、记忆、主动行为、小屋模式和城市地图。

项目目录可以放在任意盘符、任意路径，不要求放在 `E:` 盘。

## 快速开始

```powershell
git clone https://github.com/BigWhiteCPN/AI-hirori-desktop-pet.git
cd AI-hirori-desktop-pet
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\persona_bot_test.py
```

浏览器代理相关依赖是可选项：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

也可以直接双击 `run_persona_bot_test.bat`。

## API 模型

默认配置是 API 模型模式。

你可以二选一：

- 在 `persona_llm_config.json` 中填写 `api_key`
- 设置环境变量 `DEEPSEEK_API_KEY`

如果要使用豆包/火山语音服务，再设置：

- `DOUBAO_ASR_API_KEY`
- `VOLCENGINE_TTS_API_KEY`

## 本地模型

项目里的本地 TTS 使用 `faster-qwen3-tts`，底层模型是 Qwen3-TTS。当前最适合这个项目的入门选项是 `Qwen/Qwen3-TTS-12Hz-0.6B-Base`，它支持参考音频语音克隆。

本地 TTS 不是“零门槛 CPU 模式”。按 `faster-qwen3-tts` 官方说明，它至少需要 Python 3.10+、PyTorch 2.5.1+、NVIDIA GPU 和 CUDA。

### 方案一：首次运行时自动下载

如果你的电脑可以访问 Hugging Face，可以在 `persona_llm_config.json` 里设置：

```json
{
  "tts_provider": "local",
  "qwen_tts_model_path": "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
}
```

这样第一次加载本地 TTS 时会按模型名下载权重。

### 方案二：手动下载到项目目录

如果你希望手动管理模型，推荐放到项目默认路径，这样配置里可以少填很多内容。

Hugging Face CLI：

```powershell
.\.venv\Scripts\python.exe -m pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base --local-dir .\third_party\qwen_tts_model
```

ModelScope：

```powershell
.\.venv\Scripts\python.exe -m pip install -U modelscope
modelscope download --model Qwen/Qwen3-TTS-12Hz-0.6B-Base --local_dir .\third_party\qwen_tts_model
```

然后准备参考音频和参考文本：

- `third_party/qwen_tts_refs/neutral.wav`
- `third_party/qwen_tts_refs/neutral.txt`

再把 `persona_llm_config.json` 里的 `tts_provider` 改成 `local` 即可。如果你使用上面的默认目录，`qwen_tts_model_path`、`qwen_tts_ref_dir`、`qwen_tts_ref_audio`、`qwen_tts_ref_text` 都可以继续留空。

### 参考音频要求

- 建议 3 到 15 秒
- 人声清晰，尽量无背景噪音
- `neutral.txt` 内容要和参考音频里说的话尽量一致

## 目录说明

- `persona_bot_test.py`：程序入口
- `persona_pet/`：桌宠主要功能模块
- `assets/room/`：小屋背景和布局
- `assets/city_map/`：城市地图资源
- `assets/room_icon/`：小屋图标资源
- `hiyori_pro_zh/`：Live2D 模型资源
- `tools/`：本地维护工具

## 常用操作

- `V` / `F2`：开启自由语音监听
- `N`：关闭自由语音监听
- `C`：聚焦输入框
- `K`：打开/关闭城市地图
- `D`：打开书架
- `B`：打开记忆图谱
- `M`：打开状态面板
- `S` / `F3`：打开 API 设置
- `ESC`：退出程序

## 不要上传到 GitHub

这些目录或文件是本地运行数据，不应该提交：

- `outputs/`
- `logs/`
- `user_data_backups/`
- `persona_llm_config.json`
- `persona_llm_config.test.json`
- `third_party/`
- `.venv/`

上传前可以检查：

```powershell
git status --short --ignored
```

## 常见问题

- 本地 TTS 无法加载：先确认已经安装 `requirements_runtime.txt`，再确认 `tts_provider` 是 `local`
- 本地 TTS 找不到模型：检查 `third_party/qwen_tts_model/` 是否存在，或确认 `qwen_tts_model_path` 是否填写为有效模型名/目录
- 本地 TTS 没声音：检查 `third_party/qwen_tts_refs/neutral.wav` 和 `neutral.txt`
- Live2D 加载失败：确认 `hiyori_pro_zh/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json` 存在
