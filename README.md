# AI Hiyori Desktop Pet

这是一个本地运行的 Live2D AI 桌宠项目，包含对话、语音输入、TTS、记忆、主动行为、小屋模式和城市地图。

当前更适合的运行平台：

- Windows
- Python 3.10+
- 能联网访问你配置的模型 / 语音服务

项目目录可以放在任意盘符、任意路径，不要求放在固定目录。仓库内默认只使用相对路径；如果你需要接入外部工具或外部项目，再把那些机器专属路径写到你自己的 `persona_llm_config.json`。

## 第一次接触时先看这个

如果我是第一次接触这个项目，我会先这样判断自己能不能跑：

- 只有 Windows + DeepSeek key，没有 GPU：可以先跑文本对话，但想要稳定语音体验，最好再配 `VOLCENGINE_TTS_API_KEY`
- 有 Windows + NVIDIA GPU + CUDA：可以走本地 TTS / 本地 ASR
- 想用 browser agent：除了安装 Python 包，还要执行 `playwright install chromium`
- 想用 OCR 截图问答：除了 Python 包，还要安装系统级 Tesseract

最省事的首次体验路径：

1. 在 Windows 上克隆仓库
2. 运行 `setup_persona_bot_test.bat`
3. 先至少准备 `DEEPSEEK_API_KEY`
4. 如果你没有本地 GPU TTS 环境，再额外准备 `VOLCENGINE_TTS_API_KEY`
5. 运行 `run_persona_bot_test.bat`

## 功能矩阵

| 你的条件 | 推荐配置 | 能力范围 |
| --- | --- | --- |
| 只有 API 文本能力 | `DEEPSEEK_API_KEY` | 可用对话主链路；语音相关体验不完整 |
| 想要最稳的首次体验 | `DEEPSEEK_API_KEY` + `VOLCENGINE_TTS_API_KEY` | 对话 + 云端语音合成 |
| 想用云端语音识别 | 再加 `DOUBAO_ASR_API_KEY` | 自由语音监听 / 云端 ASR |
| 有 NVIDIA GPU + CUDA | 安装本地 TTS / ASR 依赖 | 本地 TTS、本地 ASR |
| 想用聊天截图问答 | 安装 OCR 依赖 + Tesseract | OCR / 聊天截图分析 |
| 想用 browser agent | 安装 browser 依赖 + Chromium | 浏览器代理 |

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
- 安装 `requirements_core.txt`
- 如果缺少 `persona_llm_config.json`，就从 `persona_llm_config.release.json` 复制一份
- 运行 `tools/doctor.py` 做环境预检

## 手动启动

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_core.txt
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

如果要使用云端语音服务，再设置：

- `VOLCENGINE_TTS_API_KEY`
- `DOUBAO_ASR_API_KEY`

`.env.example` 里保留了这些环境变量名，便于参考。

## 依赖分层

最小可运行依赖：

- `requirements_core.txt`

扩展能力依赖：

- `requirements_local_tts.txt`：本地 TTS
- `requirements_local_asr.txt`：本地 ASR
- `requirements_ocr.txt`：OCR Python 依赖
- `requirements_memory.txt`：向量记忆检索
- `requirements_browser_agent.txt`：browser agent
- `requirements_desktop_optional.txt`：桌面凭据存储等可选能力

兼容旧的一次性重安装方式：

- `requirements_runtime.txt`

## 路径规则

为了让别人从 GitHub 下载后更容易使用，仓库现在遵循下面几条规则：

- 文档和脚本优先使用相对路径
- 项目内资源默认相对于仓库根目录解析
- `third_party/...`、`assets/...`、`.\...`、`..\...` 这类配置路径都可以跨电脑迁移
- 外部程序路径，比如 Tesseract、Godot，可留空或写到你自己的本地配置里
- 不要把你机器上的绝对路径提交到 README、模板配置或脚本

## 本地 TTS

项目里的本地 TTS 使用 `faster-qwen3-tts`，底层模型是 Qwen3-TTS。

安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_local_tts.txt
```

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

安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_local_asr.txt
```

切到本地模式后，模型会在首次使用时自动下载和缓存。

## OCR / 聊天截图问答

Python 依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_ocr.txt
```

另外还需要：

- 在 Windows 安装 Tesseract
- 如果自动检测不到，再在 `persona_llm_config.json` 里填写 `tesseract_cmd`

## Browser Agent

浏览器代理不是默认必需项：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 自检

`tools/doctor.py` 会额外提示这些可选能力是否可用：

- browser agent
- OCR / 截图问答
- keyring 凭据存储
- 本地 TTS
- 本地 ASR

常用命令：

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

## 许可证提醒

仓库目前还没有单独放出顶层 `LICENSE`。原因不是忘了，而是仓库里带了 `hiyori_pro_zh` 这类第三方素材；在给整个仓库落许可证前，需要先确认这些素材的再分发边界和是否要拆分授权说明。

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
- browser agent 仍然打不开：安装完 Python 包后，再执行 `python -m playwright install chromium`
- 本地 TTS 找不到模型：检查 `qwen_tts_model_path` 是远程模型 ID，还是项目内相对路径
- OCR 不可用：安装 Tesseract，或在配置里填写 `tesseract_cmd`
- Live2D 加载失败：确认 `hiyori_pro_zh/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json` 存在
