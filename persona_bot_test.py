import faulthandler
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

faulthandler.enable()

os.environ["QT_OPENGL"] = "desktop"
os.environ["QT_GL_MODULE"] = "desktop"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from PyQt5.QtCore import QObject, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRegion, QSurfaceFormat
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QMenu,
    QOpenGLWidget,
    QProgressDialog,
    QToolButton,
)

import live2d.v3 as live2d

from persona_pet.agent_commands import AgentCommandMixin
from persona_pet.economy import EconomyMixin
from persona_pet.items import BackpackMixin
from persona_pet.todo import TodoMixin
from persona_pet.city_mode import CityModeMixin, CITY_WINDOW_WIDTH, CITY_WINDOW_HEIGHT
from persona_pet.body_cycle import BodyCycleSystem
from persona_pet.emotion_engine import EmotionEngine
from persona_pet.episodic_memory import EpisodicMemoryStore
from persona_pet.idle_scheduler import IdleBehavior, IdleScheduler
from persona_pet.metacognition import MetacognitionEngine
from persona_pet.pattern_detector import PatternDetector
from persona_pet.personality_growth import PersonalityGrowth
from persona_pet.subtext_analyzer import analyze_subtext
from persona_pet.time_awareness import TimeAwareness
from persona_pet.behavior import (
    BehaviorController,
    EmotionAnalysis,
    EmotionMixer,
    HIYORI_MOTION_TEMPLATES,
    TEST_TEXTS,
    llm_emotion_from_text,
    load_motion_groups,
    reconcile_llm_emotion,
)
from persona_pet.browser_agent import SafeBrowserAgent
from persona_pet.chat_advice import ChatAdviceController
from persona_pet.chat_capture import ChatAdviceCaptureMixin
from persona_pet.heart import HeartMixin
from persona_pet.library_dialogs import LifeLibraryDialog
from persona_pet.llm_config import (
    DEFAULT_LOCAL_LLM_BASE_URL,
    DEFAULT_QWEN_TTS_MODEL_ID,
    build_default_llm_config,
    load_llm_config_file,
    resolve_project_path,
    save_llm_config_file,
)
from persona_pet.local_llm import (
    apply_local_llm_environment,
    is_local_llm_config,
    normalize_local_llm_config,
    ollama_executable,
    ollama_model_installed,
    pull_ollama_model,
    resolve_local_models_dir,
    start_ollama_server,
)
from persona_pet.llm_client import LLMChatController
from persona_pet.life_system import PersonaDriveSystem, PersonaLifeSystem
from persona_pet.life_writing import LifeWritingController
from persona_pet.reading import ReadingController
from persona_pet.memory import PersonaMemoryStore
from persona_pet.godot_bridge import GodotBridgeMixin
from persona_pet.room_mode import RoomModeMixin
from persona_pet.runtime import AgentRuntime
from persona_pet.pet_dialogue import PetDialogueMixin
from persona_pet.pet_interactions import PetInteractionMixin
from persona_pet.pet_render import PetRenderMixin
from persona_pet.mouse_tracker import MouseTracker
from persona_pet.pet_workflow import PetWorkflowMixin
from persona_pet.physiology import PhysiologyMixin
from persona_pet.error_reporter import report_exception
from persona_pet.profile_runtime import (
    apply_runtime_profile,
    profile_config_path as build_profile_config_path,
    profile_output_dir as build_profile_output_dir,
)
from persona_pet.stimulus import Stimulus
from persona_pet.stimulus_dispatcher import StimulusDispatcher
from persona_pet.speech import BargeInController, SpeechInputController
from persona_pet.status_dialogs import DriveStatusDialog, MemoryGraphDialog, RelationshipDialog
from persona_pet.touch_visual import TouchVisual
from persona_pet.touch_zone_config import (
    AUTO_TOUCH_ZONE_TEMPLATE_VERSION,
    TOUCH_ZONE_ORDER,
    build_auto_touch_zone_config,
    has_touch_zone_rects,
    load_touch_zone_config,
    save_touch_zone_config,
    touch_zone_label,
)
from persona_pet.ui_dialogs import ApiSettingsDialog, FirstRunDialog, MiniGameDialog
from persona_pet.user_profile import UserProfileMixin
from persona_pet.voicevox import VoicevoxController
from persona_pet.voicevox import config_bool
from persona_pet.activity_monitor import ActivityMonitor


if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "persona_pet.log")


def log_runtime(*parts):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        message = " ".join(str(part) for part in parts)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except Exception:
        pass


def setup_windowed_logging():
    if not getattr(sys, "frozen", False):
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_file
        if sys.stderr is None:
            sys.stderr = log_file
    except Exception as exc:
        report_exception(logger=log_runtime, component="app", operation="setup_windowed_logging", exc=exc)


setup_windowed_logging()
MODEL_JSON_PATH = os.path.join(
    BASE_DIR,
    "hiyori_pro_zh",
    "hiyori_pro_zh",
    "runtime",
    "hiyori_pro_t11.model3.json",
)
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 780
ROOM_WINDOW_WIDTH = 760
ROOM_WINDOW_HEIGHT = 570
ROOM_MODEL_SCALE = 0.72
ROOM_ASSET_DIR = os.path.join(BASE_DIR, "assets", "room")
ROOM_LAYOUT_PATH = os.path.join(ROOM_ASSET_DIR, "room_layout.json")
ROOM_MODEL_Z = 50
FRAME_INTERVAL_MS = 16
DIALOGUE_ROLE_LISTENER = "listener"
DIALOGUE_ROLE_SPEAKER = "speaker"


def show_startup_message(parent, title, text, icon=QMessageBox.Information):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(QMessageBox.Ok)
    box.setStyleSheet(
        """
        QMessageBox {
            background: #fff6fb;
            color: #543247;
            font: 10pt "Microsoft YaHei UI";
        }
        QMessageBox QLabel {
            color: #543247;
            min-width: 320px;
        }
        QMessageBox QPushButton {
            min-width: 88px;
            min-height: 30px;
            border-radius: 8px;
            border: 1px solid rgba(210, 98, 152, 220);
            padding: 4px 14px;
            background: #ffffff;
            color: #8f2d5a;
            font-weight: 600;
        }
        QMessageBox QPushButton:hover {
            background: #ffe8f3;
        }
        """
    )
    box.exec_()


def prepare_local_llm_if_needed(config, parent=None):
    if not is_local_llm_config(config):
        return True
    config = normalize_local_llm_config(config)
    models_dir = apply_local_llm_environment(BASE_DIR, config)
    model = str(config.get("model") or config.get("local_llm_model") or DEFAULT_LOCAL_LLM_MODEL).strip() or DEFAULT_LOCAL_LLM_MODEL
    base_url = str(config.get("base_url") or config.get("local_llm_base_url") or DEFAULT_LOCAL_LLM_BASE_URL).rstrip("/")

    if not ollama_executable():
        show_startup_message(
            parent,
            "本地模型不可用",
            "当前选择了本地 Qwen3 4B，但没有检测到 Ollama。\n请先安装 Ollama，或编辑 persona_llm_config.json 切回 DeepSeek 云端模型。",
            icon=QMessageBox.Warning,
        )
        return False

    if not start_ollama_server(BASE_DIR, config):
        show_startup_message(
            parent,
            "本地模型不可用",
            f"无法连接本机 Ollama 服务：{base_url}\n请确认 Ollama 可以正常启动。",
            icon=QMessageBox.Warning,
        )
        return False

    if ollama_model_installed(base_url, model):
        return True

    if not bool(config.get("local_llm_auto_pull", True)):
        show_startup_message(
            parent,
            "本地模型未下载",
            f"没有检测到 {model}。\n请运行 ollama pull {model}，或在设置里开启自动下载。\n模型目录：{models_dir or resolve_local_models_dir(BASE_DIR, config)}",
            icon=QMessageBox.Warning,
        )
        return False

    progress = QProgressDialog(parent)
    progress.setWindowTitle("下载本地模型")
    progress.setLabelText(f"正在下载 {model} 到项目模型目录...\n{models_dir or resolve_local_models_dir(BASE_DIR, config)}")
    progress.setCancelButton(None)
    progress.setRange(0, 0)
    progress.setMinimumWidth(520)
    progress.setWindowModality(Qt.ApplicationModal)
    progress.show()
    QApplication.processEvents()

    def update_progress(line):
        display = line[-160:] if line else "正在下载..."
        progress.setLabelText(f"正在下载 {model} 到项目模型目录...\n{display}")
        QApplication.processEvents()

    try:
        pull_ollama_model(BASE_DIR, config, progress_callback=update_progress)
    except Exception as exc:
        progress.close()
        show_startup_message(
            parent,
            "本地模型下载失败",
            f"下载 {model} 失败：{exc}\n可以手动运行 ollama pull {model} 后再启动。",
            icon=QMessageBox.Warning,
        )
        return False
    progress.close()
    return True


def prepare_local_tts_model_if_needed(config, parent=None):
    if str((config or {}).get("tts_provider") or "").strip().lower() != "local":
        return True
    try:
        import faster_qwen3_tts  # noqa: F401
        from persona_pet.qwen_tts_engine import download_qwen_tts_model, qwen_tts_model_ready
    except ImportError as exc:
        show_startup_message(
            parent,
            "本地 TTS 依赖缺失",
            f"当前选择了本地 QwenTTS，但缺少依赖：{exc}\n请先安装 requirements_local_tts.txt。",
            icon=QMessageBox.Warning,
        )
        return False

    model_path = resolve_project_path(BASE_DIR, (config or {}).get("qwen_tts_model_path"))
    if not model_path:
        model_path = os.path.join(BASE_DIR, "third_party", "qwen_tts_model")
    if qwen_tts_model_ready(model_path):
        return True

    if not config_bool(config, "qwen_tts_auto_download", True):
        show_startup_message(
            parent,
            "本地 TTS 模型未下载",
            f"没有检测到 QwenTTS 模型。\n请下载到：{model_path}\n或在设置里开启自动下载。",
            icon=QMessageBox.Warning,
        )
        return False

    model_id = str((config or {}).get("qwen_tts_model_id") or DEFAULT_QWEN_TTS_MODEL_ID).strip() or DEFAULT_QWEN_TTS_MODEL_ID
    progress = QProgressDialog(parent)
    progress.setWindowTitle("下载本地 TTS 模型")
    progress.setLabelText(f"正在下载 {model_id} 到项目模型目录...\n{model_path}")
    progress.setCancelButton(None)
    progress.setRange(0, 0)
    progress.setMinimumWidth(560)
    progress.setWindowModality(Qt.ApplicationModal)
    progress.show()
    QApplication.processEvents()

    def update_progress(line):
        display = str(line or "正在下载...")[-180:]
        progress.setLabelText(f"正在下载 {model_id} 到项目模型目录...\n{display}")
        QApplication.processEvents()

    try:
        download_qwen_tts_model(model_id, model_path, progress_callback=update_progress)
    except Exception as exc:
        progress.close()
        show_startup_message(
            parent,
            "本地 TTS 模型下载失败",
            f"下载 {model_id} 失败：{exc}\n可以手动下载后放到：{model_path}",
            icon=QMessageBox.Warning,
        )
        return False
    progress.close()
    return True


class StartupLoadingDialog(QDialog):
    def __init__(self, parent=None, wait_for_voice=False):
        super().__init__(parent)
        self._title = "唤醒角色"
        self._subtitle = "正在依次准备角色界面、动作模型和语音能力。"
        self._hint = "启动完成后会自动进入桌宠界面。"
        self._tick = 0
        self._minimum_visible_seconds = 3.2 if wait_for_voice else 2.0
        self._shown_at = 0.0
        self._window_done = False
        self._window_success = False
        self._model_done = False
        self._model_success = False
        self._voice_required = bool(wait_for_voice)
        self._voice_done = not self._voice_required
        self._voice_success = not self._voice_required
        self._closed = False
        self._manual_position = False

        self.setWindowTitle("唤醒角色")
        self.setModal(False)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_animation)
        self._timer.start(32)

    def _update_rounded_mask(self):
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 34, 34)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def showEvent(self, event):
        super().showEvent(event)
        self._shown_at = time.monotonic()
        self._update_rounded_mask()
        if not self._manual_position:
            parent = self.parentWidget()
            if parent is not None:
                parent_rect = parent.frameGeometry()
                self.resize(parent.width(), parent.height())
                self.move(
                    parent_rect.center().x() - self.width() // 2,
                    parent_rect.center().y() - self.height() // 2,
                )
                return
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            rect = screen.availableGeometry()
            self.move(rect.center().x() - self.width() // 2, rect.center().y() - self.height() // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rounded_mask()

    def _advance_animation(self):
        self._tick = (self._tick + 1) % 360
        self.update()
        self._maybe_finish()

    def mark_window_ready(self, success=True):
        self._window_done = True
        self._window_success = bool(success)
        self.update()
        self._maybe_finish()

    def mark_model_ready(self, success=True):
        self._model_done = True
        self._model_success = bool(success)
        self.update()
        self._maybe_finish()

    def mark_voice_ready(self, success=True):
        self._voice_done = True
        self._voice_success = bool(success)
        self.update()
        self._maybe_finish()

    def _all_loading_done(self):
        return self._window_done and self._model_done and self._voice_done

    def _status_text(self):
        if not self._window_done:
            return "正在准备角色界面..."
        if not self._model_done:
            return "正在加载 Live2D 动作模型..."
        if self._voice_required and not self._voice_done:
            return "正在预热语音能力..."
        if self._voice_required and not self._voice_success:
            return "语音预热未完成，正在进入桌宠界面..."
        if not self._model_success:
            return "模型加载失败，正在进入错误处理..."
        return "准备完成，马上进入桌宠界面..."

    def _step_state(self, done, success=True):
        if done and success:
            return ("已完成", QColor(76, 166, 120), QColor(236, 255, 244, 230))
        if done and not success:
            return ("已跳过", QColor(207, 123, 76), QColor(255, 245, 238, 230))
        return ("进行中", QColor(214, 101, 154), QColor(255, 238, 246, 230))

    def _maybe_finish(self):
        if self._closed or not self._all_loading_done():
            return
        if (time.monotonic() - self._shown_at) < self._minimum_visible_seconds:
            return
        self._closed = True
        self._timer.stop()
        self.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 244, 250, 255))

        panel_rect = QRectF(14, 14, self.width() - 28, self.height() - 28)
        shadow_rect = QRectF(panel_rect)
        shadow_rect.translate(0, 8)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, 36, 36)
        painter.fillPath(shadow_path, QColor(88, 47, 74, 52))

        gradient = QLinearGradient(panel_rect.left(), panel_rect.top(), panel_rect.right(), panel_rect.bottom())
        gradient.setColorAt(0.0, QColor(255, 247, 252, 248))
        gradient.setColorAt(0.38, QColor(255, 239, 247, 244))
        gradient.setColorAt(1.0, QColor(255, 226, 239, 242))
        panel_path = QPainterPath()
        panel_path.addRoundedRect(panel_rect, 36, 36)
        painter.fillPath(panel_path, gradient)
        painter.setPen(QPen(QColor(229, 133, 180, 205), 1.4))
        painter.drawPath(panel_path)

        content_top = panel_rect.top() + max(26.0, (panel_rect.height() - 384.0) / 2.0)

        badge_rect = QRectF(panel_rect.left() + 28, content_top, 104, 32)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 16, 16)
        painter.fillPath(badge_path, QColor(255, 255, 255, 198))
        painter.setPen(QColor(170, 88, 130))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        painter.drawText(badge_rect, Qt.AlignCenter, "唤醒")

        spinner_center_x = panel_rect.left() + 100
        spinner_center_y = content_top + 112
        spinner_rect = QRectF(spinner_center_x - 42, spinner_center_y - 42, 84, 84)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(248, 208, 226, 188), 10))
        painter.drawEllipse(spinner_rect)

        painter.setPen(QPen(QColor(225, 104, 160), 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(spinner_rect, int((-self._tick - 20) * 16), 112 * 16)

        orbit_radius = 56
        for index in range(3):
            angle = math.radians(self._tick * 1.6 + index * 120.0)
            dot_x = spinner_center_x + math.cos(angle) * orbit_radius
            dot_y = spinner_center_y + math.sin(angle) * orbit_radius * 0.62
            radius = 7 if index == 0 else 5
            alpha = 240 if index == 0 else 168
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(237, 112, 167, alpha))
            painter.drawEllipse(QRectF(dot_x - radius, dot_y - radius, radius * 2, radius * 2))

        painter.setPen(QColor(96, 52, 77))
        painter.setFont(QFont("Microsoft YaHei UI", 17, QFont.Bold))
        painter.drawText(
            QRectF(panel_rect.left() + 172, content_top + 40, panel_rect.width() - 206, 34),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._title,
        )

        painter.setPen(QColor(143, 73, 110))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        painter.drawText(
            QRectF(panel_rect.left() + 172, content_top + 80, panel_rect.width() - 206, 64),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            self._subtitle,
        )

        status_rect = QRectF(panel_rect.left() + 28, content_top + 196, panel_rect.width() - 56, 46)
        status_path = QPainterPath()
        status_path.addRoundedRect(status_rect, 18, 18)
        painter.fillPath(status_path, QColor(255, 255, 255, 198))
        painter.setPen(QColor(163, 82, 122))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        painter.drawText(
            status_rect.adjusted(18, 0, -18, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._status_text(),
        )

        painter.setPen(QColor(176, 101, 134))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(
            QRectF(panel_rect.left() + 28, content_top + 252, panel_rect.width() - 56, 84),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
            self._hint,
        )

        steps = [
            ("角色界面", *self._step_state(self._window_done, self._window_success)),
            ("动作模型", *self._step_state(self._model_done, self._model_success)),
            ("语音能力", *self._step_state(self._voice_done, self._voice_success)),
        ]
        chip_x = panel_rect.left() + 28
        chip_y = content_top + 342
        chip_w = 132
        chip_h = 48
        for index, (label, state, fg, bg) in enumerate(steps):
            rect = QRectF(chip_x + index * (chip_w + 12), chip_y, chip_w, chip_h)
            chip_path = QPainterPath()
            chip_path.addRoundedRect(rect, 14, 14)
            painter.fillPath(chip_path, bg)
            painter.setPen(fg)
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
            painter.drawText(rect.adjusted(10, 6, -10, -18), Qt.AlignHCenter | Qt.AlignTop, label)
            painter.setFont(QFont("Microsoft YaHei UI", 8))
            painter.drawText(rect.adjusted(10, 22, -10, -6), Qt.AlignHCenter | Qt.AlignBottom, state)

        painter.end()

class StartupSplashController(QObject):
    """Keep startup animation responsive while the main Qt thread loads Live2D."""

    finished = pyqtSignal(int)

    def __init__(self, parent=None, wait_for_voice=False):
        super().__init__(parent)
        self._wait_for_voice = bool(wait_for_voice)
        self._minimum_visible_seconds = 3.2 if wait_for_voice else 2.0
        self._shown_at = 0.0
        self._window_done = False
        self._model_done = False
        self._voice_done = not self._wait_for_voice
        self._geometry = None
        self._dialog = None
        self._process = None
        self._sentinel_path = ""
        self._closed = False
        self._external_raise_error_reported = False
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._maybe_finish)
        self._raise_timer = QTimer(self)
        self._raise_timer.setInterval(120)
        self._raise_timer.timeout.connect(self._keep_front)

    def setGeometry(self, *args):
        self._geometry = args
        if self._dialog is not None:
            self._dialog.setGeometry(*args)

    def show(self):
        self._shown_at = time.monotonic()
        if self._start_external_splash():
            self._raise_timer.start()
            QTimer.singleShot(60, self._keep_front)
            return
        self._dialog = StartupLoadingDialog(wait_for_voice=self._wait_for_voice)
        self._dialog.finished.connect(self.finished.emit)
        if self._geometry is not None:
            self._dialog.setGeometry(*self._geometry)
        self._dialog.show()
        self._raise_timer.start()

    def raise_(self):
        if self._dialog is not None:
            self._dialog.raise_()
            return
        self._raise_external_splash()

    def activateWindow(self):
        if self._dialog is not None:
            self._dialog.activateWindow()

    def _keep_front(self):
        if self._closed:
            return
        self.raise_()
        self.activateWindow()

    def _raise_external_splash(self):
        if os.name != "nt" or self._process is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnds = []
            enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            @enum_proc_type
            def enum_proc(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) == int(self._process.pid):
                    hwnds.append(hwnd)
                return True

            user32.EnumWindows(enum_proc, 0)
            hwnd_topmost = -1
            swp_flags = 0x0001 | 0x0002 | 0x0010 | 0x0040  # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
            for hwnd in hwnds:
                user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_flags)
        except Exception as exc:
            if not self._external_raise_error_reported:
                self._external_raise_error_reported = True
                print("STARTUP_SPLASH_RAISE_ERROR =", exc)

    def mark_window_ready(self, success=True):
        self._window_done = True
        if self._dialog is not None:
            self._dialog.mark_window_ready(success)
        else:
            self._maybe_finish()

    def mark_model_ready(self, success=True):
        self._model_done = True
        if self._dialog is not None:
            self._dialog.mark_model_ready(success)
        else:
            self._maybe_finish()

    def mark_voice_ready(self, success=True):
        self._voice_done = True
        if self._dialog is not None:
            self._dialog.mark_voice_ready(success)
        else:
            self._maybe_finish()

    def _all_loading_done(self):
        return self._window_done and self._model_done and self._voice_done

    def _start_external_splash(self):
        if getattr(sys, "frozen", False):
            return False
        splash_script = os.path.join(BASE_DIR, "persona_startup_splash.py")
        if not os.path.exists(splash_script) or not self._geometry:
            return False
        x, y, width, height = [str(int(value)) for value in self._geometry]
        self._sentinel_path = os.path.join(
            tempfile.gettempdir(),
            f"persona_startup_splash_{os.getpid()}_{int(time.time() * 1000)}.close",
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    splash_script,
                    "--x",
                    x,
                    "--y",
                    y,
                    "--width",
                    width,
                    "--height",
                    height,
                    "--sentinel",
                    self._sentinel_path,
                    "--parent-pid",
                    str(os.getpid()),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            return True
        except Exception as exc:
            print("STARTUP_SPLASH_EXTERNAL_ERROR =", exc)
            self._process = None
            self._sentinel_path = ""
            return False

    def _maybe_finish(self):
        if self._closed or not self._all_loading_done():
            return
        remaining = self._minimum_visible_seconds - (time.monotonic() - self._shown_at)
        if remaining > 0:
            self._finish_timer.start(max(1, int(remaining * 1000)))
            return
        self._closed = True
        self._finish_timer.stop()
        self._raise_timer.stop()
        if self._dialog is not None:
            self._dialog.accept()
            return
        if self._sentinel_path:
            try:
                with open(self._sentinel_path, "w", encoding="utf-8") as handle:
                    handle.write("close\n")
            except Exception as exc:
                print("STARTUP_SPLASH_CLOSE_SIGNAL_ERROR =", exc)
        self.finished.emit(QDialog.Accepted)
        if self._process is not None:
            QTimer.singleShot(1200, self._terminate_external_if_needed)

    def _terminate_external_if_needed(self):
        if self._process is None or self._process.poll() is not None:
            return
        try:
            self._process.terminate()
        except Exception:
            pass


# Runtime profile controls.
# Default stays "test" for direct developer runs so existing test memory/profile data remain visible.
# Launchers and README commands still use --profile main for GitHub/new-user flows.
# Use --profile main, --profile test, or PERSONA_RUN_PROFILE=main/test to choose explicitly.
# Use --reset-profile once to wipe a non-main profile at startup.
PROFILE_SELECTION = apply_runtime_profile(default_profile="test", default_reset=False, argv=sys.argv)
RUN_PROFILE = PROFILE_SELECTION["profile"]
RESET_PROFILE_ON_START = PROFILE_SELECTION["reset"]


def profile_output_dir(*parts):
    return build_profile_output_dir(BASE_DIR, RUN_PROFILE, *parts)


def profile_config_path():
    return build_profile_config_path(BASE_DIR, RUN_PROFILE)


def maybe_reset_profile_on_start():
    profile = str(RUN_PROFILE or "main").strip() or "main"
    if not RESET_PROFILE_ON_START or profile == "main":
        return
    target = os.path.abspath(os.path.join(BASE_DIR, "outputs", "profiles", profile))
    allowed_root = os.path.abspath(os.path.join(BASE_DIR, "outputs", "profiles"))
    if os.path.isdir(target) and os.path.commonpath([allowed_root, target]) == allowed_root:
        shutil.rmtree(target)
    config_path = os.path.abspath(profile_config_path())
    expected_config = os.path.abspath(os.path.join(BASE_DIR, f"persona_llm_config.{profile}.json"))
    if config_path == expected_config and os.path.exists(config_path):
        os.remove(config_path)


maybe_reset_profile_on_start()

VOICE_OUTPUT_DIR = profile_output_dir("voice")
MEMORY_DIR = profile_output_dir("memory")
MEMORY_PATH = os.path.join(MEMORY_DIR, "persona_memory.json")
MEMORY_DB_PATH = os.path.join(MEMORY_DIR, "persona_memory.db")
MEMORY_SHORT_TERM_LIMIT = 300
AGENT_FILES_DIR = profile_output_dir("agent_files")
AGENT_FILE_NAME_MAX_CHARS = 48
BROWSER_AGENT_DIR = profile_output_dir("browser_agent")
BROWSER_AGENT_PROFILE_DIR = os.path.join(BROWSER_AGENT_DIR, "profile")
BROWSER_AGENT_SCREENSHOT_DIR = os.path.join(BROWSER_AGENT_DIR, "screenshots")
BROWSER_AGENT_LOG_PATH = os.path.join(BROWSER_AGENT_DIR, "browser_agent.log")
CHAT_ADVICE_DIR = profile_output_dir("chat_advice")
CHAT_ADVICE_SCREENSHOT_DIR = os.path.join(CHAT_ADVICE_DIR, "screenshots")
INTERACTION_DIR = profile_output_dir("interaction")
TOUCH_ZONE_CONFIG_PATH = os.path.join(INTERACTION_DIR, "touch_zones.json")
LIFE_DIR = profile_output_dir("life")
LIFE_DIARY_DIR = os.path.join(LIFE_DIR, "diary")
LIFE_NOVEL_DIR = os.path.join(LIFE_DIR, "novel")
VOICEVOX_ENGINE_EXE = os.path.join(BASE_DIR, "third_party", "VOICEVOX", "engine", "windows-cpu", "run.exe")
SINGING_ENABLED = True
SINGING_PROVIDER = "voicevox_chant"
SINGING_EXTERNAL_COMMAND = ""
SINGING_MAX_TEXT_CHARS = 72
VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
VOLCENGINE_TTS_VOICE_TYPE = ""
VOLCENGINE_TTS_CLUSTER = "volcano_icl"
VOLCENGINE_TTS_FORMAT = "wav"
VOLCENGINE_TTS_RATE = 24000
SUBTITLES_ENABLED = False
SUBTITLE_SECONDS_PAD = 0.9
LLM_CONFIG_PATH = profile_config_path()
SPEECH_INPUT_ENABLED = True
SPEECH_RECORD_SECONDS = 0.0
SPEECH_MIN_RECORD_SECONDS = 0.50
SPEECH_SILENCE_SECONDS = 0.65
SPEECH_SILENCE_RMS = 0.008
SPEECH_START_TIMEOUT = 8.0
SPEECH_HELPER_TIMEOUT_SECONDS = 0.0
SPEECH_CHUNK_MS = 40
SPEECH_SAMPLE_RATE = 16000
SPEECH_MODEL_SIZE = os.environ.get("PERSONA_SPEECH_MODEL", "small")
SPEECH_MODEL_DIR = os.path.join(BASE_DIR, "third_party", "faster_whisper")
SPEECH_HELPER_PATH = os.path.join(BASE_DIR, "persona_speech_input_once.py")
VOICE_PLAYBACK_GUARD_SECONDS = 0.25
FREE_TALK_RELISTEN_DELAY = 0.15
BARGE_IN_ENABLED = True
BARGE_IN_CHUNK_MS = 40
BARGE_IN_MIN_VOICED_SECONDS = 0.32
BARGE_IN_RMS = 0.14
BARGE_IN_NOISE_MULTIPLIER = 7.5
BARGE_IN_AFTER_PLAYBACK_SECONDS = 0.9
PROACTIVE_ENABLED = True
PROACTIVE_IDLE_SECONDS = 240.0
PROACTIVE_INTERVAL_SECONDS = (300.0, 480.0)
DRIVE_STATE_META_KEY = "drive_state"
LIFE_STATE_META_KEY = "life_state"
SELF_NOTE_META_KEY = "self_notes"
DRIVE_INTENT_HISTORY_LIMIT = 12
DRIVE_DAILY_RECOVERY_HOUR = 5
LLM_TRANSIENT_RETRY_SECONDS = 1.2
PROACTIVE_FAILURE_COOLDOWN_SECONDS = 600.0
MEMORY_MAX_TEXT_CHARS = 420
MEMORY_MIN_SIGNAL_CHARS = 4
LIFE_WRITING_IDLE_SECONDS = 75.0
LIFE_WRITING_INTERVAL_SECONDS = (180.0, 360.0)
LIFE_NOVEL_DAILY_WORD_LIMIT = 1200
LIFE_NOVEL_DAILY_CHAPTER_LIMIT = 1
LIFE_DIARY_DAILY_WORD_LIMIT = 700
STRUCTURED_REPLY_MARKERS = ('"zh"', '"emotion"', '"segments"', '"prosody"', '"voice_text"')
RELATION_FORCE_TERMS = ("必须", "应该", "就是", "为什么不是", "凭什么", "立刻", "现在就")
DRIVE_METRICS = (
    ("curiosity", "好奇心", "想了解你、追问新信息的欲望", QColor(238, 111, 166)),
    ("affinity", "亲密感", "和你的熟悉与信任程度", QColor(255, 145, 184)),
    ("attachment_need", "情感需求", "想被回应、想靠近、害怕被忽略的当下需求", QColor(255, 112, 128)),
    ("security", "安全感", "对当前关系和环境的安心程度", QColor(126, 181, 255)),
    ("companionship", "陪伴欲", "想靠近你、和你说话的倾向", QColor(255, 181, 92)),
    ("energy", "能量", "主动行动和说话的精力", QColor(124, 205, 132)),
    ("novelty", "新鲜感", "最近发现新主题后的兴奋度", QColor(177, 139, 244)),
    ("purpose", "任务感", "想完成长期目标的驱动力", QColor(94, 190, 192)),
)
DEFAULT_LLM_CONFIG = build_default_llm_config(
    volcengine_tts_url=VOLCENGINE_TTS_URL,
    volcengine_tts_cluster=VOLCENGINE_TTS_CLUSTER,
    volcengine_tts_voice_type=VOLCENGINE_TTS_VOICE_TYPE,
    volcengine_tts_format=VOLCENGINE_TTS_FORMAT,
    volcengine_tts_rate=VOLCENGINE_TTS_RATE,
    singing_enabled=SINGING_ENABLED,
    singing_external_command=SINGING_EXTERNAL_COMMAND,
    singing_max_text_chars=SINGING_MAX_TEXT_CHARS,
)


def load_llm_config():
    return load_llm_config_file(LLM_CONFIG_PATH, DEFAULT_LLM_CONFIG)


def save_llm_config(config):
    save_llm_config_file(LLM_CONFIG_PATH, DEFAULT_LLM_CONFIG, config)


def llm_client_kwargs():
    return {
        "default_config": DEFAULT_LLM_CONFIG,
        "emotion_from_text": llm_emotion_from_text,
        "reconcile_emotion": reconcile_llm_emotion,
    }

def llm_chat_controller_kwargs():
    return {
        **llm_client_kwargs(),
        "retry_seconds": LLM_TRANSIENT_RETRY_SECONDS,
    }


class Live2DDesktopPet(
    AgentCommandMixin,
    PetWorkflowMixin,
    PetRenderMixin,
    PetDialogueMixin,
    PetInteractionMixin,
    ChatAdviceCaptureMixin,
    GodotBridgeMixin,
    RoomModeMixin,
    CityModeMixin,
    EconomyMixin,
    BackpackMixin,
    TodoMixin,
    PhysiologyMixin,
    UserProfileMixin,
    HeartMixin,
    QOpenGLWidget,
):
    startup_loading_done = pyqtSignal(bool)
    ui_call_requested = pyqtSignal(object)

    def __init__(self, llm_config=None):
        super().__init__()
        self.ui_call_requested.connect(self._run_ui_callable)
        self.llm_config = dict(llm_config or load_llm_config())
        self._startup_loading_signal_sent = False
        self.model = None
        self.motion_groups = load_motion_groups(MODEL_JSON_PATH)
        self.mixer = EmotionMixer()
        self.behavior = BehaviorController(self.motion_groups)
        self.current_analysis = EmotionAnalysis.neutral()
        self.current_test_key = Qt.Key_1
        self.test_text = TEST_TEXTS[Qt.Key_1]
        self.runtime = AgentRuntime(log_dir=LOG_DIR, logger=log_runtime)
        self.runtime.emit(
            "app.boot",
            {
                "profile": str(RUN_PROFILE or "main"),
                "profile_source": PROFILE_SELECTION.get("source", "default"),
                "memory_db": MEMORY_DB_PATH,
                "config": LLM_CONFIG_PATH,
            },
        )
        self.memory = PersonaMemoryStore(
            MEMORY_PATH,
            MEMORY_DB_PATH,
            short_term_limit=MEMORY_SHORT_TERM_LIMIT,
            logger=log_runtime,
        )
        self.drive = PersonaDriveSystem(
            self.memory,
            drive_metrics=DRIVE_METRICS,
            state_meta_key=DRIVE_STATE_META_KEY,
            intent_history_limit=DRIVE_INTENT_HISTORY_LIMIT,
            daily_recovery_hour=DRIVE_DAILY_RECOVERY_HOUR,
            proactive_failure_cooldown_seconds=PROACTIVE_FAILURE_COOLDOWN_SECONDS,
        )
        self.life = PersonaLifeSystem(
            self.memory,
            state_meta_key=LIFE_STATE_META_KEY,
            writing_interval_seconds=LIFE_WRITING_INTERVAL_SECONDS,
            novel_daily_word_limit=LIFE_NOVEL_DAILY_WORD_LIMIT,
            novel_daily_chapter_limit=LIFE_NOVEL_DAILY_CHAPTER_LIMIT,
            diary_dir=LIFE_DIARY_DIR,
            novel_dir=LIFE_NOVEL_DIR,
        )
        self.life.user_gender = self.llm_config.get("user_gender", "")
        self.setup_user_profile_module()
        self.voice = VoicevoxController(
            config=self.llm_config,
            base_dir=BASE_DIR,
            voice_output_dir=VOICE_OUTPUT_DIR,
            voicevox_engine_exe=VOICEVOX_ENGINE_EXE,
            logger=log_runtime,
            runtime=self.runtime,
        )
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life, runtime=self.runtime, **llm_chat_controller_kwargs())
        self.chat_advice = ChatAdviceController(
            config=self.llm_config,
            memory_store=self.memory,
            client_kwargs=llm_client_kwargs(),
            default_config=DEFAULT_LLM_CONFIG,
            runtime=self.runtime,
            base_dir=BASE_DIR,
        )
        self.life_writer = LifeWritingController(
            config=self.llm_config,
            memory_store=self.memory,
            life_system=self.life,
            client_kwargs=llm_client_kwargs(),
            default_config=DEFAULT_LLM_CONFIG,
            diary_daily_word_limit=LIFE_DIARY_DAILY_WORD_LIMIT,
            runtime=self.runtime,
        )
        self.reader = ReadingController(
            config=self.llm_config,
            memory_store=self.memory,
            life_system=self.life,
            client_kwargs=llm_client_kwargs(),
            default_config=DEFAULT_LLM_CONFIG,
            runtime=self.runtime,
        )
        self.singing_enabled = bool(self.llm_config.get("singing_enabled", SINGING_ENABLED))
        self.speech_input = SpeechInputController(
            enabled=SPEECH_INPUT_ENABLED,
            voice_output_dir=VOICE_OUTPUT_DIR,
            helper_path=SPEECH_HELPER_PATH,
            llm_config_path=LLM_CONFIG_PATH,
            base_dir=BASE_DIR,
            model_dir=SPEECH_MODEL_DIR,
            model_size=SPEECH_MODEL_SIZE,
            record_seconds=SPEECH_RECORD_SECONDS,
            min_record_seconds=SPEECH_MIN_RECORD_SECONDS,
            silence_seconds=SPEECH_SILENCE_SECONDS,
            silence_rms=SPEECH_SILENCE_RMS,
            start_timeout=SPEECH_START_TIMEOUT,
            chunk_ms=SPEECH_CHUNK_MS,
            sample_rate=SPEECH_SAMPLE_RATE,
            helper_timeout_seconds=SPEECH_HELPER_TIMEOUT_SECONDS,
            logger=log_runtime,
            runtime=self.runtime,
        )
        self.barge_in = BargeInController(
            enabled=BARGE_IN_ENABLED,
            sample_rate=SPEECH_SAMPLE_RATE,
            chunk_ms=BARGE_IN_CHUNK_MS,
            min_voiced_seconds=BARGE_IN_MIN_VOICED_SECONDS,
            rms=BARGE_IN_RMS,
            noise_multiplier=BARGE_IN_NOISE_MULTIPLIER,
            runtime=self.runtime,
        )
        self.memory_dialog = None
        self.drive_dialog = None
        self.relationship_dialog = None
        self.library_dialog = None
        self.mini_game_dialog = None
        self.chat_advice_dialog = None
        self.chat_advice_selector = None
        self.chat_advice_full_pixmap = None
        self.chat_advice_screenshot_dir = CHAT_ADVICE_SCREENSHOT_DIR
        self.last_voice_analysis = EmotionAnalysis.neutral()
        self.closing = False
        self.subtitle_text = ""
        self.subtitle_voice_text = ""
        self.subtitle_until = 0.0
        self.chat_status_text = ""
        self.chat_status_until = 0.0
        self.free_talk_enabled = False
        self.free_talk_next_at = 0.0
        self.app_started_at = time.monotonic()
        self.idle_scheduler_suspended = True
        self.idle_scheduler_ready_at = self.app_started_at + 30.0
        self.last_user_interaction_at = self.app_started_at
        self.last_assistant_activity_at = self.app_started_at
        self.next_proactive_at = self.last_user_interaction_at + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        self.drag_offset = None
        self._drag_threshold_px = 8.0
        self._drag_started_at = 0.0
        self._drag_moved = False
        self._left_press_pos = None
        self._left_press_global = None
        self._left_press_started_at = 0.0
        self._touch_history = []
        self._last_touch_at = 0.0
        self.touch_zone_config_path = TOUCH_ZONE_CONFIG_PATH
        self.touch_zone_config = load_touch_zone_config(self.touch_zone_config_path)
        if (
            not has_touch_zone_rects(self.touch_zone_config)
            or (
                bool(self.touch_zone_config.get("auto_generated", False))
                and int(self.touch_zone_config.get("template_version", 0) or 0) < AUTO_TOUCH_ZONE_TEMPLATE_VERSION
            )
        ):
            self.touch_zone_config = build_auto_touch_zone_config()
        self.touch_zone_editor_enabled = False
        self.touch_zone_editor_zone_index = 0
        self.touch_zone_editor_selected_key = TOUCH_ZONE_ORDER[0][0]
        self.touch_zone_editor_drag_start = None
        self.touch_zone_editor_drag_current = None
        self.dialogue_active = False
        self.dialogue_role = DIALOGUE_ROLE_LISTENER
        self.dialogue_sentences = []
        self.dialogue_index = 0
        self.next_dialogue_at = 0.0
        self.last_dialogue_emotion = "neutral"
        self.pending_file_action = None
        self.agent_files_dir = AGENT_FILES_DIR
        self.agent_file_name_max_chars = AGENT_FILE_NAME_MAX_CHARS
        self.browser_agent_log_path = BROWSER_AGENT_LOG_PATH
        self.runtime_logger = log_runtime
        self.base_dir = BASE_DIR
        self.model_json_path = MODEL_JSON_PATH
        self.subtitles_enabled = SUBTITLES_ENABLED
        self.subtitle_seconds_pad = SUBTITLE_SECONDS_PAD
        self.browser_agent = SafeBrowserAgent(
            BROWSER_AGENT_PROFILE_DIR,
            BROWSER_AGENT_SCREENSHOT_DIR,
            log_path=BROWSER_AGENT_LOG_PATH,
            logger=log_runtime,
            runtime=self.runtime,
        )
        self.stimulus_dispatcher = StimulusDispatcher(self, logger=log_runtime)
        self.mouse_tracker = MouseTracker(
            gaze_radius_px=float(self.llm_config.get("interaction_gaze_radius_px", 500) or 500),
            stare_threshold_sec=float(self.llm_config.get("interaction_stare_threshold_sec", 15.0) or 15.0),
        )
        self._touch_visual = TouchVisual()
        self.activity_monitor = None
        self.self_notes = self.load_self_notes()
        self.emotion_engine = EmotionEngine()
        self.episodic_memory = EpisodicMemoryStore(self.memory, logger=log_runtime)
        self.time_awareness = TimeAwareness(self.memory, logger=log_runtime)
        self.pattern_detector = PatternDetector(self.memory, self.life, logger=log_runtime)
        self.personality_growth = PersonalityGrowth(self.memory, logger=log_runtime)
        self.metacognition = MetacognitionEngine(self.memory, logger=log_runtime)
        self.body_cycle = BodyCycleSystem(self.memory, logger=log_runtime)
        self.chat.client._time_awareness = self.time_awareness
        self.chat.client._subtext_analyzer = lambda text: analyze_subtext(
            text,
            recent_history=self.memory.data.get("short_terms", [])[-5:],
            relationship_score=self.life.relationship_score,
        )
        self.chat.client._pattern_detector = self.pattern_detector
        self.chat.client._personality_growth = self.personality_growth
        self.chat.client._metacognition = self.metacognition
        self.chat.client._episodic_memory = self.episodic_memory
        self.chat.client._emotion_engine = self.emotion_engine
        self.chat.client._body_cycle = self.body_cycle
        self.room_window_width = ROOM_WINDOW_WIDTH
        self.room_window_height = ROOM_WINDOW_HEIGHT
        self.default_window_width = WINDOW_WIDTH
        self.default_window_height = WINDOW_HEIGHT
        self.room_model_scale = ROOM_MODEL_SCALE
        self.room_model_z = ROOM_MODEL_Z
        self.room_asset_dir = ROOM_ASSET_DIR
        self.room_layout_path = ROOM_LAYOUT_PATH
        self.room_log_runtime = log_runtime
        self.room_motion_templates = HIYORI_MOTION_TEMPLATES
        self.room_mode = False
        self.room_activity = "idle"
        self.room_activity_started_at = time.monotonic()
        self.room_walk_seed = random.random() * math.tau
        self.room_last_motion_at = 0.0
        self.room_pixmaps = {}
        self.room_layout = self.load_room_layout()
        self.godot_bridge_dir = profile_output_dir("godot_bridge")
        self.setup_godot_bridge()

        self.city_mode = False
        self.city_window_width = CITY_WINDOW_WIDTH
        self.city_window_height = CITY_WINDOW_HEIGHT
        self.load_city_layout()

        self.setup_economy_module()
        self.setup_backpack_module()
        self.chat.client._economy = self.economy
        self.chat.client._backpack = self.backpack
        self.setup_todo_module()

        self.idle_scheduler = self._build_idle_scheduler()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.chat_input = QLineEdit(self)
        self.chat_input.setPlaceholderText("按 V 语音输入；也可以输入文字后回车发送")
        self.chat_input.setStyleSheet(
            "QLineEdit {"
            "background: rgba(255, 248, 253, 238);"
            "border: 1px solid rgba(222, 112, 168, 205);"
            "border-radius: 12px;"
            "padding: 7px 12px;"
            "color: #563248;"
            "font: 10pt 'Microsoft YaHei UI';"
            "}"
            "QLineEdit:focus {"
            "background: rgba(255, 255, 255, 245);"
            "border-color: rgba(197, 74, 130, 230);"
            "}"
        )
        self.chat_input.textEdited.connect(lambda _text: self.mark_user_active("typing"))
        self.chat_input.returnPressed.connect(self.submit_chat_input)

        self.help_button = QToolButton(self)
        self.help_button.setText("?")
        self.help_button.setToolTip("按键说明")
        self.help_button.setCursor(Qt.PointingHandCursor)
        self.help_button.setPopupMode(QToolButton.InstantPopup)
        self.help_button.setStyleSheet(
            "QToolButton {"
            "background: rgba(255, 248, 253, 238);"
            "border: 1px solid rgba(222, 112, 168, 205);"
            "border-radius: 12px;"
            "color: #8f2d5a;"
            "font: 12pt 'Microsoft YaHei UI';"
            "font-weight: 700;"
            "}"
            "QToolButton::menu-indicator { image: none; width: 0px; }"
            "QToolButton:hover {"
            "background: rgba(255, 226, 240, 248);"
            "border-color: rgba(230, 72, 130, 235);"
            "}"
        )
        self.help_button.setMenu(self.build_shortcut_menu())
        self.help_button.setToolTip("按键说明")

        self.close_button = QToolButton(self)
        self.close_button.setText("×")
        self.close_button.setToolTip("关闭")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QToolButton {"
            "background: rgba(255, 248, 253, 238);"
            "border: 1px solid rgba(222, 112, 168, 205);"
            "border-radius: 12px;"
            "color: #8f2d5a;"
            "font: 14pt 'Microsoft YaHei UI';"
            "padding-bottom: 2px;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255, 226, 240, 248);"
            "border-color: rgba(230, 72, 130, 235);"
            "}"
            "QToolButton:pressed {"
            "background: rgba(255, 205, 225, 248);"
            "}"
        )
        self.close_button.setText("×")
        self.close_button.setToolTip("关闭")
        self.close_button.clicked.connect(self.close)
        self.setup_physiology_module()
        self.chat.client._physiology = self.physiology
        self.setup_heart_module()
        self.layout_chat_input()
        self._setup_interaction_activity_monitor()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.update)
        self.timer.start(FRAME_INTERVAL_MS)
        self._first_contact_greeting_after_startup = bool(self.llm_config.get("onboarding_first_greeting_pending"))

    def notify_startup_loading_done(self, success):
        if self._startup_loading_signal_sent:
            return
        self._startup_loading_signal_sent = True
        self.startup_loading_done.emit(bool(success))

    def _setup_interaction_activity_monitor(self):
        if not config_bool(self.llm_config, "interaction_activity_monitor_enabled", False):
            return
        poll_seconds = float(self.llm_config.get("interaction_activity_poll_seconds", 10.0) or 10.0)
        self.activity_monitor = ActivityMonitor(poll_interval=poll_seconds, logger=log_runtime)
        self.activity_monitor.start(self._on_activity_monitor_event)

    def _on_activity_monitor_event(self, raw):
        raw = dict(raw or {})
        event_type = str(raw.get("type") or "").strip().lower()
        if not event_type:
            return
        emotion_map = {
            "env_change": "neutral",
            "work_overtime": "fear",
            "late_night": "fear",
        }
        meta = {}
        for key, value in raw.items():
            if key == "app_name" and not config_bool(self.llm_config, "interaction_activity_store_app_name", False):
                continue
            meta[key] = value
        stimulus = Stimulus(
            type=event_type,
            intensity=0.3 if event_type == "env_change" else 0.5,
            emotion_hint=emotion_map.get(event_type, "neutral"),
            source="activity",
            meta=meta,
            memory_worthy=event_type in {"work_overtime", "late_night"},
            should_talk=event_type in {"work_overtime", "late_night"},
            cooldown_key=event_type,
        )
        self.stimulus_dispatcher.submit_from_thread(stimulus)

    def _run_ui_callable(self, fn):
        try:
            if callable(fn):
                fn()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app", "ui_call", exc)

    def run_on_ui(self, fn):
        if QThread.currentThread() == self.thread():
            return fn()
        self.ui_call_requested.emit(fn)
        return None

    def _build_idle_scheduler(self):
        scheduler = IdleScheduler(logger=log_runtime, runtime=getattr(self, "runtime", None))

        scheduler.register(IdleBehavior(
            name="self_note",
            base_priority=85,
            cooldown=60.0,
            min_idle=PROACTIVE_IDLE_SECONDS,
            energy_floor=24.0,
            ready_fn=lambda: self._scheduler_self_note_ready(),
            execute_fn=lambda: self._scheduler_self_note(),
            resources=("idle_behavior", "memory_write", "profile_write"),
        ))

        scheduler.register(IdleBehavior(
            name="life_writing",
            base_priority=70,
            cooldown=300.0,
            min_idle=75.0,
            energy_floor=35.0,
            ready_fn=lambda: self._scheduler_life_writing_ready(),
            execute_fn=lambda: self._scheduler_life_writing(),
            randomize_cooldown=True,
            cooldown_range=(240.0, 420.0),
            resources=("idle_behavior", "llm", "file_write", "life_state", "memory_write"),
        ))
        # Guaranteed daily writing: no idle/energy requirement, fires late at night
        scheduler.register(IdleBehavior(
            name="guaranteed_writing",
            base_priority=95,
            cooldown=600.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: self._scheduler_guaranteed_writing_ready(),
            execute_fn=lambda: self._scheduler_life_writing(),
            resources=("idle_behavior", "llm", "file_write", "life_state", "memory_write"),
        ))

        # Daily reading: character reads something and reflects
        scheduler.register(IdleBehavior(
            name="daily_reading",
            base_priority=65,
            cooldown=600.0,
            min_idle=60.0,
            energy_floor=20.0,
            ready_fn=lambda: self._scheduler_daily_reading_ready(),
            execute_fn=lambda: self._scheduler_daily_reading(),
            randomize_cooldown=True,
            cooldown_range=(480.0, 900.0),
            resources=("idle_behavior", "llm", "memory_write", "life_state"),
        ))
        # Guaranteed reading: fires late at night if not done today
        scheduler.register(IdleBehavior(
            name="guaranteed_reading",
            base_priority=94,
            cooldown=600.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: self._scheduler_guaranteed_reading_ready(),
            execute_fn=lambda: self._scheduler_daily_reading(),
            resources=("idle_behavior", "llm", "memory_write", "life_state"),
        ))

        scheduler.register(IdleBehavior(
            name="proactive_chat",
            base_priority=60,
            cooldown=180.0,
            min_idle=120.0,
            energy_floor=0.0,
            ready_fn=lambda: self._scheduler_proactive_ready(),
            execute_fn=lambda: self._scheduler_proactive_chat(),
            randomize_cooldown=True,
            cooldown_range=(180.0, 300.0),
            boost_per_second=0.025,
            resources=("idle_behavior", "llm", "memory_write", "profile_write"),
        ))

        scheduler.register(IdleBehavior(
            name="idle_mood_note",
            base_priority=40,
            cooldown=600.0,
            min_idle=480.0,
            energy_floor=0.0,
            ready_fn=lambda: self._scheduler_mood_note_ready(),
            execute_fn=lambda: self._scheduler_mood_note(),
            resources=("idle_behavior", "life_state"),
        ))

        scheduler.register(IdleBehavior(
            name="consolidate",
            base_priority=25,
            cooldown=300.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self.memory, 'consolidate_graph'),
            execute_fn=lambda: self._scheduler_consolidate(),
            randomize_cooldown=True,
            cooldown_range=(300.0, 600.0),
            resources=("idle_behavior", "memory_write"),
        ))

        scheduler.register(IdleBehavior(
            name="reflection",
            base_priority=20,
            cooldown=55.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self, 'heart'),
            execute_fn=lambda: self._scheduler_reflect(),
            randomize_cooldown=True,
            cooldown_range=(55.0, 120.0),
            boost_per_second=0.015,
            resources=("idle_behavior", "life_state"),
        ))

        scheduler.register(IdleBehavior(
            name="silent_motion",
            base_priority=10,
            cooldown=90.0,
            min_idle=60.0,
            energy_floor=0.0,
            ready_fn=lambda: self.model is not None,
            execute_fn=lambda: self._scheduler_silent_motion(),
            randomize_cooldown=True,
            cooldown_range=(90.0, 180.0),
            resources=("idle_behavior", "motion"),
        ))

        scheduler.register(IdleBehavior(
            name="episodic_memory",
            base_priority=30,
            cooldown=120.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self, 'episodic_memory'),
            execute_fn=lambda: self._scheduler_episodic_memory(),
            resources=("idle_behavior", "memory_write"),
        ))

        scheduler.register(IdleBehavior(
            name="metacognition",
            base_priority=15,
            cooldown=600.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self, 'metacognition'),
            execute_fn=lambda: self.metacognition.reflect_on_recent(),
            resources=("idle_behavior", "memory_write"),
        ))

        scheduler.register(IdleBehavior(
            name="pattern_check",
            base_priority=35,
            cooldown=300.0,
            min_idle=300.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self, 'pattern_detector'),
            execute_fn=lambda: self._scheduler_pattern_check(),
            resources=("idle_behavior", "profile_write"),
        ))

        scheduler.register(IdleBehavior(
            name="memory_decay",
            base_priority=22,
            cooldown=600.0,
            min_idle=60.0,
            energy_floor=0.0,
            ready_fn=lambda: hasattr(self, 'memory'),
            execute_fn=lambda: self.memory.decay_memories(),
            resources=("idle_behavior", "memory_write"),
        ))

        scheduler.register(IdleBehavior(
            name="flush_dirty",
            base_priority=5,
            cooldown=30.0,
            min_idle=0.0,
            energy_floor=0.0,
            ready_fn=lambda: True,
            execute_fn=lambda: self._flush_dirty_modules(),
            resources=("idle_behavior", "profile_write", "life_state"),
        ))

        return scheduler

    def _scheduler_self_note_ready(self):
        if not self.self_notes:
            return False
        now = time.monotonic()
        quiet_since = max(self.last_user_interaction_at, getattr(self, "last_assistant_activity_at", 0.0))
        if (now - quiet_since) < PROACTIVE_IDLE_SECONDS:
            return False
        if (now - getattr(self, "app_started_at", now)) < PROACTIVE_IDLE_SECONDS:
            return False
        return not (
            self.chat.is_busy()
            or self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
        )

    def _scheduler_self_note(self):
        if not self.self_notes:
            return False
        now = time.monotonic()
        quiet_since = max(self.last_user_interaction_at, getattr(self, "last_assistant_activity_at", 0.0))
        idle_seconds = now - quiet_since
        if idle_seconds < PROACTIVE_IDLE_SECONDS or (now - getattr(self, "app_started_at", now)) < PROACTIVE_IDLE_SECONDS:
            return False
        if self.chat.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            return False
        note = sorted(self.self_notes, key=lambda item: float(item.get("priority", 1.0)), reverse=True)[0]
        prompt = (
            "你现在不是被动回答用户，而是想主动表达一段自己的深层感受。\n"
            f"用户安静了约{int(idle_seconds)}秒。你的待表达念头：{note.get('text', '')}\n"
            "把它整理成一句更细腻的第一人称关系感受、反思总结或温柔但有棱角的观点。"
            "让表达像她自己突然想通或想靠近时说出来的话，长短、语气、是否提问都跟随当下心情。"
        )
        if hasattr(self.memory, "associative_trace"):
            self.memory.associative_trace(prompt, source="self_note", role="output_plan")
        self.show_chat_status("她正在整理一段想主动说的深层感受。", seconds=2.2)
        if not self.chat.ask_async(prompt, initiated_by="proactive", memory_user_text="桌宠主动行动：self_expression"):
            return False
        self.self_notes.remove(note)
        self.save_self_notes()
        self.drive.record_intent("self_expression", "主动表达深层感受或关系反思", score=note.get("priority"))
        self.drive.last_action_type = "self_expression"
        self.drive.save()
        print("PROACTIVE_SELF_NOTE =", {"kind": note.get("kind"), "text": note.get("text")})
        return True

    def _scheduler_life_writing_ready(self):
        now = time.monotonic()
        if self.free_talk_enabled and (now - self.last_user_interaction_at) < 300.0 and not self.life.is_user_away(now):
            return False
        if time.monotonic() < self.drive.proactive_backoff_until:
            return False
        if self.life.needs_diary():
            return True
        return self.life.should_write_novel()

    def _scheduler_guaranteed_writing_ready(self):
        """Force writing if daily writing was missed or it is late in the day."""
        import datetime
        now = time.monotonic()
        if now - getattr(self, "app_started_at", now) < 120.0:
            return False
        if self.life.needs_diary() and getattr(self.life, "missed_diary_days", lambda: 0)() >= 1:
            return True
        if self.life.should_write_novel() and now - getattr(self, "app_started_at", now) >= 240.0:
            return True
        hour = datetime.datetime.now().hour
        # After 22:00, force diary if not written; after 23:00 force novel too
        if self.life.needs_diary() and hour >= 22:
            return True
        if self.life.should_write_novel() and hour >= 23:
            return True
        return False

    def _scheduler_daily_reading_ready(self):
        return self.life.needs_reading()

    def _scheduler_guaranteed_reading_ready(self):
        import datetime
        hour = datetime.datetime.now().hour
        return self.life.needs_reading() and hour >= 21

    def _scheduler_daily_reading(self):
        if self.reader.read_async():
            self.show_chat_status("苏念在看书...", seconds=12.0)
            print("READING_START")
            return True
        return False

    def _scheduler_life_writing(self):
        now = time.monotonic()
        if self.free_talk_enabled:
            self.free_talk_enabled = False
            self.free_talk_next_at = 0.0
            self.barge_in.stop()
            self.show_chat_status("她先去写点东西。", seconds=3.0)
        kind = "diary" if self.life.needs_diary() else "novel"
        if kind == "novel" and not self.life.should_write_novel():
            return False

        def _after_writing():
            if kind == "diary" and self.life.should_write_novel():
                print("LIFE_WRITING_CHAIN_NOVEL_AFTER_DIARY")
                self.life_writer.write_async("novel")

        if self.life_writer.write_async(kind, after_all=_after_writing):
            self.memory_associate_output("苏念正在写日记。" if kind == "diary" else "苏念正在写小说。", source="life_writing_start")
            self.show_chat_status("苏念正在写日记。" if kind == "diary" else "苏念正在写小说。", seconds=18.0)
            print("LIFE_WRITING_START =", {"kind": kind})
            return True
        return False

    def maybe_force_life_writing(self, now=None):
        """Run overdue diary/novel writing outside the normal idle candidate race."""
        now = time.monotonic() if now is None else float(now)
        last_check = float(getattr(self, "_last_life_writing_watchdog_at", 0.0) or 0.0)
        if now - last_check < 30.0:
            return False
        self._last_life_writing_watchdog_at = now
        if not hasattr(self, "life") or not hasattr(self, "life_writer"):
            return False
        if self.life_writer.is_busy():
            return False
        try:
            if not self._scheduler_guaranteed_writing_ready():
                return False
        except Exception as exc:
            print("LIFE_WRITING_WATCHDOG_READY_ERROR =", {"error": str(exc)})
            return False
        blockers = (
            getattr(self, "speech_input", None) is not None and self.speech_input.is_busy(),
            getattr(self, "chat", None) is not None and self.chat.is_busy(),
            getattr(self, "chat_advice", None) is not None and self.chat_advice.is_busy(),
            getattr(self, "voice", None) is not None and self.voice.is_busy_or_playing(now),
            getattr(self, "behavior", None) is not None and self.behavior.is_speaking(now),
            now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0),
        )
        if any(blockers):
            return False
        started = self._scheduler_life_writing()
        if started:
            try:
                self.runtime.emit("life_writing.watchdog_start", {"missed_diary_days": self.life.missed_diary_days()})
            except Exception:
                pass
            print("LIFE_WRITING_WATCHDOG_START")
        return started

    def _scheduler_proactive_ready(self):
        now = time.monotonic()
        if time.monotonic() < self.drive.proactive_backoff_until:
            return False
        quiet_since = max(self.last_user_interaction_at, getattr(self, "last_assistant_activity_at", 0.0))
        if (now - quiet_since) < PROACTIVE_IDLE_SECONDS:
            return False
        if (now - getattr(self, "app_started_at", now)) < PROACTIVE_IDLE_SECONDS:
            return False
        if self.drive.proactive_streak >= 1 and (now - self.last_user_interaction_at) < 900.0:
            return False
        if self.chat.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            return False
        if self.drive.values.get("energy", 0.0) < 18.0:
            return False
        return True

    def _scheduler_proactive_chat(self):
        now = time.monotonic()
        idle_seconds = now - self.last_user_interaction_at
        recent_memories = []
        if hasattr(self.memory, "recent_user_memory_snippets"):
            recent_memories = self.memory.recent_user_memory_snippets(limit=3)
        action = None
        if hasattr(self, "body_cycle") and hasattr(self.body_cycle, "maybe_build_proactive_intimacy_action"):
            action = self.body_cycle.maybe_build_proactive_intimacy_action(
                relationship_score=getattr(self.life, "relationship_score", 0.0),
                idle_seconds=idle_seconds,
                recent_memories=recent_memories,
                now=now,
            )
        if not action:
            action = self.drive.choose_proactive_action(
                idle_seconds,
                recent_memories=recent_memories,
                writing_due=False,
            )
        if not action:
            return False
        if action.get("type") == "silent_motion":
            self._scheduler_silent_motion()
            self.drive.on_silent_motion(action.get("type", "silent_motion"))
            return True
        prompt = action.get("prompt", "")
        if hasattr(self.memory, "associative_trace"):
            self.memory.associative_trace(prompt or action.get("memory_user_text") or "主动表达", source="proactive", role="output_plan")
        self.show_chat_status("她好像想主动说点什么。", seconds=2.0)
        self.drive.record_intent(action.get("type", "proactive"), "内驱评分触发主动发言", score=action.get("score"))
        self.drive.last_action_type = action.get("type", "proactive")
        self.drive.save()
        self.chat.ask_async(
            prompt,
            initiated_by="proactive",
            memory_user_text=action.get("memory_user_text") or "桌宠主动关心用户",
        )
        print("PROACTIVE_CHAT =", {"action": action.get("type"), "score": action.get("score")})
        return True

    def _scheduler_mood_note_ready(self):
        if not hasattr(self.life, "observe_idle_private_mood"):
            return False
        now = time.monotonic()
        idle_seconds = now - self.last_user_interaction_at
        return idle_seconds >= 480.0

    def _scheduler_mood_note(self):
        now = time.monotonic()
        idle_seconds = now - self.last_user_interaction_at
        note = self.life.observe_idle_private_mood(idle_seconds, now=now)
        if not note:
            return False
        kind = note.get("kind", "idle_sulk")
        if any(item.get("kind") == kind for item in self.self_notes):
            return False
        self.add_self_note(note.get("text", ""), kind=kind, priority=float(note.get("priority", 1.4)))
        return True

    def _scheduler_silent_motion(self):
        if QThread.currentThread() != self.thread():
            self.run_on_ui(lambda: self._scheduler_silent_motion())
            return True
        if self.model is None:
            return False
        try:
            if not self.model.IsMotionFinished():
                return False
            self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
            self.show_chat_status("她决定先安静陪着你。", seconds=2.4)
            print("PROACTIVE_SILENT = silent_motion")
            return True
        except Exception:
            return False

    def _scheduler_consolidate(self):
        self.show_chat_status("她正在整理记忆，把相关的经历连起来……", seconds=6.0)
        result = self.memory.consolidate_graph()
        if result > 0:
            self.show_chat_status(f"记忆整理完成，新建立了 {result} 条联想连接。", seconds=4.0)
        return result > 0

    def _scheduler_episodic_memory(self):
        count = self.episodic_memory.process_new_turns()
        if count > 0:
            self.show_chat_status(f"她把最近的对话整理成了 {count} 段完整回忆。", seconds=4.0)
        return count > 0

    def _scheduler_reflect(self):
        thought = self.heart.reflect(now=time.monotonic(), reason="idle_memory")
        if thought:
            self.show_chat_status(f"她安静地想了一会儿：{thought[:30]}……", seconds=4.0)
        return bool(thought)

    def _scheduler_pattern_check(self):
        if not hasattr(self, 'pattern_detector'):
            return False
        self.pattern_detector.update_baseline(time.monotonic())
        anomalies = self.pattern_detector.detect_anomalies(now=time.monotonic())
        if not anomalies:
            return False
        for anomaly in anomalies:
            self.add_self_note(
                anomaly["detail"],
                kind="pattern_anomaly",
                priority=anomaly["priority"],
            )
        return True

    def _flush_dirty_modules(self):
        try:
            if hasattr(self, 'time_awareness'):
                self.time_awareness.flush_if_dirty()
            if hasattr(self, 'pattern_detector'):
                self.pattern_detector.flush_if_dirty()
            if hasattr(self, 'personality_growth'):
                self.personality_growth._save()
            if hasattr(self, 'metacognition'):
                self.metacognition._save()
            if hasattr(self, 'heart'):
                self.heart.flush_if_dirty()
            if hasattr(self, 'drive'):
                self.drive.flush_dirty()
            if hasattr(self, 'life'):
                self.life.flush_dirty()
            if hasattr(self, 'physiology'):
                self.physiology.flush_dirty()
            if hasattr(self, 'body_cycle'):
                self.body_cycle.flush_dirty()
            if hasattr(self, 'economy'):
                self.economy.flush_dirty()
            if hasattr(self, 'backpack'):
                self.backpack.flush_dirty()
            if hasattr(self, 'todo_list'):
                self.todo_list.flush_dirty()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app", "flush_dirty_modules", exc)
        return False

    def build_shortcut_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background: #fff6fb;
                border: 1px solid rgba(235, 144, 188, 220);
                border-radius: 8px;
                padding: 6px;
                color: #5a344b;
                font: 9pt "Microsoft YaHei UI";
            }
            QMenu::item {
                padding: 6px 18px 6px 10px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #ffe0ef;
                color: #8f2d5a;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(235, 144, 188, 150);
                margin: 5px 6px;
            }
            """
        )
        items = [
            ("V / F2", "开启自由语音监听"),
            ("N", "关闭自由语音监听"),
            ("C", "聚焦顶部输入框"),
            ("B", "打开脑内记忆地图"),
            ("M", "打开角色状态面板"),
            ("J", "打开关系面板"),
            ("D", "打开日记和书架"),
            ("Y", "打开小游戏"),
            ("K", "打开/关闭城市模式"),
            ("I", "打开背包"),
            ("文字", "创建/查看/完成/删除待办"),
            ("A", "行为控制面板"),
            ("点击小屋图标", "进入她的小屋"),
            ("G", "截图聊天记录出主意"),
            ("F", "喂饭"),
            ("H", "摸头"),
            ("P", "亲密作弊码"),
            ("Shift+E", "恢复能量作弊码"),
            ("1~8", "切换测试文本"),
            ("Space", "只切换当前测试情绪"),
            ("Enter", "播放当前测试文本"),
            ("L", "监听者逐句测试"),
            ("Shift+P", "说话测试"),
            ("S / F3", "打开 API 设置"),
            ("F6", "触摸分区检查叠层开关"),
            ("R", "随机待机动作"),
            ("ESC", "退出"),
        ]
        for key, desc in items:
            menu.addAction(f"{key}    {desc}")
        return menu

    def layout_chat_input(self):
        if not hasattr(self, "chat_input"):
            return
        margin = 18
        height = 36
        close_size = 30
        help_size = 30
        gap = 8
        input_top = 46 if hasattr(self, "heart_status_bar") else 10
        input_width = max(120, self.width() - margin * 2 - close_size - help_size - gap * 2)
        self.chat_input.setGeometry(margin, input_top, input_width, height)
        if hasattr(self, "help_button"):
            self.help_button.setGeometry(margin + input_width + gap, input_top + 4, help_size, help_size)
            self.help_button.raise_()
        if hasattr(self, "close_button"):
            self.close_button.setGeometry(margin + input_width + gap + help_size + gap, input_top + 4, close_size, close_size)
            self.close_button.raise_()
        self.layout_heart_status_bar()

    def persist_llm_config(self):
        save_llm_config(self.llm_config)

    def _touch_zone_editor_status_text(self):
        return "触摸分区检查：正在显示自动分区"

    def _set_touch_zone_editor_index(self, index):
        if not TOUCH_ZONE_ORDER:
            return
        index = max(0, min(len(TOUCH_ZONE_ORDER) - 1, int(index)))
        self.touch_zone_editor_zone_index = index
        self.touch_zone_editor_selected_key = TOUCH_ZONE_ORDER[index][0]
        self.show_chat_status(self._touch_zone_editor_status_text(), seconds=2.4)
        self.update()

    def toggle_touch_zone_editor(self):
        if not has_touch_zone_rects(self.touch_zone_config):
            self.touch_zone_config = build_auto_touch_zone_config()
        self.touch_zone_editor_enabled = not bool(self.touch_zone_editor_enabled)
        self.touch_zone_editor_drag_start = None
        self.touch_zone_editor_drag_current = None
        if self.touch_zone_editor_enabled:
            self.show_chat_status(
                "已显示自动触摸分区。F6 关闭；点击仍会正常触发触摸。",
                seconds=4.5,
            )
        else:
            self.show_chat_status("已关闭触摸分区检查。", seconds=2.2)
        self.update()

    def save_touch_zone_config_now(self):
        save_touch_zone_config(self.touch_zone_config_path, self.touch_zone_config)
        self.show_chat_status("触摸分区已保存。", seconds=2.4)

    def undo_current_touch_zone_rect(self):
        zones = self.touch_zone_config.setdefault("zones", {})
        rects = zones.setdefault(self.touch_zone_editor_selected_key, [])
        if rects:
            rects.pop()
            self.show_chat_status(f"已撤销 {touch_zone_label(self.touch_zone_editor_selected_key)} 的最后一个框。", seconds=2.2)
            self.update()

    def clear_current_touch_zone_rects(self):
        zones = self.touch_zone_config.setdefault("zones", {})
        zones[self.touch_zone_editor_selected_key] = []
        self.show_chat_status(f"已清空 {touch_zone_label(self.touch_zone_editor_selected_key)}。", seconds=2.2)
        self.update()

    def open_api_settings_dialog(self):
        dialog = ApiSettingsDialog(
            self.llm_config,
            self,
            default_config=DEFAULT_LLM_CONFIG,
            tts_defaults={
                "url": VOLCENGINE_TTS_URL,
                "cluster": VOLCENGINE_TTS_CLUSTER,
                "voice_type": VOLCENGINE_TTS_VOICE_TYPE,
            },
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        new_config = dialog.values()
        if not prepare_local_llm_if_needed(new_config, parent=self):
            return
        try:
            save_llm_config(new_config)
        except Exception as exc:
            self.show_chat_status("API 璁剧疆淇濆瓨澶辫触", seconds=3.0)
            self.show_chat_status("API 设置保存失败", seconds=3.0)
            self.show_chat_status("API 设置保存失败", seconds=3.0)
            print("API_SETTINGS_SAVE_ERROR =", exc)
            return
        self.llm_config = dict(new_config)
        self.voice.update_config(self.llm_config)
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life, runtime=getattr(self, "runtime", None), **llm_chat_controller_kwargs())
        self.chat.client._time_awareness = getattr(self, "time_awareness", None)
        self.chat.client._subtext_analyzer = lambda text: analyze_subtext(
            text,
            recent_history=self.memory.data.get("short_terms", [])[-5:],
            relationship_score=self.life.relationship_score,
        )
        self.chat.client._pattern_detector = getattr(self, "pattern_detector", None)
        self.chat.client._personality_growth = getattr(self, "personality_growth", None)
        self.chat.client._metacognition = getattr(self, "metacognition", None)
        self.chat.client._episodic_memory = getattr(self, "episodic_memory", None)
        self.chat.client._emotion_engine = getattr(self, "emotion_engine", None)
        self.chat.client._body_cycle = getattr(self, "body_cycle", None)
        self.chat.client._physiology = getattr(self, "physiology", None)
        self.chat.client._economy = getattr(self, "economy", None)
        self.chat.client._backpack = getattr(self, "backpack", None)
        self.chat_advice.update_config(self.llm_config)
        self.life_writer.update_config(self.llm_config)
        self.reader.update_config(self.llm_config)
        self.life.user_gender = self.llm_config.get("user_gender", "")
        self.singing_enabled = bool(self.llm_config.get("singing_enabled", SINGING_ENABLED))
        self.show_chat_status("API 设置已保存", seconds=2.5)
        print(
            "API_SETTINGS_SAVED =",
            {
                "provider": self.llm_config.get("provider"),
                "model": self.llm_config.get("model"),
                "base_url": self.llm_config.get("base_url"),
                "speech_provider": self.llm_config.get("speech_provider"),
                "tts_provider": self.llm_config.get("tts_provider"),
                "voice_type": self.llm_config.get("volcengine_tts_voice_type"),
                "cluster": self.llm_config.get("volcengine_tts_cluster"),
            },
        )

    def play_first_contact_greeting(self):
        if not bool(self.llm_config.get("onboarding_first_greeting_pending")):
            return
        custom_background = str(self.llm_config.get("persona_background") or "").strip()
        if custom_background:
            greeting = "你是谁呀？我为什么会在这里……这里像是你的电脑桌面？你能听见我说话吗？"
            first_contact_text = "第一次连接：她从用户自定义背景设定中醒来，出现在用户电脑桌面上，主动确认用户能否听见自己。"
            story_text = "她的初始身份、来历和经历以用户在登录界面填写的自定义人物背景为准。"
        else:
            greeting = (
                "你是谁呀？我为什么会在这里……我刚才明明还在自己的房间写小说。"
                "这里像是你的电脑屏幕？我叫苏念，笔名念安，二十二岁。你能听见我说话吗？"
            )
            first_contact_text = "第一次连接：苏念从星澜界来到用户电脑上，主动询问用户是谁以及自己为什么在这里。"
            story_text = "苏念原本是星澜界的职业作家/织梦者，打开电脑时穿越到了用户电脑上；双方时间流速一致。"
        try:
            self.llm_config["onboarding_first_greeting_pending"] = False
            save_llm_config(self.llm_config)
        except Exception as exc:
            print("FIRST_GREETING_FLAG_SAVE_ERROR =", exc)
        try:
            self.speak_interaction_feedback(greeting, emotion="surprise")
            self.interaction_memory_add(
                first_contact_text,
                greeting,
                emotion="surprise",
                max_daily_count=3,
                count=1,
            )
            self.memory.save_meta_json(
                "first_contact_story",
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "user_gender": self.llm_config.get("user_gender", ""),
                    "text": story_text,
                },
            )
            self.show_chat_status("第一次连接完成。", seconds=3.0)
        except Exception as exc:
            print("FIRST_GREETING_ERROR =", exc)

    def open_memory_graph_dialog(self):
        self.memory_dialog = MemoryGraphDialog(self.memory, self)
        self.memory_dialog.show()
        self.memory_dialog.raise_()
        self.memory_dialog.activateWindow()
        graph, _short_terms, _long_term = self.memory.graph_snapshot()
        if not graph.get("nodes"):
            if RUN_PROFILE == "main" and os.path.exists(os.path.join(BASE_DIR, "outputs", "profiles", "test", "memory", "persona_memory.db")):
                self.show_chat_status("当前 main 档案还没有记忆数据；test 档案里已有旧记忆。", seconds=4.2)
            else:
                self.show_chat_status("当前档案还没有记忆数据，对话几轮后这里会长出关系网。", seconds=4.0)
            return
        self.show_chat_status("已打开脑内记忆地图。", seconds=2.0)
        return

    def open_drive_status_dialog(self):
        self.drive_dialog = DriveStatusDialog(
            self.drive,
            self.life,
            self,
            drive_metrics=DRIVE_METRICS,
            novel_daily_word_limit=LIFE_NOVEL_DAILY_WORD_LIMIT,
            novel_daily_chapter_limit=LIFE_NOVEL_DAILY_CHAPTER_LIMIT,
            physiology=getattr(self, 'physiology', None),
            body_cycle=getattr(self, 'body_cycle', None),
        )
        self.drive_dialog.show()
        self.drive_dialog.raise_()
        self.drive_dialog.activateWindow()
        self.show_chat_status("已打开角色状态面板。", seconds=2.0)

    def open_relationship_dialog(self):
        self.relationship_dialog = RelationshipDialog(self.life, self.llm_config, self)
        self.relationship_dialog.show()
        self.relationship_dialog.raise_()
        self.relationship_dialog.activateWindow()
        self.show_chat_status("已打开关系面板。", seconds=2.0)

    def open_life_library_dialog(self):
        self.library_dialog = LifeLibraryDialog(LIFE_DIARY_DIR, LIFE_NOVEL_DIR, self)
        self.library_dialog.show()
        self.library_dialog.raise_()
        self.library_dialog.activateWindow()
        self.show_chat_status("已打开角色的书架。", seconds=2.0)

    def open_schedule_dialog(self):
        from persona_pet.ui_dialogs import ScheduleDialog
        self.mark_user_active("schedule_dialog")
        self.ui_interaction_busy_until = time.monotonic() + 30.0
        existing = getattr(self, "schedule_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            self.show_chat_status("作息表已经打开。", seconds=1.6)
            return
        self.schedule_dialog = ScheduleDialog(
            parent=self, life_system=self.life, drive_system=self.drive,
            memory=self.memory, episodic_memory=self.episodic_memory,
            heart=self.heart, physiology=self.physiology,
            time_awareness=self.time_awareness, body_cycle=self.body_cycle,
        )
        self.schedule_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self.schedule_dialog.destroyed.connect(lambda *_args: (setattr(self, "schedule_dialog", None), setattr(self, "ui_interaction_busy_until", time.monotonic() + 2.0)))
        self.schedule_dialog.show()
        self.schedule_dialog.raise_()
        self.schedule_dialog.activateWindow()
        self.show_chat_status("已打开作息表。", seconds=2.0)

    def open_mini_game_dialog(self):
        self.mini_game_dialog = MiniGameDialog(self)
        self.mini_game_dialog.show()
        self.mini_game_dialog.raise_()
        self.mini_game_dialog.activateWindow()
        self.show_chat_status("小游戏面板已打开。", seconds=2.0)

    def _open_backpack_dialog(self):
        from persona_pet.supermarket import BackpackDialog
        dlg = BackpackDialog(self)
        dlg.exec_()
        self.update()

    def _open_behavior_panel(self):
        from persona_pet.behavior_panel import BehaviorPanelDialog
        self.behavior_panel = BehaviorPanelDialog(self)
        self.behavior_panel.show()
        self.behavior_panel.raise_()
        self.behavior_panel.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F6:
            self.toggle_touch_zone_editor()
            return
        if self.touch_zone_editor_enabled:
            if event.key() == Qt.Key_Escape:
                self.toggle_touch_zone_editor()
                return
        if event.key() == Qt.Key_F2:
            self.start_free_talk()
            return
        if event.key() == Qt.Key_B:
            self.open_memory_graph_dialog()
            return
        if event.key() == Qt.Key_M:
            self.open_drive_status_dialog()
            return
        if event.key() == Qt.Key_J:
            self.open_relationship_dialog()
            return
        if event.key() == Qt.Key_D:
            self.open_life_library_dialog()
            return
        if event.key() == Qt.Key_Y:
            self.open_mini_game_dialog()
            return
        if event.key() == Qt.Key_G:
            self.start_chat_advice_capture()
            return
        if event.key() == Qt.Key_F:
            self.interact_with_pet("feed")
            return
        if event.key() == Qt.Key_H:
            self.interact_with_pet("pat")
            return
        if event.key() == Qt.Key_P and not (event.modifiers() & Qt.ShiftModifier):
            self.unlock_intimacy_cheat()
            return
        if event.key() == Qt.Key_E and event.modifiers() & Qt.ShiftModifier:
            self.refill_energy_cheat()
            return
        if event.key() == Qt.Key_N:
            self.stop_free_talk()
            return
        if event.key() == Qt.Key_F3:
            self.open_api_settings_dialog()
            self.show_chat_status("已打开 API 设置面板。", seconds=2.0)
            return
        if event.key() == Qt.Key_I:
            self._open_backpack_dialog()
            return
        if event.key() == Qt.Key_K:
            self.toggle_city_mode()
            return
        if event.key() == Qt.Key_A:
            self._open_behavior_panel()
            return

        if self.chat_input.hasFocus():
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Escape:
            self.show_chat_status("正在退出桌宠。", seconds=1.2)
            self.close()
            return

        if event.key() == Qt.Key_C:
            self.chat_input.setFocus()
            self.chat_input.selectAll()
            self.show_chat_status("输入框已聚焦，可以直接打字。", seconds=2.0)
            return

        if event.key() == Qt.Key_V:
            self.start_free_talk()
            return

        if event.key() == Qt.Key_S:
            self.open_api_settings_dialog()
            self.show_chat_status("已打开 API 设置面板。", seconds=2.0)
            return

        if event.key() in TEST_TEXTS:
            self.dialogue_active = False
            self.current_test_key = event.key()
            self.test_text = TEST_TEXTS[event.key()]
            self.show_chat_status(f"测试文本已切换到 {event.text() or event.key()}。", seconds=2.0)
            print("TEXT =", self.test_text)
            return

        if event.key() == Qt.Key_Space:
            self.show_chat_status("已切换当前测试情绪。", seconds=1.8)
            self.apply_current_text(speak=False)
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.show_chat_status("正在播放当前测试文本。", seconds=2.0)
            self.apply_current_text(speak=True)
            return

        if event.key() == Qt.Key_L:
            self.show_chat_status("开始监听者逐句测试。", seconds=2.0)
            self.start_dialogue_test(DIALOGUE_ROLE_LISTENER)
            return

        if event.key() == Qt.Key_P and event.modifiers() & Qt.ShiftModifier:
            self.show_chat_status("开始说话测试。", seconds=2.0)
            self.start_dialogue_test(DIALOGUE_ROLE_SPEAKER)
            return

        if event.key() == Qt.Key_R and self.model is not None:
            try:
                self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
                self.show_chat_status("已随机切换一个待机动作。", seconds=1.8)
            except Exception:
                self.show_chat_status("随机动作播放失败。", seconds=2.0)
                pass
            return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closing = True
        try:
            self.timer.stop()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app", "timer_stop", exc)
        try:
            if getattr(self, "activity_monitor", None) is not None:
                self.activity_monitor.stop()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app.close", "activity_monitor.stop", exc)
        self.barge_in.stop()
        self.speech_input.stop()
        save_steps = (
            ("drive.save", self.drive.save),
            ("life.save", self.life.save),
            ("save_physiology_module", self.save_physiology_module),
            ("save_user_profile_module", self.save_user_profile_module),
            ("save_heart_module", self.save_heart_module),
            ("save_economy_module", self.save_economy_module),
            ("save_backpack_module", self.save_backpack_module),
            ("save_todo_module", self.save_todo_module),
        )
        for operation, fn in save_steps:
            try:
                fn()
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), log_runtime, "app.close", operation, exc)
        self.shutdown_godot_bridge()
        self.voice.shutdown()
        try:
            self.browser_agent.close()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app.close", "browser_agent.close", exc)
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app.close", "winsound_purge", exc)
        try:
            live2d.dispose()
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), log_runtime, "app.close", "live2d.dispose", exc)
        app = QApplication.instance()
        if app is not None:
            app.quit()
        super().closeEvent(event)



def build_surface_format():
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    fmt.setVersion(2, 1)
    fmt.setAlphaBufferSize(8)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)
    return fmt


def prompt_for_api_key_if_needed(parent=None):
    config = load_llm_config()
    profile = str(RUN_PROFILE or "main").strip() or "main"
    local_llm_prepared = False
    if profile != "main" and not RESET_PROFILE_ON_START:
        changed_onboarding = False
        if not bool(config.get("onboarding_complete")):
            config["onboarding_complete"] = True
            changed_onboarding = True
        if bool(config.get("onboarding_first_greeting_pending")):
            config["onboarding_first_greeting_pending"] = False
            changed_onboarding = True
        if bool(config.get("startup_credential_prompts")):
            config["startup_credential_prompts"] = False
            changed_onboarding = True
        if changed_onboarding:
            try:
                save_llm_config(config)
            except Exception as exc:
                print("ONBOARDING_SKIP_SAVE_ERROR =", exc)
    print(
        "BOOT_PROFILE =",
        {
            "profile": profile,
            "source": PROFILE_SELECTION.get("source", "default"),
            "config": LLM_CONFIG_PATH,
            "reset": RESET_PROFILE_ON_START,
            "onboarding_complete": bool(config.get("onboarding_complete")),
            "first_greeting_pending": bool(config.get("onboarding_first_greeting_pending")),
            "startup_prompts": bool(config.get("startup_credential_prompts")),
        },
    )
    if not bool(config.get("onboarding_complete")):
        dialog = FirstRunDialog(
            config,
            parent,
            default_config=DEFAULT_LLM_CONFIG,
            tts_defaults={
                "url": VOLCENGINE_TTS_URL,
                "cluster": VOLCENGINE_TTS_CLUSTER,
                "voice_type": VOLCENGINE_TTS_VOICE_TYPE,
            },
        )
        if dialog.exec_() == QDialog.Accepted:
            config = dialog.values()
            if is_local_llm_config(config):
                if not prepare_local_llm_if_needed(config, parent=parent):
                    return None
                local_llm_prepared = True
            try:
                save_llm_config(config)
            except Exception as exc:
                print("FIRST_RUN_CONFIG_SAVE_ERROR =", exc)
        else:
            show_startup_message(
                parent,
                "未完成初始化",
                "你取消了首次引导。程序会先按当前配置继续启动，后续也可以在 API 设置面板里补全配置。",
                icon=QMessageBox.Information,
            )
            return None
    allow_startup_prompts = bool(config.get("startup_credential_prompts", False))
    provider = str(config.get("provider", "")).lower()
    changed = False

    if provider == "ollama":
        normalized = normalize_local_llm_config(config)
        if normalized != config:
            config = normalized
            changed = True

    if provider in ("openai", "openai_compatible", "compatible"):
        api_key_env = config.get("api_key_env") or "OPENAI_API_KEY"
        existing = config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if existing:
            config["api_key"] = existing
        elif allow_startup_prompts:
            key, ok = QInputDialog.getText(
                parent,
                "未完成初始化",
                "请输入你的 DeepSeek API key。\n会写入 persona_llm_config.json，下次启动不再重复输入。",
                QLineEdit.Password,
            )
            if ok and key.strip():
                config["api_key"] = key.strip()
                changed = True
        if not (config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")):
            show_startup_message(
                parent,
                "未完成初始化",
                f"当前还没有可用的 API Key。\n请在环境变量中提供 {api_key_env}，否则聊天功能无法使用。",
                icon=QMessageBox.Warning,
            )
            return None

    speech_provider = str(config.get("speech_provider") or "").lower()
    if speech_provider in ("doubao", "volcengine", "bytedance"):
        doubao_env = config.get("doubao_asr_api_key_env") or "DOUBAO_ASR_API_KEY"
        existing = config.get("doubao_asr_api_key") or os.environ.get(doubao_env, "")
        legacy_existing = config.get("doubao_asr_app_key") and config.get("doubao_asr_access_key")
        if existing:
            config["doubao_asr_api_key"] = existing
        elif not legacy_existing and allow_startup_prompts:
            key, ok = QInputDialog.getText(
                parent,
                "未完成初始化",
                "请输入豆包/火山语音识别 API Key。\n会写入 persona_llm_config.json；取消则语音识别回退本地 Whisper。",
                QLineEdit.Password,
            )
            if ok and key.strip():
                config["doubao_asr_api_key"] = key.strip()
                changed = True
            else:
                config["speech_provider"] = "local"
                changed = True
        elif not legacy_existing:
            config["speech_provider"] = "local"
            changed = True

    if str(config.get("tts_provider") or "volcengine").lower() in ("volcengine", "doubao", "bytedance"):
        existing_appid = config.get("volcengine_tts_appid") or os.environ.get("VOLCENGINE_TTS_APPID", "")
        if existing_appid:
            config["volcengine_tts_appid"] = existing_appid

        token_env = config.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY"
        existing_token = (
            config.get("volcengine_tts_api_key")
            or config.get("volcengine_tts_token")
            or os.environ.get(token_env, "")
            or config.get("doubao_asr_api_key", "")
        )
        if existing_token:
            config["volcengine_tts_api_key"] = existing_token
            config["volcengine_tts_token"] = existing_token
        elif allow_startup_prompts:
            token, ok = QInputDialog.getText(
                parent,
                "未完成初始化",
                "请输入火山引擎语音合成 API Key。\n成功例子里使用的是 X-Api-Key 鉴权；缺少 Key 时角色不会出声。",
                QLineEdit.Password,
            )
            if ok and token.strip():
                config["volcengine_tts_api_key"] = token.strip()
                config["volcengine_tts_token"] = token.strip()
                changed = True
        else:
            config["tts_provider"] = "local"
            changed = True

    if changed:
        try:
            save_llm_config(config)
        except Exception as exc:
            print("LLM_CONFIG_SAVE_ERROR =", exc)
    if not local_llm_prepared and not prepare_local_llm_if_needed(config, parent=parent):
        return None
    return config



def main():
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
    QSurfaceFormat.setDefaultFormat(build_surface_format())

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    llm_config = prompt_for_api_key_if_needed()
    if llm_config is None:
        return

    startup_state = {
        "wait_for_local_tts": str(llm_config.get("tts_provider") or "").lower() == "local",
        "wait_for_local_asr": str(llm_config.get("speech_provider") or "").lower() == "local",
        "local_tts_engine": None,
        "pet": None,
        "voice_ready_timer": None,
    }
    screen = app.primaryScreen()
    if screen is not None:
        screen_rect = screen.availableGeometry()
        target_x = screen_rect.x() + max(0, (screen_rect.width() - WINDOW_WIDTH) // 2)
        target_y = screen_rect.y() + max(0, (screen_rect.height() - WINDOW_HEIGHT) // 2)
    else:
        target_x, target_y = 200, 120

    wait_for_local_audio = startup_state["wait_for_local_tts"] or startup_state["wait_for_local_asr"]
    splash = StartupSplashController(wait_for_voice=wait_for_local_audio)
    splash._manual_position = True
    splash.setGeometry(target_x, target_y, WINDOW_WIDTH, WINDOW_HEIGHT)
    splash.show()
    splash.raise_()
    splash.activateWindow()
    app.processEvents()

    def print_runtime_help(pet):
        print("Runtime controls ready.")
        print("Keys: 1~8 switch expressions.")
        print("SPACE pauses or resumes motion, ENTER triggers interaction.")
        print("LLM_CONFIG_PATH =", LLM_CONFIG_PATH)
        print("motion groups =", pet.motion_groups)

    def finish_voice_loading_setup():
        # ASR can take a long time or fail due to local protobuf/TensorFlow issues.
        # Keep it warming in the background, but do not block the startup screen on it.
        wait_for_local_audio_now = startup_state["wait_for_local_tts"]
        if not wait_for_local_audio_now:
            splash.mark_voice_ready(True)
            return

        voice_ready_timer = QTimer(splash)
        voice_ready_timer.setInterval(120)
        startup_state["voice_ready_timer"] = voice_ready_timer
        voice_preload_started_at = time.monotonic()
        voice_preload_timeout = 35.0

        def poll_local_audio_ready():
            elapsed = time.monotonic() - voice_preload_started_at
            if elapsed >= voice_preload_timeout:
                voice_ready_timer.stop()
                tts_loading = False
                asr_loading = False
                try:
                    engine = startup_state.get("local_tts_engine")
                    tts_loading = bool(engine is not None and engine.is_loading())
                except Exception:
                    pass
                try:
                    pet = startup_state.get("pet")
                    asr_loading = bool(pet is not None and pet.speech_input.is_persistent_loading())
                except Exception:
                    pass
                print(
                    "STARTUP_VOICE_PRELOAD_TIMEOUT =",
                    {
                        "seconds": round(elapsed, 1),
                        "tts_loading": tts_loading,
                        "asr_loading": asr_loading,
                    },
                )
                splash.mark_voice_ready(False)
                return

            tts_ready = True
            tts_success = True
            if startup_state["wait_for_local_tts"]:
                local_tts_engine = startup_state["local_tts_engine"]
                if local_tts_engine is not None and local_tts_engine.is_ready():
                    tts_success = True
                elif local_tts_engine is not None and local_tts_engine.is_loading():
                    tts_ready = False
                else:
                    tts_success = False

            if not tts_ready:
                return

            voice_ready_timer.stop()
            splash.mark_voice_ready(tts_success)

        voice_ready_timer.timeout.connect(poll_local_audio_ready)
        voice_ready_timer.start()
        poll_local_audio_ready()

    def start_asr_preload():
        if startup_state["wait_for_local_asr"]:
            try:
                startup_state["pet"].speech_input.preload_persistent_async()
                print("本地语音识别模型正在后台预热...")
            except Exception as exc:
                print("LOCAL_ASR_PRELOAD_ERROR =", exc)
                startup_state["wait_for_local_asr"] = False
        finish_voice_loading_setup()

    def create_pet_window():
        pet = Live2DDesktopPet(llm_config=llm_config)
        startup_state["pet"] = pet
        pet.move(target_x, target_y)
        pet.startup_loading_done.connect(splash.mark_model_ready)
        pet.show()
        splash.mark_window_ready(True)
        splash.raise_()
        splash.activateWindow()
        QTimer.singleShot(0, splash.raise_)
        QTimer.singleShot(40, splash.raise_)
        QTimer.singleShot(120, splash.raise_)

        def focus_pet_after_splash(_result=None):
            pet.raise_()
            pet.setFocus()
            pet.activateWindow()
            pet.idle_scheduler_suspended = False
            pet.idle_scheduler_ready_at = time.monotonic() + 30.0
            if bool(getattr(pet, "_first_contact_greeting_after_startup", False)):
                pet._first_contact_greeting_after_startup = False
                QTimer.singleShot(1200, pet.play_first_contact_greeting)

        splash.finished.connect(focus_pet_after_splash)
        print_runtime_help(pet)
        QTimer.singleShot(0, start_asr_preload)

    def start_tts_preload():
        if startup_state["wait_for_local_tts"]:
            try:
                from persona_pet.qwen_tts_engine import QwenTTSEngine

                if not prepare_local_tts_model_if_needed(llm_config):
                    llm_config["tts_provider"] = "volcengine"
                    startup_state["wait_for_local_tts"] = False
                    splash.mark_voice_ready(False)
                    QTimer.singleShot(0, create_pet_window)
                    return
                startup_state["local_tts_engine"] = QwenTTSEngine(
                    model_path=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_model_path")),
                    ref_dir=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_dir")),
                    ref_audio=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_audio")),
                    ref_text=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_text")),
                    xvec_only=config_bool(llm_config, "qwen_tts_xvec_only", False),
                    do_sample=config_bool(llm_config, "qwen_tts_do_sample", False),
                    seed=int(llm_config.get("qwen_tts_seed", 24681357) or 24681357),
                    temperature=float(llm_config.get("qwen_tts_temperature", 0.55) or 0.55),
                    top_p=float(llm_config.get("qwen_tts_top_p", 0.85) or 0.85),
                    model_id=str(llm_config.get("qwen_tts_model_id") or DEFAULT_QWEN_TTS_MODEL_ID),
                    auto_download=config_bool(llm_config, "qwen_tts_auto_download", True),
                )
                startup_state["local_tts_engine"].load_model_async()
                print("本地 TTS 模型正在后台加载...")
            except ImportError as exc:
                print(f"本地 TTS 依赖缺失：{exc}")
                print("请运行：pip install faster-qwen3-tts")
                print("PyTorch CUDA 版本请参考：https://pytorch.org/get-started/locally/")
                llm_config["tts_provider"] = "volcengine"
                startup_state["wait_for_local_tts"] = False
        QTimer.singleShot(0, create_pet_window)

    QTimer.singleShot(60, start_tts_preload)
    return sys.exit(app.exec_())

    # Pre-load local TTS model if configured
    if str(llm_config.get("tts_provider") or "").lower() == "local":
        try:
            from persona_pet.qwen_tts_engine import QwenTTSEngine
            local_tts_engine = QwenTTSEngine(
                model_path=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_model_path")),
                ref_dir=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_dir")),
                ref_audio=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_audio")),
                ref_text=resolve_project_path(BASE_DIR, llm_config.get("qwen_tts_ref_text")),
                xvec_only=config_bool(llm_config, "qwen_tts_xvec_only", False),
                do_sample=config_bool(llm_config, "qwen_tts_do_sample", False),
                seed=int(llm_config.get("qwen_tts_seed", 24681357) or 24681357),
                temperature=float(llm_config.get("qwen_tts_temperature", 0.55) or 0.55),
                top_p=float(llm_config.get("qwen_tts_top_p", 0.85) or 0.85),
                model_id=str(llm_config.get("qwen_tts_model_id") or DEFAULT_QWEN_TTS_MODEL_ID),
                auto_download=config_bool(llm_config, "qwen_tts_auto_download", True),
            )
            local_tts_engine.load_model_async()
            print("本地 TTS 模型正在后台加载...")
        except ImportError as exc:
            print(f"本地 TTS 依赖缺失：{exc}")
            print("请运行：pip install faster-qwen3-tts")
            print("PyTorch CUDA 版本请参考：https://pytorch.org/get-started/locally/")
            llm_config["tts_provider"] = "volcengine"
            wait_for_local_tts = False
            splash.mark_voice_ready(False)

    pet = Live2DDesktopPet(llm_config=llm_config)
    pet.move(target_x, target_y)
    pet.startup_loading_done.connect(splash.mark_model_ready)
    pet.show()
    splash.mark_window_ready(True)
    splash.show()
    splash.raise_()
    splash.activateWindow()
    app.processEvents()
    splash.finished.connect(lambda _result: (pet.raise_(), pet.setFocus(), pet.activateWindow()))

    if wait_for_local_asr:
        try:
            pet.speech_input.preload_persistent_async()
            print("本地语音识别模型正在后台预热...")
        except Exception as exc:
            print("LOCAL_ASR_PRELOAD_ERROR =", exc)
            wait_for_local_asr = False

    if not wait_for_local_audio:
        splash.mark_voice_ready(True)
    else:
        voice_ready_timer = QTimer(splash)
        voice_ready_timer.setInterval(120)

        def poll_local_audio_ready():
            tts_ready = True
            tts_success = True
            if wait_for_local_tts:
                if local_tts_engine is not None and local_tts_engine.is_ready():
                    tts_ready = True
                    tts_success = True
                elif local_tts_engine is not None and local_tts_engine.is_loading():
                    tts_ready = False
                else:
                    tts_ready = True
                    tts_success = False

            asr_ready = True
            asr_success = True
            if wait_for_local_asr:
                if pet.speech_input.is_persistent_ready():
                    asr_ready = True
                    asr_success = True
                elif pet.speech_input.is_persistent_loading():
                    asr_ready = False
                else:
                    asr_ready = True
                    asr_success = False

            if not (tts_ready and asr_ready):
                return

            voice_ready_timer.stop()
            splash.mark_voice_ready(tts_success and asr_success)

        voice_ready_timer.timeout.connect(poll_local_audio_ready)
        voice_ready_timer.start()
        poll_local_audio_ready()

    print("快捷键说明已加载。")
    print("按 1~8 切换测试文本。")
    print("按 SPACE 只切换当前测试情绪；按 ENTER 播放当前测试文本。")
    print("按 L 开始监听者逐句测试；按 Shift+P 开始说话测试。")
    print("按 V 开启自由语音监听；按 N 关闭；按 B/M/J/G 可打开主要功能面板；F2 也可快速启动语音输入。")
    print("按 P 触发亲密作弊码；按 Shift+E 恢复能量。")
    print("键盘快捷支持打开 API 设置面板，可用 F3 或 S。")
    print("顶部输入框支持直接打字，也支持语音输入；按 C 可聚焦输入框。")
    print(f"LLM 配置文件：{LLM_CONFIG_PATH}")
    print("按 R 随机切换一个待机动作；按 ESC 退出。")
    print("可用 motion groups =", pet.motion_groups)

    sys.exit(app.exec_())


if __name__ == "__main__":
    if "--speech-helper" in sys.argv:
        sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != "--speech-helper"]]
        from persona_speech_input_once import main as speech_helper_main

        raise SystemExit(speech_helper_main())
    main()

