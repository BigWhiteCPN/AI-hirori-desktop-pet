"""Behavior control panel dialog for PersonaPet."""

import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

DIALOG_STYLE = """
QDialog {
    background: #fff6fb;
    color: #543247;
    font: 10pt "Microsoft YaHei UI";
}
QLabel#titleLabel {
    color: #8f2d5a;
    font: 15pt "Microsoft YaHei UI";
    font-weight: 700;
}
QLabel#statusLabel {
    color: #6b4058;
    font: 10pt "Microsoft YaHei UI";
}
QPushButton {
    min-height: 38px;
    padding: 6px 18px;
    border: 1px solid rgba(225, 135, 180, 210);
    border-radius: 8px;
    background: rgba(255, 240, 248, 245);
    color: #8f2d5a;
    font-weight: 600;
    font-size: 10pt;
}
QPushButton:hover {
    background: #fce4f0;
    border: 1px solid #d85f9b;
}
QPushButton:pressed {
    background: #f8d0e2;
}
QPushButton:disabled {
    background: #f0e8ec;
    color: #b8a0ac;
    border: 1px solid #ddd0d6;
}
QPushButton#activeBtn {
    background: #f8d0e2;
    border: 2px solid #d85f9b;
    color: #8f2d5a;
}
QGroupBox {
    background: rgba(255, 255, 255, 210);
    border: 1px solid rgba(235, 144, 188, 210);
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 10px 12px;
    font-weight: 700;
    color: #8f2d5a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    background: #fff6fb;
}
"""


class BehaviorPanelDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.pet = parent_pet
        self.setWindowTitle("行为控制")
        self.setModal(False)
        self.resize(360, 520)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(1000)
        self._refresh_status()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        title = QLabel("\U0001f3ae 行为控制面板")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # Status
        status_group = QGroupBox("当前状态")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        root.addWidget(status_group)

        # Writing
        write_group = QGroupBox("写作")
        write_layout = QVBoxLayout(write_group)

        self.diary_btn = QPushButton("\U0001f4dd 写日记")
        self.diary_btn.setToolTip("让她写今天的日记")
        self.diary_btn.clicked.connect(lambda: self._do_action("diary"))
        write_layout.addWidget(self.diary_btn)

        self.novel_btn = QPushButton("\U0001f4d6 写小说")
        self.novel_btn.setToolTip("让她写小说章节，完成后赚金币")
        self.novel_btn.clicked.connect(lambda: self._do_action("novel"))
        write_layout.addWidget(self.novel_btn)
        root.addWidget(write_group)

        # Memory
        memory_group = QGroupBox("记忆")
        memory_layout = QVBoxLayout(memory_group)

        self.consolidate_btn = QPushButton("\U0001f9e0 整理记忆")
        self.consolidate_btn.setToolTip("让她整理和巩固记忆")
        self.consolidate_btn.clicked.connect(lambda: self._do_action("consolidate"))
        memory_layout.addWidget(self.consolidate_btn)

        self.reflect_btn = QPushButton("\U0001f4ad 反思")
        self.reflect_btn.setToolTip("让她反思最近的经历")
        self.reflect_btn.clicked.connect(lambda: self._do_action("reflect"))
        memory_layout.addWidget(self.reflect_btn)

        self.decay_btn = QPushButton("\U0001f5d1 清理遗忘")
        self.decay_btn.setToolTip("清理已经淡忘的记忆")
        self.decay_btn.clicked.connect(lambda: self._do_action("decay"))
        memory_layout.addWidget(self.decay_btn)
        root.addWidget(memory_group)

        # Interaction
        interact_group = QGroupBox("互动")
        interact_layout = QVBoxLayout(interact_group)

        self.feed_btn = QPushButton("\U0001f35e 喂饭")
        self.feed_btn.clicked.connect(lambda: self._do_action("feed"))
        interact_layout.addWidget(self.feed_btn)

        self.pat_btn = QPushButton("\U0001f4a7 摸头")
        self.pat_btn.clicked.connect(lambda: self._do_action("pat"))
        interact_layout.addWidget(self.pat_btn)
        root.addWidget(interact_group)

        # Close
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn)

    def _refresh_status(self):
        life = getattr(self.pet, 'life', None)
        drive = getattr(self.pet, 'drive', None)
        economy = getattr(self.pet, 'economy', None)
        writer = getattr(self.pet, 'life_writer', None)

        parts = []
        if life:
            stage, _ = life.relationship_stage()
            parts.append(f"关系: {stage}({life.relationship_score:.0f})")
        if drive:
            mood = drive.compute_mood()
            parts.append(f"心情: {mood}")
            parts.append(f"能量: {drive.values.get('energy', 0):.0f}")
        if economy:
            parts.append(f"你的金币: {economy.user_wallet:.0f}")
            parts.append(f"她的金币: {economy.character_wallet:.0f}")
        if writer:
            if writer.is_busy():
                parts.append("状态: 写作中...")

        self.status_label.setText("\n".join(parts) if parts else "系统未初始化")

        # Update button states
        busy = writer.is_busy() if writer else False
        self.diary_btn.setEnabled(not busy)
        self.novel_btn.setEnabled(not busy)

    def _do_action(self, action):
        if action == "diary":
            writer = getattr(self.pet, 'life_writer', None)
            if writer and not writer.is_busy():
                writer.write_async("diary")
                self.pet.show_chat_status("开始写日记...", seconds=3.0)

        elif action == "novel":
            writer = getattr(self.pet, 'life_writer', None)
            if writer and not writer.is_busy():
                writer.write_async("novel")
                self.pet.show_chat_status("开始写小说...", seconds=3.0)

        elif action == "consolidate":
            memory = getattr(self.pet, 'memory', None)
            if memory:
                try:
                    count = memory.consolidate_graph()
                    self.pet.show_chat_status(f"记忆整理完成，新增 {count} 条连线", seconds=3.0)
                except Exception as e:
                    self.pet.show_chat_status(f"整理失败: {e}", seconds=3.0)

        elif action == "reflect":
            heart = getattr(self.pet, 'heart', None)
            if heart:
                thought = heart.reflect(reason="manual")
                if thought:
                    self.pet.show_chat_status("反思完成", seconds=3.0)
                else:
                    self.pet.show_chat_status("暂时没有需要反思的", seconds=3.0)

        elif action == "decay":
            memory = getattr(self.pet, 'memory', None)
            if memory:
                removed = memory.decay_memories()
                self.pet.show_chat_status(f"清理了 {removed} 条淡忘的记忆", seconds=3.0)

        elif action == "feed":
            self.pet.interact_with_pet("feed")

        elif action == "pat":
            self.pet.interact_with_pet("pat")

        self._refresh_status()
