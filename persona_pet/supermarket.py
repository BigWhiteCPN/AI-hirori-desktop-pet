"""Supermarket and Backpack dialogs for PersonaPet."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from persona_pet.items import (
    CATEGORY_DRINK,
    CATEGORY_FOOD,
    CATEGORY_GIFT,
    CATEGORY_LABELS,
    ITEMS,
    get_all_categories,
    get_items_by_category,
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
QLabel#balanceLabel {
    color: #8f2d5a;
    font: 12pt "Microsoft YaHei UI";
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
    min-height: 32px;
    padding: 5px 16px;
    border: 1px solid rgba(225, 135, 180, 210);
    border-radius: 8px;
    background: rgba(255, 240, 248, 245);
    color: #8f2d5a;
    font-weight: 600;
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
QTabWidget::pane {
    border: 1px solid rgba(235, 144, 188, 180);
    border-radius: 8px;
    background: rgba(255, 255, 255, 200);
}
QTabBar::tab {
    min-width: 80px;
    min-height: 30px;
    padding: 5px 14px;
    margin-right: 2px;
    border: 1px solid rgba(225, 135, 180, 150);
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    background: #fff0f6;
    color: #8a6178;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #8f2d5a;
    border-bottom: 1px solid #ffffff;
}
QLabel#itemNameLabel {
    color: #8f2d5a;
    font: 12pt "Microsoft YaHei UI";
    font-weight: 700;
}
QLabel#itemDescLabel {
    color: #6b4058;
    font: 10pt "Microsoft YaHei UI";
}
QLabel#itemPriceLabel {
    color: #d4780a;
    font: 11pt "Microsoft YaHei UI";
    font-weight: 700;
}
QLabel#itemEffectLabel {
    color: #4a7a5a;
    font: 9pt "Microsoft YaHei UI";
}
"""


class ItemCard(QFrame):
    def __init__(self, item_def, quantity=0, parent=None):
        super().__init__(parent)
        self.item_def = item_def
        self.item_id = item_def["id"]
        self.setFixedSize(100, 90)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 230);
                border: 1px solid rgba(225, 180, 210, 180);
                border-radius: 8px;
            }
            QFrame:hover {
                background: #fce4f0;
                border: 1px solid #d85f9b;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        icon_label = QLabel(self._category_icon(item_def["category"]))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font: 20pt; border: none;")
        layout.addWidget(icon_label)

        name_label = QLabel(item_def["name"])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font: 9pt; font-weight: 600; color: #543247; border: none;")
        layout.addWidget(name_label)

        price_text = f"{item_def['price']:.0f}"
        if quantity > 0:
            price_text += f"  x{quantity}"
        price_label = QLabel(price_text)
        price_label.setAlignment(Qt.AlignCenter)
        price_label.setStyleSheet("font: 8pt; color: #d4780a; border: none;")
        layout.addWidget(price_label)

    def _category_icon(self, category):
        icons = {CATEGORY_FOOD: "\U0001f35e", CATEGORY_DRINK: "\U0001f95b", CATEGORY_GIFT: "\U0001f381"}
        return icons.get(category, "\U0001f4e6")


class SupermarketDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.pet = parent_pet
        self.setWindowTitle("超市")
        self.setModal(True)
        self.resize(520, 480)
        self.setStyleSheet(DIALOG_STYLE)
        self.selected_item = None
        self._build_ui()
        self.refresh_balance()
        self._select_first_item()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        title = QLabel("\U0001f6d2  超市")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self.balance_label = QLabel()
        self.balance_label.setObjectName("balanceLabel")
        self.balance_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.balance_label)

        body = QHBoxLayout()
        body.setSpacing(10)

        left = QVBoxLayout()
        self.tabs = QTabWidget()
        for cat in get_all_categories():
            tab = QWidget()
            grid = QGridLayout(tab)
            grid.setSpacing(8)
            items = get_items_by_category(cat)
            for idx, item_def in enumerate(items):
                card = ItemCard(item_def)
                card.mousePressEvent = lambda e, iid=item_def["id"]: self._on_card_click(iid)
                grid.addWidget(card, idx // 3, idx % 3)
            self.tabs.addTab(tab, CATEGORY_LABELS.get(cat, cat))
        left.addWidget(self.tabs)
        body.addLayout(left, 2)

        right = QGroupBox("物品详情")
        detail_layout = QVBoxLayout(right)

        self.detail_name = QLabel("选择一个物品")
        self.detail_name.setObjectName("itemNameLabel")
        self.detail_name.setWordWrap(True)
        detail_layout.addWidget(self.detail_name)

        self.detail_desc = QLabel("")
        self.detail_desc.setObjectName("itemDescLabel")
        self.detail_desc.setWordWrap(True)
        detail_layout.addWidget(self.detail_desc)

        self.detail_price = QLabel("")
        self.detail_price.setObjectName("itemPriceLabel")
        detail_layout.addWidget(self.detail_price)

        self.detail_effects = QLabel("")
        self.detail_effects.setObjectName("itemEffectLabel")
        self.detail_effects.setWordWrap(True)
        detail_layout.addWidget(self.detail_effects)

        detail_layout.addStretch()

        self.buy_btn = QPushButton("购买")
        self.buy_btn.setEnabled(False)
        self.buy_btn.clicked.connect(self._buy_item)
        detail_layout.addWidget(self.buy_btn)

        body.addWidget(right, 1)
        root.addLayout(body)

    def refresh_balance(self):
        econ = getattr(self.pet, 'economy', None)
        if econ:
            self.balance_label.setText(
                f"\U0001f4b0 你的金币: {econ.user_wallet:.0f}    |    小日和的金币: {econ.character_wallet:.0f}"
            )
        else:
            self.balance_label.setText("经济系统未初始化")

    def _on_card_click(self, item_id):
        item = ITEMS.get(item_id)
        if not item:
            return
        self.selected_item = item
        self.detail_name.setText(f"{item['name']}")
        self.detail_desc.setText(item.get("description", ""))
        self.detail_price.setText(f"价格: {item['price']:.0f} 金币")
        effects = item.get("effects", {})
        effect_parts = []
        for k, v in effects.items():
            label = {"hunger": "饥饿", "thirst": "口渴", "fatigue": "疲劳", "sleepiness": "困倦",
                     "comfort": "舒适", "stress": "紧张", "closeness_need": "亲近需求"}.get(k, k)
            sign = "+" if v > 0 else ""
            effect_parts.append(f"{label}{sign}{v:.0f}")
        bonus = item.get("relation_bonus", 0)
        if bonus > 0:
            effect_parts.append(f"好感+{bonus:.1f}")
        self.detail_effects.setText("效果: " + ", ".join(effect_parts) if effect_parts else "")
        econ = getattr(self.pet, 'economy', None)
        can_afford = econ and econ.user_wallet >= item["price"]
        self.buy_btn.setEnabled(can_afford)
        self.buy_btn.setText(f"购买 ({item['price']:.0f} 金币)")

    def _select_first_item(self):
        items = get_items_by_category(CATEGORY_FOOD)
        if items:
            self._on_card_click(items[0]["id"])

    def _buy_item(self):
        if not self.selected_item:
            return
        item = self.selected_item
        econ = getattr(self.pet, 'economy', None)
        bp = getattr(self.pet, 'backpack', None)
        if not econ or not bp:
            return
        if not econ.spend(item["price"], wallet="user", detail=f"购买{item['name']}"):
            return
        if not bp.add_item(item["id"]):
            econ.earn(item["price"], wallet="user", detail=f"退款{item['name']}(背包已满)")
            return
        self.refresh_balance()
        self._on_card_click(item["id"])
        self.pet.show_chat_status(f"购买了 {item['name']}", seconds=2.0)


class BackpackDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet)
        self.pet = parent_pet
        self.setWindowTitle("背包")
        self.setModal(True)
        self.resize(460, 400)
        self.setStyleSheet(DIALOG_STYLE)
        self.selected_item_id = None
        self._build_ui()
        self.refresh_items()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        title = QLabel("\U0001f392  背包")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #8a6178;")
        root.addWidget(self.info_label)

        body = QHBoxLayout()
        body.setSpacing(10)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        body.addWidget(self.grid_widget, 2)

        right = QGroupBox("物品操作")
        right_layout = QVBoxLayout(right)

        self.detail_name = QLabel("选择一个物品")
        self.detail_name.setObjectName("itemNameLabel")
        self.detail_name.setWordWrap(True)
        right_layout.addWidget(self.detail_name)

        self.detail_desc = QLabel("")
        self.detail_desc.setObjectName("itemDescLabel")
        self.detail_desc.setWordWrap(True)
        right_layout.addWidget(self.detail_desc)

        self.detail_qty = QLabel("")
        self.detail_qty.setStyleSheet("color: #6b4058; font-weight: 600;")
        right_layout.addWidget(self.detail_qty)

        self.detail_effects = QLabel("")
        self.detail_effects.setObjectName("itemEffectLabel")
        self.detail_effects.setWordWrap(True)
        right_layout.addWidget(self.detail_effects)

        right_layout.addStretch()

        self.use_btn = QPushButton("给小日和使用")
        self.use_btn.setEnabled(False)
        self.use_btn.clicked.connect(self._use_item)
        right_layout.addWidget(self.use_btn)

        body.addWidget(right, 1)
        root.addLayout(body)

    def refresh_items(self):
        while self.grid_layout.count():
            w = self.grid_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        bp = getattr(self.pet, 'backpack', None)
        if not bp:
            self.info_label.setText("背包系统未初始化")
            return
        all_items = bp.get_all_items()
        total_qty = sum(q for _, q in all_items)
        self.info_label.setText(f"已用 {len(all_items)}/{bp.capacity} 格  |  共 {total_qty} 件物品")
        for idx, (item_def, qty) in enumerate(all_items):
            card = ItemCard(item_def, quantity=qty)
            card.mousePressEvent = lambda e, iid=item_def["id"]: self._on_card_click(iid)
            self.grid_layout.addWidget(card, idx // 3, idx % 3)
        if not all_items:
            empty_label = QLabel("背包是空的，去超市买点东西吧~")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #b8a0ac; font: 11pt;")
            self.grid_layout.addWidget(empty_label, 0, 0, 1, 3)

    def _on_card_click(self, item_id):
        item = ITEMS.get(item_id)
        bp = getattr(self.pet, 'backpack', None)
        if not item or not bp:
            return
        self.selected_item_id = item_id
        qty = bp.get_quantity(item_id)
        self.detail_name.setText(item["name"])
        self.detail_desc.setText(item.get("description", ""))
        self.detail_qty.setText(f"持有数量: {qty}")
        effects = item.get("effects", {})
        effect_parts = []
        for k, v in effects.items():
            label = {"hunger": "饥饿", "thirst": "口渴", "fatigue": "疲劳", "sleepiness": "困倦",
                     "comfort": "舒适", "stress": "紧张", "closeness_need": "亲近需求"}.get(k, k)
            sign = "+" if v > 0 else ""
            effect_parts.append(f"{label}{sign}{v:.0f}")
        bonus = item.get("relation_bonus", 0)
        if bonus > 0:
            effect_parts.append(f"好感+{bonus:.1f}")
        self.detail_effects.setText("效果: " + ", ".join(effect_parts) if effect_parts else "")
        self.use_btn.setEnabled(True)
        self.use_btn.setText(f"给小日和使用 {item['name']}")

    def _use_item(self):
        if not self.selected_item_id:
            return
        success, desc = self.pet.backpack_use_item(self.selected_item_id)
        if success:
            self.refresh_items()
            bp = getattr(self.pet, 'backpack', None)
            if bp and bp.get_quantity(self.selected_item_id) <= 0:
                self.selected_item_id = None
                self.detail_name.setText("选择一个物品")
                self.detail_desc.setText("")
                self.detail_qty.setText("")
                self.detail_effects.setText("")
                self.use_btn.setEnabled(False)
                self.use_btn.setText("给小日和使用")
            else:
                self._on_card_click(self.selected_item_id)
