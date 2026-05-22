"""2D city map mode rendering and click handling for PersonaPet."""

import os

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap

CITY_WINDOW_WIDTH = 900
CITY_WINDOW_HEIGHT = 600

CITY_LOCATIONS = [
    {
        "id": "supermarket",
        "name": "超市",
        "icon": "\U0001f6d2",
        "icon_asset": "icons/supermarket.png",
        "x": 0.08, "y": 0.22,
        "w": 0.18, "h": 0.20,
        "color": QColor(255, 200, 60),
        "desc": "购买日用品和食物",
    },
    {
        "id": "farm",
        "name": "农场",
        "icon": "\U0001f33e",
        "icon_asset": "icons/farm.png",
        "x": 0.38, "y": 0.50,
        "w": 0.20, "h": 0.22,
        "color": QColor(120, 200, 100),
        "desc": "打工赚金币",
    },
    {
        "id": "home",
        "name": "小屋",
        "icon": "\U0001f3e0",
        "icon_asset": "icons/home.png",
        "x": 0.72, "y": 0.18,
        "w": 0.20, "h": 0.22,
        "color": QColor(255, 170, 180),
        "desc": "回到温馨的小屋",
    },
    {
        "id": "factory",
        "name": "工业区",
        "icon": "\U0001f3ed",
        "icon_asset": "icons/factory.png",
        "x": 0.08, "y": 0.60,
        "w": 0.18, "h": 0.20,
        "color": QColor(160, 170, 200),
        "desc": "即将开放",
    },
    {
        "id": "city_hall",
        "name": "市政厅",
        "icon": "\U0001f3db",
        "icon_asset": "icons/city_hall.png",
        "x": 0.72, "y": 0.56,
        "w": 0.20, "h": 0.22,
        "color": QColor(200, 180, 240),
        "desc": "查看统计和成就",
    },
]


class CityModeMixin:
    def default_city_layout(self):
        return {"version": 1, "locations": CITY_LOCATIONS}

    def load_city_layout(self):
        self.city_layout = self.default_city_layout()
        self.city_locations = self.city_layout.get("locations", CITY_LOCATIONS)
        self.city_hover_location = None

    def toggle_city_mode(self):
        self.city_mode = not getattr(self, 'city_mode', False)
        if self.city_mode:
            if getattr(self, 'room_mode', False):
                self.room_mode = False
            self.resize(CITY_WINDOW_WIDTH, CITY_WINDOW_HEIGHT)
            self.show_chat_status("城市模式：点击地点可以探索", seconds=4.0)
        else:
            self.resize(self.default_window_width, self.default_window_height)
            if self.model is not None:
                try:
                    self.model.SetScale(1.0)
                    self.model.SetOffset(0.0, 0.0)
                except Exception:
                    pass
            self.show_chat_status("已退出城市模式", seconds=2.0)
        if self.model is not None:
            try:
                self.model.Resize(self.width(), self.height())
            except Exception:
                pass

    def city_background_pixmap(self):
        pixmap = getattr(self, "_city_background_pixmap", None)
        if pixmap is not None:
            return pixmap if not pixmap.isNull() else None
        base_dir = getattr(self, "base_dir", None)
        if not base_dir:
            self._city_background_pixmap = QPixmap()
            return None
        path = os.path.join(base_dir, "assets", "city_map", "background.png")
        pixmap = QPixmap(path)
        self._city_background_pixmap = pixmap
        return pixmap if not pixmap.isNull() else None

    def city_location_pixmap(self, loc):
        asset = loc.get("icon_asset")
        if not asset:
            return None
        cache = getattr(self, "_city_location_pixmaps", None)
        if cache is None:
            cache = {}
            self._city_location_pixmaps = cache
        pixmap = cache.get(asset)
        if pixmap is not None:
            return pixmap if not pixmap.isNull() else None
        base_dir = getattr(self, "base_dir", None)
        if not base_dir:
            cache[asset] = QPixmap()
            return None
        relative_asset = asset.replace("/", os.sep)
        path = os.path.join(base_dir, "assets", "city_map", relative_asset)
        pixmap = QPixmap(path)
        cache[asset] = pixmap
        return pixmap if not pixmap.isNull() else None

    def draw_city_icon_pixmap(self, painter, pixmap, rect):
        icon_path = QPainterPath()
        icon_path.addRoundedRect(rect, 10, 10)
        painter.save()
        painter.setClipPath(icon_path)
        painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
        painter.drawPath(icon_path)

    def draw_city_scene(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        background = self.city_background_pixmap()
        if background is not None:
            painter.drawPixmap(QRectF(0, 0, w, h), background, QRectF(background.rect()))
            painter.end()
            return

        # Sky gradient
        for i in range(int(h * 0.45)):
            ratio = i / (h * 0.45)
            r = int(135 + (200 - 135) * ratio)
            g = int(200 + (230 - 200) * ratio)
            b = int(255 + (255 - 255) * ratio)
            painter.fillRect(0, i, w, 1, QColor(r, g, b))

        # Sun
        sun_path = QPainterPath()
        sun_path.addEllipse(QPointF(w * 0.85, h * 0.12), 30, 30)
        painter.fillPath(sun_path, QColor(255, 230, 100, 200))

        # Clouds
        for cx, cy, cw in [(0.15, 0.08, 80), (0.45, 0.05, 60), (0.70, 0.10, 70)]:
            cloud_path = QPainterPath()
            cloud_path.addEllipse(QPointF(w * cx, h * cy), cw * 0.5, 18)
            cloud_path.addEllipse(QPointF(w * cx + cw * 0.3, h * cy - 8), cw * 0.4, 16)
            cloud_path.addEllipse(QPointF(w * cx - cw * 0.2, h * cy + 4), cw * 0.35, 14)
            painter.fillPath(cloud_path, QColor(255, 255, 255, 200))

        # Ground
        ground_y = int(h * 0.45)
        painter.fillRect(0, ground_y, w, h - ground_y, QColor(140, 200, 100))

        # Road horizontal
        road_y = int(h * 0.44)
        painter.fillRect(0, road_y, w, int(h * 0.06), QColor(180, 180, 170))
        # Road dashes
        painter.setPen(QPen(QColor(255, 255, 200, 180), 2, Qt.DashLine))
        painter.drawLine(0, road_y + int(h * 0.03), w, road_y + int(h * 0.03))

        # Road vertical
        road_x = int(w * 0.47)
        painter.fillRect(road_x - int(w * 0.025), int(h * 0.44), int(w * 0.05), h - int(h * 0.44), QColor(180, 180, 170))
        painter.setPen(QPen(QColor(255, 255, 200, 180), 2, Qt.DashLine))
        painter.drawLine(road_x, int(h * 0.44), road_x, h)

        # Trees decoration
        tree_positions = [(0.30, 0.38), (0.55, 0.36), (0.62, 0.40), (0.88, 0.38), (0.05, 0.42), (0.92, 0.42)]
        for tx, ty in tree_positions:
            trunk = QPainterPath()
            trunk.addRoundedRect(QRectF(w * tx - 3, h * ty, 6, 20), 2, 2)
            painter.fillPath(trunk, QColor(130, 90, 60))
            canopy = QPainterPath()
            canopy.addEllipse(QPointF(w * tx, h * ty - 8), 16, 14)
            painter.fillPath(canopy, QColor(80, 160, 80, 200))

        painter.end()

    def draw_city_locations(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        hover_id = getattr(self, 'city_hover_location', None)

        for loc in self.city_locations:
            rect = QRectF(
                w * loc["x"], h * loc["y"],
                w * loc["w"], h * loc["h"],
            )
            is_hover = (loc["id"] == hover_id)
            base_color = loc.get("color", QColor(200, 200, 200))
            if is_hover:
                fill_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 220)
                border_color = QColor(255, 255, 255)
                border_width = 3
            else:
                fill_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 180)
                border_color = QColor(255, 255, 255, 150)
                border_width = 2

            path = QPainterPath()
            path.addRoundedRect(rect, 12, 12)
            painter.fillPath(path, fill_color)
            painter.setPen(QPen(border_color, border_width))
            painter.drawPath(path)

            # Icon image, with the old emoji kept as a fallback if the asset is missing.
            icon_size = min(rect.width() - 24, rect.height() * (0.62 if is_hover else 0.58))
            icon_rect = QRectF(
                rect.center().x() - icon_size / 2,
                rect.top() + 8,
                icon_size,
                icon_size,
            )
            icon_pixmap = self.city_location_pixmap(loc)
            if icon_pixmap is not None:
                self.draw_city_icon_pixmap(painter, icon_pixmap, icon_rect)
            else:
                icon_font = QFont("Segoe UI Emoji", 28 if is_hover else 24)
                painter.setFont(icon_font)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(icon_rect, Qt.AlignCenter, loc.get("icon", ""))

            # Name
            name_font = QFont("Microsoft YaHei UI", 11 if is_hover else 10, QFont.Bold)
            painter.setFont(name_font)
            painter.setPen(QColor(255, 255, 255))
            name_rect = QRectF(rect.left(), rect.top() + rect.height() * 0.55, rect.width(), 24)
            painter.drawText(name_rect, Qt.AlignCenter, loc["name"])

            # Description on hover
            if is_hover and loc.get("desc"):
                desc_font = QFont("Microsoft YaHei UI", 8)
                painter.setFont(desc_font)
                painter.setPen(QColor(255, 255, 255, 220))
                desc_rect = QRectF(rect.left(), rect.top() + rect.height() * 0.75, rect.width(), 20)
                painter.drawText(desc_rect, Qt.AlignCenter, loc["desc"])

        painter.end()

    def draw_city_hud(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        # Top bar background
        bar_rect = QRectF(0, 0, w, 36)
        bar_path = QPainterPath()
        bar_path.addRoundedRect(bar_rect.adjusted(8, 4, -8, 0), 8, 8)
        painter.fillPath(bar_path, QColor(0, 0, 0, 80))

        # Balance text
        econ = getattr(self, 'economy', None)
        if econ:
            balance_text = f"\U0001f4b0 你的: {econ.user_wallet:.0f}  |  小日和的: {econ.character_wallet:.0f}"
        else:
            balance_text = "\U0001f4b0 经济系统未初始化"

        hud_font = QFont("Microsoft YaHei UI", 10, QFont.Bold)
        painter.setFont(hud_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(bar_rect.adjusted(16, 4, -16, 0), Qt.AlignVCenter | Qt.AlignLeft, balance_text)

        # Bottom hint
        hint_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(hint_font)
        painter.setPen(QColor(255, 255, 255, 160))
        painter.drawText(QRectF(0, w > 600 and self.height() - 28 or self.height() - 22, w, 22),
                         Qt.AlignCenter, "按 K 退出城市  |  点击地点进入")

        painter.end()

    def city_hit_test(self, pos):
        w = self.width()
        h = self.height()
        for loc in self.city_locations:
            rect = QRectF(
                w * loc["x"], h * loc["y"],
                w * loc["w"], h * loc["h"],
            )
            if rect.contains(pos):
                return loc["id"]
        return None

    def city_mouse_move(self, pos):
        if not getattr(self, 'city_mode', False):
            return False
        new_hover = self.city_hit_test(pos)
        if new_hover != getattr(self, 'city_hover_location', None):
            self.city_hover_location = new_hover
            self.update()
        return True

    def city_mouse_press(self, pos):
        if not getattr(self, 'city_mode', False):
            return False
        location_id = self.city_hit_test(pos)
        if location_id:
            self.enter_city_location(location_id)
            return True
        return False

    def enter_city_location(self, location_id):
        handlers = {
            "supermarket": self._city_open_supermarket,
            "home": self._city_go_home,
            "farm": self._city_open_farm,
            "city_hall": self._city_open_city_hall,
            "factory": self._city_open_factory,
        }
        handler = handlers.get(location_id)
        if handler:
            handler()

    def _city_open_supermarket(self):
        from persona_pet.supermarket import SupermarketDialog
        dlg = SupermarketDialog(self)
        dlg.exec_()
        self.update()

    def _city_go_home(self):
        self.toggle_city_mode()

    def _city_open_farm(self):
        from persona_pet.city_dialogs import FarmWorkDialog
        dlg = FarmWorkDialog(self)
        dlg.exec_()
        self.update()

    def _city_open_city_hall(self):
        from persona_pet.city_dialogs import CityHallDialog
        dlg = CityHallDialog(self)
        dlg.exec_()
        self.update()

    def _city_open_factory(self):
        from persona_pet.city_dialogs import IndustrialAreaDialog
        dlg = IndustrialAreaDialog(self)
        dlg.exec_()
        self.update()
