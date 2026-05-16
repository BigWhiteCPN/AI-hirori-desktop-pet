# person_test_all 运行说明

这个目录是桌宠项目的可运行工作区。入口文件是 `persona_bot_test.py`。

## 运行

```powershell
cd E:\PythonProject1\pythonProject_1\person_test_all
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe .\persona_bot_test.py
```

或运行 `run_persona_bot_test.bat`。

## 必要文件

- `hiyori_pro_zh/`：Live2D 模型
- `persona_pet/`：功能模块
- `assets/room/`：小屋背景和布局，当前背景来自 Godot 小屋画面
- `assets/city_map/`：城市点击地图背景
- `persona_llm_config.release.json`：配置模板

## 首次配置

```powershell
Copy-Item .\persona_llm_config.release.json .\persona_llm_config.json
```

填写 API Key 后再运行。`persona_llm_config.json` 是本机私有文件，不要提交。

## 常用快捷键

- 点击小屋图标：进入她的小屋
- `K`：城市点击地图
- `D`：书架
- `S` / `F3`：API 设置
- `ESC`：退出

## 本地生成物

这些目录会在运行时自动生成，不适合提交：

- `logs/`
- `outputs/`
- `user_data_backups/`
- `__pycache__/`

本次整理已把旧内容归档到：

```text
E:\PythonProject1\pythonProject_1\person_test_all_local_archive_20260511
```
