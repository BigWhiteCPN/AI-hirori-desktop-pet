# Room Assets

旧 Live2D 小屋模式资源目录。新小屋入口会在长时间未互动后显示 `assets/room_icon/star_room_icon_256.png`，点击图标进入 Godot 小屋场景。

当前 `background.png` 已替换为 Godot 项目里的小屋游戏画面：

```text
E:\godot_game\2dworld\assets\backgrounds\room_base.png
```

因此运行时不再额外绘制床、桌子、窗户、书架等分件家具，避免和整张背景里的家具重复。

当前使用的文件：

- `background.png` - Godot 小屋整图背景。
- `room_layout.json` - Live2D 角色在小屋各状态下的位置和缩放。

`activities` 控制 Live2D 角色在不同状态下的位置和缩放。坐标是归一化值，普通状态使用 `x`、`y`、`scale`；散步状态可使用 `x_min` 和 `x_max`。

如果运行时出现棋盘格，说明图片不是真透明 PNG。优先重新导出带 alpha 的 PNG；临时兜底可以在对应对象上加 `"remove_checkerboard": true`。
