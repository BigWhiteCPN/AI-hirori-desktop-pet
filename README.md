# AI Hiyori Desktop Pet

这是一个本地运行的 Live2D AI 桌宠项目。当前版本包含对话、语音输入、TTS、记忆、主动行为、日记/小说写作、小屋状态展示，以及城市点击地图。

## 快速启动

建议使用项目上一级已有的虚拟环境：

```powershell
cd E:\PythonProject1\pythonProject_1\person_test_all
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe .\persona_bot_test.py
```

也可以直接双击：

```text
run_persona_bot_test.bat
```

首次运行前，复制配置模板：

```powershell
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
```

然后在 `persona_llm_config.json` 中填写本地 API 配置，或使用环境变量。不要把 `persona_llm_config.json` 上传到 GitHub。

## 依赖

安装最小运行依赖：

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe -m pip install -r .\requirements_runtime.txt
```

浏览器自动化相关能力需要额外安装：

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe -m pip install -r .\requirements_browser_agent.txt
```

本项目依赖 `hiyori_pro_zh/` 中的 Live2D 运行资源。`third_party/` 下的本地语音模型和引擎通常体积较大，默认不建议提交。

## 主要快捷键

- `V` / `F2`：开启自由语音监听
- `N`：关闭自由语音监听
- `C`：聚焦输入框
- 点击小屋图标：进入她的小屋
- `K`：打开/关闭城市点击地图
- `F`：喂饭
- `D`：打开日记和小说书架
- `B`：打开记忆地图
- `M`：打开角色状态面板
- `J`：打开关系面板
- `I`：打开背包
- `Y`：打开小游戏
- `S` / `F3`：打开 API 设置
- `ESC`：退出程序

## 模块结构

- `persona_bot_test.py`：桌宠入口程序。
- `persona_pet/`：主要功能模块，包括渲染、对话、记忆、小屋、城市、经济、背包、阅读和行为面板。
- `assets/room/`：小屋模式背景和布局。当前背景来自 `E:\godot_game\2dworld\assets\backgrounds\room_base.png`。
- `assets/city_map/`：城市点击地图背景。
- `hiyori_pro_zh/`：Live2D 模型资源。
- `tools/`：本地维护工具，例如进度备份/恢复脚本。

## 小屋与地图

长时间没有互动时，Live2D 会切换成小屋图标；点击图标进入 Godot 小屋场景，双击场景里的苏念可回到 Live2D。`assets/room/room_layout.json` 只保留旧 Live2D 小屋布局数据。

城市地图只保留 `K` 打开的点击地图。可移动探索地图入口已移除。

## GitHub 上传前检查

这些是本地运行生成物，不要提交：

- `logs/`
- `outputs/`
- `user_data_backups/`
- `__pycache__/`
- `persona_llm_config.json`
- `third_party/` 中的大型本地模型或引擎
- 打包产物：`build/`、`dist/`、`dist_fixed/`

本次整理已把旧的本地生成物移到项目外：

```text
E:\PythonProject1\pythonProject_1\person_test_all_local_archive_20260511
```

## 进度备份

运行数据默认写入 `outputs/`。切换分支或更新代码前可以备份：

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe .\tools\persona_progress.py backup
```

查看和恢复备份：

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe .\tools\persona_progress.py list
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe .\tools\persona_progress.py restore user_data_backups\persona_progress_YYYYMMDD_HHMMSS.zip
```

只有明确需要时才使用 `--include-config`，因为配置文件可能包含 API 密钥。

## 常见问题

- Live2D 加载失败：确认 `hiyori_pro_zh/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json` 存在。
- 没有语音：检查 TTS 配置、本地引擎路径或云服务 API Key。
- 城市地图背景缺失：确认 `assets/city_map/background.png` 存在。
- 小屋图标没有出现：确认 `assets/room_icon/star_room_icon_256.png` 存在。
