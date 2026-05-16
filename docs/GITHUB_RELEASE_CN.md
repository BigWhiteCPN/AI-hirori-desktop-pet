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

当前 `.gitignore` 已经覆盖这些目录。上传前可以执行：

```powershell
git status --short --ignored
```

其中以 `!!` 开头的 `outputs/`、`logs/`、`persona_llm_config.json` 等就是被正确忽略的本地文件。

## 新用户运行方式

1. 克隆仓库并进入项目目录：

```powershell
git clone <your-repo-url>
cd person_test_all
```

2. 创建虚拟环境并安装依赖：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
```

浏览器代理能力是可选项：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

3. 复制发布配置：

```powershell
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
```

4. 选择一种模型配置方式。

API 模型：

- 设置环境变量 `DEEPSEEK_API_KEY`，或在右键/API 设置里填写 API Key。
- 默认 `base_url` 是 `https://api.deepseek.com`，模型名可在 `persona_llm_config.json` 里调整。
- 如使用火山/豆包语音，设置 `DOUBAO_ASR_API_KEY` 和 `VOLCENGINE_TTS_API_KEY`。

本地 TTS 模型：

- 把模型权重放到本机路径，例如 `third_party/qwen_tts_model/`。
- 把参考音频和文本放到 `third_party/qwen_tts_refs/neutral.wav` 与 `neutral.txt`，或在 API 设置里填写自定义路径。
- 在 `persona_llm_config.json` 中把 `tts_provider` 改为 `local`，并设置 `qwen_tts_model_path`。
- 模型权重通常很大，不建议直接提交到 GitHub；需要发布时优先写下载链接或使用 Git LFS。

5. 启动：

```powershell
.\.venv\Scripts\python.exe .\persona_bot_test.py
```

也可以双击 `run_persona_bot_test.bat`。

## 上传前检查

```powershell
git status --short
git diff -- .gitignore persona_llm_config.release.json persona_pet/llm_config.py persona_pet/godot_bridge.py
git add .gitignore .env.example persona_llm_config.release.json persona_pet/llm_config.py persona_pet/godot_bridge.py docs/GITHUB_RELEASE_CN.md
git status --short
```

确认 `persona_llm_config.json`、`persona_llm_config.test.json`、`outputs/`、`logs/` 没有出现在待提交列表里，再提交和推送。
