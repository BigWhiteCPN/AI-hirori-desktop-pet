"""Room-mode rendering and activity mixin for the desktop pet."""

import json
import math
import os
import random

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap

from persona_pet.error_reporter import report_exception


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


class RoomModeMixin:
    def default_room_layout(self):
            return {
                "version": 2,
                "model_z": self.room_model_z,
                "background": {"asset": "background.png"},
                "activities": {
                    "idle": {"label": "待机", "detail": "在小屋里安静待着。", "x": 0.50, "y": 0.68, "scale": 0.68},
                    "writing": {"label": "写作", "detail": "坐在桌前整理自己的稿子。", "x": 0.72, "y": 0.63, "scale": 0.60},
                    "planning": {"label": "构思", "detail": "在桌前整理下一件想做的事。", "x": 0.70, "y": 0.63, "scale": 0.60},
                    "walking": {"label": "散步", "detail": "在小屋里慢慢走动，换换心情。", "x_min": 0.34, "x_max": 0.62, "y": 0.69, "scale": 0.62},
                    "playing": {"label": "玩耍", "detail": "被房间里的小物件吸引住了。", "x": 0.56, "y": 0.69, "scale": 0.63},
                    "resting": {"label": "休息", "detail": "能量偏低，先在床边安静恢复。", "x": 0.30, "y": 0.66, "scale": 0.58},
                    "waiting": {"label": "想你", "detail": "有点想靠近，但还在克制地等你。", "x": 0.44, "y": 0.68, "scale": 0.64},
                    "chatting": {"label": "陪你", "detail": "正在把注意力放在你身上。", "x": 0.50, "y": 0.67, "scale": 0.68},
                },
                "objects": [],
            }

    def merge_room_layout(self, base, override):
            if not isinstance(override, dict):
                return base
            merged = dict(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    child = dict(merged[key])
                    child.update(value)
                    merged[key] = child
                else:
                    merged[key] = value
            return merged

    def load_room_layout(self):
            layout = self.default_room_layout()
            if not os.path.exists(self.room_layout_path):
                return layout
            try:
                with open(self.room_layout_path, "r", encoding="utf-8") as handle:
                    custom = json.load(handle)
                return self.merge_room_layout(layout, custom)
            except Exception as exc:
                self.room_log_runtime("ROOM_LAYOUT_ERROR", {"path": self.room_layout_path, "error": str(exc)})
                return layout

    def reload_room_layout(self):
            self.room_pixmaps = {}
            self.room_layout = self.load_room_layout()
            self.show_chat_status("小屋布局已重新读取", seconds=2.8)

    def room_activity_layout(self, activity=None):
            activities = self.room_layout.get("activities", {})
            if not isinstance(activities, dict):
                activities = {}
            data = activities.get(activity or self.room_activity) or activities.get("idle") or {}
            return data if isinstance(data, dict) else {}

    def room_asset_path(self, asset):
            if not asset:
                return ""
            asset = str(asset).replace("\\", os.sep).replace("/", os.sep)
            if os.path.isabs(asset):
                return asset
            return os.path.join(self.room_asset_dir, asset)

    def remove_checkerboard_from_pixmap(self, pixmap):
            image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
            width = image.width()
            height = image.height()
            if width <= 0 or height <= 0:
                return pixmap

            samples = []
            step_x = max(1, width // 24)
            step_y = max(1, height // 24)
            for x in range(0, width, step_x):
                for y in (0, height - 1):
                    color = QColor(image.pixel(x, y))
                    samples.append((color.red(), color.green(), color.blue()))
            for y in range(0, height, step_y):
                for x in (0, width - 1):
                    color = QColor(image.pixel(x, y))
                    samples.append((color.red(), color.green(), color.blue()))

            buckets = {}
            for r, g, b in samples:
                if max(abs(r - g), abs(g - b), abs(r - b)) > 8:
                    continue
                key = int(round((r + g + b) / 3.0 / 12.0) * 12)
                buckets[key] = buckets.get(key, 0) + 1
            candidates = sorted((count, value) for value, count in buckets.items() if value >= 170)
            key_values = [value for _count, value in candidates[-3:]]
            if not key_values:
                key_values = [204, 221, 238, 255]

            for y in range(height):
                for x in range(width):
                    color = QColor(image.pixel(x, y))
                    r, g, b = color.red(), color.green(), color.blue()
                    if max(abs(r - g), abs(g - b), abs(r - b)) > 8:
                        continue
                    gray = (r + g + b) / 3.0
                    if any(abs(gray - key) <= 10 for key in key_values):
                        color.setAlpha(0)
                        image.setPixelColor(x, y, color)
            return QPixmap.fromImage(image)

    def room_pixmap(self, asset, remove_checkerboard=False):
            path = self.room_asset_path(asset)
            if not path:
                return None
            cache_key = (path, bool(remove_checkerboard))
            cached = self.room_pixmaps.get(cache_key)
            if cached is not None:
                return cached if not cached.isNull() else None
            pixmap = QPixmap(path)
            if remove_checkerboard and not pixmap.isNull():
                pixmap = self.remove_checkerboard_from_pixmap(pixmap)
            self.room_pixmaps[cache_key] = pixmap
            return pixmap if not pixmap.isNull() else None

    def draw_room_pixmap_object(self, painter, item):
            if not isinstance(item, dict):
                return False
            pixmap = self.room_pixmap(
                item.get("asset"),
                remove_checkerboard=bool(item.get("remove_checkerboard") or self.room_layout.get("remove_checkerboard")),
            )
            if pixmap is None:
                return False
            window_w = max(1, self.width())
            window_h = max(1, self.height())
            width_ratio = float(item.get("w", item.get("width", 0.2)))
            target_w = max(1.0, width_ratio * window_w)
            if item.get("h") is not None:
                target_h = max(1.0, float(item.get("h")) * window_h)
            else:
                target_h = target_w * pixmap.height() / max(1, pixmap.width())
            x = float(item.get("x", 0.0)) * window_w
            y = float(item.get("y", 0.0)) * window_h
            anchor = str(item.get("anchor") or "top_left")
            if anchor == "center":
                x -= target_w / 2.0
                y -= target_h / 2.0
            elif anchor == "bottom_center":
                x -= target_w / 2.0
                y -= target_h
            elif anchor == "bottom_left":
                y -= target_h
            shadow = item.get("shadow", True)
            if shadow:
                shadow_opacity = int(_clamp(float(item.get("shadow_opacity", 0.18)), 0.0, 0.5) * 255)
                shadow_h = max(6.0, target_h * float(item.get("shadow_h", 0.08)))
                shadow_w = target_w * float(item.get("shadow_w", 0.72))
                shadow_x = x + (target_w - shadow_w) / 2.0
                shadow_y = y + target_h - shadow_h * 0.45
                shadow_path = QPainterPath()
                shadow_path.addRoundedRect(QRectF(shadow_x, shadow_y, shadow_w, shadow_h), shadow_h / 2.0, shadow_h / 2.0)
                painter.fillPath(shadow_path, QColor(80, 48, 62, shadow_opacity))
            painter.setOpacity(_clamp(float(item.get("opacity", 1.0)), 0.0, 1.0))
            painter.drawPixmap(QRectF(x, y, target_w, target_h), pixmap, QRectF(pixmap.rect()))
            painter.setOpacity(1.0)
            return True

    def draw_room_asset_objects(self, painter, min_z=None, max_z=None):
            objects = self.room_layout.get("objects", [])
            if not isinstance(objects, list):
                return 0
            model_z = int(self.room_layout.get("model_z", self.room_model_z) or self.room_model_z)
            if min_z is None:
                min_z = -9999
            if max_z is None:
                max_z = 9999
            drawn = 0
            for item in sorted(objects, key=lambda obj: int(obj.get("z", model_z) if isinstance(obj, dict) else model_z)):
                if not isinstance(item, dict):
                    continue
                z_value = int(item.get("z", model_z))
                if z_value < min_z or z_value > max_z:
                    continue
                if self.draw_room_pixmap_object(painter, item):
                    drawn += 1
            return drawn

    def draw_room_asset_background(self, painter):
            background = self.room_layout.get("background", {})
            if not isinstance(background, dict):
                return False
            pixmap = self.room_pixmap(
                background.get("asset"),
                remove_checkerboard=bool(background.get("remove_checkerboard")),
            )
            if pixmap is None:
                return False
            painter.drawPixmap(QRectF(0, 0, self.width(), self.height()), pixmap, QRectF(pixmap.rect()))
            return True

    def room_position_to_model_offset(self, x, y):
            offset_x = (float(x) - 0.5) * 1.15
            offset_y = (0.62 - float(y)) * 0.36 - 0.05
            return _clamp(offset_x, -0.55, 0.55), _clamp(offset_y, -0.18, 0.10)

    def toggle_room_mode(self):
            self.room_mode = not self.room_mode
            if self.room_mode:
                if getattr(self, "city_mode", False):
                    self.city_mode = False
                self.resize(self.room_window_width, self.room_window_height)
                self.show_chat_status("小屋模式已打开：会显示写作、休息、散步和玩耍状态", seconds=4.0)
            else:
                self.resize(self.default_window_width, self.default_window_height)
                if self.model is not None:
                    try:
                        self.model.SetScale(1.0)
                        self.model.SetOffset(0.0, 0.0)
                    except Exception as exc:
                        report_exception(getattr(self, "runtime", None), getattr(self, "room_log_runtime", None), "room_mode", "reset_model_transform", exc)
                self.show_chat_status("小屋模式已关闭", seconds=2.6)
            if self.model is not None:
                try:
                    self.model.Resize(self.width(), self.height())
                except Exception as exc:
                    report_exception(getattr(self, "runtime", None), getattr(self, "room_log_runtime", None), "room_mode", "resize_model", exc)

    def choose_room_activity(self, now):
            values = self.drive.values
            idle_seconds = max(0.0, now - self.last_user_interaction_at)
            if self.life_writer.is_busy():
                return "writing"
            if self.chat.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
                return "chatting"
            if values.get("energy", 50.0) < 28.0:
                return "resting"
            if values.get("attachment_need", 0.0) > 72.0 and values.get("affinity", 0.0) > 55.0:
                return "waiting"
            if values.get("purpose", 0.0) > 72.0 and idle_seconds > 180.0:
                return "planning"
            if values.get("novelty", 0.0) > 62.0 and values.get("energy", 0.0) > 48.0:
                return "playing"
            if idle_seconds > 120.0 and values.get("energy", 0.0) > 34.0:
                return "walking"
            return "idle"

    def update_room_activity(self, now):
            selected = self.choose_room_activity(now)
            urgent = selected in {"writing", "chatting", "resting", "waiting"}
            if selected != self.room_activity and (urgent or now - self.room_activity_started_at > 10.0):
                self.room_activity = selected
                self.room_activity_started_at = now
                self.room_last_motion_at = 0.0
                info = self.room_activity_info()
                self.show_chat_status(f"小屋状态：{info.get('label', self.room_activity)} - {info.get('detail', '')}", seconds=3.4)
                print("ROOM_ACTIVITY =", {"activity": self.room_activity})

    def room_activity_info(self):
            title = self.life.novel.get("title") if isinstance(self.life.novel, dict) else ""
            info = {
                "idle": ("待机", "在房间里发呆，偶尔看看你。", QColor(255, 166, 194)),
                "writing": ("写作", f"正在写{'《' + title + '》' if title else '自己的稿子'}。", QColor(110, 170, 232)),
                "planning": ("构思", "在桌前整理下一件想做的事。", QColor(138, 116, 214)),
                "walking": ("散步", "在小屋里慢慢走动，换换心情。", QColor(93, 183, 156)),
                "playing": ("玩耍", "被玩具和新鲜东西吸引住了。", QColor(244, 156, 83)),
                "resting": ("休息", "能量偏低，先在床边安静恢复。", QColor(132, 186, 132)),
                "waiting": ("想你", "有点想靠近，但还在克制地等你。", QColor(232, 116, 136)),
                "chatting": ("陪你", "正在把注意力放在你身上。", QColor(230, 124, 178)),
            }
            label, detail, color = info.get(self.room_activity, info["idle"])
            layout = self.room_activity_layout()
            label = str(layout.get("label") or label)
            detail = str(layout.get("detail") or detail)
            if self.room_activity == "writing" and title and "自己的稿子" in detail:
                detail = f"正在写《{title}》。"
            return {"label": label, "detail": detail, "color": color}

    def room_model_transform(self, now):
            layout = self.room_activity_layout()
            if layout:
                if self.room_activity == "walking":
                    x_min = float(layout.get("x_min", 0.30))
                    x_max = float(layout.get("x_max", 0.68))
                    x = (x_min + x_max) / 2.0 + math.sin(now * 0.42 + self.room_walk_seed) * abs(x_max - x_min) / 2.0
                else:
                    x = float(layout.get("x", 0.5))
                y = float(layout.get("y", 0.66))
                scale = float(layout.get("scale", self.room_model_scale))
                offset_x = layout.get("offset_x")
                offset_y = layout.get("offset_y")
                if offset_x is None or offset_y is None:
                    offset_x, offset_y = self.room_position_to_model_offset(x, y)
                return float(offset_x), float(offset_y), scale

            base = {
                "idle": (0.00, -0.05, self.room_model_scale),
                "writing": (0.26, -0.07, 0.60),
                "planning": (0.25, -0.06, 0.62),
                "walking": (math.sin(now * 0.42 + self.room_walk_seed) * 0.32, -0.07, 0.63),
                "playing": (0.18 + math.sin(now * 1.2) * 0.05, -0.08, 0.65),
                "resting": (-0.30, -0.10, 0.58),
                "waiting": (-0.08, -0.07, 0.64),
                "chatting": (0.02, -0.05, 0.68),
            }
            return base.get(self.room_activity, base["idle"])

    def apply_room_model_transform(self, now):
            if self.model is None:
                return
            try:
                if self.room_mode:
                    x, y, scale = self.room_model_transform(now)
                    self.model.SetScale(scale)
                    self.model.SetOffset(x, y)
                else:
                    self.model.SetScale(1.0)
                    self.model.SetOffset(0.0, 0.0)
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "room_log_runtime", None), "room_mode", "apply_model_transform", exc, activity=getattr(self, "room_activity", ""))

    def maybe_trigger_room_motion(self, now):
            if not self.room_mode or self.model is None:
                return
            if self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
                return
            if now - self.room_last_motion_at < 9.0:
                return
            try:
                if not self.model.IsMotionFinished():
                    return
            except Exception:
                pass
            motion_keys = {
                "writing": "m01_thinking",
                "planning": "m02_question_smile",
                "walking": "m03_carefree_joy",
                "playing": "m06_cute_joy",
                "resting": "m01_thinking",
                "waiting": "m04_wronged_sadness",
                "idle": "m01_thinking",
            }
            motion = self.room_motion_templates.get(motion_keys.get(self.room_activity, "m01_thinking"))
            try:
                if motion and self.motion_groups.get(motion["group"], 0) > motion["index"]:
                    self.model.StartMotion(motion["group"], motion["index"], 1)
                elif self.motion_groups.get("Idle", 0):
                    self.model.StartMotion("Idle", random.randrange(self.motion_groups["Idle"]), 1)
                self.room_last_motion_at = now
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "room_log_runtime", None), "room_mode", "trigger_room_motion", exc, activity=getattr(self, "room_activity", ""))

    def draw_room_base_surfaces(self, painter):
            w = self.width()
            h = self.height()
            wall_h = int(h * 0.64)
            painter.fillRect(0, 0, w, wall_h, QColor(255, 241, 247, 255))
            painter.fillRect(0, wall_h, w, h - wall_h, QColor(232, 211, 190, 255))

            painter.setPen(QColor(213, 166, 184, 120))
            for x in range(0, w, 54):
                painter.drawLine(x, wall_h, x + 34, h)
            painter.setPen(QColor(176, 130, 102, 85))
            for y in range(wall_h + 22, h, 30):
                painter.drawLine(0, y, w, y)
            return wall_h

    def draw_room_background(self, behind_model=False):
            target_pixmap = None
            if behind_model:
                target_pixmap = QPixmap(self.size())
                target_pixmap.fill(Qt.transparent)
                painter = QPainter(target_pixmap)
            else:
                painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            def finish_painting():
                painter.end()
                if target_pixmap is not None:
                    target_painter = QPainter(self)
                    target_painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
                    target_painter.drawPixmap(0, 0, target_pixmap)
                    target_painter.end()

            w = self.width()
            h = self.height()
            background_drawn = self.draw_room_asset_background(painter)
            if not background_drawn:
                wall_h = self.draw_room_base_surfaces(painter)
            else:
                wall_h = int(h * 0.64)
            model_z = int(self.room_layout.get("model_z", self.room_model_z) or self.room_model_z)
            asset_count = self.draw_room_asset_objects(painter, max_z=model_z - 1)
            if background_drawn or asset_count:
                finish_painting()
                return

            painter.setPen(QColor(184, 122, 150, 140))
            window = QRectF(54, 84, 150, 112)
            path = QPainterPath()
            path.addRoundedRect(window, 10, 10)
            painter.fillPath(path, QColor(205, 235, 255, 230))
            painter.drawPath(path)
            painter.drawLine(window.center().x(), window.top() + 8, window.center().x(), window.bottom() - 8)
            painter.drawLine(window.left() + 8, window.center().y(), window.right() - 8, window.center().y())

            shelf = QRectF(w - 196, 86, 128, 108)
            shelf_path = QPainterPath()
            shelf_path.addRoundedRect(shelf, 8, 8)
            painter.fillPath(shelf_path, QColor(167, 118, 91, 220))
            painter.fillRect(QRectF(shelf.left() + 10, shelf.top() + 28, shelf.width() - 20, 8), QColor(126, 83, 64, 190))
            painter.fillRect(QRectF(shelf.left() + 10, shelf.top() + 68, shelf.width() - 20, 8), QColor(126, 83, 64, 190))
            for i, color in enumerate((QColor(112, 170, 232), QColor(244, 156, 83), QColor(138, 116, 214), QColor(93, 183, 156))):
                painter.fillRect(QRectF(shelf.left() + 18 + i * 22, shelf.top() + 36, 14, 30), color)

            bed = QRectF(40, wall_h - 24, 188, 88)
            bed_path = QPainterPath()
            bed_path.addRoundedRect(bed, 16, 16)
            painter.fillPath(bed_path, QColor(255, 226, 237, 238))
            painter.fillPath(bed_path, QColor(255, 226, 237, 120))
            pillow = QRectF(bed.left() + 16, bed.top() + 14, 58, 28)
            pillow_path = QPainterPath()
            pillow_path.addRoundedRect(pillow, 10, 10)
            painter.fillPath(pillow_path, QColor(255, 250, 253, 235))

            desk = QRectF(w - 248, wall_h - 16, 198, 88)
            desk_path = QPainterPath()
            desk_path.addRoundedRect(desk, 10, 10)
            painter.fillPath(desk_path, QColor(174, 128, 92, 232))
            painter.fillRect(QRectF(desk.left() + 22, desk.top() + 18, 70, 46), QColor(255, 251, 238, 230))
            painter.fillRect(QRectF(desk.left() + 104, desk.top() + 16, 38, 46), QColor(118, 91, 72, 210))

            rug = QRectF(w * 0.33, h - 118, w * 0.34, 66)
            rug_path = QPainterPath()
            rug_path.addRoundedRect(rug, 28, 28)
            painter.fillPath(rug_path, QColor(248, 176, 142, 175))
            finish_painting()

    def draw_room_foreground(self):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            model_z = int(self.room_layout.get("model_z", self.room_model_z) or self.room_model_z)
            self.draw_room_asset_objects(painter, min_z=model_z)
            w = self.width()
            h = self.height()
            info = self.room_activity_info()
            color = info["color"]

            shadow = QRectF(w * 0.34, h - 116, w * 0.32, 34)
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(shadow, 17, 17)
            painter.fillPath(shadow_path, QColor(92, 55, 76, 46))

            panel = QRectF(24, h - 88, min(330, w - 48), 58)
            panel_path = QPainterPath()
            panel_path.addRoundedRect(panel, 16, 16)
            painter.fillPath(panel_path, QColor(255, 250, 253, 235))
            painter.setPen(QColor(color.red(), color.green(), color.blue(), 230))
            painter.drawPath(panel_path)

            dot = QRectF(panel.left() + 16, panel.top() + 17, 18, 18)
            dot_path = QPainterPath()
            dot_path.addEllipse(dot)
            painter.fillPath(dot_path, color)

            painter.setPen(QColor(88, 50, 72))
            painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.DemiBold))
            painter.drawText(QRectF(panel.left() + 44, panel.top() + 9, panel.width() - 58, 22), Qt.AlignLeft | Qt.AlignVCenter, info["label"])
            painter.setPen(QColor(132, 82, 108))
            painter.setFont(QFont("Microsoft YaHei UI", 8))
            painter.drawText(QRectF(panel.left() + 44, panel.top() + 30, panel.width() - 58, 20), Qt.AlignLeft | Qt.AlignVCenter, info["detail"])
            painter.end()
