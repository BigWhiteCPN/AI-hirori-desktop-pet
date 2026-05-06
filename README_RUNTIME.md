# person_test_all 运行包

这个文件夹是从 `person_ai_memery` 中单独整理出来的运行包，用于运行当前 Live2D 桌宠对话测试程序。

## 启动

双击：

```bat
run_persona_bot_test.bat
```

或手动运行：

```powershell
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe E:\PythonProject1\pythonProject_1\person_test_all\persona_bot_test.py
```

## 已包含

- `persona_bot_test.py`：兼容入口脚本
- `persona_pet/`：拆分后的功能模块，包括记忆、LLM、语音、渲染、互动、状态系统等
- `persona_speech_input_once.py`：独立语音识别子进程，防止录音/Whisper 崩溃带崩主程序
- `persona_llm_config.json`：DeepSeek/OpenAI-compatible 配置
- `hiyori_pro_zh/`：Live2D 模型和动作文件
- `assets/room/`：小屋模式素材
- `outputs/`：运行时生成的记忆、语音、截图、日记/小说等输出目录

本地如果使用 VOICEVOX 或 faster-whisper，还需要对应的 `third_party/` 资源；这些通常不提交到 GitHub。

## 运行前提

当前启动脚本默认使用上级目录的虚拟环境：

```text
E:\PythonProject1\pythonProject_1\.venv
```

如果换电脑或换环境，请先安装 `requirements_runtime.txt` 中的依赖。

## 操作

- `V / F2`：开启自由语音监听
- `N`：关闭自由语音监听
- `C`：聚焦顶部输入框
- 顶部输入框：备用文字输入，回车发送
- `B`：打开脑内记忆地图
- `M`：打开角色状态面板
- `Y`：打开小游戏
- `O`：打开/关闭小屋模式
- `Ctrl+O`：重新读取小屋素材
- `G`：截图聊天记录并让角色给建议
- `F`：喂饭
- `H`：摸头
- `S / F3`：打开 API 设置
- `1~8`：切换测试文本
- `SPACE`：只切换情绪
- `ENTER`：模拟角色说当前测试句
- `L`：按监听者模式逐句测试
- `P`：按说话者模式逐句测试
- `R`：随机待机动作
- `ESC`：退出

DeepSeek API key 会在首次启动时弹窗输入，并写入 `persona_llm_config.json`；如果已设置环境变量 `DEEPSEEK_API_KEY`，则不会弹窗。

语音识别默认优先使用豆包/火山 ASR。首次启动会额外弹窗输入豆包语音识别 API Key，并写入同一个 `persona_llm_config.json`；如果取消输入，会自动改回本地 Whisper。也可以用环境变量：

```powershell
$env:DOUBAO_ASR_API_KEY="你的豆包语音识别APIKey"
```

VOICEVOX/火山 TTS 相关参数在 API 设置面板里配置，结果会写入 `persona_llm_config.json`。

轻量唱歌模式默认开启。用户说“唱歌 / 唱一首 / 哼一段”等请求时，程序会改用单独的唱歌渲染分支：如果 `persona_llm_config.json` 里配置了 `singing_provider: "external"` 和 `singing_external_command`，会优先调用外部 OpenUtau/DiffSinger 渲染命令；否则使用内置的 VOICEVOX 旋律化 fallback。

本地回退识别使用 `faster-whisper base`。如果已经下载了更大的模型，可以用环境变量切换，例如：

```powershell
$env:PERSONA_SPEECH_MODEL="small"
E:\PythonProject1\pythonProject_1\.venv\Scripts\python.exe E:\PythonProject1\pythonProject_1\person_test_all\persona_bot_test.py
```
