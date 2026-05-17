import os
import math
import re
import sys
import time
import traceback

import live2d.v3 as live2d
from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu
from live2d.v3.params import StandardParams

from persona_pet.behavior import (
    DIALOGUE_ROLE_SPEAKER,
    EmotionAnalysis,
    analyze_text_to_emotion,
    apply_params,
    clamp,
    compose_params,
    dominant_weight_emotion,
    emotion_to_params,
    expressive_weights_for_render,
    PARAM_ARM_LA,
    PARAM_ARM_RA,
)
from persona_pet.stimulus import Stimulus
from persona_pet.touch_zone_config import (
    TOUCH_ZONE_ORDER,
    hit_test_touch_zone,
    normalize_zone_rect,
    rect_from_normalized,
    touch_zone_color,
    touch_zone_label,
)
from persona_pet.voicevox import estimate_sentence_seconds


class PetRenderMixin:
    def initializeGL(self):
        success = False
        try:
            self.runtime_logger(
                "LIVE2D_INIT",
                {
                    "base_dir": getattr(self, "base_dir", ""),
                    "model_json": self.model_json_path,
                    "model_exists": os.path.exists(self.model_json_path),
                    "frozen": bool(getattr(sys, "frozen", False)),
                },
            )
            live2d.init()
            live2d.glInit()

            self.model = live2d.LAppModel()
            self.model.LoadModelJson(self.model_json_path)
            self.model.Resize(self.width(), self.height())
            self.model.SetAutoBreathEnable(True)
            self.model.SetAutoBlinkEnable(True)
            self.runtime_logger("LIVE2D_READY")
            success = True
        except Exception:
            self.model = None
            self.runtime_logger("LIVE2D_INIT_ERROR", traceback.format_exc())
            self.show_chat_status("Live2D 加载失败，查看 logs/persona_pet.log", seconds=8.0)
        finally:
            if hasattr(self, "notify_startup_loading_done"):
                QTimer.singleShot(0, lambda ok=success: self.notify_startup_loading_done(ok))

    def show_subtitle(self, text, voice_text="", duration=None):
        if hasattr(self, "memory_associate_output"):
            self.memory_associate_output(text, source="subtitle")
        if not self.subtitles_enabled:
            self.subtitle_text = ""
            self.subtitle_voice_text = ""
            self.subtitle_until = 0.0
            self.runtime_logger("SUBTITLE_SUPPRESSED", {"text": text, "voice_text": voice_text})
            return
        now = time.monotonic()
        display_seconds = duration
        if display_seconds is None:
            zh_len = len(re.sub(r"\s+", "", text or ""))
            ja_len = len(re.sub(r"\s+", "", voice_text or ""))
            display_seconds = max(
                estimate_sentence_seconds(text, role=DIALOGUE_ROLE_SPEAKER),
                2.8 + zh_len * 0.055 + ja_len * 0.035,
            )
        self.subtitle_text = text
        self.subtitle_voice_text = voice_text
        self.subtitle_until = now + clamp(display_seconds, 3.2, 14.0) + self.subtitle_seconds_pad
        self.runtime_logger(
            "SUBTITLE",
            {
                "text": text,
                "voice_text": voice_text,
                "seconds": round(self.subtitle_until - now, 2),
            },
        )

    def show_chat_status(self, text, seconds=2.6):
        if hasattr(self, "memory_associate_output"):
            self.memory_associate_output(text, source="status")
        self.chat_status_text = text
        self.chat_status_until = time.monotonic() + seconds
        if hasattr(self, "heart_status_bar"):
            self.heart_status_bar.refresh()

    def draw_subtitle_bubble(self):
        now = time.monotonic()
        if not self.subtitle_text or now > self.subtitle_until:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = 22
        zh_len = len(self.subtitle_text or "")
        ja_len = len(self.subtitle_voice_text or "")
        bubble_width = self.width() - margin * 2
        zh_lines = max(1, math.ceil(zh_len / max(10, int(bubble_width / 18))))
        ja_lines = max(0, math.ceil(ja_len / max(12, int(bubble_width / 15)))) if self.subtitle_voice_text else 0
        bubble_height = 42 + zh_lines * 24 + ja_lines * 20
        bubble_height = int(clamp(bubble_height, 92, min(260, self.height() * 0.42)))
        rect = QRectF(
            margin,
            self.height() - bubble_height - 26,
            bubble_width,
            bubble_height,
        )
        shadow_rect = QRectF(rect)
        shadow_rect.translate(0, 4)

        shadow = QPainterPath()
        shadow.addRoundedRect(shadow_rect, 18, 18)
        painter.fillPath(shadow, QColor(80, 44, 78, 72))

        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        painter.fillPath(path, QColor(255, 248, 253, 238))
        painter.setPen(QColor(255, 150, 205, 230))
        painter.drawPath(path)

        if self.subtitle_voice_text:
            jp_height = min(62, max(28, ja_lines * 20 + 8))
        else:
            jp_height = 0

        text_rect = rect.adjusted(18, 13, -18, -14 - jp_height)
        painter.setPen(QColor(88, 50, 72))
        zh_font_size = 10 if zh_lines <= 4 else 9
        painter.setFont(QFont("Microsoft YaHei UI", zh_font_size, QFont.DemiBold))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.subtitle_text)

        if self.subtitle_voice_text:
            jp_rect = QRectF(rect.left() + 18, rect.bottom() - jp_height - 8, rect.width() - 36, jp_height)
            painter.setPen(QColor(180, 82, 138))
            painter.setFont(QFont("Yu Gothic UI", 9))
            painter.drawText(jp_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.subtitle_voice_text)

        painter.end()

    def draw_home_icon_surface(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        icon_path = getattr(self, "home_icon_path", "")
        pixmap = getattr(self, "_home_icon_pixmap", None)
        if pixmap is None or pixmap.isNull() or getattr(self, "_home_icon_pixmap_path", "") != icon_path:
            pixmap = QPixmap(icon_path)
            self._home_icon_pixmap = pixmap
            self._home_icon_pixmap_path = icon_path

        top_reserved = 96 if hasattr(self, "heart_status_bar") else 60
        available_h = max(140, self.height() - top_reserved - 22)
        icon_size = min(245, self.width() - 38, available_h)
        x = (self.width() - icon_size) / 2.0
        y = top_reserved + max(0, (available_h - icon_size) / 2.0)
        icon_rect = QRectF(x, y, icon_size, icon_size)
        self.home_icon_rect = icon_rect

        shadow = QPainterPath()
        shadow.addEllipse(QRectF(x + icon_size * 0.12, y + icon_size * 0.82, icon_size * 0.76, icon_size * 0.12))
        painter.fillPath(shadow, QColor(75, 43, 67, 54))

        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(icon_rect, pixmap, QRectF(pixmap.rect()))
        else:
            fallback = QPainterPath()
            fallback.addRoundedRect(icon_rect, 24, 24)
            painter.fillPath(fallback, QColor(255, 210, 232, 235))
            painter.setPen(QColor(146, 66, 118, 230))
            painter.drawPath(fallback)

        if self.chat_status_text and time.monotonic() < self.chat_status_until:
            label_rect = QRectF(18, max(58, y - 34), self.width() - 36, 28)
            label = QPainterPath()
            label.addRoundedRect(label_rect, 12, 12)
            painter.fillPath(label, QColor(255, 248, 253, 232))
            painter.setPen(QColor(126, 66, 104))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
            painter.drawText(label_rect.adjusted(10, 0, -10, 0), Qt.AlignCenter | Qt.TextWordWrap, self.chat_status_text)
        painter.end()

    def paintGL(self):
        try:
            if getattr(self, 'city_mode', False):
                self.process_voice_events()
                self.process_barge_in_events()
                self.process_speech_events()
                self.process_chat_events()
                self.process_chat_advice_events()
                self.process_life_writing_events()
                self.process_reading_events()
                self.maybe_force_life_writing(time.monotonic())
                self.draw_city_scene()
                self.draw_city_locations()
                self.draw_city_hud()
                return

            if getattr(self, "home_icon_mode", False):
                self.process_godot_runtime_tick()
                self.write_godot_bridge()
                self.draw_home_icon_surface()
                self.draw_subtitle_bubble()
                return

            if not self.model:
                now = time.monotonic()
                self.process_life_writing_events()
                self.process_reading_events()
                self.maybe_force_life_writing(now)
                if self.room_mode:
                    self.draw_room_background()
                    self.draw_room_foreground()
                self.draw_subtitle_bubble()
                return

            now = time.monotonic()
            self.process_voice_events()
            self.process_barge_in_events()
            self.process_speech_events()
            self.process_chat_events()
            self.process_chat_advice_events()
            self.process_life_writing_events()
            self.process_reading_events()
            self.maybe_force_life_writing(now)
            self.update_dialogue_sequence()
            self.maybe_continue_free_talk()
            busy = (
                self.speech_input.is_busy()
                or self.chat.is_busy()
                or self.chat_advice.is_busy()
                or self.life_writer.is_busy()
                or self.voice.is_busy_or_playing()
                or self.behavior.is_speaking()
                or now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0)
            )
            self.drive.relationship_score = self.life.relationship_score
            self.life.attachment_need = self.drive.values.get("attachment_need", 28.0)
            self.drive.tick(busy=busy)
            self.tick_physiology_module(now=now, busy=busy)
            self.tick_heart_module(now=now, busy=busy)
            if hasattr(self, 'body_cycle'):
                self.body_cycle.tick(now=now)
            if hasattr(self, 'idle_scheduler'):
                idle_seconds = now - self.last_user_interaction_at
                energy = self.drive.values.get('energy', 50.0)
                self.idle_scheduler.tick(now=now, busy=busy, energy=energy, idle_seconds=idle_seconds)
            self.update_barge_in_monitor()
            if self.maybe_auto_enter_home_icon(now=now, busy=busy):
                self.draw_home_icon_surface()
                self.draw_subtitle_bubble()
                return
            if self.room_mode:
                self.update_room_activity(now)
                self.maybe_trigger_room_motion(now)

            speed = 0.08 + self.current_analysis.intensity * 0.10
            mixed_emo = self.mixer.update(speed=speed)
            render_weights = expressive_weights_for_render(
                EmotionAnalysis(
                    weights=mixed_emo,
                    intensity=self.current_analysis.intensity,
                    dominant=self.current_analysis.dominant,
                    speaking_energy=self.current_analysis.speaking_energy,
                    matched_tokens=self.current_analysis.matched_tokens,
                )
            )
            mixed_analysis = EmotionAnalysis(
                weights=render_weights,
                intensity=self.current_analysis.intensity,
                dominant=dominant_weight_emotion(self.current_analysis),
                speaking_energy=self.current_analysis.speaking_energy,
                matched_tokens=self.current_analysis.matched_tokens,
            )

            base_params = emotion_to_params(mixed_analysis)
            tracker = getattr(self, "mouse_tracker", None)
            attention = float(getattr(tracker, "focus_strength", 0.0) or 0.0) if tracker is not None else 0.0
            overlay_params = self.behavior.update(self.model, attention=attention)
            final_params = compose_params(base_params, overlay_params)
            apply_params(self.model, final_params)
            self.apply_room_model_transform(now)
            self._maybe_submit_stare_stimulus()

            live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
            try:
                self.model.Update()
            except Exception:
                pass
            late_params = {}
            late_params.update(self._motion_finished_reset_params(final_params))
            late_params.update(self._update_mouse_gaze_params(final_params, now=now))
            if late_params:
                apply_params(self.model, late_params)
            self._apply_touch_visual_params(final_params, now)
            late_mouth_params = self.behavior.build_late_mouth_params(now)
            if late_mouth_params:
                apply_params(self.model, late_mouth_params)
            try:
                self.model.Draw()
            except Exception:
                pass
            if self.room_mode:
                self.draw_room_background(behind_model=True)
                self.draw_room_foreground()
            self.draw_subtitle_bubble()
            self.draw_touch_zone_editor_overlay()
        except Exception:
            now = time.monotonic()
            last_error_at = getattr(self, "_last_paint_error_at", 0.0)
            if now - last_error_at > 3.0:
                self._last_paint_error_at = now
                self.runtime_logger("PAINT_ERROR", traceback.format_exc())

    def resizeGL(self, w, h):
        if self.model:
            self.model.Resize(w, h)

    def resizeEvent(self, event):
        self.layout_chat_input()
        super().resizeEvent(event)

    def show_right_click_menu(self, global_pos):
        if hasattr(self, "mark_user_active"):
            self.mark_user_active("context_menu")
        self.ui_interaction_busy_until = time.monotonic() + 20.0
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #fff6fb;
                color: #543247;
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 6px;
                padding: 4px;
                font: 10pt "Microsoft YaHei UI";
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #ffe8f3;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(235, 144, 188, 150);
                margin: 4px 8px;
            }
        """)

        # API settings action
        api_action = QAction("API 设置", self)
        api_action.triggered.connect(lambda: QTimer.singleShot(0, self.open_api_settings_dialog))
        menu.addAction(api_action)

        # Schedule action
        schedule_action = QAction("作息表", self)
        schedule_action.triggered.connect(lambda: QTimer.singleShot(0, self.open_schedule_dialog))
        menu.addAction(schedule_action)

        menu.addSeparator()

        # TTS provider submenu
        tts_menu = menu.addMenu("TTS 音色")
        current_provider = str(self.llm_config.get("tts_provider") or "volcengine")

        provider_group = QActionGroup(self)
        provider_group.setExclusive(True)

        volc_action = QAction("火山云服务", self)
        volc_action.setCheckable(True)
        volc_action.setChecked(current_provider != "local")
        volc_action.triggered.connect(lambda: self._switch_tts_provider("volcengine"))
        provider_group.addAction(volc_action)
        tts_menu.addAction(volc_action)

        local_action = QAction("本地模型", self)
        local_action.setCheckable(True)
        local_action.setChecked(current_provider == "local")
        local_action.triggered.connect(lambda: self._switch_tts_provider("local"))
        provider_group.addAction(local_action)
        tts_menu.addAction(local_action)

        if current_provider == "local":
            tts_menu.addSeparator()
            info_action = QAction("情绪由对话自动匹配", self)
            info_action.setEnabled(False)
            tts_menu.addAction(info_action)

        self._context_menu = menu
        menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self._release_context_menu))
        menu.popup(global_pos)

    def _release_context_menu(self):
        menu = getattr(self, "_context_menu", None)
        self._context_menu = None
        self.ui_interaction_busy_until = time.monotonic() + 2.0
        if menu is not None:
            menu.deleteLater()

    def _switch_tts_provider(self, provider):
        self.llm_config["tts_provider"] = provider
        if hasattr(self, "voice"):
            self.voice.update_config(self.llm_config)
        if hasattr(self, "persist_llm_config"):
            try:
                self.persist_llm_config()
            except Exception as exc:
                print("TTS_PROVIDER_SAVE_ERROR =", exc)
        label = "本地模型" if provider == "local" else "火山云服务"
        if hasattr(self, "show_chat_status"):
            self.show_chat_status(f"TTS 已切换为: {label}", seconds=2.5)
        print("TTS_PROVIDER_SWITCHED =", provider)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_right_click_menu(event.globalPos())
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            if getattr(self, "home_icon_mode", False):
                rect = getattr(self, "home_icon_rect", None)
                if rect is not None and rect.contains(event.pos()):
                    self.start_godot_room_game()
                    event.accept()
                    return
            if getattr(self, 'city_mode', False):
                if self.city_mouse_press(event.pos()):
                    event.accept()
                    return
            press_zone = ""
            if not getattr(self, "home_icon_mode", False) and not getattr(self, "city_mode", False):
                try:
                    press_zone = self._hit_test_touch_zone(event.pos())
                except Exception:
                    press_zone = ""
            self._left_press_pos = event.pos()
            self._left_press_global = event.globalPos()
            self._left_press_started_at = time.monotonic()
            self._left_press_zone = press_zone
            self._drag_started_at = 0.0
            self._drag_moved = False
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            print(
                "MOUSE_LEFT_PRESS =",
                {
                    "x": int(event.pos().x()),
                    "y": int(event.pos().y()),
                    "zone": press_zone,
                },
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, 'city_mode', False):
            if self.city_mouse_move(event.pos()):
                event.accept()
                return
        if event.buttons() & Qt.LeftButton and self.drag_offset is not None:
            if not getattr(self, "_drag_moved", False):
                press_pos = getattr(self, "_left_press_pos", None)
                if press_pos is not None:
                    dx = float(event.pos().x() - press_pos.x())
                    dy = float(event.pos().y() - press_pos.y())
                    distance = math.hypot(dx, dy)
                    threshold = float(getattr(self, "_drag_threshold_px", 8.0) or 8.0)
                    if distance >= threshold:
                        self._drag_moved = True
                        self._drag_started_at = time.monotonic()
                        self._submit_drag_stimulus("drag_start", event)
            if getattr(self, "_drag_moved", False):
                self.move(event.globalPos() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.drag_offset is not None:
                if getattr(self, "_drag_moved", False):
                    self._submit_drag_stimulus("drag_drop", event)
                elif not getattr(self, "home_icon_mode", False) and not getattr(self, "city_mode", False):
                    self._submit_touch_stimulus(
                        event.pos(),
                        zone_hint=str(getattr(self, "_left_press_zone", "") or ""),
                        phase="release",
                    )
            self.drag_offset = None
            self._left_press_pos = None
            self._left_press_global = None
            self._left_press_zone = ""
            self._left_press_started_at = 0.0
            self._drag_started_at = 0.0
            self._drag_moved = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_mouse_gaze_params(self, final_params, now=None):
        if getattr(self, "city_mode", False) or getattr(self, "home_icon_mode", False):
            return {}
        tracker = getattr(self, "mouse_tracker", None)
        if tracker is None:
            return {}
        late_params = {}
        try:
            cursor_pos = self.cursor().pos()
            frame_geo = self.frameGeometry()
            tracker.update(
                cursor_pos.x(),
                cursor_pos.y(),
                frame_geo.x(),
                frame_geo.y(),
                frame_geo.width(),
                frame_geo.height(),
            )
            now = time.monotonic() if now is None else float(now)
            in_range = bool(getattr(tracker, "in_range", False)) or float(getattr(tracker, "focus_strength", 0.0) or 0.0) >= 0.08
            self._mouse_attention_in_range = in_range
            if in_range:
                last_stop_at = float(getattr(self, "_last_attention_motion_stop_at", 0.0) or 0.0)
                if now - last_stop_at >= 1.0 and hasattr(self, "behavior"):
                    self._last_attention_motion_stop_at = now
                    self.behavior.next_idle_motion_at = max(self.behavior.next_idle_motion_at, now + 1.2)
            engagement = tracker.focus_strength
            if not in_range and engagement <= 0.001:
                return {}
            eye_x = final_params.get(StandardParams.ParamEyeBallX, 0.0)
            eye_y = final_params.get(StandardParams.ParamEyeBallY, 0.0)
            gaze_x, gaze_y = tracker.get_gaze_blend(eye_x, eye_y, blend=0.985)
            late_params[StandardParams.ParamEyeBallX] = gaze_x
            late_params[StandardParams.ParamEyeBallY] = gaze_y
            if engagement > 0.001:
                mx = tracker.smoothed_x
                my = tracker.smoothed_y
                # Late-apply only gaze-related parameters, so Live2D motions keep
                # their body/arm continuity underneath the attention layer.
                late_params[StandardParams.ParamEyeBallX] = final_params.get(StandardParams.ParamEyeBallX, 0.0) * (1.0 - 0.92 * engagement) + mx * 1.42 * engagement
                late_params[StandardParams.ParamEyeBallY] = final_params.get(StandardParams.ParamEyeBallY, 0.0) * (1.0 - 0.92 * engagement) + (-my) * 1.34 * engagement
                late_params[StandardParams.ParamAngleX] = final_params.get(StandardParams.ParamAngleX, 0.0) * (1.0 - 0.62 * engagement) + mx * 16.0 * engagement
                late_params[StandardParams.ParamAngleY] = final_params.get(StandardParams.ParamAngleY, 0.0) * (1.0 - 0.62 * engagement) + (-my) * 11.5 * engagement
        except Exception:
            pass
        return late_params

    def _maybe_submit_stare_stimulus(self):
        if getattr(self, "city_mode", False) or getattr(self, "home_icon_mode", False):
            return False
        tracker = getattr(self, "mouse_tracker", None)
        dispatcher = getattr(self, "stimulus_dispatcher", None)
        if tracker is None or dispatcher is None:
            return False
        duration = tracker.consume_stare_event()
        if duration is None:
            return False
        stimulus = Stimulus(
            type="stare",
            intensity=0.35,
            emotion_hint="surprise",
            duration=duration,
            source="mouse",
            memory_worthy=True,
            should_talk=True,
            cooldown_key="stare",
            meta={"cooldown_seconds": 90.0},
        )
        return dispatcher.submit(stimulus)

    def _apply_touch_visual_params(self, final_params, now):
        visual = getattr(self, "_touch_visual", None)
        if visual is None:
            return False
        if not bool(getattr(visual, "active", False)):
            return False
        try:
            before = dict(final_params)
            visual.apply_to_params(final_params, now=now)
            param_ids = getattr(self, "_live2d_param_ids", None)
            if param_ids is None:
                try:
                    param_ids = set(self.model.GetParamIds())
                except Exception:
                    param_ids = set()
                self._live2d_param_ids = param_ids
            for key, value in final_params.items():
                delta = float(value) - float(before.get(key, 0.0) or 0.0)
                if abs(delta) <= 1e-5:
                    continue
                if param_ids and key not in param_ids:
                    continue
                try:
                    self.model.SetParameterValue(key, value, 1)
                except Exception:
                    pass
            return True
        except Exception:
            pass
        return False

    def _motion_finished_reset_params(self, final_params):
        try:
            if not self.model or not self.model.IsMotionFinished():
                return {}
        except Exception:
            return {}
        return {
            PARAM_ARM_LA: final_params.get(PARAM_ARM_LA, 0.0),
            PARAM_ARM_RA: final_params.get(PARAM_ARM_RA, 0.0),
        }

    def _hit_test_touch_zone(self, pos):
        configured_zone = hit_test_touch_zone(
            getattr(self, "touch_zone_config", {}),
            float(pos.x()),
            float(pos.y()),
            self.width(),
            self.height(),
        )
        if configured_zone:
            return configured_zone
        w = float(self.width() or 0)
        h = float(self.height() or 0)
        if w <= 1 or h <= 1:
            return ""
        nx = (float(pos.x()) - w / 2.0) / max(1.0, w / 2.0)
        ny = (float(pos.y()) - h / 2.0) / max(1.0, h / 2.0)
        if abs(nx) > 0.94 or ny > 0.82 or ny < -0.95:
            return ""
        if ny < -0.50:
            return "hair"
        if ny < -0.14:
            return "cheek" if abs(nx) < 0.58 else "arm"
        if ny < -0.02:
            if abs(nx) < 0.22:
                return "neck"
            return "arm" if abs(nx) > 0.56 else "cheek"
        if ny < 0.24:
            if abs(nx) > 0.52:
                return "arm"
            return "chest" if ny < 0.08 else "belly"
        if ny < 0.62:
            if abs(nx) < 0.18:
                return "private"
            if abs(nx) < 0.52:
                return "thigh"
            if abs(nx) < 0.72:
                return "belly"
            return "arm"
        if ny < 0.78:
            if abs(nx) < 0.42:
                return "calf"
        if ny < 0.88:
            if abs(nx) < 0.40:
                return "foot"
            return ""
        return ""

    def _commit_touch_zone_editor_rect(self, end_pos):
        start_pos = getattr(self, "touch_zone_editor_drag_start", None)
        if start_pos is None:
            return False
        rect = normalize_zone_rect(start_pos, end_pos, self.width(), self.height())
        min_w = abs(float(rect["x2"]) - float(rect["x1"]))
        min_h = abs(float(rect["y2"]) - float(rect["y1"]))
        if min_w < 0.015 or min_h < 0.015:
            self.show_chat_status("框太小了，已忽略。", seconds=1.6)
            return False
        zones = self.touch_zone_config.setdefault("zones", {})
        zones.setdefault(self.touch_zone_editor_selected_key, []).append(rect)
        self.show_chat_status(
            f"已添加 {touch_zone_label(self.touch_zone_editor_selected_key)} 区域。F7 保存。",
            seconds=2.0,
        )
        self.update()
        return True

    def draw_touch_zone_editor_overlay(self):
        if not getattr(self, "touch_zone_editor_enabled", False):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 10, 18, 24))
        zones = dict(getattr(self, "touch_zone_config", {}).get("zones", {}) or {})
        for key, _label, _color in TOUCH_ZONE_ORDER:
            color = QColor(touch_zone_color(key))
            color.setAlpha(68 if key != getattr(self, "touch_zone_editor_selected_key", "") else 96)
            border = QColor(color)
            border.setAlpha(188)
            for rect in zones.get(key, []):
                x, y, w, h = rect_from_normalized(rect, self.width(), self.height())
                box = QRectF(x, y, w, h)
                painter.fillRect(box, color)
                painter.setPen(border)
                painter.drawRoundedRect(box, 6, 6)
                painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
                painter.drawText(box.adjusted(4, 2, -4, -2), Qt.AlignLeft | Qt.AlignTop, touch_zone_label(key))
        panel_width = min(212.0, max(176.0, self.width() * 0.24))
        panel_height = 132.0
        panel_left = 12.0
        panel_top = 72.0
        panel_rect = QRectF(panel_left, panel_top, panel_width, min(panel_height, self.height() - panel_top - 12.0))
        panel_path = QPainterPath()
        panel_path.addRoundedRect(panel_rect, 14, 14)
        painter.fillPath(panel_path, QColor(255, 248, 253, 214))
        painter.setPen(QColor(151, 66, 115, 220))
        painter.drawPath(panel_path)
        painter.setPen(QColor(92, 49, 74))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        painter.drawText(panel_rect.adjusted(12, 10, -12, 0), "触摸分区检查")
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        lines = [
            "F6 关闭",
            "仅检查自动分区",
            "点击仍会正常触发触摸",
        ]
        for index, line in enumerate(lines):
            text_y = panel_rect.top() + 34 + index * 20
            painter.drawText(QRectF(panel_rect.left() + 12, text_y, panel_rect.width() - 24, 16), Qt.AlignLeft | Qt.AlignVCenter, line)
        list_top = panel_rect.top() + 92
        col_gap = 10.0
        col_width = (panel_rect.width() - 24.0 - col_gap) / 2.0
        row_height = 16.0
        for index, (key, _label, _color) in enumerate(TOUCH_ZONE_ORDER):
            color = QColor(touch_zone_color(key))
            color.setAlpha(150)
            column = 0 if index < 5 else 1
            row = index if index < 5 else index - 5
            base_x = panel_rect.left() + 12 + column * (col_width + col_gap)
            base_y = list_top + row * row_height
            painter.fillRect(QRectF(base_x, base_y + 3, 10, 10), color)
            painter.setPen(QColor(96, 68, 84))
            painter.drawText(
                QRectF(base_x + 16, base_y, col_width - 16, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                touch_zone_label(key),
            )
        painter.end()

    def _submit_touch_stimulus(self, pos, zone_hint="", phase=""):
        zone = self._hit_test_touch_zone(pos)
        if not zone and zone_hint:
            press_pos = getattr(self, "_left_press_pos", None)
            move_dist = 9999.0
            if press_pos is not None:
                dx = float(pos.x() - press_pos.x())
                dy = float(pos.y() - press_pos.y())
                move_dist = math.hypot(dx, dy)
            if move_dist <= max(10.0, float(getattr(self, "_drag_threshold_px", 8.0) or 8.0) * 1.5):
                zone = zone_hint
        if not zone:
            print(
                "TOUCH_STIMULUS_MISS =",
                {
                    "phase": phase or "unknown",
                    "x": int(pos.x()),
                    "y": int(pos.y()),
                    "hint": zone_hint,
                },
            )
            return False
        now = time.monotonic()
        history = list(getattr(self, "_touch_history", []) or [])
        previous_touch_at = float(history[-1]) if history else 0.0
        interval = now - previous_touch_at if previous_touch_at > 0 else 9999.0
        history.append(now)
        history = [item for item in history if now - float(item) <= 2.0][-12:]
        self._touch_history = history
        self._previous_touch_at = previous_touch_at
        self._last_touch_at = now
        count = len(history)
        stimulus = Stimulus(
            type="touch",
            intensity=min(1.0, 0.42 + count * 0.08),
            emotion_hint="joy",
            zone=zone,
            source="mouse",
            memory_worthy=True,
            should_talk=count <= 3,
            cooldown_key="touch",
            meta={
                "zone": zone,
                "pos": (float(pos.x()), float(pos.y())),
                "norm_pos": (
                    round(float(pos.x()) / max(1.0, float(self.width() or 1.0)), 4),
                    round(float(pos.y()) / max(1.0, float(self.height() or 1.0)), 4),
                ),
                "count": count,
                "interval": round(interval, 3),
            },
        )
        print(
            "TOUCH_STIMULUS_HIT =",
            {
                "phase": phase or "unknown",
                "zone": zone,
                "count": count,
                "interval": round(interval, 3),
            },
        )
        dispatcher = getattr(self, "stimulus_dispatcher", None)
        if dispatcher is not None:
            dispatched = dispatcher.submit(stimulus)
            print("TOUCH_STIMULUS_DISPATCH =", {"ok": bool(dispatched), "zone": zone})
            return dispatched
        dispatched = self.on_stimulus(stimulus)
        print("TOUCH_STIMULUS_DISPATCH =", {"ok": bool(dispatched), "zone": zone})
        return dispatched

    def _submit_drag_stimulus(self, kind, event=None):
        press_global = getattr(self, "_left_press_global", None)
        if press_global is None or event is None:
            return False
        dx = float(event.globalPos().x() - press_global.x())
        dy = float(event.globalPos().y() - press_global.y())
        distance = math.hypot(dx, dy)
        elapsed = max(0.05, time.monotonic() - float(getattr(self, "_left_press_started_at", 0.0) or 0.0))
        velocity = distance / elapsed
        is_drop = kind == "drag_drop"
        stimulus = Stimulus(
            type=kind,
            intensity=max(0.15, min(1.0, distance / 220.0)),
            emotion_hint="fear" if is_drop and velocity > 850.0 else "surprise",
            source="drag",
            memory_worthy=is_drop,
            should_talk=is_drop and velocity > 950.0,
            cooldown_key="drag",
            meta={
                "distance": round(distance, 2),
                "velocity": round(velocity, 2),
            },
        )
        dispatcher = getattr(self, "stimulus_dispatcher", None)
        if dispatcher is not None:
            return dispatcher.submit(stimulus)
        return self.on_stimulus(stimulus)
