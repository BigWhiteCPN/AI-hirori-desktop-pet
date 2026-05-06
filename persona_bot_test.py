import math
import os
import random
import sys
import time

os.environ["QT_OPENGL"] = "desktop"
os.environ["QT_GL_MODULE"] = "desktop"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QSurfaceFormat
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMenu,
    QOpenGLWidget,
    QToolButton,
)

import live2d.v3 as live2d

from persona_pet.agent_commands import AgentCommandMixin
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
from persona_pet.llm_config import build_default_llm_config, load_llm_config_file, save_llm_config_file
from persona_pet.llm_client import LLMChatController
from persona_pet.life_system import PersonaDriveSystem, PersonaLifeSystem
from persona_pet.life_writing import LifeWritingController
from persona_pet.memory import PersonaMemoryStore
from persona_pet.room_mode import RoomModeMixin
from persona_pet.pet_dialogue import PetDialogueMixin
from persona_pet.pet_interactions import PetInteractionMixin
from persona_pet.pet_render import PetRenderMixin
from persona_pet.pet_workflow import PetWorkflowMixin
from persona_pet.physiology import PhysiologyMixin
from persona_pet.speech import BargeInController, SpeechInputController
from persona_pet.status_dialogs import DriveStatusDialog, MemoryGraphDialog
from persona_pet.ui_dialogs import ApiSettingsDialog, MiniGameDialog
from persona_pet.user_profile import UserProfileMixin
from persona_pet.voicevox import VoicevoxController


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
    except Exception:
        pass


setup_windowed_logging()
MODEL_JSON_PATH = os.path.join(
    BASE_DIR,
    "hiyori_pro_zh",
    "hiyori_pro_zh",
    "runtime",
    "hiyori_pro_t11.model3.json",
)
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 700
ROOM_WINDOW_WIDTH = 760
ROOM_WINDOW_HEIGHT = 520
ROOM_MODEL_SCALE = 0.72
ROOM_ASSET_DIR = os.path.join(BASE_DIR, "assets", "room")
ROOM_LAYOUT_PATH = os.path.join(ROOM_ASSET_DIR, "room_layout.json")
ROOM_MODEL_Z = 50
FRAME_INTERVAL_MS = 16
IDLE_MOTION_INTERVAL = (3.0, 5.6)
EMOTION_MOTION_COOLDOWN = 0.9
PRIMARY_EMOTION_THRESHOLD = 0.30
DIALOGUE_ROLE_LISTENER = "listener"
DIALOGUE_ROLE_SPEAKER = "speaker"
DIALOGUE_SENTENCE_GAP = {
    DIALOGUE_ROLE_LISTENER: 0.75,
    DIALOGUE_ROLE_SPEAKER: 0.45,
}
LLM_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
MOUTH_ENABLE_FOR_SPEAKER = True
MOUTH_OPEN_SCALE = 0.92
MOUTH_FORM_SCALE = 0.14
VOICE_OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "voice")
MEMORY_DIR = os.path.join(BASE_DIR, "outputs", "memory")
MEMORY_PATH = os.path.join(MEMORY_DIR, "persona_memory.json")
MEMORY_DB_PATH = os.path.join(MEMORY_DIR, "persona_memory.db")
MEMORY_SHORT_TERM_LIMIT = 300
AGENT_FILES_DIR = os.path.join(BASE_DIR, "outputs", "agent_files")
AGENT_FILE_NAME_MAX_CHARS = 48
BROWSER_AGENT_DIR = os.path.join(BASE_DIR, "outputs", "browser_agent")
BROWSER_AGENT_PROFILE_DIR = os.path.join(BROWSER_AGENT_DIR, "profile")
BROWSER_AGENT_SCREENSHOT_DIR = os.path.join(BROWSER_AGENT_DIR, "screenshots")
BROWSER_AGENT_LOG_PATH = os.path.join(BROWSER_AGENT_DIR, "browser_agent.log")
CHAT_ADVICE_DIR = os.path.join(BASE_DIR, "outputs", "chat_advice")
CHAT_ADVICE_SCREENSHOT_DIR = os.path.join(CHAT_ADVICE_DIR, "screenshots")
LIFE_DIR = os.path.join(BASE_DIR, "outputs", "life")
LIFE_DIARY_DIR = os.path.join(LIFE_DIR, "diary")
LIFE_NOVEL_DIR = os.path.join(LIFE_DIR, "novel")
VOICEVOX_ENGINE_EXE = os.path.join(BASE_DIR, "third_party", "VOICEVOX", "engine", "windows-cpu", "run.exe")
SINGING_ENABLED = True
SINGING_PROVIDER = "voicevox_chant"
SINGING_EXTERNAL_COMMAND = ""
SINGING_MAX_TEXT_CHARS = 72
VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
VOLCENGINE_TTS_VOICE_TYPE = "S_zEdGPhR02"
VOLCENGINE_TTS_CLUSTER = "volcano_icl"
VOLCENGINE_TTS_FORMAT = "wav"
VOLCENGINE_TTS_RATE = 24000
SUBTITLES_ENABLED = False
SUBTITLE_SECONDS_PAD = 0.9
LLM_CONFIG_PATH = os.path.join(BASE_DIR, "persona_llm_config.json")
SPEECH_INPUT_ENABLED = True
SPEECH_RECORD_SECONDS = 0.0
SPEECH_MIN_RECORD_SECONDS = 0.75
SPEECH_SILENCE_SECONDS = 1.05
SPEECH_SILENCE_RMS = 0.008
SPEECH_START_TIMEOUT = 8.0
SPEECH_HELPER_TIMEOUT_SECONDS = 0.0
SPEECH_CHUNK_MS = 40
SPEECH_SAMPLE_RATE = 16000
SPEECH_MODEL_SIZE = os.environ.get("PERSONA_SPEECH_MODEL", "base")
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
PROACTIVE_IDLE_SECONDS = 60.0
PROACTIVE_INTERVAL_SECONDS = (90.0, 180.0)
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
    RoomModeMixin,
    PhysiologyMixin,
    UserProfileMixin,
    HeartMixin,
    QOpenGLWidget,
):
    def __init__(self, llm_config=None):
        super().__init__()
        self.llm_config = dict(llm_config or load_llm_config())
        self.model = None
        self.motion_groups = load_motion_groups(MODEL_JSON_PATH)
        self.mixer = EmotionMixer()
        self.behavior = BehaviorController(self.motion_groups)
        self.current_analysis = EmotionAnalysis.neutral()
        self.current_test_key = Qt.Key_1
        self.test_text = TEST_TEXTS[Qt.Key_1]
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
        self.setup_user_profile_module()
        self.voice = VoicevoxController(
            config=self.llm_config,
            base_dir=BASE_DIR,
            voice_output_dir=VOICE_OUTPUT_DIR,
            voicevox_engine_exe=VOICEVOX_ENGINE_EXE,
            logger=log_runtime,
        )
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life, **llm_chat_controller_kwargs())
        self.chat_advice = ChatAdviceController(
            config=self.llm_config,
            memory_store=self.memory,
            client_kwargs=llm_client_kwargs(),
            default_config=DEFAULT_LLM_CONFIG,
        )
        self.life_writer = LifeWritingController(
            config=self.llm_config,
            memory_store=self.memory,
            life_system=self.life,
            client_kwargs=llm_client_kwargs(),
            default_config=DEFAULT_LLM_CONFIG,
            diary_daily_word_limit=LIFE_DIARY_DAILY_WORD_LIMIT,
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
        )
        self.barge_in = BargeInController(
            enabled=BARGE_IN_ENABLED,
            sample_rate=SPEECH_SAMPLE_RATE,
            chunk_ms=BARGE_IN_CHUNK_MS,
            min_voiced_seconds=BARGE_IN_MIN_VOICED_SECONDS,
            rms=BARGE_IN_RMS,
            noise_multiplier=BARGE_IN_NOISE_MULTIPLIER,
        )
        self.memory_dialog = None
        self.drive_dialog = None
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
        self.last_user_interaction_at = time.monotonic()
        self.next_proactive_at = self.last_user_interaction_at + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        self.drag_offset = None
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
        )
        self.self_notes = self.load_self_notes()
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
            "background: rgba(255, 248, 253, 230);"
            "border: 1px solid rgba(255, 150, 205, 210);"
            "border-radius: 14px;"
            "padding: 8px 12px;"
            "color: #563248;"
            "font: 10pt 'Microsoft YaHei UI';"
            "}"
        )
        self.chat_input.returnPressed.connect(self.submit_chat_input)

        self.help_button = QToolButton(self)
        self.help_button.setText("?")
        self.help_button.setToolTip("按键说明")
        self.help_button.setCursor(Qt.PointingHandCursor)
        self.help_button.setPopupMode(QToolButton.InstantPopup)
        self.help_button.setStyleSheet(
            "QToolButton {"
            "background: rgba(255, 248, 253, 238);"
            "border: 1px solid rgba(255, 150, 205, 210);"
            "border-radius: 14px;"
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

        self.close_button = QToolButton(self)
        self.close_button.setText("×")
        self.close_button.setToolTip("关闭")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QToolButton {"
            "background: rgba(255, 248, 253, 238);"
            "border: 1px solid rgba(255, 120, 170, 220);"
            "border-radius: 14px;"
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
        self.close_button.clicked.connect(self.close)
        self.setup_physiology_module()
        self.setup_heart_module()
        self.layout_chat_input()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(FRAME_INTERVAL_MS)

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
            ("D", "打开日记和书架"),
            ("Y", "打开小游戏"),
            ("O", "打开/关闭小屋模式"),
            ("Ctrl+O", "重新读取小屋素材"),
            ("G", "截图聊天记录出主意"),
            ("F", "喂饭"),
            ("H", "摸头"),
            ("P", "亲密作弊码"),
            ("Shift+P", "说话测试"),
            ("S / F3", "打开 API 设置"),
            ("R", "随机待机动作"),
            ("ESC", "退出"),
        ]
        for key, desc in items:
            menu.addAction(f"{key}    {desc}")
        return menu

    def layout_chat_input(self):
        if not hasattr(self, "chat_input"):
            return
        margin = 22
        height = 38
        close_size = 30
        help_size = 30
        gap = 8
        input_top = 28 if hasattr(self, "heart_status_bar") else 6
        input_width = max(120, self.width() - margin * 2 - close_size - help_size - gap * 2)
        self.chat_input.setGeometry(margin, input_top, input_width, height)
        if hasattr(self, "help_button"):
            self.help_button.setGeometry(margin + input_width + gap, input_top + 4, help_size, help_size)
            self.help_button.raise_()
        if hasattr(self, "close_button"):
            self.close_button.setGeometry(margin + input_width + gap + help_size + gap, input_top + 4, close_size, close_size)
            self.close_button.raise_()
        self.layout_heart_status_bar()

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
        try:
            save_llm_config(new_config)
        except Exception as exc:
            self.show_chat_status("API 设置保存失败", seconds=3.0)
            print("API_SETTINGS_SAVE_ERROR =", exc)
            return
        self.llm_config = dict(new_config)
        self.voice.update_config(self.llm_config)
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life, **llm_chat_controller_kwargs())
        self.chat_advice.update_config(self.llm_config)
        self.life_writer.update_config(self.llm_config)
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

    def open_memory_graph_dialog(self):
        self.memory_dialog = MemoryGraphDialog(self.memory, self)
        self.memory_dialog.show()
        self.memory_dialog.raise_()
        self.memory_dialog.activateWindow()
        self.show_chat_status("已打开脑内记忆地图。", seconds=2.0)

    def open_drive_status_dialog(self):
        self.drive_dialog = DriveStatusDialog(
            self.drive,
            self.life,
            self,
            drive_metrics=DRIVE_METRICS,
            novel_daily_word_limit=LIFE_NOVEL_DAILY_WORD_LIMIT,
            novel_daily_chapter_limit=LIFE_NOVEL_DAILY_CHAPTER_LIMIT,
        )
        self.drive_dialog.show()
        self.drive_dialog.raise_()
        self.drive_dialog.activateWindow()
        self.show_chat_status("已打开角色状态面板。", seconds=2.0)

    def open_life_library_dialog(self):
        self.library_dialog = LifeLibraryDialog(LIFE_DIARY_DIR, LIFE_NOVEL_DIR, self)
        self.library_dialog.show()
        self.library_dialog.raise_()
        self.library_dialog.activateWindow()
        self.show_chat_status("已打开小日和的书架。", seconds=2.0)

    def open_mini_game_dialog(self):
        self.mini_game_dialog = MiniGameDialog(self)
        self.mini_game_dialog.show()
        self.mini_game_dialog.raise_()
        self.mini_game_dialog.activateWindow()
        self.show_chat_status("小游戏面板已打开。", seconds=2.0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F2:
            self.start_free_talk()
            return
        if event.key() == Qt.Key_B:
            self.open_memory_graph_dialog()
            return
        if event.key() == Qt.Key_M:
            self.open_drive_status_dialog()
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

        if event.key() == Qt.Key_O:
            if event.modifiers() & Qt.ControlModifier:
                self.reload_room_layout()
                return
            self.toggle_room_mode()
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
            self.show_chat_status("开始说话者逐句测试。", seconds=2.0)
            self.start_dialogue_test(DIALOGUE_ROLE_SPEAKER)
            return

        if event.key() == Qt.Key_R and self.model is not None:
            try:
                self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
                self.show_chat_status("已触发随机待机动作。", seconds=1.8)
            except Exception:
                self.show_chat_status("随机动作触发失败。", seconds=2.0)
                pass
            return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closing = True
        try:
            self.timer.stop()
        except Exception:
            pass
        self.barge_in.stop()
        self.speech_input.stop()
        try:
            self.drive.save()
        except Exception:
            pass
        try:
            self.life.save()
        except Exception:
            pass
        try:
            self.save_physiology_module()
        except Exception:
            pass
        try:
            self.save_user_profile_module()
        except Exception:
            pass
        try:
            self.save_heart_module()
        except Exception:
            pass
        self.voice.shutdown()
        try:
            self.browser_agent.close()
        except Exception:
            pass
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        try:
            live2d.dispose()
        except Exception:
            pass
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
    provider = str(config.get("provider", "")).lower()
    changed = False

    if provider in ("openai", "openai_compatible", "compatible"):
        api_key_env = config.get("api_key_env") or "OPENAI_API_KEY"
        existing = config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if existing:
            config["api_key"] = existing
        else:
            key, ok = QInputDialog.getText(
                parent,
                "DeepSeek API Key",
                "请输入你的 DeepSeek API key。\n会写入 persona_llm_config.json，下次启动不再重复输入。",
                QLineEdit.Password,
            )
            if ok and key.strip():
                config["api_key"] = key.strip()
                changed = True

    speech_provider = str(config.get("speech_provider") or "").lower()
    if speech_provider in ("doubao", "volcengine", "bytedance"):
        doubao_env = config.get("doubao_asr_api_key_env") or "DOUBAO_ASR_API_KEY"
        existing = config.get("doubao_asr_api_key") or os.environ.get(doubao_env, "")
        legacy_existing = config.get("doubao_asr_app_key") and config.get("doubao_asr_access_key")
        if existing:
            config["doubao_asr_api_key"] = existing
        elif not legacy_existing:
            key, ok = QInputDialog.getText(
                parent,
                "Doubao ASR API Key",
                "请输入豆包/火山语音识别 API Key。\n会写入 persona_llm_config.json；取消则语音识别回退本地 Whisper。",
                QLineEdit.Password,
            )
            if ok and key.strip():
                config["doubao_asr_api_key"] = key.strip()
                changed = True
            else:
                config["speech_provider"] = "local"
                changed = True

    if str(config.get("tts_provider") or "volcengine").lower() in ("volcengine", "doubao", "bytedance"):
        existing_appid = config.get("volcengine_tts_appid") or os.environ.get("VOLCENGINE_TTS_APPID", "")
        if existing_appid:
            config["volcengine_tts_appid"] = existing_appid
        else:
            appid, ok = QInputDialog.getText(
                parent,
                "火山 TTS AppID",
                "请输入火山引擎语音合成 AppID。\n也可以之后右键角色打开 API 设置面板填写。",
            )
            if ok and appid.strip():
                config["volcengine_tts_appid"] = appid.strip()
                changed = True

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
        else:
            token, ok = QInputDialog.getText(
                parent,
                "火山 TTS API Key",
                "请输入火山引擎语音合成 API Key。\n成功例子里使用的是 X-Api-Key 鉴权；缺少 Key 时角色不会出声。",
                QLineEdit.Password,
            )
            if ok and token.strip():
                config["volcengine_tts_api_key"] = token.strip()
                config["volcengine_tts_token"] = token.strip()
                changed = True

    if changed:
        try:
            save_llm_config(config)
        except Exception as exc:
            print("LLM_CONFIG_SAVE_ERROR =", exc)
    return config



def main():
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
    QSurfaceFormat.setDefaultFormat(build_surface_format())

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    llm_config = prompt_for_api_key_if_needed()
    pet = Live2DDesktopPet(llm_config=llm_config)
    pet.show()
    pet.move(200, 120)
    pet.setFocus()
    pet.activateWindow()

    print("左键拖动整个桌宠窗口。")
    print("按 1~8 切换测试文本。")
    print("按 SPACE 只切换情绪，按 ENTER 模拟角色说这句话。")
    print("按 L 把当前文本当作用户说话逐句监听，按 P 把当前文本当作角色自己逐句说话。")
    print("按 V 开启自由语音对话，按 N 关闭自由语音对话；按 B 打开脑内记忆地图，按 M 打开角色状态面板，按 G 截图聊天记录出主意；按 F2 也可以开启（输入框聚焦时可用）。")
    print("作弊键：P 直接最高亲密，Shift+E 直接回满能量。")
    print("右键角色打开 API 设置面板；输入框未聚焦时也可以按 F3 或 S。")
    print("顶部输入框仍保留为备用：输入文字并回车发送给大模型。按 C 聚焦输入框。")
    print(f"LLM 配置文件：{LLM_CONFIG_PATH}")
    print("按 R 触发一次随机待机动作，按 ESC 退出。")
    print("可用 motion groups =", pet.motion_groups)

    sys.exit(app.exec_())


if __name__ == "__main__":
    if "--speech-helper" in sys.argv:
        sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != "--speech-helper"]]
        from persona_speech_input_once import main as speech_helper_main

        raise SystemExit(speech_helper_main())
    main()
