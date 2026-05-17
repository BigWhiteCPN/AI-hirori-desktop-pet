# AI Hiyori Desktop Pet

这是一个本地运行的 Live2D AI 桌宠项目，包含对话、语音输入、TTS、记忆、主动行为、小屋模式和城市地图。

项目目录可以放在任意盘符、任意路径，不要求放在固定目录。仓库内默认只使用相对路径；如果你需要接入外部工具或外部项目，再把那些机器专属路径写到你自己的 `persona_llm_config.json`。

## 新用户最快上手

1. 克隆仓库
2. 双击 `setup_persona_bot_test.bat`
3. 按提示填写 `persona_llm_config.json`
4. 双击 `run_persona_bot_test.bat`

命令行方式：

```powershell
git clone https://github.com/BigWhiteCPN/AI-hirori-desktop-pet.git
cd AI-hirori-desktop-pet
.\setup_persona_bot_test.bat
.\run_persona_bot_test.bat
```

`setup_persona_bot_test.bat` 会做这些事：

- 创建 `.venv`
- 安装 `requirements_runtime.txt`
- 如果缺少 `persona_llm_config.json`，就从 `persona_llm_config.release.json` 复制一份
- 运行 `tools/doctor.py` 做环境预检

## 手动启动

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
.\.venv\Scripts\python.exe .\tools\doctor.py
.\.venv\Scripts\python.exe .\persona_bot_test.py --profile main
```

说明：

- GitHub 发布场景默认使用 `main` profile
- 首次运行主要读取的是 `persona_llm_config.json`
- 如果你要做多 profile 调试，再显式使用 `--profile test` 或 `PERSONA_RUN_PROFILE=test`

## 首次配置

默认配置是 API 模式。你可以二选一：

- 在 `persona_llm_config.json` 中填写 `api_key`
- 设置环境变量 `DEEPSEEK_API_KEY`

如果要使用豆包/火山语音服务，再设置：

- `DOUBAO_ASR_API_KEY`
- `VOLCENGINE_TTS_API_KEY`

`.env.example` 里保留了这些环境变量名，便于参考。

## 路径规则

为了让别人从 GitHub 下载后更容易使用，仓库现在遵循下面几条规则：

- 文档和脚本优先使用相对路径
- 项目内资源默认相对于仓库根目录解析
- `third_party/...`、`assets/...`、`.\...`、`..\...` 这类配置路径都可以跨电脑迁移
- 外部程序路径，比如 Tesseract、Godot，可留空或写到你自己的本地配置里
- 不要把你机器上的绝对路径提交到 README、模板配置或脚本

## 本地 TTS

项目里的本地 TTS 使用 `faster-qwen3-tts`，底层模型是 Qwen3-TTS。

推荐两种写法：

- 远程模型 ID：`Qwen/Qwen3-TTS-12Hz-1.7B-Base`
- 项目内相对路径：`third_party/qwen_tts_model`

如果你使用项目内默认目录，下面这些字段都可以写相对路径：

- `qwen_tts_model_path`
- `qwen_tts_ref_dir`
- `qwen_tts_ref_audio`
- `qwen_tts_ref_text`

默认参考文件位置：

- `third_party/qwen_tts_refs/neutral.wav`
- `third_party/qwen_tts_refs/neutral.txt`

本地 TTS 不是零门槛 CPU 模式。通常至少需要：

- Python 3.10+
- PyTorch 2.5.1+
- NVIDIA GPU
- 可用的 CUDA 环境

## 本地语音识别

这个项目的语音识别有两种模式：

- 云端模式：`speech_provider = "doubao"`，默认值，不需要下载本地识别模型
- 本地模式：`speech_provider = "local"`，使用 `FunASR + SenseVoiceSmall`

切到本地模式后，模型会在首次使用时自动下载和缓存。

## 可选功能依赖

浏览器代理不是默认必需项：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

`tools/doctor.py` 会额外提示这些可选能力是否可用：

- browser agent
- OCR / 截图问答
- keyring 凭据存储
- 本地 TTS
- 本地 ASR

## 常用命令

```powershell
.\setup_persona_bot_test.bat
.\run_persona_bot_test.bat
.\.venv\Scripts\python.exe .\tools\doctor.py
.\.venv\Scripts\python.exe .\persona_bot_test.py --profile main
.\.venv\Scripts\python.exe -m compileall persona_bot_test.py persona_pet
```

## 目录说明

- `persona_bot_test.py`：程序入口
- `persona_pet/`：桌宠主要功能模块
- `assets/room/`：小屋背景和布局
- `assets/city_map/`：城市地图资源
- `assets/room_icon/`：小屋图标资源
- `hiyori_pro_zh/`：Live2D 模型资源
- `tools/doctor.py`：环境预检
- `tools/`：本地维护工具

## 键位

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

- 双击启动脚本报缺环境：先运行 `setup_persona_bot_test.bat`
- 改了 `persona_llm_config.json` 但程序没读到：请确认你是用 `--profile main` 启动
- 本地 TTS 找不到模型：检查 `qwen_tts_model_path` 是远程模型 ID，还是项目内相对路径
- OCR 不可用：安装 Tesseract，或在配置里填写 `tesseract_cmd`
- Live2D 加载失败：确认 `hiyori_pro_zh/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json` 存在
