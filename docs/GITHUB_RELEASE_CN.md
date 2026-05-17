# GitHub 发布与本地配置说明

这份说明用于把项目上传到 GitHub，同时尽量减少新用户下载后的环境配置成本。

## 推荐保留到仓库里的内容

- 源码：`persona_bot_test.py`、`persona_pet/`、`tools/`、`tests/`
- 文档：`README.md`、`README_RUNTIME.md`、`RELEASE_USAGE.txt`、`docs/`
- 轻量资源：`assets/`、`hiyori_pro_zh/`
- 依赖清单：`requirements_runtime.txt`、`requirements_browser_agent.txt`
- 配置模板：`persona_llm_config.release.json`、`.env.example`
- 启动脚本：`setup_persona_bot_test.bat`、`run_persona_bot_test.bat`

## 不要上传

- 本地运行数据：`outputs/`、`logs/`、`user_data_backups/`
- 本地配置和密钥：`persona_llm_config.json`、`persona_llm_config.test.json`、`.env`
- 大模型和第三方引擎：`third_party/`、`.venv/`
- 打包产物和缓存：`build/`、`dist/`、`__pycache__/`、`Microsoft/`

## 路径原则

- 仓库内默认使用相对路径
- 不在 README、脚本、模板配置里写死你机器上的绝对路径
- 项目内资源路径默认相对于仓库根目录解析
- 外部工具路径只留在本地 `persona_llm_config.json`

## 新用户建议流程

```powershell
git clone https://github.com/BigWhiteCPN/AI-hirori-desktop-pet.git
cd AI-hirori-desktop-pet
.\setup_persona_bot_test.bat
.\run_persona_bot_test.bat
```

## 默认 profile

GitHub / 新用户场景默认使用 `main` profile：

- 启动读取 `persona_llm_config.json`
- 如需调试独立配置，再手动使用 `--profile test`

## 自检建议

```powershell
.\.venv\Scripts\python.exe .\tools\doctor.py
git status --short --ignored
```

确认这些内容没有出现在待提交列表里，再推送：

- `persona_llm_config.json`
- `persona_llm_config.test.json`
- `outputs/`
- `logs/`
- `third_party/`
