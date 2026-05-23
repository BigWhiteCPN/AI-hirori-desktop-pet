"""City location dialogs: Farm, City Hall, Industrial Area."""

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
QLabel#statLabel {
    color: #6b4058;
    font: 10pt "Microsoft YaHei UI";
}
QLabel#valueLabel {
    color: #8f2d5a;
    font: 11pt "Microsoft YaHei UI";
    font-weight: 700;
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
QPushButton {
    min-height: 36px;
    padding: 6px 20px;
    border: 1px solid rgba(225, 135, 180, 210);
    border-radius: 8px;
    background: rgba(255, 240, 248, 245);
    color: #8f2d5a;
    font-weight: 600;
    font-size: 11pt;
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
"""


class FarmWorkDialog(QDialog):
    COOLDOWN = 300.0

    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.pet = parent_pet
        self.setWindowTitle("农场")
        self.setModal(True)
        self.resize(400, 320)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._update_cooldown()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("\U0001f33e  农场打工")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        desc = QLabel("在农场帮忙干活，赚取金币。\n每次打工后需要休息5分钟。")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #6b4058; font: 10pt;")
        root.addWidget(desc)

        info_group = QGroupBox("打工信息")
        info_layout = QVBoxLayout(info_group)

        self.reward_label = QLabel(f"每次奖励: 15 金币")
        self.reward_label.setObjectName("valueLabel")
        info_layout.addWidget(self.reward_label)

        self.energy_label = QLabel("体力消耗: 疲劳+8, 饥饿+5")
        self.energy_label.setObjectName("statLabel")
        info_layout.addWidget(self.energy_label)

        self.cooldown_label = QLabel("")
        self.cooldown_label.setStyleSheet("color: #d4780a; font-weight: 600;")
        info_layout.addWidget(self.cooldown_label)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setStyleSheet("color: #4a7a5a; font: 11pt; font-weight: 600;")
        info_layout.addWidget(self.result_label)

        root.addWidget(info_group)

        self.work_btn = QPushButton("开始打工")
        self.work_btn.clicked.connect(self._do_work)
        root.addWidget(self.work_btn)

        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self._update_cooldown)
        self.cooldown_timer.start(1000)

    def _update_cooldown(self):
        econ = getattr(self.pet, 'economy', None)
        if not econ:
            self.work_btn.setEnabled(False)
            self.cooldown_label.setText("经济系统未初始化")
            return
        elapsed = time.monotonic() - econ.last_farm_work_at
        if elapsed >= self.COOLDOWN:
            self.work_btn.setEnabled(True)
            self.cooldown_label.setText("可以打工")
            self.work_btn.setText("开始打工")
        else:
            remaining = self.COOLDOWN - elapsed
            self.work_btn.setEnabled(False)
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            self.cooldown_label.setText(f"休息中: {mins}分{secs}秒")
            self.work_btn.setText(f"休息中 ({mins}:{secs:02d})")

    def _do_work(self):
        econ = getattr(self.pet, 'economy', None)
        if not econ:
            return
        success, msg = econ.on_farm_work()
        if success:
            phys = getattr(self.pet, 'physiology', None)
            if phys:
                phys.adjust(fatigue=8.0, hunger=5.0)
            drive = getattr(self.pet, 'drive', None)
            if drive:
                drive.adjust(energy=-5.0, purpose=3.0)
            self.result_label.setText(f"✅ {msg}")
            self.pet.show_chat_status(msg, seconds=3.0)
        else:
            self.result_label.setText(f"⏳ {msg}")
        self._update_cooldown()


class CityHallDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.pet = parent_pet
        self.setWindowTitle("市政厅")
        self.setModal(True)
        self.resize(420, 400)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("\U0001f3db  市政厅 - 城市统计")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        econ_group = QGroupBox("经济统计")
        econ_layout = QVBoxLayout(econ_group)
        self.econ_labels = {}
        for key, label_text in [
            ("user_wallet", "你的金币"),
            ("char_wallet", "角色的金币"),
            ("total_earned", "累计收入"),
            ("total_spent", "累计支出"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("statLabel")
            val = QLabel("0")
            val.setObjectName("valueLabel")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addWidget(val)
            econ_layout.addLayout(row)
            self.econ_labels[key] = val
        root.addWidget(econ_group)

        life_group = QGroupBox("生活统计")
        life_layout = QVBoxLayout(life_group)
        self.life_labels = {}
        for key, label_text in [
            ("relationship", "关系阶段"),
            ("novel_chapters", "小说章节"),
            ("backpack_items", "背包物品"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("statLabel")
            val = QLabel("—")
            val.setObjectName("valueLabel")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addWidget(val)
            life_layout.addLayout(row)
            self.life_labels[key] = val
        root.addWidget(life_group)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn)

    def _refresh(self):
        econ = getattr(self.pet, 'economy', None)
        if econ:
            self.econ_labels["user_wallet"].setText(f"{econ.user_wallet:.0f}")
            self.econ_labels["char_wallet"].setText(f"{econ.character_wallet:.0f}")
            self.econ_labels["total_earned"].setText(f"{econ.total_earned:.0f}")
            self.econ_labels["total_spent"].setText(f"{econ.total_spent:.0f}")
        life = getattr(self.pet, 'life', None)
        if life:
            stage, _ = life.relationship_stage()
            self.life_labels["relationship"].setText(f"{stage} ({life.relationship_score:.0f}分)")
            novel = life.novel or {}
            chapters = novel.get("chapter", 0)
            self.life_labels["novel_chapters"].setText(str(chapters))
        bp = getattr(self.pet, 'backpack', None)
        if bp:
            all_items = bp.get_all_items()
            total = sum(q for _, q in all_items)
            self.life_labels["backpack_items"].setText(f"{total}件 ({len(all_items)}/{bp.capacity}格)")


class IndustrialAreaDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.setWindowTitle("工业区")
        self.setModal(True)
        self.resize(350, 220)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("\U0001f3ed  工业区")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        msg = QLabel("工业区正在建设中...\n\n未来的功能:\n- 合成系统：用原材料制作高级物品\n- 工厂打工：更高收入的打工方式\n- 产品交易：出售多余物品赚金币")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: #6b4058; font: 10pt; line-height: 150%;")
        msg.setWordWrap(True)
        root.addWidget(msg)

        close_btn = QPushButton("返回")
        close_btn.clicked.connect(self.close)
        root.addWidget(close_btn)
