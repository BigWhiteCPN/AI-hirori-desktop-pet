import os
import math
import re
import sys
import time
import traceback

import live2d.v3 as live2d
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath

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
)
from persona_pet.voicevox import estimate_sentence_seconds


class PetRenderMixin:
    def initializeGL(self):
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
        except Exception:
            self.model = None
            self.runtime_logger("LIVE2D_INIT_ERROR", traceback.format_exc())
            self.show_chat_status("Live2D 加载失败，查看 logs/persona_pet.log", seconds=8.0)

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

    def paintGL(self):
        try:
            if not self.model:
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
            self.update_dialogue_sequence()
            self.maybe_continue_free_talk()
            busy = (
                self.speech_input.is_busy()
                or self.chat.is_busy()
                or self.chat_advice.is_busy()
                or self.life_writer.is_busy()
                or self.voice.is_busy_or_playing()
                or self.behavior.is_speaking()
            )
            self.drive.tick(busy=busy)
            self.tick_physiology_module(now=now, busy=busy)
            self.tick_heart_module(now=now, busy=busy)
            self.maybe_start_life_writing()
            self.maybe_start_proactive_chat()
            self.update_barge_in_monitor()
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
            overlay_params = self.behavior.update(self.model)
            final_params = compose_params(base_params, overlay_params)
            apply_params(self.model, final_params)
            self.apply_room_model_transform(now)

            live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
            self.model.Update()
            late_mouth_params = self.behavior.build_late_mouth_params(now)
            if late_mouth_params:
                apply_params(self.model, late_mouth_params)
            self.model.Draw()
            if self.room_mode:
                self.draw_room_background(behind_model=True)
                self.draw_room_foreground()
            self.draw_subtitle_bubble()
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

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.open_api_settings_dialog()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_offset is not None:
            self.move(event.globalPos() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)




