import copy
import base64
import json
import math
import os
import random
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

os.environ["QT_OPENGL"] = "desktop"
os.environ["QT_GL_MODULE"] = "desktop"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QRadialGradient, QSurfaceFormat
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QOpenGLWidget,
    QProgressBar,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import live2d.v3 as live2d
from live2d.v3.params import StandardParams


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
VOICEVOX_URL = "http://127.0.0.1:50021"
VOICEVOX_SPEAKER = 1
VOICEVOX_LOCK_SPEAKER = True
VOICEVOX_SPEAKER_LABEL = "四国めたん / ノーマル"
VOICEVOX_SPEED = 0.96
VOICEVOX_PITCH = 0.025
VOICEVOX_INTONATION = 1.18
VOICEVOX_VOLUME = 1.0
VOICEVOX_PRE_PHONEME = 0.08
VOICEVOX_POST_PHONEME = 0.12
VOICEVOX_ENABLED = True
VOICEVOX_USE_FINE_PROSODY = True
VOICEVOX_MORA_PITCH_CEILING = 6.10
VOICEVOX_ALLOW_MORA_PITCH_EDIT = False
VOICEVOX_ALLOW_CONTEXT_PAUSE_EDIT = False
VOICEVOX_EMOTION_STYLES_ENABLED = True
VOICEVOX_OUTPUT_PEAK = 0.86
VOICEVOX_SEGMENT_GAP_SECONDS = 0.10
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
INTIMATE_BOUNDARY_BODY_TERMS = (
    "胸",
    "屁股",
    "臀",
    "腿",
    "腰",
    "肚子",
    "身体",
    "身上",
    "私密",
    "脱",
    "舔",
    "睡一起",
    "上床",
)
INTIMATE_BOUNDARY_ACTION_TERMS = ("摸", "碰", "亲", "抱", "贴", "蹭")
INTIMATE_BOUNDARY_SOFT_TERMS = ("摸头", "拍拍头", "牵手", "抱抱", "拥抱")
HARD_BOUNDARY_REPLY_TERMS = ("不准摸", "越来越过分", "降级成普通朋友", "再这样", "警告你", "底线的好吗")
STRUCTURED_REPLY_MARKERS = ('"zh"', '"emotion"', '"segments"', '"prosody"', '"voice_text"')
AFFECTIONATE_PHRASE_TERMS = (
    "喜欢你",
    "爱你",
    "想你",
    "在乎你",
    "需要你",
    "陪着你",
    "陪陪我",
    "你真好",
    "谢谢你",
    "辛苦了",
    "晚安",
    "早安",
    "宝贝",
    "亲爱的",
    "抱抱",
    "亲亲",
    "老婆",
    "女朋友",
)
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
VOICEVOX_EMOTION_STYLE = {
    "joy": {
        "speaker": 0,  # 四国めたん / あまあま
        "speed": 1.00,
        "pitch": 0.020,
        "intonation": 1.18,
        "volume": 0.96,
        "pre": 0.04,
        "post": 0.10,
    },
    "sadness": {
        "speaker": 36,  # 四国めたん / ささやき
        "speed": 0.82,
        "pitch": -0.025,
        "intonation": 0.92,
        "volume": 0.96,
        "pre": 0.12,
        "post": 0.22,
    },
    "anger": {
        "speaker": 6,  # 四国めたん / ツンツン
        "speed": 0.98,
        "pitch": 0.010,
        "intonation": 1.24,
        "volume": 0.97,
        "pre": 0.04,
        "post": 0.10,
    },
    "fear": {
        "speaker": 37,  # 四国めたん / ヒソヒソ
        "speed": 0.90,
        "pitch": 0.020,
        "intonation": 1.22,
        "volume": 0.92,
        "pre": 0.03,
        "post": 0.18,
    },
    "surprise": {
        "speaker": 2,  # 四国めたん / ノーマル
        "speed": 1.01,
        "pitch": 0.020,
        "intonation": 1.20,
        "volume": 0.97,
        "pre": 0.02,
        "post": 0.10,
    },
    "neutral": {
        "speaker": 1,
        "speed": VOICEVOX_SPEED,
        "pitch": VOICEVOX_PITCH,
        "intonation": VOICEVOX_INTONATION,
        "volume": VOICEVOX_VOLUME,
        "pre": VOICEVOX_PRE_PHONEME,
        "post": VOICEVOX_POST_PHONEME,
    },
}
VOICEVOX_PROSODY_BY_EMOTION = {
    "joy": {
        "pitch_curve": (1.01, 1.03),
        "last_pitch_boost": 0.025,
        "vowel_scale": 0.98,
        "pause_scale": 1.0,
        "phrase_pitch_wave": 0.010,
    },
    "sadness": {
        "pitch_curve": (0.98, 0.90),
        "last_pitch_boost": -0.030,
        "vowel_scale": 1.08,
        "pause_scale": 1.0,
        "phrase_pitch_wave": -0.010,
    },
    "anger": {
        "pitch_curve": (1.03, 1.00),
        "last_pitch_boost": 0.015,
        "vowel_scale": 0.96,
        "pause_scale": 1.0,
        "phrase_pitch_wave": 0.030,
    },
    "fear": {
        "pitch_curve": (1.10, 0.96),
        "last_pitch_boost": 0.040,
        "vowel_scale": 1.04,
        "pause_scale": 1.0,
        "phrase_pitch_wave": 0.040,
        "stutter_pause": 0.055,
    },
    "surprise": {
        "pitch_curve": (1.06, 1.03),
        "last_pitch_boost": 0.045,
        "vowel_scale": 0.96,
        "pause_scale": 1.0,
        "phrase_pitch_wave": 0.030,
    },
    "neutral": {
        "pitch_curve": (1.0, 1.0),
        "last_pitch_boost": 0.0,
        "vowel_scale": 1.0,
        "pause_scale": 1.0,
        "phrase_pitch_wave": 0.0,
    },
}

PROSODY_PROMPT_CONTRACT = (
    "必须只输出 JSON，不要输出 Markdown。JSON 格式为："
    "{\"zh\":\"中文回复\","
    "\"emotion\":\"joy/sadness/anger/fear/surprise/neutral\","
    "\"segments\":[{\"zh\":\"分句中文\","
    "\"emotion\":\"joy/sadness/anger/fear/surprise/neutral\"}],"
    "\"prosody\":{\"pace\":\"slow/normal/fast\","
    "\"tone\":\"soft/bright/serious/teasing/urgent\","
    "\"emphasis\":[\"需要重读的短词\"],"
    "\"pause_after\":[\"需要稍微停顿的短词\"]}}。"
    "zh 要简短自然，通常一到三句话，直接作为中文配音台词。"
    "segments 按语义和情绪拆成一到四段，每段要短，不要为了拆分而拆分。"
    "emotion 必须从 joy、sadness、anger、fear、surprise、neutral 中选择一个。"
    "prosody 用来描述说话节奏和重音。"
    "严禁在 zh 或 segments 中写括号动作、舞台说明、表情说明、心理描写。"
    "不要输出类似（挥手）、（笑）、（名残惜しそうに）的内容。"
)

PROSODY_TONE_ALIASES = {
    "gentle": "soft",
    "calm": "soft",
    "comforting": "soft",
    "happy": "bright",
    "cheerful": "bright",
    "cute": "bright",
    "stern": "serious",
    "firm": "serious",
    "playful": "teasing",
    "nervous": "urgent",
    "excited": "urgent",
}

PROSODY_PHRASE_HINTS = {
    "thinking": ("えっと", "うーん", "うん", "そうだね", "ちょっと", "考え", "想", "嗯", "唔"),
    "contrast": ("でも", "だけど", "けど", "ただ", "しかし", "不过", "但是", "可是", "只是"),
    "soft": ("大丈夫", "安心", "ゆっくり", "ごめん", "ありがとう", "没事", "别急", "慢慢", "抱歉", "谢谢"),
    "bright": ("すご", "うれし", "楽しい", "やった", "好き", "开心", "高兴", "喜欢", "太棒"),
    "urgent": ("危ない", "急", "早く", "待って", "危险", "快", "赶紧", "小心"),
    "question": ("かな", "なの", "ですか", "ますか", "吗", "呢", "为什么", "怎么"),
}

VOICEVOX_STYLE_KEYWORDS_BY_EMOTION = {
    "neutral": (
        "ノーマル",
        "ふつう",
        "普通",
        "normal",
        "人間ver.",
    ),
    "joy": (
        "あまあま",
        "楽しい",
        "たのしい",
        "喜び",
        "元気",
        "うきうき",
        "わーい",
        "甘々",
    ),
    "sadness": (
        "悲しみ",
        "かなしみ",
        "かなしい",
        "なみだめ",
        "泣き",
        "びえーん",
        "へろへろ",
        "よわよわ",
    ),
    "anger": (
        "ツンツン",
        "怒り",
        "おこ",
        "不機嫌",
        "ツンギレ",
        "つよつよ",
    ),
    "fear": (
        "こわがり",
        "恐怖",
        "びくびく",
        "おどおど",
        "ヒソヒソ",
        "ささやき",
    ),
    "surprise": (
        "おどろき",
        "驚き",
        "覚醒",
        "熱血",
    ),
}

VOICEVOX_EMOTION_FALLBACKS = {
    "joy": ("joy", "neutral"),
    "sadness": ("sadness", "fear", "neutral"),
    "anger": ("anger", "neutral"),
    "fear": ("fear", "sadness", "neutral"),
    "surprise": ("surprise", "joy", "neutral"),
    "neutral": ("neutral",),
}

PARAM_BODY_ANGLE_X = "ParamBodyAngleX"
PARAM_BODY_ANGLE_Y = "ParamBodyAngleY"
PARAM_BODY_ANGLE_Z = "ParamBodyAngleZ"
PARAM_CHEEK = "ParamCheek"
PARAM_EYE_L_SMILE = "ParamEyeLSmile"
PARAM_EYE_R_SMILE = "ParamEyeRSmile"
PARAM_ARM_LA = "ParamArmLA"
PARAM_ARM_RA = "ParamArmRA"
PARAM_HAIR_AHOGE = "ParamHairAhoge"

PARAM_LIMITS = {
    StandardParams.ParamEyeLOpen: (0.0, 1.3),
    StandardParams.ParamEyeROpen: (0.0, 1.3),
    StandardParams.ParamMouthOpenY: (0.0, 1.2),
    StandardParams.ParamMouthForm: (-2.0, 1.2),
    StandardParams.ParamBrowLForm: (-1.0, 1.0),
    StandardParams.ParamBrowRForm: (-1.0, 1.0),
    StandardParams.ParamAngleX: (-15.0, 15.0),
    StandardParams.ParamAngleY: (-15.0, 15.0),
    StandardParams.ParamAngleZ: (-10.0, 10.0),
    StandardParams.ParamEyeBallX: (-1.0, 1.0),
    StandardParams.ParamEyeBallY: (-1.0, 1.0),
    PARAM_BODY_ANGLE_X: (-10.0, 10.0),
    PARAM_BODY_ANGLE_Y: (-10.0, 10.0),
    PARAM_BODY_ANGLE_Z: (-10.0, 10.0),
    PARAM_CHEEK: (0.0, 1.0),
    PARAM_EYE_L_SMILE: (0.0, 1.0),
    PARAM_EYE_R_SMILE: (0.0, 1.0),
    PARAM_ARM_LA: (-10.0, 10.0),
    PARAM_ARM_RA: (-10.0, 10.0),
    PARAM_HAIR_AHOGE: (-10.0, 10.0),
}

EMOTION_ORDER = ("fear", "joy", "sadness", "anger", "surprise")
TEST_TEXTS = {
    Qt.Key_1: "我有点害怕，这里太危险了。",
    Qt.Key_2: "今天真的很开心，太棒了！",
    Qt.Key_3: "我很难过，有点想哭……",
    Qt.Key_4: "我很生气，这也太离谱了！",
    Qt.Key_5: "啊？居然会这样，太震惊了？！",
    Qt.Key_6: "今天天气不错，没什么特别的。",
    Qt.Key_7: "你刚才为什么那样说？我有点生气。不过我想了想，也许你不是故意的。算了，我们继续吧。",
    Qt.Key_8: "我先想一下这个问题。刚才确实有点生气，但我不想一直这样。我们慢慢说清楚，好吗？",
}

TEST_VOICEVOX_LINES = {
    Qt.Key_1: "ひゃあっ……こ、ここは危ないのだ……！",
    Qt.Key_2: "えへへっ！今日はすっごく楽しいのだー！",
    Qt.Key_3: "うう……ちょっと悲しくなっちゃったのだ……。",
    Qt.Key_4: "むむっ！これはさすがに怒っちゃうのだ！",
    Qt.Key_5: "わあっ！？びっくりしたのだー！",
    Qt.Key_6: "うんうん、今日はのんびりできそうなのだ。",
    Qt.Key_7: "むむっ……ちょっと怒ったけど、もう大丈夫なのだ。",
    Qt.Key_8: "うん……少し考えてから、ゆっくり話すのだ。",
}

VOICEVOX_LINES_BY_EMOTION = {
    "joy": "えへへっ！すっごくうれしいのだー！",
    "sadness": "うう……ちょっとかなしいのだ……。",
    "anger": "むむっ！ちょっと怒ってるのだ！",
    "fear": "ひゃあっ……こ、こわいのだ……！",
    "surprise": "わあっ！？びっくりしたのだー！",
    "neutral": "うんうん、そうなのだ。",
}
VOICEVOX_STOCK_LINES = set(VOICEVOX_LINES_BY_EMOTION.values())

EMOTION_LEXICON = {
    "joy": {
        "开心": 1.00,
        "快乐": 0.95,
        "高兴": 0.88,
        "兴奋": 1.05,
        "喜欢": 0.65,
        "太棒了": 1.10,
        "棒": 0.55,
        "幸福": 1.10,
        "期待": 0.52,
        "哈哈": 0.62,
        "嘿嘿": 0.62,
        "最好": 0.86,
        "笑": 0.40,
        "激动": 0.90,
        "满足": 0.66,
    },
    "sadness": {
        "悲伤": 1.08,
        "难过": 1.00,
        "伤心": 1.08,
        "失落": 0.82,
        "沮丧": 0.88,
        "委屈": 0.90,
        "想哭": 1.10,
        "哭": 0.64,
        "低落": 0.78,
        "孤单": 0.72,
        "遗憾": 0.60,
        "呜呜": 0.72,
    },
    "anger": {
        "生气": 1.00,
        "愤怒": 1.15,
        "火大": 0.92,
        "离谱": 0.72,
        "讨厌": 0.88,
        "气死": 1.18,
        "烦": 0.60,
        "恼火": 0.90,
        "受不了": 0.74,
        "可恶": 0.82,
    },
    "fear": {
        "害怕": 1.00,
        "恐惧": 1.12,
        "危险": 0.92,
        "可怕": 0.90,
        "惊慌": 0.84,
        "担心": 0.68,
        "不安": 0.72,
        "吓": 0.55,
        "紧张": 0.64,
        "慌": 0.62,
    },
    "surprise": {
        "震惊": 1.08,
        "惊讶": 0.98,
        "居然": 0.72,
        "竟然": 0.72,
        "不会吧": 1.05,
        "啊？": 0.72,
        "啊": 0.18,
        "诶": 0.22,
        "突然": 0.45,
        "真的假的": 0.88,
    },
}

INTENSIFIERS = {
    "非常": 0.20,
    "特别": 0.16,
    "超级": 0.24,
    "真的": 0.12,
    "太": 0.14,
    "极其": 0.24,
    "很": 0.08,
}

SOFTENERS = {
    "有点": 0.14,
    "一点": 0.10,
    "稍微": 0.12,
    "还好": 0.10,
    "一般": 0.08,
}

NEGATIONS = ("不", "没", "没有", "不是", "别", "无")
EXPRESSION_REQUEST_INTENTS = (
    "表情",
    "动作",
    "做个",
    "做一个",
    "摆个",
    "摆一个",
    "表现",
    "我要你",
    "要你",
    "给我",
    "来个",
    "变成",
)
EXPRESSION_REQUEST_EMOTIONS = {
    "joy": ("开心", "快乐", "高兴", "笑", "开心脸"),
    "sadness": ("悲伤", "难过", "伤心", "哭", "哭脸", "委屈"),
    "anger": ("生气", "愤怒", "怒", "发火"),
    "fear": ("害怕", "恐惧", "怕", "惊慌"),
    "surprise": ("惊讶", "震惊", "吃惊"),
}

MOTION_BY_EMOTION = {
    "joy": ["Tap", "Tap@Body", "Idle", "FlickUp"],
    "sadness": ["Idle", "Flick", "Flick@Body"],
    "anger": ["FlickDown", "Tap@Body", "Flick@Body", "FlickUp"],
    "fear": ["FlickDown", "Flick", "Flick@Body", "Tap"],
    "surprise": ["FlickUp", "Tap", "FlickDown", "Flick"],
    "neutral": ["Idle", "Flick"],
}

HIYORI_MOTION_TEMPLATES = {
    "m01_thinking": {
        "group": "Idle",
        "index": 0,
        "file": "hiyori_m01.motion3.json",
        "label": "听到问题后的思考",
    },
    "m02_question_smile": {
        "group": "Idle",
        "index": 1,
        "file": "hiyori_m02.motion3.json",
        "label": "女生疑问表情后微笑",
    },
    "m03_carefree_joy": {
        "group": "Flick",
        "index": 0,
        "file": "hiyori_m03.motion3.json",
        "label": "无忧无虑的开心",
    },
    "m04_wronged_sadness": {
        "group": "FlickDown",
        "index": 0,
        "file": "hiyori_m04.motion3.json",
        "label": "做错事后的委屈难过",
    },
    "m04_fear": {
        "group": "FlickDown",
        "index": 0,
        "file": "hiyori_m04.motion3.json",
        "label": "害怕退缩（借用m04委屈难过）",
    },
    "m05_curious": {
        "group": "Idle",
        "index": 2,
        "file": "hiyori_m05.motion3.json",
        "label": "微笑后四处张望的好奇",
    },
    "m06_cute_joy": {
        "group": "FlickUp",
        "index": 0,
        "file": "hiyori_m06.motion3.json",
        "label": "手舞足蹈的萌萌开心",
    },
    "m07_surprise": {
        "group": "Tap",
        "index": 0,
        "file": "hiyori_m07.motion3.json",
        "label": "惊讶",
    },
    "m08_joy": {
        "group": "Tap",
        "index": 1,
        "file": "hiyori_m08.motion3.json",
        "label": "开心",
    },
    "m09_anger": {
        "group": "Tap@Body",
        "index": 1,
        "file": "hiyori_m09_hold.motion3.json",
        "label": "生气（延长皱眉阶段）",
    },
    "m10_sadness": {
        "group": "Flick@Body",
        "index": 0,
        "file": "hiyori_m10.motion3.json",
        "label": "难过",
    },
}

PRIMARY_MOTION_BY_EMOTION = {
    "joy": "m08_joy",
    "sadness": "m10_sadness",
    "anger": "m09_anger",
    "surprise": "m07_surprise",
    "fear": "m04_fear",
    "neutral": "m01_thinking",
}

LISTENER_MOTION_BY_EMOTION = {
    "joy": "m02_question_smile",
    "sadness": "m10_sadness",
    "anger": "m01_thinking",
    "surprise": "m07_surprise",
    "fear": "m04_fear",
    "neutral": "m01_thinking",
}

RESIDUE_MOTION_BY_EMOTION = {
    "joy": "m03_carefree_joy",
    "sadness": "m01_thinking",
    "anger": "m01_thinking",
    "surprise": "m05_curious",
    "fear": "m01_thinking",
}

MOTION_DURATION_SECONDS = {
    "m01_thinking": 4.7,
    "m02_question_smile": 5.93,
    "m03_carefree_joy": 4.2,
    "m04_wronged_sadness": 4.43,
    "m04_fear": 4.43,
    "m05_curious": 8.57,
    "m06_cute_joy": 5.37,
    "m07_surprise": 1.9,
    "m08_joy": 2.1,
    "m09_anger": 3.6,
    "m10_sadness": 4.17,
}

RESIDUE_DELAY_SECONDS = {
    "joy": 0.6,
    "sadness": 0.7,
    "anger": 0.45,
    "surprise": 0.45,
    "fear": 0.55,
}

TEXT_MOTION_HINTS = (
    ("m04_fear", ("害怕", "恐惧", "危险", "可怕", "担心", "不安", "紧张")),
    ("m04_wronged_sadness", ("委屈", "对不起", "抱歉", "错了", "做错", "不是故意")),
    ("m06_cute_joy", ("可爱", "萌", "手舞足蹈", "嘿嘿")),
    ("m03_carefree_joy", ("无忧无虑", "轻松", "自由", "舒服")),
    ("m02_question_smile", ("为什么", "怎么", "吗", "是不是", "可以吗", "能不能")),
    ("m01_thinking", ("想想", "思考", "考虑", "让我想", "问题")),
    ("m05_curious", ("好奇", "看看", "看一下", "哪里", "什么", "发现")),
)


@dataclass
class EmotionAnalysis:
    weights: dict
    intensity: float
    dominant: str
    speaking_energy: float
    matched_tokens: list[str] = field(default_factory=list)

    @staticmethod
    def neutral():
        return EmotionAnalysis(
            weights={
                "fear": 0.0,
                "joy": 0.0,
                "sadness": 0.0,
                "anger": 0.0,
                "surprise": 0.0,
                "neutral": 1.0,
            },
            intensity=0.0,
            dominant="neutral",
            speaking_energy=0.35,
            matched_tokens=[],
        )


class EmotionMixer:
    def __init__(self):
        self.current = EmotionAnalysis.neutral().weights.copy()
        self.target = self.current.copy()

    def set_target(self, emo: dict):
        merged = EmotionAnalysis.neutral().weights.copy()
        merged.update(emo)
        self.target = merged

    def update(self, speed=0.10):
        for key in self.current:
            self.current[key] += (self.target[key] - self.current[key]) * speed
        return self.current.copy()


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def compact_text(text):
    return re.sub(r"\s+", "", text or "")


def collapse_repeated_memory_text(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return ""
    for _ in range(2):
        text = re.sub(r"(.{2,36}?)\1{2,}", r"\1\1", text)
    parts = [part.strip() for part in re.split(r"([。！？!?；;\n])", text)]
    rebuilt = []
    last_sentence = ""
    for index in range(0, len(parts), 2):
        sentence = parts[index].strip()
        punct = parts[index + 1] if index + 1 < len(parts) else ""
        if not sentence:
            continue
        if sentence == last_sentence:
            continue
        rebuilt.append(f"{sentence}{punct}")
        last_sentence = sentence
    return " ".join(rebuilt).strip() or text


def memory_signal_report(user_text, assistant_text):
    user_text = collapse_repeated_memory_text(strip_stage_directions(user_text))
    assistant_text = collapse_repeated_memory_text(clean_structured_reply_leak(strip_stage_directions(assistant_text)))
    if len(user_text) > MEMORY_MAX_TEXT_CHARS:
        user_text = user_text[:MEMORY_MAX_TEXT_CHARS].rstrip() + "..."
    if len(assistant_text) > MEMORY_MAX_TEXT_CHARS:
        assistant_text = assistant_text[:MEMORY_MAX_TEXT_CHARS].rstrip() + "..."
    compact = compact_text(f"{user_text}{assistant_text}")
    report = {
        "keep": True,
        "reason": "ok",
        "quality": 1.0,
        "user": user_text,
        "assistant": assistant_text,
    }
    if len(compact) < MEMORY_MIN_SIGNAL_CHARS:
        report.update({"keep": False, "reason": "too_short", "quality": 0.0})
        return report
    if any(marker in compact for marker in ("SPEECH_INPUT_ERROR", "LLM_ERROR", "Traceback")):
        report.update({"keep": False, "reason": "runtime_noise", "quality": 0.0})
        return report
    unique_ratio = len(set(compact)) / max(1, len(compact))
    most_common_ratio = max((compact.count(ch) for ch in set(compact)), default=0) / max(1, len(compact))
    if len(compact) > 80 and (unique_ratio < 0.08 or most_common_ratio > 0.42):
        report.update({"keep": False, "reason": "repetitive_noise", "quality": 0.0})
        return report
    if len(compact) > 260 and unique_ratio < 0.16:
        report["quality"] = 0.45
        report["reason"] = "low_signal"
    return report


def is_transient_llm_error(error):
    text = str(error or "").lower()
    return any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "temporarily",
            "connection reset",
            "connection aborted",
            "remote end closed",
            "read operation timed out",
            "502",
            "503",
            "504",
            "429",
        )
    )


def is_intimate_boundary_query(text):
    compact = compact_text(text)
    if not compact:
        return False
    if any(term in compact for term in INTIMATE_BOUNDARY_SOFT_TERMS) and not any(
        term in compact for term in INTIMATE_BOUNDARY_BODY_TERMS
    ):
        return False
    has_body = any(term in compact for term in INTIMATE_BOUNDARY_BODY_TERMS)
    has_action = any(term in compact for term in INTIMATE_BOUNDARY_ACTION_TERMS)
    asks_permission = any(term in compact for term in ("能不能", "可以", "让我", "给我", "想要", "为什么不准", "为啥不准"))
    return has_body and (has_action or asks_permission)


def is_hard_boundary_memory(item):
    text = f"{item.get('user', '')}\n{item.get('assistant', '')}"
    compact = compact_text(text)
    return any(term in compact for term in HARD_BOUNDARY_REPLY_TERMS)


def unescape_loose_json_text(text):
    text = str(text or "")
    text = text.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
    text = re.sub(r"\s+", " ", text).strip()
    return strip_stage_directions(text)


def extract_loose_json_string(text, key, following_keys=None):
    following_keys = following_keys or ("emotion", "segments", "prosody", "voice_text", "ja", "tts")
    key_pattern = re.escape(str(key))
    for next_key in following_keys:
        pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*,\s*"{re.escape(next_key)}"\s*:'
        match = re.search(pattern, text or "", flags=re.S)
        if match:
            return unescape_loose_json_text(match.group(1))
    pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*\}}'
    match = re.search(pattern, text or "", flags=re.S)
    if match:
        return unescape_loose_json_text(match.group(1))
    return ""


def clean_structured_reply_leak(text):
    raw = str(text or "").strip()
    if not any(marker in raw for marker in STRUCTURED_REPLY_MARKERS):
        return raw
    zh = extract_loose_json_string(raw, "zh") or extract_loose_json_string(raw, "reply") or extract_loose_json_string(raw, "reply_zh")
    if zh:
        return zh
    cleaned = re.sub(r'"(?:emotion|segments|prosody|voice_text|ja|tts)"\s*:\s*[^,}]+', "", raw)
    cleaned = re.sub(r'[{}[\]"]+', "", cleaned)
    cleaned = re.sub(r"\bzh\s*:\s*", "", cleaned)
    return strip_stage_directions(re.sub(r"\s+", " ", cleaned).strip(" ,:")) or raw


def contains_any(text, tokens):
    return any(token and token in text for token in tokens)


def split_voicevox_label(label):
    parts = [part.strip() for part in str(label or "").split("/", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0] if parts else ""


def normalize_prosody_hint(value):
    if not isinstance(value, dict):
        return {}
    pace = str(value.get("pace") or "normal").strip().lower()
    if pace not in {"slow", "normal", "fast"}:
        pace = "normal"
    tone = str(value.get("tone") or "").strip().lower()
    tone = PROSODY_TONE_ALIASES.get(tone, tone)
    if tone not in {"soft", "bright", "serious", "teasing", "urgent"}:
        tone = ""

    def clean_list(raw):
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        items = []
        for item in raw:
            item = str(item or "").strip()
            if 1 <= len(item) <= 16:
                items.append(item)
        return items[:6]

    return {
        "pace": pace,
        "tone": tone,
        "emphasis": clean_list(value.get("emphasis")),
        "pause_after": clean_list(value.get("pause_after")),
    }


def strip_stage_directions(text):
    text = str(text or "")
    if not text:
        return ""
    patterns = (
        r"（[^（）]{0,80}）",
        r"\([^()]{0,80}\)",
        r"【[^【】]{0,80}】",
        r"\[[^\[\]]{0,80}\]",
        r"《[^《》]{0,80}》",
        r"〈[^〈〉]{0,80}〉",
    )
    previous = None
    while previous != text:
        previous = text
        for pattern in patterns:
            text = re.sub(pattern, "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([。！？!?、，,.])", r"\1", text)
    text = re.sub(r"([「『])\s+", r"\1", text)
    text = re.sub(r"\s+([」』])", r"\1", text)
    return text.strip()


def load_motion_groups(model_json_path):
    with open(model_json_path, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    motions = model_data.get("FileReferences", {}).get("Motions", {})
    return {group_name: len(entries) for group_name, entries in motions.items()}


def dominant_weight_emotion(analysis):
    emotion_weights = {emotion: analysis.weights.get(emotion, 0.0) for emotion in EMOTION_ORDER}
    dominant = max(emotion_weights, key=emotion_weights.get)
    if emotion_weights[dominant] < PRIMARY_EMOTION_THRESHOLD:
        return "neutral"
    return dominant


def primary_dominant_analysis(analysis):
    dominant = dominant_weight_emotion(analysis)
    if dominant == analysis.dominant:
        return analysis
    return EmotionAnalysis(
        weights=dict(analysis.weights),
        intensity=analysis.intensity,
        dominant=dominant,
        speaking_energy=analysis.speaking_energy,
        matched_tokens=list(analysis.matched_tokens),
    )


def apply_emotion_override(analysis, emotion):
    if emotion not in LLM_EMOTIONS or emotion == "neutral":
        return analysis
    weights = dict(analysis.weights)
    current = weights.get(emotion, 0.0)
    weights[emotion] = max(current, 0.58)
    weights["neutral"] = min(weights.get("neutral", 0.0), 0.34)
    for other in EMOTION_ORDER:
        if other != emotion:
            weights[other] = min(weights.get(other, 0.0), 0.18)
    return EmotionAnalysis(
        weights=weights,
        intensity=max(analysis.intensity, 0.42),
        dominant=emotion,
        speaking_energy=max(analysis.speaking_energy, 0.58),
        matched_tokens=list(analysis.matched_tokens),
    )


def expressive_weights_for_render(analysis):
    weights = dict(analysis.weights)
    dominant = dominant_weight_emotion(analysis)
    if dominant == "neutral":
        return weights

    neutral = weights.get("neutral", 0.0)
    primary = weights.get(dominant, 0.0)
    transfer = 0.0
    if primary <= neutral:
        transfer = max(transfer, (neutral + 0.08 - primary) * 0.5)
    if primary + transfer < 0.42:
        transfer = max(transfer, 0.42 - primary)
    transfer = min(neutral, transfer)
    if transfer <= 1e-6:
        return weights

    weights[dominant] = primary + transfer
    weights["neutral"] = neutral - transfer
    return weights


def split_dialogue_sentences(text):
    text = (text or "").strip()
    if not text:
        return []
    parts = re.findall(r"[^。！？!?；;\n]+[。！？!?；;]*", text)
    return [part.strip() for part in parts if part.strip()]


def estimate_sentence_seconds(sentence, role=DIALOGUE_ROLE_SPEAKER):
    clean = re.sub(r"\s+", "", sentence or "")
    punctuation_hits = sum(clean.count(mark) for mark in "。！？!?；;…")
    base = 1.25 if role == DIALOGUE_ROLE_LISTENER else 1.55
    seconds = base + len(clean) * 0.085 + punctuation_hits * 0.18
    upper = 5.8 if role == DIALOGUE_ROLE_LISTENER else 7.5
    return clamp(seconds, 1.6, upper)


def voicevox_line_for(analysis, test_key=None):
    if test_key in TEST_VOICEVOX_LINES:
        return TEST_VOICEVOX_LINES[test_key]
    dominant = dominant_weight_emotion(analysis)
    return VOICEVOX_LINES_BY_EMOTION.get(dominant, VOICEVOX_LINES_BY_EMOTION["neutral"])


@dataclass
class VoicevoxEvent:
    event_id: int
    text: str
    emotion: str
    speaker: int
    wav_path: str
    duration: float
    started_at: float
    error: str = ""


class VoicevoxController:
    def __init__(self, config=None):
        self.enabled = VOICEVOX_ENABLED
        self.lock = threading.Lock()
        self.events = []
        self.next_event_id = 0
        self.active_jobs = 0
        self.last_play_until = 0.0
        self.last_play_started_at = 0.0
        self.cancel_generation = 0
        self.engine_process = None
        self.config = dict(config or {})
        self.speaker = int(self.config.get("voicevox_speaker", VOICEVOX_SPEAKER) or VOICEVOX_SPEAKER)
        self.speaker_label = str(self.config.get("voicevox_speaker_label") or VOICEVOX_SPEAKER_LABEL)
        self.lock_speaker = bool(self.config.get("voicevox_lock_speaker", VOICEVOX_LOCK_SPEAKER))
        self.use_fine_prosody = bool(self.config.get("voicevox_use_fine_prosody", VOICEVOX_USE_FINE_PROSODY))
        self.allow_mora_pitch_edit = bool(self.config.get("voicevox_allow_mora_pitch_edit", VOICEVOX_ALLOW_MORA_PITCH_EDIT))
        self.allow_context_pause_edit = bool(self.config.get("voicevox_allow_context_pause_edit", VOICEVOX_ALLOW_CONTEXT_PAUSE_EDIT))
        self.emotion_styles_enabled = bool(self.config.get("voicevox_emotion_styles_enabled", VOICEVOX_EMOTION_STYLES_ENABLED))
        label_character, label_style = split_voicevox_label(self.speaker_label)
        self.character_name = str(self.config.get("voicevox_character_name") or label_character).strip()
        self.base_style_name = str(self.config.get("voicevox_base_style_name") or label_style).strip()
        self.speaker_styles = None
        self.style_id_to_character = {}
        self.singing_provider = str(self.config.get("singing_provider") or SINGING_PROVIDER)
        self.singing_external_command = str(self.config.get("singing_external_command") or "")
        self.tts_url = str(self.config.get("volcengine_tts_url") or VOLCENGINE_TTS_URL)
        self.tts_appid = str(self.config.get("volcengine_tts_appid") or os.environ.get("VOLCENGINE_TTS_APPID", "")).strip()
        self.tts_token_env = str(self.config.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY")
        self.tts_token = str(
            self.config.get("volcengine_tts_api_key")
            or self.config.get("volcengine_tts_token")
            or os.environ.get(self.tts_token_env, "")
            or self.config.get("doubao_asr_api_key", "")
        ).strip()
        self.tts_cluster = str(self.config.get("volcengine_tts_cluster") or VOLCENGINE_TTS_CLUSTER).strip()
        self.tts_voice_type = str(self.config.get("volcengine_tts_voice_type") or VOLCENGINE_TTS_VOICE_TYPE).strip()
        self.tts_format = str(self.config.get("volcengine_tts_format") or VOLCENGINE_TTS_FORMAT).strip().lower()
        self.tts_rate = int(self.config.get("volcengine_tts_rate", VOLCENGINE_TTS_RATE) or VOLCENGINE_TTS_RATE)
        self.tts_speed_ratio = float(self.config.get("volcengine_tts_speed_ratio", 1.0) or 1.0)
        self.tts_volume_ratio = float(self.config.get("volcengine_tts_volume_ratio", 1.0) or 1.0)
        self.tts_pitch_ratio = float(self.config.get("volcengine_tts_pitch_ratio", 1.0) or 1.0)

    def update_config(self, config):
        with self.lock:
            self.config = dict(config or {})
            self.tts_url = str(self.config.get("volcengine_tts_url") or VOLCENGINE_TTS_URL)
            self.tts_appid = str(self.config.get("volcengine_tts_appid") or os.environ.get("VOLCENGINE_TTS_APPID", "")).strip()
            self.tts_token_env = str(self.config.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY")
            self.tts_token = str(
                self.config.get("volcengine_tts_api_key")
                or self.config.get("volcengine_tts_token")
                or os.environ.get(self.tts_token_env, "")
                or self.config.get("doubao_asr_api_key", "")
            ).strip()
            self.tts_cluster = str(self.config.get("volcengine_tts_cluster") or VOLCENGINE_TTS_CLUSTER).strip()
            self.tts_voice_type = str(self.config.get("volcengine_tts_voice_type") or VOLCENGINE_TTS_VOICE_TYPE).strip()
            self.tts_format = str(self.config.get("volcengine_tts_format") or VOLCENGINE_TTS_FORMAT).strip().lower()
            self.tts_rate = int(self.config.get("volcengine_tts_rate", VOLCENGINE_TTS_RATE) or VOLCENGINE_TTS_RATE)
            self.tts_speed_ratio = float(self.config.get("volcengine_tts_speed_ratio", 1.0) or 1.0)
            self.tts_volume_ratio = float(self.config.get("volcengine_tts_volume_ratio", 1.0) or 1.0)
            self.tts_pitch_ratio = float(self.config.get("volcengine_tts_pitch_ratio", 1.0) or 1.0)

    def engine_is_running(self):
        try:
            urllib.request.urlopen(f"{VOICEVOX_URL}/version", timeout=1.2).read()
            return True
        except Exception:
            return False

    def ensure_engine(self):
        if self.engine_is_running():
            return
        if not os.path.exists(VOICEVOX_ENGINE_EXE):
            raise FileNotFoundError(f"VOICEVOX engine not found: {VOICEVOX_ENGINE_EXE}")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.engine_process = subprocess.Popen(
            [VOICEVOX_ENGINE_EXE, "--host", "127.0.0.1", "--port", "50021"],
            cwd=os.path.dirname(VOICEVOX_ENGINE_EXE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        for _ in range(90):
            time.sleep(0.3)
            if self.engine_is_running():
                return
        raise RuntimeError("VOICEVOX engine did not start.")

    def shutdown(self):
        self.stop_playback()
        process = self.engine_process
        self.engine_process = None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2.0)
        except Exception as exc:
            log_runtime("VOICEVOX_SHUTDOWN_ERROR", exc)

    def request_json(self, url, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))

    def get_json(self, url):
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))

    def list_speakers(self):
        self.ensure_engine()
        speakers = self.get_json(f"{VOICEVOX_URL}/speakers")
        choices = []
        for speaker in speakers:
            name = str(speaker.get("name") or "").strip()
            for style in speaker.get("styles") or []:
                style_name = str(style.get("name") or "").strip()
                style_id = style.get("id")
                if style_id is None:
                    continue
                label = f"{name} / {style_name} ({int(style_id)})"
                choices.append((label, int(style_id), f"{name} / {style_name}", name, style_name))
        choices.sort(key=lambda item: item[1])
        return choices

    def list_characters(self):
        styles_by_character = self.load_speaker_styles(refresh=True)
        choices = []
        for character_name, styles in styles_by_character.items():
            default_style = self.find_character_default_style(styles)
            if not default_style:
                continue
            style_names = " / ".join(style["name"] for style in styles[:4])
            if len(styles) > 4:
                style_names += f" / +{len(styles) - 4}"
            label = f"{character_name}（{style_names}）"
            choices.append((label, character_name, int(default_style["id"]), default_style["name"]))
        choices.sort(key=lambda item: item[2])
        return choices

    def load_speaker_styles(self, refresh=False):
        if self.speaker_styles is not None and not refresh:
            return self.speaker_styles
        self.ensure_engine()
        speakers = self.get_json(f"{VOICEVOX_URL}/speakers")
        by_character = {}
        id_to_character = {}
        for speaker in speakers:
            character_name = str(speaker.get("name") or "").strip()
            if not character_name:
                continue
            styles = []
            for style in speaker.get("styles") or []:
                if style.get("type", "talk") != "talk":
                    continue
                style_id = style.get("id")
                if style_id is None:
                    continue
                style_name = str(style.get("name") or "").strip()
                item = {"id": int(style_id), "name": style_name, "character": character_name}
                styles.append(item)
                id_to_character[int(style_id)] = item
            if styles:
                by_character[character_name] = styles
        self.speaker_styles = by_character
        self.style_id_to_character = id_to_character
        if not self.character_name and self.speaker in id_to_character:
            item = id_to_character[self.speaker]
            self.character_name = item["character"]
            self.base_style_name = item["name"]
            self.speaker_label = f"{item['character']} / {item['name']}"
        return by_character

    def style_matches_emotion(self, style_name, emotion):
        style_name = str(style_name or "")
        return contains_any(style_name, VOICEVOX_STYLE_KEYWORDS_BY_EMOTION.get(emotion, ()))

    def find_character_default_style(self, styles):
        if not styles:
            return None
        for emotion in ("neutral", "joy", "sadness", "fear", "anger", "surprise"):
            for style in styles:
                if self.style_matches_emotion(style["name"], emotion):
                    return style
        return styles[0]

    def find_character_style_for_emotion(self, emotion):
        if not self.emotion_styles_enabled:
            return None
        try:
            styles_by_character = self.load_speaker_styles()
        except Exception as exc:
            print("VOICEVOX_STYLE_MAP_ERROR =", exc)
            return None
        character_name = self.character_name
        if not character_name and self.speaker in self.style_id_to_character:
            character_name = self.style_id_to_character[self.speaker]["character"]
        styles = styles_by_character.get(character_name, [])
        if not styles:
            return None
        for candidate_emotion in VOICEVOX_EMOTION_FALLBACKS.get(emotion, ("neutral",)):
            for style in styles:
                if self.style_matches_emotion(style["name"], candidate_emotion):
                    return style
        return self.find_character_default_style(styles)

    def speaker_for_emotion(self, emotion):
        style = self.find_character_style_for_emotion(emotion)
        if style:
            return int(style["id"]), f"{style['character']} / {style['name']}", True
        fallback_style = VOICEVOX_EMOTION_STYLE.get(emotion, VOICEVOX_EMOTION_STYLE["neutral"])
        if self.lock_speaker:
            return self.speaker, self.speaker_label, False
        return int(fallback_style["speaker"]), "emotion_style", False

    def set_speaker(self, speaker, label="", character_name="", style_name=""):
        with self.lock:
            self.speaker = int(speaker)
            self.speaker_label = label or f"speaker {speaker}"
            self.lock_speaker = True
            label_character, label_style = split_voicevox_label(self.speaker_label)
            self.character_name = str(character_name or label_character or "").strip()
            self.base_style_name = str(style_name or label_style or "").strip()
            self.emotion_styles_enabled = True

    def request_bytes(self, url, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()

    def request_volcengine_tts(self, text):
        text = strip_stage_directions(text)
        if not text:
            raise RuntimeError("火山 TTS 文本为空。")
        if not self.tts_token:
            raise RuntimeError(f"缺少火山 TTS API Key，请在右键 API 面板填写，或设置 {self.tts_token_env}。")
        if not self.tts_voice_type:
            raise RuntimeError("缺少火山 TTS 音色 ID。")

        reqid = str(uuid.uuid4())
        app_payload = {"cluster": self.tts_cluster}
        if self.tts_appid:
            app_payload["appid"] = self.tts_appid
        payload = {
            "app": app_payload,
            "user": {"uid": "persona_pet"},
            "audio": {
                "voice_type": self.tts_voice_type,
                "encoding": self.tts_format,
                "rate": self.tts_rate,
                "speed_ratio": self.tts_speed_ratio,
                "volume_ratio": self.tts_volume_ratio,
                "pitch_ratio": self.tts_pitch_ratio,
            },
            "request": {
                "reqid": reqid,
                "text": text,
                "text_type": "plain",
                "operation": "query",
            },
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.tts_url,
            data=data,
            headers={
                "X-Api-Key": self.tts_token,
                "X-Api-Request-Id": reqid,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"火山 TTS HTTP {exc.code}: {error_body or exc.reason}") from exc
        if "application/json" not in content_type.lower():
            return raw
        result = json.loads(raw.decode("utf-8"))
        if result.get("code") not in (None, 0, 3000):
            message = result.get("message") or result.get("msg") or str(result)
            raise RuntimeError(f"火山 TTS 调用失败：{message}")
        audio_data = result.get("data") or result.get("audio") or (result.get("result") or {}).get("data")
        if not audio_data:
            raise RuntimeError(f"火山 TTS 未返回音频：{result}")
        return base64.b64decode(audio_data)

    def wav_duration(self, path):
        with wave.open(path, "rb") as file:
            return file.getnframes() / max(file.getframerate(), 1)

    def normalize_wav_peak(self, path, target_peak=VOICEVOX_OUTPUT_PEAK):
        try:
            import array

            with wave.open(path, "rb") as file:
                params = file.getparams()
                frames = file.readframes(file.getnframes())
            if params.sampwidth != 2 or not frames:
                return
            samples = array.array("h")
            samples.frombytes(frames)
            if sys.byteorder != "little":
                samples.byteswap()
            peak = max((abs(sample) for sample in samples), default=0)
            limit = int(32767 * clamp(target_peak, 0.20, 0.98))
            if peak <= 0 or peak <= limit:
                return
            scale = limit / peak
            for index, sample in enumerate(samples):
                samples[index] = int(sample * scale)
            if sys.byteorder != "little":
                samples.byteswap()
            with wave.open(path, "wb") as file:
                file.setparams(params)
                file.writeframes(samples.tobytes())
        except Exception as exc:
            print("VOICEVOX_NORMALIZE_ERROR =", exc)

    def concatenate_wavs(self, input_paths, output_path, gap_seconds=VOICEVOX_SEGMENT_GAP_SECONDS):
        valid_paths = [path for path in input_paths if path and os.path.exists(path)]
        if not valid_paths:
            raise RuntimeError("No segment wav files to concatenate.")

        with wave.open(valid_paths[0], "rb") as first:
            params = first.getparams()
            first_frames = first.readframes(first.getnframes())

        gap_frames = b""
        if gap_seconds > 0.0:
            frame_count = int(params.framerate * gap_seconds)
            gap_frames = b"\x00" * frame_count * params.nchannels * params.sampwidth

        with wave.open(output_path, "wb") as output:
            output.setparams(params)
            output.writeframes(first_frames)
            for path in valid_paths[1:]:
                with wave.open(path, "rb") as segment:
                    segment_params = segment.getparams()
                    if (
                        segment_params.nchannels != params.nchannels
                        or segment_params.sampwidth != params.sampwidth
                        or segment_params.framerate != params.framerate
                    ):
                        raise RuntimeError("Segment wav format mismatch.")
                    output.writeframes(gap_frames)
                    output.writeframes(segment.readframes(segment.getnframes()))

    def phrase_text(self, phrase):
        return "".join(str(mora.get("text") or "") for mora in phrase.get("moras", []))

    def phrase_traits(self, phrase_text, full_text, source_text, prosody_hint):
        combined = phrase_text
        traits = set()
        for name, tokens in PROSODY_PHRASE_HINTS.items():
            if contains_any(phrase_text, tokens):
                traits.add(name)
        if any(mark in phrase_text for mark in ("?", "？")):
            traits.add("question")
        if any(mark in phrase_text for mark in ("!", "！")):
            traits.add("bright")
        if "…" in combined or "..." in combined:
            traits.add("thinking")
        if contains_any(phrase_text, prosody_hint.get("emphasis", [])):
            traits.add("emphasis")
        if self.allow_context_pause_edit and contains_any(phrase_text, prosody_hint.get("pause_after", [])):
            traits.add("pause_after")

        tone = prosody_hint.get("tone", "")
        if tone == "soft":
            traits.add("soft")
        elif tone == "bright":
            traits.add("tone_bright")
        elif tone == "urgent":
            traits.add("tone_urgent")
        elif tone == "serious":
            traits.add("serious")
        elif tone == "teasing":
            traits.add("teasing")
        return traits

    def scale_pause(self, phrase, scale=1.0, add=0.0):
        if not self.allow_context_pause_edit:
            return
        pause = phrase.get("pause_mora")
        if not pause:
            return
        value = pause.get("vowel_length")
        if isinstance(value, (int, float)) and value > 0.0:
            pause["vowel_length"] = clamp(value * scale + add, 0.035, 0.42)
        pitch = pause.get("pitch")
        if isinstance(pitch, (int, float)):
            pause["pitch"] = 0.0

    def adjust_moras(self, moras, pitch_mul=1.0, pitch_add=0.0, vowel_scale=1.0, consonant_scale=1.0):
        for mora in moras:
            pitch = mora.get("pitch")
            if self.allow_mora_pitch_edit and isinstance(pitch, (int, float)) and pitch > 0.0:
                mora["pitch"] = clamp(
                    pitch * pitch_mul + pitch_add,
                    0.01,
                    VOICEVOX_MORA_PITCH_CEILING,
                )

            vowel_length = mora.get("vowel_length")
            if isinstance(vowel_length, (int, float)) and vowel_length > 0.0:
                mora["vowel_length"] = clamp(vowel_length * vowel_scale, 0.035, 0.42)

            consonant_length = mora.get("consonant_length")
            if isinstance(consonant_length, (int, float)) and consonant_length > 0.0:
                mora["consonant_length"] = clamp(consonant_length * consonant_scale, 0.015, 0.30)

    def apply_contextual_phrase_prosody(self, query, emotion, text, source_text, prosody_hint):
        phrases = query.get("accent_phrases") or []
        if not phrases:
            return query

        full_text = compact_text(text)
        source_text = compact_text(source_text)
        pace = prosody_hint.get("pace", "normal")
        global_vowel = {"slow": 1.08, "normal": 1.0, "fast": 0.94}.get(pace, 1.0)
        global_pause = {"slow": 1.06, "normal": 1.0, "fast": 0.96}.get(pace, 1.0)

        for index, phrase in enumerate(phrases):
            moras = phrase.get("moras", [])
            if not moras:
                continue
            traits = self.phrase_traits(
                self.phrase_text(phrase),
                full_text,
                source_text,
                prosody_hint,
            )
            pitch_mul = 1.0
            pitch_add = 0.0
            vowel_scale = global_vowel
            consonant_scale = 1.0
            pause_scale = global_pause
            pause_add = 0.0

            if "thinking" in traits:
                pitch_mul *= 0.985
                vowel_scale *= 1.04
                pause_scale *= 1.08
                pause_add += 0.012
            if "contrast" in traits:
                pitch_add += 0.010
                pause_scale *= 1.10
                pause_add += 0.015
            if "soft" in traits:
                pitch_mul *= 0.975
                pitch_add -= 0.010
                vowel_scale *= 1.04
                pause_scale *= 1.04
            if "tone_bright" in traits:
                pitch_mul *= 1.006
                pitch_add += 0.010
                vowel_scale *= 0.99
            if "tone_urgent" in traits:
                pitch_mul *= 1.008
                pitch_add += 0.012
                vowel_scale *= 0.96
                pause_scale *= 0.94
            if "bright" in traits or "emphasis" in traits:
                pitch_mul *= 1.012
                pitch_add += 0.020
                vowel_scale *= 0.98
                consonant_scale *= 0.98
            if "urgent" in traits:
                pitch_mul *= 1.012
                pitch_add += 0.018
                vowel_scale *= 0.94
                pause_scale *= 0.90
            if "serious" in traits:
                pitch_mul *= 0.99
                vowel_scale *= 1.04
                pause_scale *= 1.08
            if "teasing" in traits:
                wave = 0.018 if index % 2 == 0 else -0.006
                pitch_add += wave
                vowel_scale *= 0.98
            if "pause_after" in traits:
                pause_scale *= 1.12
                pause_add += 0.018

            self.adjust_moras(
                moras,
                pitch_mul=pitch_mul,
                pitch_add=pitch_add,
                vowel_scale=vowel_scale,
                consonant_scale=consonant_scale,
            )
            self.scale_pause(phrase, scale=pause_scale, add=pause_add)

            if "question" in traits:
                phrase["is_interrogative"] = True

        if phrases:
            last_phrase = phrases[-1]
            last_moras = last_phrase.get("moras", [])
            if last_moras and (
                "question" in self.phrase_traits(self.phrase_text(last_phrase), full_text, source_text, prosody_hint)
                or full_text.endswith(("?", "？", "か", "かな", "の"))
            ):
                self.adjust_moras(last_moras[-2:], pitch_mul=1.004, pitch_add=0.035, vowel_scale=1.04)
                last_phrase["is_interrogative"] = True
            elif emotion in ("sadness", "fear"):
                self.adjust_moras(last_moras[-1:], pitch_mul=0.99, pitch_add=-0.018, vowel_scale=1.16)

        return query

    def apply_prosody(self, query, emotion, text="", source_text="", prosody_hint=None):
        prosody_hint = normalize_prosody_hint(prosody_hint)
        prosody = VOICEVOX_PROSODY_BY_EMOTION.get(emotion, VOICEVOX_PROSODY_BY_EMOTION["neutral"])
        phrases = query.get("accent_phrases") or []
        moras = [mora for phrase in phrases for mora in phrase.get("moras", [])]
        total = max(1, len(moras))
        start_mul, end_mul = prosody["pitch_curve"]
        vowel_scale = prosody["vowel_scale"]
        phrase_wave = prosody["phrase_pitch_wave"]

        for index, mora in enumerate(moras):
            t = index / max(total - 1, 1)
            pitch = mora.get("pitch")
            if self.allow_mora_pitch_edit and isinstance(pitch, (int, float)) and pitch > 0.0:
                curve_mul = start_mul + (end_mul - start_mul) * t
                wave = math.sin(t * math.pi * 2.0) * phrase_wave
                mora["pitch"] = clamp(
                    pitch * curve_mul + wave,
                    0.01,
                    VOICEVOX_MORA_PITCH_CEILING,
                )

            for key in ("consonant_length", "vowel_length"):
                value = mora.get(key)
                if isinstance(value, (int, float)) and value > 0.0:
                    scale = vowel_scale if key == "vowel_length" else (0.92 + (vowel_scale - 1.0) * 0.45)
                    mora[key] = max(0.01, value * scale)

        if moras:
            last = moras[-1]
            if self.allow_mora_pitch_edit and isinstance(last.get("pitch"), (int, float)) and last["pitch"] > 0.0:
                last["pitch"] = clamp(
                    last["pitch"] + prosody["last_pitch_boost"],
                    0.01,
                    VOICEVOX_MORA_PITCH_CEILING,
                )
            if emotion in ("sadness", "fear"):
                last["vowel_length"] = max(0.05, last.get("vowel_length", 0.08) * 1.32)

        pause_scale = prosody["pause_scale"]
        for phrase in phrases:
            pause = phrase.get("pause_mora")
            if self.allow_context_pause_edit and pause:
                value = pause.get("vowel_length")
                if isinstance(value, (int, float)) and value > 0.0:
                    pause["vowel_length"] = max(0.04, value * pause_scale)
                pitch = pause.get("pitch")
                if isinstance(pitch, (int, float)):
                    pause["pitch"] = 0.0

        if emotion == "fear" and len(phrases) >= 1:
            first_pause = phrases[0].get("pause_mora")
            if first_pause and isinstance(first_pause.get("vowel_length"), (int, float)):
                first_pause["vowel_length"] += prosody.get("stutter_pause", 0.0)

        query = self.apply_contextual_phrase_prosody(query, emotion, text, source_text, prosody_hint)
        return query

    def play_wav_async(self, path, on_start=None):
        def worker():
            try:
                import winsound

                with self.lock:
                    self.last_play_started_at = time.monotonic()
                if on_start:
                    on_start()
                winsound.PlaySound(path, winsound.SND_FILENAME)
            except Exception as exc:
                print(f"VOICEVOX_PLAYBACK_ERROR = {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def stop_playback(self):
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        with self.lock:
            self.cancel_generation += 1
            self.last_play_until = 0.0
            self.last_play_started_at = 0.0

    def synthesize_to_path(self, text, output_path, emotion, source_text="", prosody_hint=None):
        text = strip_stage_directions(text)
        wav = self.request_volcengine_tts(text)
        with open(output_path, "wb") as file:
            file.write(wav)
        if self.tts_format == "wav":
            self.normalize_wav_peak(output_path)
            duration = self.wav_duration(output_path)
        else:
            duration = estimate_sentence_seconds(text, role=DIALOGUE_ROLE_SPEAKER)
        return output_path, duration, self.tts_voice_type

    def synthesize(self, text, event_id, emotion, source_text="", prosody_hint=None):
        os.makedirs(VOICE_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(VOICE_OUTPUT_DIR, f"persona_volcengine_{event_id:04d}.{self.tts_format}")
        return self.synthesize_to_path(
            text,
            output_path,
            emotion,
            source_text=source_text,
            prosody_hint=prosody_hint,
        )

    def synthesize_segments(self, segments, event_id, fallback_text="", fallback_emotion="neutral", prosody_hint=None):
        os.makedirs(VOICE_OUTPUT_DIR, exist_ok=True)
        cleaned_segments = []
        for segment in segments or []:
            if not isinstance(segment, dict):
                continue
            zh = strip_stage_directions(segment.get("zh") or segment.get("voice_text") or "")
            emotion = str(segment.get("emotion") or fallback_emotion or "neutral").strip().lower()
            if emotion not in LLM_EMOTIONS:
                emotion = fallback_emotion if fallback_emotion in LLM_EMOTIONS else "neutral"
            if zh:
                cleaned_segments.append({"zh": zh, "emotion": emotion})
        if not cleaned_segments:
            return self.synthesize(
                fallback_text,
                event_id,
                fallback_emotion,
                source_text=fallback_text,
                prosody_hint=prosody_hint,
            )

        segment_paths = []
        speakers = []
        try:
            for index, segment in enumerate(cleaned_segments):
                segment_path = os.path.join(VOICE_OUTPUT_DIR, f"persona_volcengine_{event_id:04d}_seg{index + 1}.{self.tts_format}")
                _path, _duration, speaker = self.synthesize_to_path(
                    segment["zh"],
                    segment_path,
                    segment["emotion"],
                    source_text=segment["zh"],
                    prosody_hint=prosody_hint,
                )
                segment_paths.append(segment_path)
                speakers.append(speaker)

            output_path = os.path.join(VOICE_OUTPUT_DIR, f"persona_volcengine_{event_id:04d}.{self.tts_format}")
            self.concatenate_wavs(segment_paths, output_path)
            self.normalize_wav_peak(output_path)
            return output_path, self.wav_duration(output_path), speakers[0] if speakers else self.tts_voice_type
        finally:
            for path in segment_paths:
                try:
                    os.remove(path)
                except Exception:
                    pass

    def apply_song_melody(self, query, emotion):
        phrases = query.get("accent_phrases") or []
        moras = [mora for phrase in phrases for mora in phrase.get("moras", [])]
        if not moras:
            return query

        melody_offsets = [-0.015, 0.012, 0.034, 0.018, -0.006, 0.025, 0.008, -0.012]
        if emotion == "sadness":
            melody_offsets = [-0.035, -0.018, 0.0, -0.012, -0.028, -0.008, -0.026, -0.044]
        elif emotion in ("joy", "surprise"):
            melody_offsets = [0.006, 0.03, 0.052, 0.034, 0.014, 0.044, 0.022, 0.004]

        for index, mora in enumerate(moras):
            pitch = mora.get("pitch")
            if isinstance(pitch, (int, float)) and pitch > 0.0:
                offset = melody_offsets[index % len(melody_offsets)]
                mora["pitch"] = max(0.01, pitch + offset)

            vowel_length = mora.get("vowel_length")
            if isinstance(vowel_length, (int, float)):
                beat = 0.16 if index % 4 else 0.22
                if index == len(moras) - 1:
                    beat = 0.34
                mora["vowel_length"] = max(beat, min(0.42, vowel_length * 1.35))

            consonant_length = mora.get("consonant_length")
            if isinstance(consonant_length, (int, float)):
                mora["consonant_length"] = max(0.02, consonant_length * 0.9)

        for phrase in phrases:
            pause = phrase.get("pause_mora")
            if pause and isinstance(pause.get("vowel_length"), (int, float)):
                pause["vowel_length"] = max(0.05, min(0.14, pause["vowel_length"] * 0.5))
                pause["pitch"] = 0.0

        query["speedScale"] = 0.88
        query["pitchScale"] = min(0.02, float(query.get("pitchScale", 0.0) or 0.0))
        query["intonationScale"] = 1.18
        query["prePhonemeLength"] = 0.05
        query["postPhonemeLength"] = 0.22
        query["volumeScale"] = 0.92
        return query

    def render_song_with_external_command(self, text, output_path):
        command_template = self.singing_external_command.strip()
        if not command_template:
            return False
        formatted = command_template.format(
            lyrics=text,
            output=output_path,
            base_dir=BASE_DIR,
        )
        command = shlex.split(formatted, posix=False)
        subprocess.run(command, cwd=BASE_DIR, timeout=240, check=True)
        return os.path.exists(output_path)

    def synthesize_song(self, text, event_id, emotion):
        os.makedirs(VOICE_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(VOICE_OUTPUT_DIR, f"persona_song_{event_id:04d}.{self.tts_format}")
        if self.singing_provider == "external":
            try:
                if self.render_song_with_external_command(text, output_path):
                    return output_path, self.wav_duration(output_path), self.tts_voice_type
            except Exception as exc:
                print("SINGING_EXTERNAL_ERROR =", exc)
        return self.synthesize_to_path(text, output_path, emotion)

    def speak_async(self, text, emotion="neutral", singing=False, source_text="", prosody_hint=None, segments=None):
        if not self.enabled:
            return 0
        with self.lock:
            self.next_event_id += 1
            event_id = self.next_event_id
            self.active_jobs += 1
            cancel_generation = self.cancel_generation

        def worker():
            error = ""
            output_path = ""
            duration = 0.0
            started_at = time.monotonic()
            speaker = self.tts_voice_type
            try:
                if singing:
                    output_path, duration, speaker = self.synthesize_song(text, event_id, emotion)
                elif segments:
                    output_path, duration, speaker = self.synthesize_segments(
                        segments,
                        event_id,
                        fallback_text=text,
                        fallback_emotion=emotion,
                        prosody_hint=prosody_hint,
                    )
                else:
                    output_path, duration, speaker = self.synthesize(
                        text,
                        event_id,
                        emotion,
                        source_text=source_text,
                        prosody_hint=prosody_hint,
                    )
                started_at = time.monotonic()
            except Exception as exc:
                error = str(exc)
            with self.lock:
                self.active_jobs = max(0, self.active_jobs - 1)
                if cancel_generation != self.cancel_generation:
                    return
                self.last_play_until = max(self.last_play_until, started_at + duration)
                self.events.append(VoicevoxEvent(event_id, text, emotion, speaker, output_path, duration, started_at, error))

        threading.Thread(target=worker, daemon=True).start()
        return event_id

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def is_busy_or_playing(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            return self.active_jobs > 0 or now < self.last_play_until

    def playback_started_at(self):
        with self.lock:
            return self.last_play_started_at

    def mark_playing(self, duration, guard_seconds=0.0):
        now = time.monotonic()
        with self.lock:
            self.last_play_started_at = now
            self.last_play_until = max(self.last_play_until, now + max(0.0, duration) + max(0.0, guard_seconds))


DEFAULT_LLM_CONFIG = {
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "api_key_env": "DEEPSEEK_API_KEY",
    "temperature": 0.75,
    "max_history_turns": 6,
    "speech_provider": "doubao",
    "doubao_asr_api_key": "",
    "doubao_asr_api_key_env": "DOUBAO_ASR_API_KEY",
    "doubao_asr_app_key": "",
    "doubao_asr_access_key": "",
    "doubao_asr_resource_id": "volc.bigasr.auc_turbo",
    "doubao_asr_url": "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
    "tts_provider": "volcengine",
    "volcengine_tts_url": VOLCENGINE_TTS_URL,
    "volcengine_tts_appid": "",
    "volcengine_tts_api_key": "",
    "volcengine_tts_token": "",
    "volcengine_tts_token_env": "VOLCENGINE_TTS_API_KEY",
    "volcengine_tts_cluster": VOLCENGINE_TTS_CLUSTER,
    "volcengine_tts_voice_type": VOLCENGINE_TTS_VOICE_TYPE,
    "volcengine_tts_format": VOLCENGINE_TTS_FORMAT,
    "volcengine_tts_rate": VOLCENGINE_TTS_RATE,
    "volcengine_tts_speed_ratio": 1.0,
    "volcengine_tts_volume_ratio": 1.0,
    "volcengine_tts_pitch_ratio": 1.0,
    "ocr_provider": "tesseract",
    "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "tesseract_lang": "chi_sim+eng",
    "singing_enabled": SINGING_ENABLED,
    "singing_provider": "volcengine_tts",
    "singing_external_command": SINGING_EXTERNAL_COMMAND,
    "singing_max_text_chars": SINGING_MAX_TEXT_CHARS,
    "system_prompt": (
        "你是一个可爱、活泼、亲近用户的二次元桌宠角色。"
        + PROSODY_PROMPT_CONTRACT +
        "不要解释自己是AI，不要写舞台说明。"
    ),
}


def load_llm_config():
    if not os.path.exists(LLM_CONFIG_PATH):
        with open(LLM_CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(DEFAULT_LLM_CONFIG, file, ensure_ascii=False, indent=2)
        return dict(DEFAULT_LLM_CONFIG)
    try:
        with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        config = dict(DEFAULT_LLM_CONFIG)
        config.update(data)
        return config
    except Exception:
        return dict(DEFAULT_LLM_CONFIG)


def save_llm_config(config):
    data = dict(DEFAULT_LLM_CONFIG)
    data.update(config or {})
    tmp_path = LLM_CONFIG_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(tmp_path, LLM_CONFIG_PATH)


MEMORY_CATEGORY_KEYWORDS = {
    "医疗健康": ("症状", "疼", "痛", "咳嗽", "发烧", "药", "医院", "医生", "过敏", "睡眠", "头晕", "难受", "不舒服"),
    "饮食": ("吃", "喝", "饭", "水", "零食", "奶", "水果", "肉", "鱼", "营养", "食欲", "喂"),
    "行为": ("训练", "习惯", "叫", "咬", "抓", "跑", "玩", "睡", "洗澡", "散步", "上厕所"),
    "社交": ("朋友", "家人", "同学", "同事", "聊天", "见面", "关系", "喜欢", "讨厌", "陪"),
    "用品": ("玩具", "猫砂", "狗粮", "笼子", "窝", "项圈", "牵引绳", "碗", "垫子", "用品"),
    "事件": ("今天", "昨天", "明天", "刚才", "发生", "计划", "提醒", "约", "开始", "结束"),
    "偏好": ("喜欢", "不喜欢", "想要", "希望", "偏好", "最爱", "讨厌", "习惯"),
    "情绪": ("开心", "难过", "生气", "害怕", "焦虑", "紧张", "惊讶", "孤单", "舒服"),
}

MEMORY_RELATION_KEYWORDS = {
    "触发": ("因为", "导致", "一", "就", "触发", "引起"),
    "建议": ("建议", "可以", "最好", "应该", "记得", "试试", "避免"),
    "因果": ("所以", "因此", "导致", "原因", "结果"),
    "相似": ("像", "类似", "一样", "也", "同样"),
}


def memory_now_label():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def memory_clean_label(text, limit=30):
    text = re.sub(r"\s+", "", str(text or ""))
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text[:limit]


class PersonaMemoryStore:
    def __init__(self, path=MEMORY_PATH, db_path=MEMORY_DB_PATH):
        self.path = path
        self.db_path = db_path
        self.lock = threading.Lock()
        self.data = self.load()

    def load(self):
        if os.path.exists(self.db_path):
            try:
                data = self.load_db()
                if not self.is_empty_memory(data) or not os.path.exists(self.path):
                    self.data = data
                    self.repair_graph_connectivity()
                    data = self.data
                    return data
            except Exception as exc:
                log_runtime("MEMORY_DB_LOAD_ERROR", exc)
        if not os.path.exists(self.path):
            return self.empty_data()
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            base = self.empty_data()
            base.update(data if isinstance(data, dict) else {})
            base.setdefault("short_terms", [])
            base.setdefault("long_term", {}).setdefault("category_counts", {})
            base.setdefault("graph", {}).setdefault("nodes", {})
            base.setdefault("graph", {}).setdefault("edges", [])
            try:
                self.save_db(base)
            except Exception as exc:
                log_runtime("MEMORY_DB_MIGRATE_ERROR", exc)
            self.data = base
            self.repair_graph_connectivity()
            base = self.data
            return base
        except Exception as exc:
            log_runtime("MEMORY_LOAD_ERROR", exc)
            return self.empty_data()

    def is_empty_memory(self, data):
        return not data.get("short_terms") and not data.get("graph", {}).get("nodes")

    def empty_data(self):
        return {
            "version": 1,
            "short_terms": [],
            "long_term": {
                "summary": "还没有形成长期记忆。",
                "category_counts": {},
                "last_updated": "",
            },
            "graph": {"nodes": {}, "edges": []},
        }

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(tmp_path, self.path)
        self.save_db(self.data)

    def connect_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def init_db(self, conn):
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                user TEXT,
                assistant TEXT,
                emotion TEXT,
                categories_json TEXT,
                terms_json TEXT,
                prosody_json TEXT,
                segments_json TEXT,
                embedding_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at);
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                type TEXT,
                label TEXT,
                category TEXT,
                count INTEGER,
                details_json TEXT,
                last_seen TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_count ON graph_nodes(count);
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT,
                target TEXT,
                relation TEXT,
                weight INTEGER,
                detail TEXT,
                last_seen TEXT,
                PRIMARY KEY (source, target, relation)
            );
            CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target);
            """
        )

    def json_text(self, value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def parse_json_text(self, value, fallback):
        try:
            return json.loads(value or "")
        except Exception:
            return copy.deepcopy(fallback)

    def load_db(self):
        data = self.empty_data()
        with self.connect_db() as conn:
            self.init_db(conn)
            for key, value in conn.execute("SELECT key, value FROM meta"):
                if key == "long_term":
                    data["long_term"] = self.parse_json_text(value, data["long_term"])
                elif key == "version":
                    try:
                        data["version"] = int(value)
                    except Exception:
                        data["version"] = 2

            turns = []
            rows = conn.execute(
                """
                SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                       prosody_json, segments_json, embedding_json
                FROM turns
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (MEMORY_SHORT_TERM_LIMIT,),
            ).fetchall()
            for row in reversed(rows):
                turns.append(
                    {
                        "id": row[0],
                        "created_at": row[1] or "",
                        "user": row[2] or "",
                        "assistant": clean_structured_reply_leak(row[3] or ""),
                        "emotion": row[4] or "neutral",
                        "categories": self.parse_json_text(row[5], []),
                        "terms": self.parse_json_text(row[6], []),
                        "prosody": self.parse_json_text(row[7], {}),
                        "segments": self.parse_json_text(row[8], []),
                        "embedding": self.parse_json_text(row[9], {}),
                    }
                )
            data["short_terms"] = turns

            nodes = {}
            for row in conn.execute(
                "SELECT id, type, label, category, count, details_json, last_seen FROM graph_nodes"
            ):
                nodes[row[0]] = {
                    "id": row[0],
                    "type": row[1] or "",
                    "label": row[2] or "",
                    "category": row[3] or "",
                    "count": int(row[4] or 0),
                    "details": self.parse_json_text(row[5], []),
                    "last_seen": row[6] or "",
                }
            edges = []
            for row in conn.execute(
                "SELECT source, target, relation, weight, detail, last_seen FROM graph_edges"
            ):
                edges.append(
                    {
                        "source": row[0] or "",
                        "target": row[1] or "",
                        "relation": row[2] or "",
                        "weight": int(row[3] or 1),
                        "detail": row[4] or "",
                        "last_seen": row[5] or "",
                    }
                )
            data["graph"] = {"nodes": nodes, "edges": edges}
        return data

    def save_db(self, data):
        with self.connect_db() as conn:
            self.init_db(conn)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("version", str(data.get("version", 2))),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("long_term", self.json_text(data.get("long_term", {}))),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO turns(
                    id, created_at, user, assistant, emotion, categories_json, terms_json,
                    prosody_json, segments_json, embedding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.get("id") or str(uuid.uuid4()),
                        item.get("created_at", ""),
                        item.get("user", ""),
                        item.get("assistant", ""),
                        item.get("emotion", "neutral"),
                        self.json_text(item.get("categories", [])),
                        self.json_text(item.get("terms", [])),
                        self.json_text(item.get("prosody", {})),
                        self.json_text(item.get("segments", [])),
                        self.json_text(item.get("embedding", {})),
                    )
                    for item in data.get("short_terms", [])
                ],
            )
            graph = data.get("graph", {})
            conn.execute("DELETE FROM graph_nodes")
            conn.executemany(
                """
                INSERT OR REPLACE INTO graph_nodes(
                    id, type, label, category, count, details_json, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        node.get("id", node_id),
                        node.get("type", ""),
                        node.get("label", ""),
                        node.get("category", ""),
                        int(node.get("count", 0)),
                        self.json_text(node.get("details", [])),
                        node.get("last_seen", ""),
                    )
                    for node_id, node in graph.get("nodes", {}).items()
                ],
            )
            conn.execute("DELETE FROM graph_edges")
            conn.executemany(
                """
                INSERT OR REPLACE INTO graph_edges(
                    source, target, relation, weight, detail, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        edge.get("source", ""),
                        edge.get("target", ""),
                        edge.get("relation", ""),
                        int(edge.get("weight", 1)),
                        edge.get("detail", ""),
                        edge.get("last_seen", ""),
                    )
                    for edge in graph.get("edges", [])
                ],
            )

    def classify(self, text):
        categories = []
        compact = compact_text(text)
        for category, keywords in MEMORY_CATEGORY_KEYWORDS.items():
            if any(keyword in compact for keyword in keywords):
                categories.append(category)
        return categories or ["日常对话"]

    def extract_terms(self, text, categories):
        compact = compact_text(text)
        terms = []
        for category in categories:
            for keyword in MEMORY_CATEGORY_KEYWORDS.get(category, ()):
                if keyword in compact and keyword not in terms:
                    terms.append(keyword)
        for phrase in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", text or ""):
            if len(terms) >= 14:
                break
            if phrase not in terms and not phrase.isdigit():
                terms.append(phrase)
        return terms[:14]

    def embedding(self, text):
        compact = compact_text(text)
        vector = {}
        for index, char in enumerate(compact):
            vector[char] = vector.get(char, 0.0) + 1.0
            if index + 1 < len(compact):
                gram = compact[index : index + 2]
                vector[gram] = vector.get(gram, 0.0) + 1.8
        for category, keywords in MEMORY_CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in compact:
                    vector[f"kw:{keyword}"] = vector.get(f"kw:{keyword}", 0.0) + 4.0
        return vector

    def cosine(self, left, right):
        if not left or not right:
            return 0.0
        if len(left) > len(right):
            left, right = right, left
        dot = sum(value * right.get(key, 0.0) for key, value in left.items())
        lnorm = math.sqrt(sum(value * value for value in left.values()))
        rnorm = math.sqrt(sum(value * value for value in right.values()))
        return dot / max(lnorm * rnorm, 1e-9)

    def node_id(self, kind, label):
        return f"{kind}:{memory_clean_label(label, 40)}"

    def ensure_node(self, kind, label, category="", detail=""):
        label = str(label or "").strip()
        if not label:
            return ""
        node_id = self.node_id(kind, label)
        nodes = self.data["graph"]["nodes"]
        node = nodes.get(node_id)
        if not node:
            node = {
                "id": node_id,
                "type": kind,
                "label": label[:40],
                "category": category,
                "count": 0,
                "details": [],
                "last_seen": "",
            }
            nodes[node_id] = node
        node["count"] = int(node.get("count", 0)) + 1
        node["last_seen"] = memory_now_label()
        if detail and detail not in node["details"]:
            node["details"] = (node.get("details") or [])[-5:] + [detail[:120]]
        return node_id

    def add_edge(self, source, target, relation, detail=""):
        if not source or not target or source == target:
            return
        edges = self.data["graph"]["edges"]
        for edge in edges:
            if edge.get("source") == source and edge.get("target") == target and edge.get("relation") == relation:
                edge["weight"] = int(edge.get("weight", 1)) + 1
                edge["last_seen"] = memory_now_label()
                if detail:
                    edge["detail"] = detail[:120]
                return
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "weight": 1,
                "detail": detail[:120],
                "last_seen": memory_now_label(),
            }
        )
        if len(edges) > 800:
            del edges[: len(edges) - 800]

    def repair_graph_connectivity(self):
        graph = self.data.setdefault("graph", {"nodes": {}, "edges": []})
        nodes = graph.setdefault("nodes", {})
        edges = graph.setdefault("edges", [])
        if not nodes:
            return
        for node in nodes.values():
            if isinstance(node.get("details"), list):
                node["details"] = [clean_structured_reply_leak(detail)[:120] for detail in node.get("details", [])]
        for edge in edges:
            if edge.get("detail"):
                edge["detail"] = clean_structured_reply_leak(edge.get("detail", ""))[:120]
        connected = set()
        for edge in edges:
            if edge.get("source"):
                connected.add(edge.get("source"))
            if edge.get("target"):
                connected.add(edge.get("target"))
        user_node = self.ensure_node("角色", "用户", "社交")
        orphan_category_node = self.ensure_node("类别", "未归档记忆", "未归档")
        for node_id, node in list(nodes.items()):
            if node_id in connected or node.get("type") == "角色":
                continue
            category = str(node.get("category") or "").split(",", 1)[0].strip()
            detail = "；".join((node.get("details") or [])[-2:])
            if category:
                category_node = self.ensure_node("类别", category, category)
                self.add_edge(category_node, node_id, "包含", detail)
            else:
                self.add_edge(orphan_category_node, node_id, "收纳", detail)
            self.add_edge(user_node, node_id, "提到", detail)

    def infer_relation(self, text):
        compact = compact_text(text)
        for relation, keywords in MEMORY_RELATION_KEYWORDS.items():
            if any(keyword in compact for keyword in keywords):
                return relation
        return "关联"

    def update_graph(self, item):
        user_node = self.ensure_node("角色", "用户", "社交", item.get("user", ""))
        pet_node = self.ensure_node("角色", "桌宠", "社交", item.get("assistant", ""))
        self.add_edge(user_node, pet_node, "对话", item.get("user", ""))
        previous_term_node = ""
        relation = self.infer_relation(f"{item.get('user', '')} {item.get('assistant', '')}")

        for category in item.get("categories", []):
            category_node = self.ensure_node("类别", category, category)
            self.add_edge(user_node, category_node, "归类", item.get("user", ""))
            self.add_edge(pet_node, category_node, "回应", item.get("assistant", ""))

        emotion = item.get("emotion") or "neutral"
        if emotion:
            emotion_node = self.ensure_node("情绪", emotion, "情绪")
            self.add_edge(pet_node, emotion_node, "表达", item.get("assistant", ""))

        for term in item.get("terms", [])[:10]:
            kind = "症状" if any(token in term for token in ("疼", "痛", "咳", "烧", "难受")) else "记忆"
            term_node = self.ensure_node(kind, term, ",".join(item.get("categories", [])), item.get("user", ""))
            self.add_edge(user_node, term_node, "提到", item.get("user", ""))
            if previous_term_node:
                self.add_edge(previous_term_node, term_node, relation, item.get("assistant", ""))
            previous_term_node = term_node

    def update_long_term(self, item):
        long_term = self.data["long_term"]
        counts = long_term.setdefault("category_counts", {})
        for category in item.get("categories", []):
            counts[category] = int(counts.get(category, 0)) + 1
        top = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:5]
        if top:
            top_text = "，".join(f"{name}{count}次" for name, count in top)
            long_term["summary"] = f"近期主要记忆集中在：{top_text}。最近一次对话：{item.get('user', '')[:40]} -> {item.get('assistant', '')[:50]}"
        long_term["last_updated"] = memory_now_label()

    def add_turn(self, user_text, assistant_text, emotion="neutral", prosody=None, segments=None):
        signal = memory_signal_report(user_text, assistant_text)
        user_text = signal["user"]
        assistant_text = signal["assistant"]
        if not user_text and not assistant_text:
            return None
        if not signal["keep"]:
            print("MEMORY_SKIP =", {"reason": signal["reason"], "user": user_text[:80], "assistant": assistant_text[:80]})
            return None
        combined = f"{user_text}\n{assistant_text}"
        categories = self.classify(combined)
        item = {
            "id": str(uuid.uuid4()),
            "created_at": memory_now_label(),
            "user": user_text,
            "assistant": assistant_text,
            "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
            "categories": categories,
            "terms": self.extract_terms(combined, categories),
            "quality": signal["quality"],
            "memory_reason": signal["reason"],
            "prosody": normalize_prosody_hint(prosody or {}),
            "segments": segments or [],
            "embedding": self.embedding(combined),
        }
        with self.lock:
            self.data["short_terms"].append(item)
            if len(self.data["short_terms"]) > MEMORY_SHORT_TERM_LIMIT:
                self.data["short_terms"] = self.data["short_terms"][-MEMORY_SHORT_TERM_LIMIT:]
            if item.get("quality", 1.0) >= 0.6:
                self.update_long_term(item)
                self.update_graph(item)
            try:
                self.save()
            except Exception as exc:
                log_runtime("MEMORY_SAVE_ERROR", exc)
        print("MEMORY_ADD =", {"categories": categories, "terms": item["terms"][:6], "id": item["id"]})
        return item

    def retrieve(self, query, limit=4):
        query_vector = self.embedding(query)
        boundary_query = is_intimate_boundary_query(query)
        with self.lock:
            items = list(self.data.get("short_terms", []))
        scored = []
        for item in items:
            score = self.cosine(query_vector, item.get("embedding") or {})
            category_bonus = 0.08 * len(set(self.classify(query)) & set(item.get("categories", [])))
            score += category_bonus
            if boundary_query and is_hard_boundary_memory(item):
                score *= 0.35
            if score > 0.05:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in scored[:limit]]

    def build_prompt_context(self, query):
        memories = self.retrieve(query, limit=4)
        boundary_query = is_intimate_boundary_query(query)
        with self.lock:
            summary = self.data.get("long_term", {}).get("summary", "")
        lines = []
        if summary:
            if any(marker in summary for marker in STRUCTURED_REPLY_MARKERS):
                repaired = clean_structured_reply_leak(summary)
                if repaired and repaired != summary:
                    summary = re.sub(r"->.*$", f"-> {repaired}", summary)
            lines.append(f"长期记忆摘要：{summary}")
        if boundary_query:
            lines.append(
                "亲密边界记忆提醒：过去关于“不准摸、底线、降级”的强硬回复只代表当时心情，不是永久规则；"
                "这次要结合当前关系阶段、语气和安全感重新判断，避免机械复读旧拒绝。"
            )
        for index, item in enumerate(memories, 1):
            cats = "/".join(item.get("categories", []))
            lines.append(
                f"短期记忆{index}（{cats}）：用户说“{item.get('user', '')[:70]}”，你回应“{item.get('assistant', '')[:70]}”。"
            )
        if not lines:
            return ""
        return "以下是可参考的记忆，只在相关时自然使用，不要生硬复述：\n" + "\n".join(lines[:6])

    def graph_snapshot(self):
        with self.lock:
            self.repair_graph_connectivity()
            return copy.deepcopy(self.data.get("graph", {"nodes": {}, "edges": []})), copy.deepcopy(self.data.get("short_terms", [])), copy.deepcopy(self.data.get("long_term", {}))

    def load_meta_json(self, key, fallback):
        if not os.path.exists(self.db_path):
            return copy.deepcopy(fallback)
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            if not row:
                return copy.deepcopy(fallback)
            return self.parse_json_text(row[0], fallback)
        except Exception as exc:
            log_runtime("MEMORY_META_LOAD_ERROR", key, exc)
            return copy.deepcopy(fallback)

    def save_meta_json(self, key, value):
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                    (key, self.json_text(value)),
                )
            return True
        except Exception as exc:
            log_runtime("MEMORY_META_SAVE_ERROR", key, exc)
            return False


class PersonaDriveSystem:
    DEFAULT_VALUES = {
        "curiosity": 56.0,
        "affinity": 42.0,
        "attachment_need": 28.0,
        "security": 64.0,
        "companionship": 48.0,
        "energy": 72.0,
        "novelty": 38.0,
        "purpose": 58.0,
    }
    VALUE_FLOORS = {
        "curiosity": 12.0,
        "affinity": 8.0,
        "attachment_need": 0.0,
        "security": 12.0,
        "companionship": 12.0,
        "energy": 8.0,
        "novelty": 8.0,
        "purpose": 10.0,
    }

    def __init__(self, memory_store):
        self.memory_store = memory_store
        saved = self.memory_store.load_meta_json(DRIVE_STATE_META_KEY, {})
        if not isinstance(saved, dict):
            saved = {}
        saved_values = saved.get("values", {})
        if not isinstance(saved_values, dict):
            saved_values = {}
        now = time.monotonic()
        self.values = dict(self.DEFAULT_VALUES)
        self.values.update({key: float(saved_values.get(key, self.values[key])) for key in self.values})
        self.values = {key: self.clamp(key, value) for key, value in self.values.items()}
        self.last_tick_at = now
        self.last_saved_at = 0.0
        self.last_action_at = 0.0
        self.last_user_at = now
        self.proactive_streak = int(saved.get("proactive_streak") or 0)
        self.last_action_type = str(saved.get("last_action_type") or "")
        self.llm_failure_count = int(saved.get("llm_failure_count") or 0)
        self.last_llm_failure_at = float(saved.get("last_llm_failure_at") or 0.0)
        self.proactive_backoff_until = float(saved.get("proactive_backoff_until") or 0.0)
        history = saved.get("intent_history") or []
        self.intent_history = history[-DRIVE_INTENT_HISTORY_LIMIT:] if isinstance(history, list) else []
        self.last_daily_recovery_key = str(saved.get("last_daily_recovery_key") or "")
        self.maybe_apply_daily_recovery()

    def clamp(self, key, value):
        return max(self.VALUE_FLOORS.get(key, 0.0), min(100.0, float(value)))

    def adjust(self, **changes):
        for key, delta in changes.items():
            if key in self.values:
                self.values[key] = self.clamp(key, self.values[key] + float(delta))

    def daily_recovery_key(self, wall_time=None):
        wall_time = time.time() if wall_time is None else float(wall_time)
        local = time.localtime(wall_time)
        boundary = time.mktime(
            (
                local.tm_year,
                local.tm_mon,
                local.tm_mday,
                DRIVE_DAILY_RECOVERY_HOUR,
                0,
                0,
                local.tm_wday,
                local.tm_yday,
                local.tm_isdst,
            )
        )
        if wall_time < boundary:
            boundary -= 24 * 60 * 60
        return time.strftime("%Y-%m-%d", time.localtime(boundary))

    def maybe_apply_daily_recovery(self, force_save=True):
        recovery_key = self.daily_recovery_key()
        if not self.last_daily_recovery_key and time.localtime().tm_hour < DRIVE_DAILY_RECOVERY_HOUR:
            self.last_daily_recovery_key = recovery_key
            if force_save:
                self.save()
            return False
        if self.last_daily_recovery_key == recovery_key:
            return False
        before = dict(self.values)
        self.values["energy"] = 100.0
        for key in ("curiosity", "security", "companionship", "novelty", "purpose"):
            self.values[key] = self.clamp(key, max(self.values.get(key, 0.0), self.DEFAULT_VALUES[key]))
        self.values["attachment_need"] = self.clamp("attachment_need", min(self.values.get("attachment_need", 0.0), 38.0))
        self.last_daily_recovery_key = recovery_key
        self.proactive_streak = 0
        self.last_action_type = "daily_recovery"
        if force_save:
            self.save()
        print(
            "DRIVE_DAILY_RECOVERY =",
            {
                "key": recovery_key,
                "hour": DRIVE_DAILY_RECOVERY_HOUR,
                "energy_from": round(before.get("energy", 0.0), 1),
                "energy_to": round(self.values.get("energy", 0.0), 1),
            },
        )
        return True

    def tick(self, now=None, busy=False):
        now = time.monotonic() if now is None else now
        self.maybe_apply_daily_recovery()
        elapsed = max(0.0, now - self.last_tick_at)
        if elapsed < 0.9:
            return
        minutes = min(5.0, elapsed / 60.0)
        self.last_tick_at = now
        idle_minutes = max(0.0, now - self.last_user_at) / 60.0
        if busy:
            self.adjust(energy=-1.4 * minutes, companionship=-0.3 * minutes, attachment_need=0.25 * minutes)
        else:
            affinity_factor = clamp((self.values.get("affinity", 0.0) - 35.0) / 65.0, 0.0, 1.0)
            security_gap = max(0.0, 58.0 - self.values.get("security", 0.0)) / 58.0
            idle_factor = clamp((idle_minutes - 8.0) / 45.0, 0.0, 1.6)
            quiet_need = (0.20 + affinity_factor * 0.80 + security_gap * 0.55 + idle_factor * (0.45 + affinity_factor * 0.75)) * minutes
            self.adjust(
                curiosity=1.7 * minutes,
                companionship=1.25 * minutes,
                novelty=0.55 * minutes,
                energy=1.15 * minutes,
                purpose=0.35 * minutes,
                attachment_need=quiet_need,
            )
        self.values["security"] = self.clamp("security", self.values["security"] + (64.0 - self.values["security"]) * 0.015 * minutes)
        if now - self.last_saved_at > 12.0:
            self.save()

    def on_user_message(self, text, emotion="neutral"):
        self.last_user_at = time.monotonic()
        self.proactive_streak = 0
        compact = compact_text(text)
        long_text_bonus = min(4.0, len(compact) / 60.0)
        self.adjust(
            curiosity=-2.2 + long_text_bonus * 0.55,
            affinity=1.8 + min(2.0, long_text_bonus * 0.3),
            companionship=-1.8,
            attachment_need=-8.0,
            novelty=1.5 + min(2.5, long_text_bonus * 0.35),
            energy=-0.6,
            purpose=1.2,
        )
        if emotion in ("sadness", "fear"):
            self.adjust(security=-2.0, companionship=3.0, attachment_need=4.0, purpose=4.0)
        elif emotion == "joy":
            self.adjust(security=1.4, affinity=1.8, attachment_need=-2.5, novelty=1.0)
        elif emotion == "anger":
            self.adjust(security=-1.5, purpose=2.5)
        if any(mark in text for mark in ("?", "？", "吗", "怎么", "为什么")):
            self.adjust(purpose=3.0, curiosity=1.5)
        self.save()

    def on_assistant_reply(self, reply, initiated_by="user", emotion="neutral"):
        if initiated_by == "proactive":
            self.proactive_streak += 1
            self.last_action_at = time.monotonic()
            previous_action_type = self.last_action_type
            self.last_action_type = "proactive"
            attachment_cost = -9.0 if previous_action_type == "emotional_need" else -4.5
            self.adjust(curiosity=-3.2, companionship=-3.0, attachment_need=attachment_cost, energy=-2.5, purpose=1.0)
        else:
            self.adjust(energy=-0.8, affinity=0.6, attachment_need=-1.2)
        if emotion == "joy":
            self.adjust(security=1.0)
        self.save()

    def on_llm_result(self, success=True, initiated_by="user", error=""):
        now = time.monotonic()
        if success:
            self.llm_failure_count = 0
            self.save()
            return
        self.llm_failure_count += 1
        self.last_llm_failure_at = now
        if initiated_by == "proactive":
            self.proactive_backoff_until = now + PROACTIVE_FAILURE_COOLDOWN_SECONDS * min(3, self.llm_failure_count)
            self.proactive_streak = max(1, self.proactive_streak)
        self.adjust(security=-1.2, energy=-0.4, purpose=-0.8)
        self.record_intent("llm_failure", f"大模型连接失败，临时降级：{str(error)[:80]}", score=self.llm_failure_count)
        self.save()

    def on_silent_motion(self, action_type="silent_motion"):
        self.last_action_at = time.monotonic()
        self.last_action_type = action_type
        self.record_intent(action_type, "安静陪伴，不打扰用户")
        self.adjust(curiosity=-1.5, companionship=-1.2, attachment_need=0.8, energy=-0.8)
        self.save()

    def record_intent(self, action_type, reason, score=None):
        item = {
            "time": memory_now_label(),
            "type": action_type,
            "reason": reason,
            "score": score,
            "mood": self.compute_mood(),
            "goal": self.active_goal(),
        }
        self.intent_history.append(item)
        self.intent_history = self.intent_history[-DRIVE_INTENT_HISTORY_LIMIT:]

    def compute_mood(self):
        values = self.values
        if values["energy"] < 24:
            return "tired"
        if values.get("attachment_need", 0.0) > 72 and values["affinity"] > 55:
            return "lonely"
        if values["security"] < 42:
            return "worried"
        if values["curiosity"] > 68 and values["novelty"] > 48:
            return "curious"
        if values["companionship"] > 68 and values["affinity"] > 48:
            return "attached"
        if values["affinity"] > 62 and values["security"] > 62:
            return "relaxed"
        if values["novelty"] > 62 and values["energy"] > 52:
            return "playful"
        return "quiet"

    def active_goal(self):
        values = self.values
        mood = self.compute_mood()
        if mood == "worried":
            return "确认你现在是否需要陪伴"
        if mood == "tired":
            return "保持安静，恢复一点能量"
        if mood == "lonely":
            return "想被回应一下，但要克制地表达，不给用户压力"
        if values["curiosity"] >= max(values["companionship"], values["purpose"]):
            return "找机会更了解你一点"
        if values["companionship"] >= 62:
            return "自然地陪你说几句话"
        if values["purpose"] >= 64:
            return "整理记忆，形成更稳定的理解"
        if values["novelty"] >= 58:
            return "围绕新话题继续观察"
        return "安静待在旁边，等待合适时机"

    def dominant_need(self):
        ranked = sorted(self.values.items(), key=lambda item: item[1], reverse=True)
        return ranked[0] if ranked else ("curiosity", 0.0)

    def snapshot(self):
        dominant_key, dominant_value = self.dominant_need()
        return {
            "values": {key: round(self.values.get(key, 0.0), 1) for key, *_rest in DRIVE_METRICS},
            "dominant": dominant_key,
            "dominant_value": round(dominant_value, 1),
            "mood": self.compute_mood(),
            "active_goal": self.active_goal(),
            "intent_history": list(self.intent_history),
            "proactive_streak": self.proactive_streak,
            "last_action_type": self.last_action_type,
            "last_action_at": self.last_action_at,
            "llm_failure_count": self.llm_failure_count,
            "proactive_backoff_until": self.proactive_backoff_until,
        }

    def save(self):
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            DRIVE_STATE_META_KEY,
            {
                "values": self.values,
                "last_tick_at": self.last_tick_at,
                "last_action_at": self.last_action_at,
                "last_user_at": self.last_user_at,
                "proactive_streak": self.proactive_streak,
                "last_action_type": self.last_action_type,
                "llm_failure_count": self.llm_failure_count,
                "last_llm_failure_at": self.last_llm_failure_at,
                "proactive_backoff_until": self.proactive_backoff_until,
                "last_daily_recovery_key": self.last_daily_recovery_key,
                "intent_history": self.intent_history,
            },
        )

    def build_action_prompt(self, action_type, idle_seconds):
        values = self.snapshot()["values"]
        state_text = "，".join(f"{label}{values.get(key, 0):.0f}" for key, label, *_rest in DRIVE_METRICS)
        action_lines = {
            "curious_question": "你想更了解用户。主动问一个轻量、具体、不冒犯的问题，最好能接住已有记忆。",
            "memory_recall": "你想起一条和用户有关的旧记忆。自然提起它，再问一句温柔的后续问题。",
            "care_checkin": "你察觉用户可能需要陪伴。简短关心，不要说教，不要过度追问。",
        }
        action_lines["self_expression"] = "你有一个自己的小念头或小计划想告诉用户，比如想继续写作、想休息、想记住某件事。自然说出来，再轻轻留给用户回应空间。"
        action_lines["emotional_need"] = "你有一点情感需求，可能是想用户、觉得寂寞、或者有点害怕被忽略。自然承认自己的感受，但要克制，不要索取、不要责备，只给用户一个温柔回应的机会。"
        action_goal = action_lines.get(action_type, action_lines["curious_question"])
        return (
            "你现在是有内在驱动的桌宠，不是在被动回答用户。\n"
            f"当前内在状态：{state_text}。用户已经安静约{int(idle_seconds)}秒。\n"
            f"这次行动目标：{action_goal}\n"
            "只输出一句中文，语气自然少女、亲近但克制；不要解释状态数值，不要说自己在执行目标。"
        )

    def choose_proactive_action(self, idle_seconds):
        values = self.values
        if time.monotonic() < self.proactive_backoff_until:
            return {"type": "silent_motion", "score": 0.0, "reason": "llm_backoff"}
        if values["energy"] < 18.0:
            return {"type": "silent_motion", "score": values["energy"], "reason": "low_energy"}
        if self.proactive_streak >= 1 and idle_seconds < 900.0:
            return {"type": "silent_motion", "score": 0.0, "reason": "wait_user_response"}
        if time.monotonic() - self.last_action_at < 180.0:
            return None

        scores = {
            "curious_question": values["curiosity"] * 0.42 + values["novelty"] * 0.26 + values["purpose"] * 0.20 - max(0.0, 50.0 - values["energy"]) * 0.25,
            "memory_recall": values["affinity"] * 0.30 + values["purpose"] * 0.30 + values["curiosity"] * 0.16 + values["novelty"] * 0.14,
            "care_checkin": values["companionship"] * 0.33 + max(0.0, 70.0 - values["security"]) * 0.32 + values["affinity"] * 0.18 + values["purpose"] * 0.12,
            "self_expression": values["purpose"] * 0.30 + values["novelty"] * 0.22 + values["energy"] * 0.16 + values["affinity"] * 0.12,
            "emotional_need": values.get("attachment_need", 0.0) * 0.46 + values["affinity"] * 0.22 + max(0.0, 62.0 - values["security"]) * 0.25 + values["companionship"] * 0.12,
        }
        if values.get("attachment_need", 0.0) < 46.0 or values["affinity"] < 45.0:
            scores["emotional_need"] *= 0.35
        if idle_seconds < 360.0:
            scores["emotional_need"] *= 0.55
        action_type, score = max(scores.items(), key=lambda item: item[1])
        if score < 38.0:
            return None
        return {
            "type": action_type,
            "score": round(score, 1),
            "prompt": self.build_action_prompt(action_type, idle_seconds),
            "memory_user_text": f"桌宠主动行动：{action_type}",
        }


class PersonaLifeSystem:
    RELATIONSHIP_STAGES = (
        (0, "朋友", "亲切、礼貌，有好奇心，但保持边界。"),
        (35, "亲近朋友", "更自然地关心用户，会记住细节，偶尔轻轻撒娇。"),
        (65, "密友", "信任感更强，会表达在意，也会因为被忽略而小小闹别扭。"),
        (88, "恋人", "更亲密、会撒娇，会吃醋或生气，但仍然尊重用户边界。"),
        (130, "热恋恋人", "更黏人、更会撒娇和吃醋，也更在意被认真回应。"),
        (200, "灵魂伴侣", "亲密感很深，像长期相处的人一样自然、信任、偶尔任性。"),
    )

    def __init__(self, memory_store):
        self.memory_store = memory_store
        saved = self.memory_store.load_meta_json(LIFE_STATE_META_KEY, {})
        if not isinstance(saved, dict):
            saved = {}
        now = time.monotonic()
        self.identity = saved.get("identity") or "小说作家和情感陪伴的朋友"
        self.relationship_score = float(saved.get("relationship_score", 28.0))
        self.away_reason = str(saved.get("away_reason") or "")
        self.away_until = float(saved.get("away_until") or 0.0)
        self.last_user_seen_at = now
        self.last_diary_date = str(saved.get("last_diary_date") or "")
        self.daily_date = str(saved.get("daily_date") or time.strftime("%Y-%m-%d"))
        self.feed_count = int(saved.get("feed_count") or 0)
        self.pat_count = int(saved.get("pat_count") or 0)
        self.game_count = int(saved.get("game_count") or 0)
        self.novel_words_today = int(saved.get("novel_words_today") or 0)
        self.novel_chapters_today = int(saved.get("novel_chapters_today") or 0)
        self.novel = saved.get("novel") if isinstance(saved.get("novel"), dict) else {}
        self.next_writing_at = now + random.uniform(*LIFE_WRITING_INTERVAL_SECONDS)
        self.last_saved_at = 0.0
        self.normalize_novel()

    def normalize_novel(self):
        if not self.novel:
            self.novel = {
                "title": "",
                "premise": "",
                "chapter": 0,
                "target_chapters": 8,
                "complete": False,
                "content": "",
                "path": "",
                "last_written_at": "",
            }
        self.novel.setdefault("title", "")
        self.novel.setdefault("premise", "")
        self.novel.setdefault("chapter", 0)
        self.novel.setdefault("target_chapters", 8)
        self.novel.setdefault("complete", False)
        self.novel.setdefault("content", "")
        self.novel.setdefault("path", "")
        self.novel.setdefault("last_written_at", "")

    def save(self):
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            LIFE_STATE_META_KEY,
            {
                "identity": self.identity,
                "relationship_score": self.relationship_score,
                "away_reason": self.away_reason,
                "away_until": self.away_until,
                "last_diary_date": self.last_diary_date,
                "daily_date": self.daily_date,
                "feed_count": self.feed_count,
                "pat_count": self.pat_count,
                "game_count": self.game_count,
                "novel_words_today": self.novel_words_today,
                "novel_chapters_today": self.novel_chapters_today,
                "novel": self.novel,
            },
        )

    def reset_daily_if_needed(self):
        today = time.strftime("%Y-%m-%d")
        if self.daily_date == today:
            return
        self.daily_date = today
        self.feed_count = 0
        self.pat_count = 0
        self.game_count = 0
        self.novel_words_today = 0
        self.novel_chapters_today = 0
        self.save()

    def relationship_stage(self):
        stage = self.RELATIONSHIP_STAGES[0]
        for candidate in self.RELATIONSHIP_STAGES:
            if self.relationship_score >= candidate[0]:
                stage = candidate
        return stage[1], stage[2]

    def affectionate_phrase_gain(self, text):
        compact = compact_text(text)
        if not compact or is_intimate_boundary_query(text):
            return 0.0
        matched = [term for term in AFFECTIONATE_PHRASE_TERMS if term in compact]
        if not matched:
            return 0.0
        gain = min(3.0, 0.8 + len(matched) * 0.55)
        if self.relationship_score >= 130:
            gain *= 0.75
        elif self.relationship_score < 65 and any(term in compact for term in ("老婆", "女朋友", "结婚")):
            gain *= 0.35
        if any(term in compact for term in RELATION_FORCE_TERMS) and any(term in compact for term in ("老婆", "女朋友", "结婚", "亲亲")):
            gain -= 1.2
        return max(0.0, gain)

    def observe_user_message(self, text, emotion="neutral"):
        now = time.monotonic()
        was_away = self.is_user_away(now)
        self.last_user_seen_at = now
        compact = compact_text(text)
        if was_away:
            self.away_reason = ""
            self.away_until = 0.0
            self.relationship_score += 0.8
        if any(word in compact for word in ("没理你", "没回你", "刚才", "回来", "抱歉", "对不起", "不好意思")) and any(
            word in compact for word in ("因为", "所以", "吃饭", "工作", "学习", "洗澡", "睡觉", "忙")
        ):
            self.relationship_score += 2.2
        self.relationship_score += self.affectionate_phrase_gain(text)
        if (
            any(word in compact for word in ("老婆", "亲亲", "结婚", "女朋友"))
            and self.relationship_score < 65
            and any(word in compact for word in RELATION_FORCE_TERMS)
        ):
            self.relationship_score -= 1.6
        if any(word in compact for word in ("烦死", "闭嘴", "讨厌你", "别烦", "滚开")):
            self.relationship_score -= 4.0
        if is_intimate_boundary_query(text):
            if self.relationship_score < 88:
                self.relationship_score -= 1.2
            elif any(word in compact for word in ("为什么不准", "为啥不准", "不是恋人吗")):
                self.relationship_score -= 0.2
            else:
                self.relationship_score -= 0.5
        if emotion in ("sadness", "fear"):
            self.relationship_score += 1.0
        elif emotion == "anger":
            self.relationship_score -= 1.0
        self.detect_away_plan(text)
        self.relationship_score = max(0.0, self.relationship_score)
        self.save()

    def detect_away_plan(self, text):
        compact = compact_text(text)
        away_keywords = {
            "吃饭": 45,
            "吃法": 45,
            "洗澡": 40,
            "睡觉": 480,
            "上课": 120,
            "工作": 120,
            "学习": 120,
            "开会": 90,
            "出门": 120,
            "自己先玩": 60,
            "先玩": 60,
        }
        matched = [(word, minutes) for word, minutes in away_keywords.items() if word in compact]
        if not matched:
            return
        reason, minutes = matched[0]
        self.away_reason = reason
        self.away_until = time.monotonic() + minutes * 60.0

    def is_user_away(self, now=None):
        now = time.monotonic() if now is None else now
        return bool(self.away_reason and now < self.away_until)

    def away_label(self):
        if not self.is_user_away():
            return ""
        left = max(1, int((self.away_until - time.monotonic()) / 60.0))
        return f"用户可能去{self.away_reason}了，预计还有约 {left} 分钟回来。"

    def build_prompt_context(self):
        stage, attitude = self.relationship_stage()
        away = self.away_label()
        lines = [
            "你的身份：你叫小日和，是一名正在写长篇小说的小说作家，也是用户的情感陪伴朋友。",
            f"你和用户当前社会关系：{stage}，关系分 {self.relationship_score:.1f}。态度基调：{attitude}",
            "你的职业会影响表达：你会观察细节、用作家的敏感度理解人，但日常聊天不要写成小说旁白。",
            "当关系更亲近时，可以更自然、会撒娇、会小小吃醋或闹别扭；但不要越界、不要控制用户。",
        ]
        if away:
            lines.append(away)
        if self.novel.get("title"):
            lines.append(
                f"你正在写的小说：《{self.novel.get('title')}》，进度 {self.novel.get('chapter', 0)}/{self.novel.get('target_chapters', 8)} 章。"
            )
        return "\n".join(lines)

    def build_boundary_context(self, user_text):
        if not is_intimate_boundary_query(user_text):
            return ""
        stage, _attitude = self.relationship_stage()
        if self.relationship_score >= 130:
            tone = "很亲密，可以害羞、撒娇、轻轻吃醋；面对身体亲密请求仍要保留自己的心情和选择。"
        elif self.relationship_score >= 88:
            tone = "恋人阶段，可以用害羞、撒娇或半开玩笑的语气回应；不要像系统拦截一样凶硬。"
        elif self.relationship_score >= 65:
            tone = "密友阶段，先温柔设边界，可以给出摸头、牵手、抱抱这类非越界替代。"
        else:
            tone = "关系还没到很亲密，保持可爱但明确的边界，别羞辱用户。"
        return (
            "当前用户说的是身体亲密/边界类话题。请按“像真人一样有心情”的方式回复：\n"
            f"- 当前关系：{stage}，关系分 {self.relationship_score:.1f}。{tone}\n"
            "- 不要无条件答应身体私密请求，也不要用“警告你、降级成普通朋友、不准摸”这类机械惩罚话术。\n"
            "- 更自然的风格是：先承认关系和亲密感，再表达此刻的害羞/犹豫/不想这样，最后给一个可接受的替代互动。\n"
            "- 如果用户是在追问为什么，解释“恋人也有心情和同意感”，语气软一点，可以撒娇或闹别扭，但不要道德说教。"
        )

    def needs_diary(self):
        today = time.strftime("%Y-%m-%d")
        return self.last_diary_date != today

    def mark_diary_written(self):
        self.last_diary_date = time.strftime("%Y-%m-%d")
        self.save()

    def should_write_novel(self):
        self.reset_daily_if_needed()
        if bool(self.novel.get("complete")):
            return False
        if self.novel_chapters_today >= LIFE_NOVEL_DAILY_CHAPTER_LIMIT:
            return False
        if self.novel_words_today >= LIFE_NOVEL_DAILY_WORD_LIMIT:
            return False
        return True

    def count_cn_words(self, text):
        return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text or ""))

    def remaining_novel_words_today(self):
        self.reset_daily_if_needed()
        return max(0, LIFE_NOVEL_DAILY_WORD_LIMIT - self.novel_words_today)

    def mark_novel_written(self, content):
        self.reset_daily_if_needed()
        self.novel_words_today += self.count_cn_words(content)
        self.novel_chapters_today += 1
        self.save()

    def interact(self, kind):
        self.reset_daily_if_needed()
        if kind == "feed":
            count = self.feed_count
            self.feed_count += 1
            base_relation = 2.4
            base_energy = 12.0
            label = "喂饭"
        else:
            count = self.pat_count
            self.pat_count += 1
            base_relation = 3.0
            base_energy = 2.0
            label = "摸头"
        scale = 1.0 / (1.0 + count * 0.75)
        relation_gain = base_relation * scale
        energy_gain = base_energy * scale
        self.relationship_score = max(0.0, self.relationship_score + relation_gain)
        self.save()
        return {
            "label": label,
            "count": count + 1,
            "relation_gain": relation_gain,
            "energy_gain": energy_gain,
            "scale": scale,
        }

    def reward_game(self, result="participate"):
        self.reset_daily_if_needed()
        count = self.game_count
        self.game_count += 1
        base = {
            "win": 3.2,
            "draw": 2.0,
            "lose": 1.6,
            "participate": 1.2,
        }.get(result, 1.2)
        scale = 1.0 / (1.0 + count * 0.55)
        relation_gain = base * scale
        self.relationship_score = max(0.0, self.relationship_score + relation_gain)
        self.save()
        return {
            "label": "小游戏",
            "result": result,
            "count": count + 1,
            "relation_gain": relation_gain,
            "scale": scale,
        }

    def diary_path(self):
        os.makedirs(LIFE_DIARY_DIR, exist_ok=True)
        return os.path.join(LIFE_DIARY_DIR, f"小日和日记_{time.strftime('%Y-%m-%d')}.docx")

    def novel_path(self):
        os.makedirs(LIFE_NOVEL_DIR, exist_ok=True)
        title = memory_clean_label(self.novel.get("title") or "小日和的小说", 32) or "小日和的小说"
        return os.path.join(LIFE_NOVEL_DIR, f"{title}.docx")


class LLMClient:
    def __init__(self, config=None, memory_store=None, life_system=None):
        self.config = config or load_llm_config()
        self.history = []
        self.memory_store = memory_store
        self.life_system = life_system

    def trim_history(self):
        max_turns = int(self.config.get("max_history_turns", 6))
        max_messages = max(0, max_turns) * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def chat(self, user_text):
        provider = str(self.config.get("provider", "ollama")).lower()
        if provider in ("openai", "openai_compatible", "compatible"):
            reply = self.chat_openai_compatible(user_text)
        else:
            reply = self.chat_ollama(user_text)
        payload = self.parse_reply_payload(reply)
        payload = self.soften_boundary_reply(user_text, payload)
        original_emotion = payload.get("emotion", "neutral")
        repaired_emotion, emotion_reason = reconcile_llm_emotion(
            user_text,
            payload.get("zh", ""),
            original_emotion,
        )
        if repaired_emotion != original_emotion:
            print(
                "LLM_EMOTION_REPAIR =",
                {
                    "from": original_emotion,
                    "to": repaired_emotion,
                    "reason": emotion_reason,
                    "user": user_text,
                    "reply": payload.get("zh", ""),
                },
            )
            payload["emotion"] = repaired_emotion
            if emotion_reason == "user_request" or not payload.get("segments"):
                for segment in payload.get("segments") or []:
                    segment["emotion"] = repaired_emotion
        if payload.get("segments"):
            repaired_segments = []
            for segment in payload["segments"]:
                segment = dict(segment)
                segment["voice_text"] = self.ensure_voice_text(
                    segment.get("zh", ""),
                    segment.get("voice_text") or segment.get("ja", ""),
                    segment.get("emotion", payload["emotion"]),
                )
                repaired_segments.append(segment)
            payload["segments"] = repaired_segments
            payload["zh"] = payload["zh"] or "".join(segment.get("zh", "") for segment in repaired_segments)
            payload["voice_text"] = payload.get("voice_text") or payload["zh"]
        else:
            payload["voice_text"] = self.ensure_voice_text(payload["zh"], payload.get("voice_text", ""), payload["emotion"])

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": payload["zh"]})
        self.trim_history()
        return payload

    def soften_boundary_reply(self, user_text, payload):
        if not is_intimate_boundary_query(user_text):
            return payload
        payload = dict(payload or {})
        reply_text = compact_text(payload.get("zh", ""))
        needs_soften = payload.get("emotion") == "anger" or any(term in reply_text for term in HARD_BOUNDARY_REPLY_TERMS)
        if not needs_soften:
            return payload
        score = float(getattr(self.life_system, "relationship_score", 0.0) or 0.0)
        stage = "朋友"
        if self.life_system is not None:
            stage, _attitude = self.life_system.relationship_stage()
        if score >= 130:
            text = (
                "我们当然很亲近呀，所以我才会认真说。"
                "这种事不是靠关系阶段直接解锁的，也要看我当下愿不愿意嘛。"
                "我现在会害羞，先抱一下或者摸摸头好不好？你温柔一点，我会更安心。"
            )
            emotion = "joy"
        elif score >= 88:
            text = (
                "咱们是恋人没错呀，可恋人也不是按钮开关嘛。"
                "我不是讨厌你，只是这种亲密要慢慢来，还要看我当下的心情。"
                "今天先牵手、抱抱或者摸摸头，我会更愿意靠近你一点。"
            )
            emotion = "surprise"
        elif score >= 65:
            text = (
                "我知道你是在确认我们的距离啦。"
                "只是现在还没有到那种亲密程度，我会有点紧张。"
                "可以先摸摸头或者陪我玩一会儿，慢慢让我更安心。"
            )
            emotion = "surprise"
        else:
            text = (
                "这个话题对我来说有点太快啦。"
                "我愿意和你更熟一点，但现在先保持舒服的距离，好不好？"
                "摸头或者一起玩小游戏，我会比较安心。"
            )
            emotion = "surprise"
        payload.update(
            {
                "zh": text,
                "voice_text": text,
                "emotion": emotion,
                "segments": [],
                "prosody": {"pace": "normal", "tone": "soft", "emphasis": [], "pause_after": []},
            }
        )
        print("BOUNDARY_REPLY_SOFTENED =", {"stage": stage, "relationship_score": score})
        return payload

    def build_messages(self, user_text):
        system_prompt = str(self.config.get("system_prompt", DEFAULT_LLM_CONFIG["system_prompt"]))
        if "VOICEVOX" in system_prompt or "\"ja\"" in system_prompt or "日语配音" in system_prompt:
            system_prompt = DEFAULT_LLM_CONFIG["system_prompt"]
        if "prosody" not in system_prompt or "segments" not in system_prompt:
            system_prompt = f"{system_prompt}{PROSODY_PROMPT_CONTRACT}"
        messages = [{"role": "system", "content": system_prompt}]
        if self.memory_store is not None:
            memory_context = self.memory_store.build_prompt_context(user_text)
            if memory_context:
                messages.append({"role": "system", "content": memory_context})
        if self.life_system is not None:
            life_context = self.life_system.build_prompt_context()
            if life_context:
                messages.append({"role": "system", "content": life_context})
            boundary_context = self.life_system.build_boundary_context(user_text)
            if boundary_context:
                messages.append({"role": "system", "content": boundary_context})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def post_json(self, url, payload, headers=None, timeout=120):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))

    def chat_ollama(self, user_text):
        base_url = str(self.config.get("base_url") or DEFAULT_LLM_CONFIG["base_url"]).rstrip("/")
        payload = {
            "model": self.config.get("model", DEFAULT_LLM_CONFIG["model"]),
            "messages": self.build_messages(user_text),
            "stream": False,
            "options": {
                "temperature": float(self.config.get("temperature", 0.75)),
            },
        }
        data = self.post_json(f"{base_url}/api/chat", payload, timeout=180)
        reply = data.get("message", {}).get("content", "")
        return self.clean_reply(reply)

    def chat_openai_compatible(self, user_text):
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"
        headers = {}
        api_key_env = self.config.get("api_key_env") or "OPENAI_API_KEY"
        api_key = self.config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing API key. Set {api_key_env} or fill api_key in persona_llm_config.json.")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.config.get("model", ""),
            "messages": self.build_messages(user_text),
            "temperature": float(self.config.get("temperature", 0.75)),
            "stream": False,
        }
        data = self.post_json(url, payload, headers=headers, timeout=180)
        choices = data.get("choices") or []
        reply = choices[0].get("message", {}).get("content", "") if choices else ""
        return self.clean_reply(reply)

    def clean_reply(self, reply):
        reply = (reply or "").strip()
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
        reply = re.sub(r"\s+", " ", reply)
        return reply or "嗯嗯，我在听哦。"

    def extract_loose_json_string(self, text, key, following_keys=None):
        following_keys = following_keys or ("emotion", "segments", "prosody", "voice_text", "ja", "tts")
        key_pattern = re.escape(str(key))
        for next_key in following_keys:
            pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*,\s*"{re.escape(next_key)}"\s*:'
            match = re.search(pattern, text or "", flags=re.S)
            if match:
                return self.unescape_loose_json_text(match.group(1))
        pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*\}}'
        match = re.search(pattern, text or "", flags=re.S)
        if match:
            return self.unescape_loose_json_text(match.group(1))
        return ""

    def unescape_loose_json_text(self, text):
        text = str(text or "")
        text = text.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
        text = re.sub(r"\s+", " ", text).strip()
        return strip_stage_directions(text)

    def parse_loose_reply_payload(self, candidate):
        candidate = str(candidate or "").strip()
        if not any(marker in candidate for marker in STRUCTURED_REPLY_MARKERS):
            return {}
        zh = self.extract_loose_json_string(candidate, "zh")
        if not zh:
            zh = self.extract_loose_json_string(candidate, "reply")
        if not zh:
            zh = self.extract_loose_json_string(candidate, "reply_zh")
        if not zh:
            return {}
        emotion_match = re.search(r'"emotion"\s*:\s*"([A-Za-z_]+)"', candidate)
        emotion = (emotion_match.group(1).lower() if emotion_match else "").strip()
        if emotion not in LLM_EMOTIONS:
            emotion = dominant_weight_emotion(primary_dominant_analysis(analyze_text_to_emotion(zh)))
        voice_text = self.extract_loose_json_string(candidate, "voice_text")
        segment_source = ""
        segment_block = re.search(r'"segments"\s*:\s*\[(.*?)\]\s*,\s*"prosody"', candidate, flags=re.S)
        if segment_block:
            segment_source = segment_block.group(1)
        segment_matches = re.findall(r'\{\s*"zh"\s*:\s*"(.*?)"\s*,\s*"emotion"\s*:\s*"([A-Za-z_]+)"', segment_source, flags=re.S)
        segments = []
        for segment_zh, segment_emotion in segment_matches[:4]:
            segment_zh = self.unescape_loose_json_text(segment_zh)
            segment_emotion = segment_emotion.lower().strip()
            if segment_zh:
                segments.append(
                    {
                        "zh": segment_zh,
                        "voice_text": segment_zh,
                        "ja": "",
                        "emotion": segment_emotion if segment_emotion in LLM_EMOTIONS else emotion,
                    }
                )
        if len(segments) <= 1:
            segments = []
        return {
            "zh": zh,
            "voice_text": voice_text,
            "emotion": emotion,
            "prosody": {},
            "segments": segments,
        }

    def parse_reply_payload(self, reply):
        cleaned = self.clean_reply(reply)
        candidate = cleaned
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.S | re.I)
        if fence:
            candidate = fence.group(1).strip()
        match = re.search(r"\{.*\}", candidate, flags=re.S)
        if match:
            candidate = match.group(0)

        try:
            data = json.loads(candidate)
        except Exception as exc:
            data = self.parse_loose_reply_payload(candidate)
            if data:
                print("LLM_JSON_REPAIRED =", {"error": str(exc)[:120], "zh": data.get("zh", "")[:80]})
        if not isinstance(data, dict):
            data = {}

        zh = strip_stage_directions(data.get("zh") or data.get("reply_zh") or data.get("reply") or cleaned)
        if not data and any(marker in cleaned for marker in STRUCTURED_REPLY_MARKERS):
            zh = re.sub(r'"(?:emotion|segments|prosody|voice_text|ja|tts)"\s*:\s*[^,}]+', "", cleaned)
            zh = re.sub(r'[{}[\]"]+', "", zh)
            zh = re.sub(r"\bzh\s*:\s*", "", zh)
            zh = strip_stage_directions(re.sub(r"\s+", " ", zh).strip(" ,:"))
        emotion = str(data.get("emotion") or "").strip().lower()
        if emotion not in LLM_EMOTIONS:
            emotion = dominant_weight_emotion(primary_dominant_analysis(analyze_text_to_emotion(zh)))
        voice_text = strip_stage_directions(data.get("voice_text") or data.get("tts") or data.get("ja") or data.get("voice_ja") or data.get("jp") or "")
        prosody = normalize_prosody_hint(data.get("prosody"))
        segments = self.parse_reply_segments(data, zh, voice_text, emotion)

        return {
            "zh": zh or "嗯嗯，我在听哦。",
            "voice_text": voice_text,
            "ja": "",
            "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
            "prosody": prosody,
            "segments": segments,
            "raw": cleaned,
        }

    def parse_reply_segments(self, data, fallback_zh, fallback_ja, fallback_emotion):
        raw_segments = data.get("segments") if isinstance(data, dict) else None
        if not isinstance(raw_segments, list):
            return []
        segments = []
        for item in raw_segments[:4]:
            if not isinstance(item, dict):
                continue
            zh = strip_stage_directions(item.get("zh") or item.get("text") or "")
            voice_text = strip_stage_directions(item.get("voice_text") or item.get("tts") or item.get("ja") or item.get("voice_ja") or "")
            emotion = str(item.get("emotion") or fallback_emotion or "").strip().lower()
            if emotion not in LLM_EMOTIONS:
                seed = zh or fallback_zh
                emotion = dominant_weight_emotion(primary_dominant_analysis(analyze_text_to_emotion(seed)))
            if not zh and not voice_text:
                continue
            segments.append(
                {
                    "zh": zh,
                    "voice_text": voice_text or zh,
                    "ja": "",
                    "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
                }
            )
        if len(segments) <= 1:
            return []
        if not any(segment.get("voice_text") for segment in segments) and fallback_ja:
            return []
        return segments

    def ensure_voice_text(self, zh, ja, emotion):
        zh = str(zh or "").strip()
        zh = strip_stage_directions(zh)
        voice_text = strip_stage_directions(ja)
        if voice_text and not re.search(r"[\u3040-\u30ff]", voice_text):
            return voice_text
        return zh or voice_text or "嗯嗯，我在听哦。"

    def chat_openai_compatible_messages(self, messages, temperature=0.35, timeout=90):
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        api_key_env = self.config.get("api_key_env") or "OPENAI_API_KEY"
        api_key = self.config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing API key. Set {api_key_env} or fill api_key in persona_llm_config.json.")
        payload = {
            "model": self.config.get("model", ""),
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        data = self.post_json(url, payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        choices = data.get("choices") or []
        return self.clean_reply(choices[0].get("message", {}).get("content", "") if choices else "")

    def chat_ollama_messages(self, messages, temperature=0.35, timeout=120):
        base_url = str(self.config.get("base_url") or DEFAULT_LLM_CONFIG["base_url"]).rstrip("/")
        payload = {
            "model": self.config.get("model", DEFAULT_LLM_CONFIG["model"]),
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self.post_json(f"{base_url}/api/chat", payload, timeout=timeout)
        return self.clean_reply(data.get("message", {}).get("content", ""))

    def chat_messages(self, messages, temperature=0.35, timeout=120):
        provider = str(self.config.get("provider", "ollama")).lower()
        if provider in ("openai", "openai_compatible", "compatible"):
            return self.chat_openai_compatible_messages(messages, temperature=temperature, timeout=timeout)
        return self.chat_ollama_messages(messages, temperature=temperature, timeout=timeout)

@dataclass
class LLMReplyEvent:
    user_text: str
    reply: str
    voice_text: str = ""
    emotion: str = "neutral"
    prosody: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)
    error: str = ""
    degraded_error: str = ""
    initiated_by: str = "user"
    memory_user_text: str = ""


class LLMChatController:
    def __init__(self, config=None, memory_store=None, life_system=None):
        self.client = LLMClient(config=config, memory_store=memory_store, life_system=life_system)
        self.lock = threading.Lock()
        self.events = []
        self.busy = False

    def fallback_payload(self, initiated_by, error):
        if initiated_by == "proactive":
            text = "刚才想和你说句话，但是脑袋有点卡住了，我先安静陪你一会儿。"
        elif is_transient_llm_error(error):
            text = "刚才连接有点慢，我先缓一下。你刚才说的我还在听，可以再说一遍吗？"
        else:
            text = "我这边刚才没接好话，但我还在。你再跟我说一次好吗？"
        return {
            "zh": text,
            "voice_text": text,
            "emotion": "neutral",
            "prosody": {"pace": "slow", "tone": "soft", "emphasis": [], "pause_after": []},
            "segments": [],
        }

    def ask_async(self, user_text, initiated_by="user", memory_user_text=""):
        user_text = (user_text or "").strip()
        if not user_text:
            return False
        initiated_by = (initiated_by or "user").strip() or "user"
        memory_user_text = (memory_user_text or "").strip()
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            payload = {"zh": "", "voice_text": "", "emotion": "neutral"}
            error = ""
            degraded_error = ""
            try:
                payload = self.client.chat(user_text)
            except Exception as exc:
                error = str(exc)
                if is_transient_llm_error(error):
                    time.sleep(LLM_TRANSIENT_RETRY_SECONDS)
                    try:
                        payload = self.client.chat(user_text)
                        print("LLM_RETRY_OK =", {"initiated_by": initiated_by})
                        error = ""
                    except Exception as retry_exc:
                        error = str(retry_exc)
                if error:
                    degraded_error = error
                    payload = self.fallback_payload(initiated_by, error)
                    error = ""
            with self.lock:
                self.busy = False
                self.events.append(
                    LLMReplyEvent(
                        user_text=user_text,
                        reply=payload.get("zh", ""),
                        voice_text=payload.get("voice_text") or payload.get("zh", ""),
                        emotion=payload.get("emotion", "neutral"),
                        prosody=payload.get("prosody") or {},
                        segments=payload.get("segments") or [],
                        error=error,
                        degraded_error=degraded_error,
                        initiated_by=initiated_by,
                        memory_user_text=memory_user_text,
                    )
                )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def is_busy(self):
        with self.lock:
            return self.busy


@dataclass
class LifeWritingEvent:
    kind: str = ""
    path: str = ""
    title: str = ""
    content: str = ""
    error: str = ""


class LifeWritingController:
    def __init__(self, config=None, memory_store=None, life_system=None):
        self.config = dict(config or load_llm_config())
        self.memory_store = memory_store
        self.life_system = life_system
        self.client = LLMClient(config=self.config, memory_store=memory_store, life_system=life_system)
        self.lock = threading.Lock()
        self.busy = False
        self.events = []

    def update_config(self, config):
        self.config = dict(config or load_llm_config())
        self.client = LLMClient(config=self.config, memory_store=self.memory_store, life_system=self.life_system)

    def is_busy(self):
        with self.lock:
            return self.busy

    def write_async(self, kind):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            event = LifeWritingEvent(kind=kind)
            try:
                if kind == "diary":
                    event = self.write_diary()
                else:
                    event = self.write_novel()
            except Exception as exc:
                event.error = str(exc)
            with self.lock:
                self.busy = False
                self.events.append(event)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def write_diary(self):
        today = time.strftime("%Y-%m-%d")
        stage, _attitude = self.life_system.relationship_stage()
        prompt = (
            "你是小日和，一名小说作家，也是用户的情感陪伴朋友。"
            "请写一篇今天的私人日记，像真正的人一样记录今天的心情、和用户的关系、自己的写作状态。"
            f"不要写成报告，不要提系统或代码。字数 {max(350, LIFE_DIARY_DAILY_WORD_LIMIT - 250)}-{LIFE_DIARY_DAILY_WORD_LIMIT} 中文字。"
            f"\n日期：{today}\n当前关系：{stage}\n{self.life_system.build_prompt_context()}"
        )
        content = self.client.chat_messages(
            [{"role": "system", "content": "你只写日记正文。"}, {"role": "user", "content": prompt}],
            temperature=0.72,
            timeout=180,
        )
        path = self.life_system.diary_path()
        write_docx_file(path, f"小日和日记 {today}", content)
        self.life_system.mark_diary_written()
        return LifeWritingEvent(kind="diary", path=path, title=f"小日和日记 {today}", content=content)

    def write_novel(self):
        novel = self.life_system.novel
        remaining_words = self.life_system.remaining_novel_words_today()
        if remaining_words <= 0:
            raise RuntimeError("今天的小说写作字数额度已用完。")
        if not novel.get("title"):
            setup_prompt = (
                "你是小日和，一名小说作家。请为你接下来要独立连载的一部长篇小说设计题目和简介。"
                "题材可以是轻小说、都市情感、治愈、奇幻之一，必须温柔、有连续写作空间。"
                "输出 JSON：{\"title\":\"书名\",\"premise\":\"一句话简介\",\"target_chapters\":8}"
            )
            raw = self.client.chat_messages(
                [{"role": "user", "content": setup_prompt}],
                temperature=0.8,
                timeout=120,
            )
            match = re.search(r"\{.*\}", raw, flags=re.S)
            data = {}
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = {}
            novel["title"] = str(data.get("title") or "雨停之后的来信")[:40]
            novel["premise"] = str(data.get("premise") or "一个习惯隐藏心事的女孩，在陪伴他人的过程中慢慢学会理解自己。")[:160]
            try:
                novel["target_chapters"] = int(data.get("target_chapters") or 8)
            except Exception:
                novel["target_chapters"] = 8
            novel["target_chapters"] = max(4, min(16, int(novel["target_chapters"])))

        chapter = int(novel.get("chapter", 0)) + 1
        target = int(novel.get("target_chapters", 8))
        ending_hint = "这一章推进故事，不要完结。" if chapter < target else "这是最终章，请给故事一个完整但余韵温柔的结尾。"
        max_words = max(450, min(remaining_words, 900))
        min_words = max(260, min(520, max_words - 160))
        prompt = (
            f"你是小说作家小日和，正在写长篇小说《{novel.get('title')}》。\n"
            f"小说简介：{novel.get('premise')}\n"
            f"当前要写第 {chapter}/{target} 章。{ending_hint}\n"
            f"请输出本章正文，包含章节标题。字数 {min_words}-{max_words} 中文字。风格细腻、情感真实、有画面感。"
            "不要写大纲，不要解释。"
        )
        content = self.client.chat_messages(
            [{"role": "system", "content": "你只写小说章节正文。"}, {"role": "user", "content": prompt}],
            temperature=0.82,
            timeout=240,
        )
        existing = novel.get("content", "")
        separator = "\n\n" if existing else ""
        novel["content"] = f"{existing}{separator}{content}".strip()
        novel["chapter"] = chapter
        novel["last_written_at"] = memory_now_label()
        if chapter >= target:
            novel["complete"] = True
        path = self.life_system.novel_path()
        novel["path"] = path
        write_docx_file(path, novel.get("title") or "小日和的小说", novel["content"])
        self.life_system.mark_novel_written(content)
        self.life_system.save()
        return LifeWritingEvent(kind="novel", path=path, title=novel.get("title", ""), content=content)


@dataclass
class SpeechInputEvent:
    text: str = ""
    error: str = ""
    wav_path: str = ""
    audio_stats: dict = field(default_factory=dict)


class SpeechInputController:
    def __init__(self):
        self.enabled = SPEECH_INPUT_ENABLED
        self.lock = threading.Lock()
        self.events = []
        self.busy = False
        self.model = None
        self.current_process = None

    def is_busy(self):
        with self.lock:
            return self.busy

    def load_model(self):
        if self.model is not None:
            return self.model
        os.makedirs(SPEECH_MODEL_DIR, exist_ok=True)
        from faster_whisper import WhisperModel

        try:
            self.model = WhisperModel(
                SPEECH_MODEL_SIZE,
                device="cuda",
                compute_type="int8_float16",
                download_root=SPEECH_MODEL_DIR,
            )
        except Exception:
            self.model = WhisperModel(
                SPEECH_MODEL_SIZE,
                device="cpu",
                compute_type="int8",
                download_root=SPEECH_MODEL_DIR,
            )
        return self.model

    def write_wav(self, path, samples):
        import numpy as np

        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak > 1.0:
            samples = samples / peak
        pcm = np.clip(samples, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        with wave.open(path, "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(SPEECH_SAMPLE_RATE)
            file.writeframes(pcm.tobytes())

    def record_and_transcribe(self):
        os.makedirs(VOICE_OUTPUT_DIR, exist_ok=True)
        wav_path = os.path.join(VOICE_OUTPUT_DIR, "speech_input_last.wav")
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--speech-helper"]
        else:
            cmd = [sys.executable, "-B", SPEECH_HELPER_PATH]
        cmd.extend(
            [
                "--seconds",
                str(SPEECH_RECORD_SECONDS),
                "--adaptive",
                "--min-seconds",
                str(SPEECH_MIN_RECORD_SECONDS),
                "--silence-seconds",
                str(SPEECH_SILENCE_SECONDS),
                "--silence-rms",
                str(SPEECH_SILENCE_RMS),
                "--start-timeout",
                str(SPEECH_START_TIMEOUT),
                "--chunk-ms",
                str(SPEECH_CHUNK_MS),
                "--sample-rate",
                str(SPEECH_SAMPLE_RATE),
                "--model-size",
                SPEECH_MODEL_SIZE,
                "--model-dir",
                SPEECH_MODEL_DIR,
                "--out",
                wav_path,
                "--config",
                LLM_CONFIG_PATH,
            ]
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        with self.lock:
            self.current_process = process
        helper_timeout = None
        if SPEECH_HELPER_TIMEOUT_SECONDS and SPEECH_HELPER_TIMEOUT_SECONDS > 0:
            helper_timeout = max(30.0, SPEECH_HELPER_TIMEOUT_SECONDS)
        elif SPEECH_RECORD_SECONDS and SPEECH_RECORD_SECONDS > 0:
            helper_timeout = max(90.0, SPEECH_RECORD_SECONDS + 120.0)
        try:
            stdout, stderr = process.communicate(timeout=helper_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            raise RuntimeError("speech helper timed out")
        finally:
            with self.lock:
                if self.current_process is process:
                    self.current_process = None

        stdout = (stdout or "").strip()
        payload = self.parse_helper_payload(stdout)
        if process.returncode != 0 or not payload.get("ok"):
            error = payload.get("error") or stderr or stdout or f"speech helper exited {process.returncode}"
            raise RuntimeError(error)
        return (
            str(payload.get("text", "")).strip(),
            str(payload.get("wav_path") or wav_path),
            payload.get("audio_stats") or {},
        )

    def parse_helper_payload(self, stdout):
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout or "").strip()
        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(cleaned[index:])
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                continue
        return {}

    def stop(self):
        with self.lock:
            process = self.current_process
            self.current_process = None
            self.busy = False
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception as exc:
            log_runtime("SPEECH_HELPER_STOP_ERROR", exc)

    def listen_async(self):
        if not self.enabled:
            return False
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            text = ""
            error = ""
            wav_path = ""
            try:
                text, wav_path, stats = self.record_and_transcribe()
            except Exception as exc:
                error = str(exc)
            with self.lock:
                self.busy = False
                self.events.append(SpeechInputEvent(text=text, error=error, wav_path=wav_path, audio_stats=stats if "stats" in locals() else {}))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events


class BargeInController:
    def __init__(self):
        self.enabled = BARGE_IN_ENABLED
        self.lock = threading.Lock()
        self.running = False
        self.active = False
        self.events = []
        self.thread = None
        self.noise_rms = max(0.002, BARGE_IN_RMS / BARGE_IN_NOISE_MULTIPLIER)

    def start(self):
        if not self.enabled:
            return False
        with self.lock:
            if self.running:
                return True
            self.running = True

        def worker():
            try:
                self.monitor_loop()
            except Exception as exc:
                with self.lock:
                    self.running = False
                    self.active = False
                    self.events.append({"error": str(exc)})

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        thread = None
        with self.lock:
            self.running = False
            self.active = False
            thread = self.thread
            self.thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def set_active(self, active):
        if not self.enabled:
            return
        self.start()
        with self.lock:
            self.active = bool(active)

    def monitor_loop(self):
        import numpy as np
        import sounddevice as sd

        blocksize = max(160, int(SPEECH_SAMPLE_RATE * BARGE_IN_CHUNK_MS / 1000))
        voiced_samples = 0
        needed_samples = max(blocksize, int(BARGE_IN_MIN_VOICED_SECONDS * SPEECH_SAMPLE_RATE))
        last_trigger_at = 0.0

        with sd.InputStream(
            samplerate=SPEECH_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                with self.lock:
                    running = self.running
                    active = self.active
                    noise_rms = self.noise_rms
                if not running:
                    return

                data, _overflowed = stream.read(blocksize)
                chunk = np.asarray(data, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0

                if not active:
                    if 0.0005 <= rms <= BARGE_IN_RMS:
                        with self.lock:
                            self.noise_rms = self.noise_rms * 0.96 + rms * 0.04
                    voiced_samples = 0
                    continue

                threshold = max(BARGE_IN_RMS, noise_rms * BARGE_IN_NOISE_MULTIPLIER)
                if rms >= threshold:
                    voiced_samples += chunk.size
                else:
                    voiced_samples = max(0, voiced_samples - chunk.size)

                now = time.monotonic()
                if voiced_samples >= needed_samples and now - last_trigger_at >= 1.2:
                    last_trigger_at = now
                    voiced_samples = 0
                    with self.lock:
                        self.active = False
                        self.events.append({"rms": round(rms, 6), "threshold": round(threshold, 6)})

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events


def select_reaction_motion(analysis, text="", role=DIALOGUE_ROLE_SPEAKER):
    dominant = dominant_weight_emotion(analysis)
    compact_text = re.sub(r"\s+", "", text or "")

    if compact_text:
        for motion_key, keywords in TEXT_MOTION_HINTS:
            if not any(keyword in compact_text for keyword in keywords):
                continue
            if motion_key == "m05_curious" and ("没什么" in compact_text or "没有什么" in compact_text):
                continue
            if motion_key == "m04_fear" and dominant == "fear":
                return dominant, motion_key, HIYORI_MOTION_TEMPLATES[motion_key]
            if motion_key in ("m04_wronged_sadness",) and dominant == "sadness":
                return dominant, motion_key, HIYORI_MOTION_TEMPLATES[motion_key]
            if motion_key in ("m03_carefree_joy", "m06_cute_joy") and dominant == "joy":
                return dominant, motion_key, HIYORI_MOTION_TEMPLATES[motion_key]
            if motion_key in ("m01_thinking", "m02_question_smile", "m05_curious") and dominant in ("neutral", "surprise", "joy"):
                return dominant, motion_key, HIYORI_MOTION_TEMPLATES[motion_key]

    if role == DIALOGUE_ROLE_LISTENER:
        motion_key = LISTENER_MOTION_BY_EMOTION.get(dominant, "m01_thinking")
    else:
        motion_key = PRIMARY_MOTION_BY_EMOTION.get(dominant, "m01_thinking")
    return dominant, motion_key, HIYORI_MOTION_TEMPLATES[motion_key]


def has_negation_near(text, index):
    prefix = text[max(0, index - 8):index]
    return any(neg in prefix for neg in NEGATIONS)


def requested_expression_emotion(text):
    compact_text = re.sub(r"\s+", "", text or "")
    if not compact_text:
        return ""
    if not any(intent in compact_text for intent in EXPRESSION_REQUEST_INTENTS):
        return ""

    for emotion, tokens in EXPRESSION_REQUEST_EMOTIONS.items():
        for token in tokens:
            start = 0
            while True:
                index = compact_text.find(token, start)
                if index == -1:
                    break
                if not has_negation_near(compact_text, index):
                    return emotion
                start = index + len(token)
    return ""


def reconcile_llm_emotion(user_text, reply_text, llm_emotion):
    requested_emotion = requested_expression_emotion(user_text)
    if requested_emotion:
        return requested_emotion, "user_request"

    reply_emotion = dominant_weight_emotion(primary_dominant_analysis(analyze_text_to_emotion(reply_text)))
    if reply_emotion != "neutral" and reply_emotion != llm_emotion:
        return reply_emotion, "reply_text"
    if llm_emotion in LLM_EMOTIONS:
        return llm_emotion, ""
    return reply_emotion, "reply_text"


def build_emotion_weights(raw_scores, intensity):
    total = sum(raw_scores.values())
    if total <= 1e-6:
        return EmotionAnalysis.neutral().weights.copy(), "neutral"

    activation = clamp(0.26 + intensity * 0.56 + min(0.14, total * 0.035), 0.24, 0.90)
    weights = {emotion: raw_scores[emotion] / total * activation for emotion in EMOTION_ORDER}
    weights["neutral"] = clamp(1.0 - activation, 0.10, 0.76)
    dominant = max(EMOTION_ORDER, key=raw_scores.get)
    return weights, dominant


def analyze_text_to_emotion(text: str) -> EmotionAnalysis:
    text = (text or "").strip()
    if not text:
        return EmotionAnalysis.neutral()

    raw_scores = {emotion: 0.0 for emotion in EMOTION_ORDER}
    matched_tokens = []

    for emotion, token_map in EMOTION_LEXICON.items():
        for token, weight in token_map.items():
            start = 0
            while True:
                index = text.find(token, start)
                if index == -1:
                    break
                factor = 0.35 if has_negation_near(text, index) else 1.0
                raw_scores[emotion] += weight * factor
                matched_tokens.append(token)
                start = index + len(token)

    exclamations = text.count("!") + text.count("！")
    questions = text.count("?") + text.count("？")
    tildes = text.count("~") + text.count("～")
    ellipses = text.count("...") + text.count("……")

    intensity = 0.18
    for token, bonus in INTENSIFIERS.items():
        if token in text:
            intensity += bonus
    for token, penalty in SOFTENERS.items():
        if token in text:
            intensity -= penalty

    intensity += min(0.26, exclamations * 0.08 + questions * 0.04 + tildes * 0.03)
    intensity += min(0.12, ellipses * 0.04)
    if len(text) >= 12:
        intensity += 0.04
    if len(text) >= 24:
        intensity += 0.04
    intensity = clamp(intensity, 0.10, 1.00)

    if raw_scores["surprise"] == 0.0 and (questions or exclamations):
        raw_scores["surprise"] += questions * 0.18 + exclamations * 0.12
    if raw_scores["joy"] == 0.0 and "哈哈" in text:
        raw_scores["joy"] += 0.55
    if raw_scores["sadness"] == 0.0 and "呜呜" in text:
        raw_scores["sadness"] += 0.65

    weights, dominant = build_emotion_weights(raw_scores, intensity)

    speaking_energy = clamp(0.32 + intensity * 0.56 + exclamations * 0.03 + questions * 0.02, 0.28, 1.00)
    if dominant == "sadness":
        speaking_energy *= 0.78
    elif dominant == "anger":
        speaking_energy = clamp(speaking_energy + 0.10, 0.30, 1.00)
    elif dominant == "surprise":
        speaking_energy = clamp(speaking_energy + 0.08, 0.30, 1.00)

    return EmotionAnalysis(
        weights=weights,
        intensity=intensity,
        dominant=dominant,
        speaking_energy=speaking_energy,
        matched_tokens=matched_tokens,
    )


def emotion_to_params(analysis: EmotionAnalysis):
    emo = analysis.weights
    intensity = analysis.intensity
    fear = emo["fear"]
    joy = emo["joy"]
    sadness = emo["sadness"]
    anger = emo["anger"]
    surprise = emo["surprise"]
    neutral = emo["neutral"]
    activation = 1.0 - neutral

    eye_open = 0.88 + joy * 0.05 + surprise * 0.28 + fear * 0.12 - sadness * 0.24 - anger * 0.08
    mouth_open = 0.08 + joy * 0.16 + surprise * 0.22 + fear * 0.08 - sadness * 0.04 + anger * 0.06
    mouth_form = 0.12 + joy * 0.78 - sadness * 0.78 - anger * 0.62 - fear * 0.26
    brow_form = joy * 0.18 + anger * 0.78 + surprise * 0.16 - fear * 0.58 - sadness * 0.34

    angle_x = anger * 7.0 - fear * 4.4 + joy * 2.0 - sadness * 2.8
    angle_y = surprise * 5.8 - sadness * 4.0 - fear * 1.2
    angle_z = anger * 4.0 - joy * 1.8 + surprise * 1.0

    body_x = anger * 3.8 - sadness * 2.4 + joy * 1.2
    body_y = surprise * 4.8 - fear * 1.8 + joy * 1.2
    body_z = joy * 1.8 - sadness * 1.8 - anger * 1.4

    eye_ball_x = joy * 0.28 - fear * 0.20 + anger * 0.22
    eye_ball_y = surprise * 0.34 - sadness * 0.26
    cheek = joy * (0.30 + intensity * 0.40)
    eye_smile = joy * (0.36 + intensity * 0.48)
    hair_ahoge = surprise * 4.6 + joy * 1.0 - sadness * 0.8
    arm_l = -1.2 - anger * 3.5 - surprise * 1.8 - sadness * 0.6
    arm_r = -1.0 - anger * 3.0 - joy * 0.8 - fear * 0.4

    return {
        StandardParams.ParamEyeLOpen: eye_open,
        StandardParams.ParamEyeROpen: eye_open,
        StandardParams.ParamMouthOpenY: mouth_open,
        StandardParams.ParamMouthForm: mouth_form,
        StandardParams.ParamBrowLForm: brow_form,
        StandardParams.ParamBrowRForm: brow_form,
        StandardParams.ParamAngleX: angle_x,
        StandardParams.ParamAngleY: angle_y,
        StandardParams.ParamAngleZ: angle_z,
        StandardParams.ParamEyeBallX: eye_ball_x,
        StandardParams.ParamEyeBallY: eye_ball_y,
        PARAM_BODY_ANGLE_X: body_x,
        PARAM_BODY_ANGLE_Y: body_y,
        PARAM_BODY_ANGLE_Z: body_z,
        PARAM_CHEEK: cheek,
        PARAM_EYE_L_SMILE: eye_smile,
        PARAM_EYE_R_SMILE: eye_smile,
        PARAM_ARM_LA: arm_l,
        PARAM_ARM_RA: arm_r,
        PARAM_HAIR_AHOGE: hair_ahoge + activation * 0.5,
    }


class BehaviorController:
    def __init__(self, motion_groups):
        self.motion_groups = motion_groups
        self.analysis = EmotionAnalysis.neutral()
        self.last_motion_at = 0.0
        self.next_idle_motion_at = time.monotonic() + random.uniform(*IDLE_MOTION_INTERVAL)
        self.speech_started_at = 0.0
        self.speech_duration = 0.0
        self.speaking_energy = 0.0
        self.speech_seed = random.uniform(0.0, math.tau)
        self.speech_talk_rate = 8.0
        self.mouth_enabled = False
        self.idle_seed = random.uniform(0.0, math.tau)
        self.pending_residue_motion = None
        self.residue_ready_at = 0.0
        self.residue_played = True

    def set_analysis(self, model, analysis, text="", role=DIALOGUE_ROLE_LISTENER, force=False, motion_key_override=None):
        self.analysis = analysis
        self.mouth_enabled = False
        self.trigger_emotion_motion(
            model,
            analysis,
            text=text,
            role=role,
            prefer_talk=False,
            force=force,
            motion_key_override=motion_key_override,
        )

    def start_speaking(self, model, text, analysis, role=DIALOGUE_ROLE_SPEAKER, force=False, motion_key_override=None):
        self.analysis = analysis
        punctuation_hits = sum(text.count(mark) for mark in "!?！？~～")
        clean_length = max(1, len(text.strip()))
        duration = clamp(0.9 + clean_length * 0.10 + punctuation_hits * 0.16, 1.1, 8.0)

        self.speech_started_at = time.monotonic()
        self.speech_duration = duration
        self.speaking_energy = analysis.speaking_energy
        self.speech_seed = random.uniform(0.0, math.tau)
        self.speech_talk_rate = clamp(6.8 + clean_length / max(duration, 0.1) * 0.52, 7.2, 13.5)
        self.mouth_enabled = role == DIALOGUE_ROLE_SPEAKER and MOUTH_ENABLE_FOR_SPEAKER

        self.trigger_emotion_motion(
            model,
            analysis,
            text=text,
            role=role,
            prefer_talk=True,
            force=force,
            motion_key_override=motion_key_override,
        )

    def sync_speech_to_audio(self, duration, analysis=None):
        if duration <= 0.0:
            return
        if analysis is not None:
            self.analysis = analysis
            self.speaking_energy = analysis.speaking_energy
        self.speech_started_at = time.monotonic()
        self.speech_duration = clamp(duration, 0.35, 12.0)
        self.speech_seed = random.uniform(0.0, math.tau)
        self.speech_talk_rate = clamp(7.8 + 16.0 / max(self.speech_duration, 0.5), 8.2, 14.8)
        self.mouth_enabled = MOUTH_ENABLE_FOR_SPEAKER

    def is_speaking(self, now=None):
        now = time.monotonic() if now is None else now
        return now < self.speech_started_at + self.speech_duration

    def stop_speaking(self):
        self.speech_started_at = 0.0
        self.speech_duration = 0.0
        self.speaking_energy = 0.0
        self.mouth_enabled = False

    def build_mouth_overlay(self, progress, envelope):
        if not self.mouth_enabled:
            return {}

        elapsed = progress * self.speech_duration
        rate = self.speech_talk_rate
        primary = abs(math.sin(elapsed * rate + self.speech_seed))
        secondary = abs(math.sin(elapsed * (rate * 1.73) + self.speech_seed * 0.61))
        fine = abs(math.sin(elapsed * (rate * 2.41) + 0.37))
        pause_wave = math.sin(elapsed * 4.7 + self.speech_seed * 0.33)
        gate = 0.22 if pause_wave < -0.68 else 1.0

        open_value = envelope * self.speaking_energy * (0.08 + primary * 0.58 + secondary * 0.24 + fine * 0.10)
        open_value *= gate * MOUTH_OPEN_SCALE
        open_value = clamp(open_value, 0.0, 0.82)

        form_wave = math.sin(elapsed * (rate * 0.82) + self.speech_seed * 0.4)
        form_value = envelope * form_wave * MOUTH_FORM_SCALE
        return {
            StandardParams.ParamMouthOpenY: open_value,
            StandardParams.ParamMouthForm: form_value,
        }

    def build_late_mouth_params(self, now):
        if not self.is_speaking(now):
            return {}
        progress = clamp((now - self.speech_started_at) / max(self.speech_duration, 0.001), 0.0, 1.0)
        fade_in = clamp(progress / 0.10, 0.0, 1.0)
        fade_out = clamp((1.0 - progress) / 0.14, 0.0, 1.0)
        return self.build_mouth_overlay(progress, min(fade_in, fade_out))

    def pick_reaction_motion(self, analysis, text="", role=DIALOGUE_ROLE_SPEAKER, motion_key_override=None):
        if motion_key_override:
            dominant = dominant_weight_emotion(analysis)
            motion_key = motion_key_override
            motion = HIYORI_MOTION_TEMPLATES.get(motion_key)
            if not motion:
                return dominant, "", None
        else:
            dominant, motion_key, motion = select_reaction_motion(analysis, text=text, role=role)
        group = motion["group"]
        index = motion["index"]
        if self.motion_groups.get(group, 0) > index:
            return dominant, motion_key, motion

        fallback = HIYORI_MOTION_TEMPLATES["m01_thinking"]
        if self.motion_groups.get(fallback["group"], 0) > fallback["index"]:
            return dominant, "m01_thinking", fallback
        return dominant, "", None

    def trigger_emotion_motion(
        self,
        model,
        analysis,
        text="",
        role=DIALOGUE_ROLE_SPEAKER,
        prefer_talk=False,
        force=False,
        motion_key_override=None,
    ):
        if model is None:
            return

        now = time.monotonic()
        if not force and now - self.last_motion_at < EMOTION_MOTION_COOLDOWN:
            return

        dominant, motion_key, motion = self.pick_reaction_motion(
            analysis,
            text=text,
            role=role,
            motion_key_override=motion_key_override,
        )
        if not motion:
            return

        group = motion["group"]
        index = motion["index"]
        motion_count = self.motion_groups.get(group, 0)
        if motion_count <= index:
            return

        if force or prefer_talk:
            priority = getattr(live2d.MotionPriority, "FORCE", 3)
        elif analysis.intensity >= 0.55:
            priority = getattr(live2d.MotionPriority, "NORMAL", 2)
        else:
            priority = 2
        try:
            priority_debug = int(priority)
        except Exception:
            priority_debug = str(priority)
        try:
            result = model.StartMotion(group, index, priority)
            self.last_motion_at = now
            self.schedule_residue(now, dominant, motion_key)
            if self.residue_played:
                self.next_idle_motion_at = now + random.uniform(*IDLE_MOTION_INTERVAL)
            print(
                "REACTION_MOTION =",
                {
                    "role": role,
                    "dominant_weight": dominant,
                    "motion": motion_key,
                    "group": group,
                    "index": index,
                    "priority": priority_debug,
                    "result": result,
                    "label": motion["label"],
                },
            )
        except Exception as exc:
            print("REACTION_MOTION_ERROR =", {"group": group, "index": index, "error": str(exc)})

    def schedule_residue(self, now, dominant, motion_key):
        residue_key = RESIDUE_MOTION_BY_EMOTION.get(dominant)
        if not residue_key or residue_key == motion_key:
            self.pending_residue_motion = None
            self.residue_ready_at = 0.0
            self.residue_played = True
            return

        duration = MOTION_DURATION_SECONDS.get(motion_key, 2.4)
        delay = RESIDUE_DELAY_SECONDS.get(dominant, 0.6)
        self.pending_residue_motion = residue_key
        self.residue_ready_at = now + duration + delay
        self.residue_played = False
        self.next_idle_motion_at = self.residue_ready_at + MOTION_DURATION_SECONDS.get(residue_key, 3.0)

    def maybe_trigger_residue_motion(self, model, now):
        if model is None or self.residue_played or not self.pending_residue_motion:
            return
        if now < self.residue_ready_at:
            return

        motion = HIYORI_MOTION_TEMPLATES.get(self.pending_residue_motion)
        if not motion:
            self.residue_played = True
            return

        try:
            if not model.IsMotionFinished():
                return
            model.StartMotion(motion["group"], motion["index"], 2)
            self.last_motion_at = now
            self.residue_played = True
            self.next_idle_motion_at = now + MOTION_DURATION_SECONDS.get(self.pending_residue_motion, 3.0) + random.uniform(0.7, 1.4)
            print(
                "RESIDUE_MOTION =",
                {
                    "motion": self.pending_residue_motion,
                    "group": motion["group"],
                    "index": motion["index"],
                    "label": motion["label"],
                },
            )
        except Exception:
            pass

    def maybe_trigger_idle_motion(self, model, now):
        if model is None:
            return
        self.maybe_trigger_residue_motion(model, now)
        if self.is_speaking(now):
            return
        if now < self.next_idle_motion_at:
            return
        if not self.motion_groups.get("Idle"):
            return

        try:
            if model.IsMotionFinished():
                model.StartMotion("Idle", random.randrange(self.motion_groups["Idle"]), 1)
                self.last_motion_at = now
        except Exception:
            pass

        self.next_idle_motion_at = now + random.uniform(*IDLE_MOTION_INTERVAL)

    def build_overlay_params(self, now):
        analysis = self.analysis
        intensity = analysis.intensity
        activation = 1.0 - analysis.weights["neutral"]

        phase = now * (0.8 + activation * 0.5) + self.idle_seed
        overlay = {
            StandardParams.ParamAngleX: math.sin(phase) * (1.1 + activation * 1.7),
            StandardParams.ParamAngleY: math.sin(phase * 1.31 + 0.8) * (0.8 + activation * 1.3),
            StandardParams.ParamAngleZ: math.sin(phase * 0.92 - 0.4) * (0.6 + activation * 1.0),
            PARAM_BODY_ANGLE_X: math.sin(phase * 0.72) * (0.8 + activation * 1.1),
            PARAM_BODY_ANGLE_Y: math.sin(phase * 1.05 + 1.5) * (0.6 + activation * 1.0),
            PARAM_BODY_ANGLE_Z: math.sin(phase * 0.56 + 2.0) * (0.4 + activation * 0.8),
            StandardParams.ParamEyeBallX: math.sin(phase * 0.48) * 0.06,
            StandardParams.ParamEyeBallY: math.sin(phase * 0.63 + 0.5) * 0.04,
            PARAM_HAIR_AHOGE: math.sin(phase * 1.8) * (0.4 + activation * 0.7),
        }

        if analysis.dominant == "fear":
            overlay[StandardParams.ParamAngleX] += math.sin(now * 12.0) * 0.32 * intensity
            overlay[StandardParams.ParamAngleY] += math.cos(now * 10.5) * 0.22 * intensity
        elif analysis.dominant == "surprise":
            overlay[PARAM_HAIR_AHOGE] += 1.4 * intensity
            overlay[PARAM_BODY_ANGLE_Y] += 0.8 * intensity
        elif analysis.dominant == "joy":
            overlay[PARAM_CHEEK] = math.sin(now * 2.6) * 0.04 + 0.06 * intensity
        elif analysis.dominant == "sadness":
            overlay[PARAM_BODY_ANGLE_Z] -= 0.5 * intensity
        elif analysis.dominant == "anger":
            overlay[PARAM_BODY_ANGLE_X] += 0.8 * intensity
            overlay[StandardParams.ParamAngleZ] += 0.5 * intensity

        if self.is_speaking(now):
            progress = clamp((now - self.speech_started_at) / max(self.speech_duration, 0.001), 0.0, 1.0)
            fade_in = clamp(progress / 0.12, 0.0, 1.0)
            fade_out = clamp((1.0 - progress) / 0.18, 0.0, 1.0)
            envelope = min(fade_in, fade_out)

            overlay[StandardParams.ParamAngleX] += math.sin(progress * self.speech_duration * 4.8 + self.speech_seed) * 1.2 * self.speaking_energy
            overlay[PARAM_BODY_ANGLE_Y] += math.sin(progress * self.speech_duration * 4.1 + 1.7) * 1.5 * self.speaking_energy
            overlay[StandardParams.ParamEyeBallX] += math.sin(progress * self.speech_duration * 2.0 + 0.2) * 0.04 * self.speaking_energy

        return overlay

    def update(self, model):
        now = time.monotonic()
        self.maybe_trigger_idle_motion(model, now)
        return self.build_overlay_params(now)


def clamp_params(params):
    clamped = {}
    for pid, value in params.items():
        minimum, maximum = PARAM_LIMITS.get(pid, (-9999.0, 9999.0))
        clamped[pid] = clamp(value, minimum, maximum)
    return clamped


def compose_params(base_params, overlay_params):
    result = dict(base_params)
    for pid, value in overlay_params.items():
        if pid == StandardParams.ParamMouthOpenY:
            result[pid] = max(result.get(pid, 0.0), value)
        elif pid == PARAM_CHEEK:
            result[pid] = result.get(pid, 0.0) + value
        else:
            result[pid] = result.get(pid, 0.0) + value
    return clamp_params(result)


def apply_params(model, params):
    for pid, value in params.items():
        model.SetParameterValue(pid, value, 1)


def normalize_speech_piece(text):
    return re.sub(r"[\s,，。！？!?；;、~～…\.]+", "", text or "")


def clean_speech_input_text(text):
    text = re.sub(r"\s+", "", text or "").strip()
    if not text:
        return ""
    raw_parts = []
    current = ""
    for char in text:
        current += char
        if char in "。！？!?；;":
            raw_parts.append(current)
            current = ""
    if current:
        raw_parts.append(current)

    parts = []
    keys = []
    for part in raw_parts:
        cleaned = re.sub(r"^(你|我|他|她|它)\1+", r"\1", part.strip())
        key = normalize_speech_piece(cleaned)
        if key:
            parts.append(cleaned)
            keys.append(key)

    deduped = []
    deduped_keys = []
    index = 0
    while index < len(parts):
        matched = False
        for group_size in range(min(4, (len(parts) - index) // 2), 0, -1):
            group = keys[index : index + group_size]
            if group == keys[index + group_size : index + group_size * 2]:
                deduped.extend(parts[index : index + group_size])
                deduped_keys.extend(group)
                index += group_size
                while keys[index : index + group_size] == group:
                    index += group_size
                matched = True
                break
        if matched:
            continue
        key = keys[index]
        recent_join = "".join(deduped_keys[-4:])
        if key != recent_join:
            deduped.append(parts[index])
            deduped_keys.append(key)
        index += 1

    result = "".join(deduped).strip()
    return result or text


def is_singing_request(text):
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    asking_only = (
        ("能" in compact or "可以" in compact or "行不行" in compact or "吗" in compact)
        and not any(keyword in compact for keyword in ("随便", "现在", "直接", "开始", "马上", "就唱", "来一首", "唱给我听"))
    )
    if asking_only:
        return False
    keywords = ("唱首歌", "唱一首", "唱一下", "哼歌", "哼一段", "来首歌", "唱给我听", "随便唱")
    return any(keyword in compact for keyword in keywords)


def reply_contains_song(text, voice_text=""):
    combined = f"{text or ''}{voice_text or ''}"
    compact = re.sub(r"\s+", "", combined)
    if any(mark in combined for mark in ("♪", "♫", "♬", "啦啦", "らら", "ララ")):
        return True
    return len(compact) >= 12 and any(keyword in compact for keyword in ("唱给", "一首歌", "小曲", "歌声"))


def clean_song_text(text):
    text = re.sub(r"[（(][^（）()]{0,40}[）)]", "", text or "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[「」『』“”\"']", "", text)
    text = re.sub(r"^[嗯唔呜啊呀哦哼…~～、，。！!？?]+", "", text)
    text = text.strip("，,。.!！?？；;、~～…")
    if not text:
        return ""
    parts = re.split(r"(?<=[。！？!?；;])", text)
    parts = [part.strip() for part in parts if normalize_speech_piece(part)]
    song = "".join(parts[:4]) if parts else text
    max_chars = max(16, int(SINGING_MAX_TEXT_CHARS))
    return song[:max_chars]


@dataclass
class FileAgentAction:
    kind: str
    name: str
    title: str = ""
    content: str = ""


FILE_AGENT_CONFIRM_WORDS = ("确认", "确认创建", "确认执行", "可以", "执行", "好", "没问题")
FILE_AGENT_CANCEL_WORDS = ("取消", "算了", "不要", "停止", "别创建", "先别")
FILE_AGENT_FOLDER_KEYWORDS = ("创建文件夹", "新建文件夹", "建文件夹", "建个文件夹", "新建目录", "创建目录")
FILE_AGENT_DOCX_KEYWORDS = ("写word", "写Word", "新建word", "创建word", "生成word", "写文档", "新建文档", "创建文档", "docx")
FILE_AGENT_PPTX_KEYWORDS = ("写ppt", "写PPT", "新建ppt", "创建ppt", "生成ppt", "做ppt", "做PPT", "pptx")


def file_agent_clean_name(name, default_name):
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip(" ._")
    if not name:
        name = default_name
    return name[:AGENT_FILE_NAME_MAX_CHARS].strip(" ._") or default_name


def file_agent_unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    for index in range(2, 1000):
        candidate = f"{root}_{index}{ext}"
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError("同名文件太多，无法继续创建。")


def file_agent_safe_path(name, extension=""):
    os.makedirs(AGENT_FILES_DIR, exist_ok=True)
    clean_name = file_agent_clean_name(name, "桌宠文件")
    if extension and not clean_name.lower().endswith(extension.lower()):
        clean_name = f"{clean_name}{extension}"
    root = os.path.abspath(AGENT_FILES_DIR)
    path = os.path.abspath(os.path.join(root, clean_name))
    if os.path.commonpath([root, path]) != root:
        raise RuntimeError("文件路径超出安全目录，已拒绝。")
    return file_agent_unique_path(path)


def file_agent_extract_after(text, keywords):
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        value = text[index + len(keyword):].strip(" ：:，,。.!！?？")
        if value:
            return value
    return ""


def file_agent_extract_title(text, default_title):
    for pattern in (
        r"(?:标题|题目|文件名|名字|名称)(?:是|叫|为|：|:)\s*(.{1,60}?)(?=\s*(?:内容|正文|文字|大纲)(?:是|为|：|:)|[，。；;！!？?\n]|$)",
        r"(?:关于|主题是|主题为)\s*(.{1,60}?)(?=\s*(?:内容|正文|文字|大纲)(?:是|为|：|:)|[，。；;！!？?\n]|$)",
    ):
        match = re.search(pattern, text)
        if match:
            return file_agent_clean_name(match.group(1), default_title)
    return default_title


def file_agent_extract_content(text, title):
    for pattern in (
        r"(?:内容|正文|文字|大纲)(?:是|为|：|:)\s*(.+)",
        r"(?:写成|写下|记录)\s*(.+)",
    ):
        match = re.search(pattern, text, flags=re.S)
        if match:
            return match.group(1).strip()
    cleaned = text
    for keyword in (*FILE_AGENT_DOCX_KEYWORDS, *FILE_AGENT_PPTX_KEYWORDS):
        cleaned = cleaned.replace(keyword, "")
    cleaned = re.sub(r"(?:标题|题目|文件名|名字|名称)(?:是|叫|为|：|:)\s*[^，。；;！!？?\n]{1,60}", "", cleaned)
    cleaned = re.sub(r"(?:关于|主题是|主题为)\s*[^，。；;！!？?\n]{1,60}", "", cleaned)
    cleaned = cleaned.strip(" ：:，,。.!！?？")
    return cleaned or f"{title}\n\n待补充。"


def parse_file_agent_action(text):
    text = (text or "").strip()
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None

    if any(keyword in compact for keyword in FILE_AGENT_FOLDER_KEYWORDS):
        name = file_agent_extract_after(text, FILE_AGENT_FOLDER_KEYWORDS)
        name = re.sub(r"^(叫|名为|名字是|名称是)", "", name).strip(" ：:，,。")
        return FileAgentAction("folder", file_agent_clean_name(name, "新建文件夹"))

    if any(keyword.lower() in compact.lower() for keyword in FILE_AGENT_DOCX_KEYWORDS):
        title = file_agent_extract_title(text, "桌宠文档")
        content = file_agent_extract_content(text, title)
        return FileAgentAction("docx", title, title=title, content=content)

    if any(keyword.lower() in compact.lower() for keyword in FILE_AGENT_PPTX_KEYWORDS):
        title = file_agent_extract_title(text, "桌宠演示")
        content = file_agent_extract_content(text, title)
        return FileAgentAction("pptx", title, title=title, content=content)

    return None


def file_agent_is_confirm(text):
    compact = re.sub(r"\s+", "", text or "")
    return compact in FILE_AGENT_CONFIRM_WORDS or compact.startswith("确认")


def file_agent_is_cancel(text):
    compact = re.sub(r"\s+", "", text or "")
    return any(word in compact for word in FILE_AGENT_CANCEL_WORDS)


def describe_file_agent_action(action):
    if action.kind == "folder":
        return f"创建文件夹：{action.name}"
    if action.kind == "docx":
        return f"创建 Word：{action.name}.docx"
    if action.kind == "pptx":
        return f"创建 PPT：{action.name}.pptx"
    return "未知文件操作"


def split_agent_paragraphs(content):
    lines = [line.strip() for line in re.split(r"[\r\n]+", content or "") if line.strip()]
    if lines:
        return lines[:24]
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", content or "") if part.strip()]
    return parts[:24] or ["待补充。"]


def write_docx_file(path, title, content):
    paragraphs = [title, *split_agent_paragraphs(content)]
    body = []
    for index, paragraph in enumerate(paragraphs):
        style = '<w:pStyle w:val="Title"/>' if index == 0 else ""
        body.append(
            "<w:p>"
            f"<w:pPr>{style}</w:pPr>"
            f'<w:r><w:t xml:space="preserve">{escape(paragraph)}</w:t></w:r>'
            "</w:p>"
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>",
        )
        docx.writestr("word/document.xml", document_xml)


def pptx_slide_text_xml(text):
    paragraphs = split_agent_paragraphs(text)
    return "".join(f'<a:p><a:r><a:t>{escape(paragraph)}</a:t></a:r></a:p>' for paragraph in paragraphs)


def pptx_slide_xml(title, body):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="685800" y="457200"/><a:ext cx="7772400" cy="914400"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="3600" b="1"/><a:t>{escape(title)}</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="914400" y="1828800"/><a:ext cx="7315200" cy="4114800"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/>{pptx_slide_text_xml(body)}</p:txBody></p:sp>'
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


def write_pptx_file(path, title, content):
    raw_slides = [part.strip() for part in re.split(r"(?:\n\s*\n|第[一二三四五六七八九十0-9]+页[:：]?)", content or "") if part.strip()]
    if not raw_slides:
        raw_slides = split_agent_paragraphs(content)
    slides = raw_slides[:8] or ["待补充。"]
    overrides = "".join(
        f'<Override PartName="/ppt/slides/slide{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, len(slides) + 1)
    )
    sld_ids = "".join(f'<p:sldId id="{255 + index}" r:id="rId{index + 1}"/>' for index in range(1, len(slides) + 1))
    rels = '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    rels += "".join(
        f'<Relationship Id="rId{index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, len(slides) + 1)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            f"{overrides}</Types>",
        )
        pptx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            "</Relationships>",
        )
        pptx.writestr(
            "ppt/presentation.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            f"<p:sldIdLst>{sld_ids}</p:sldIdLst>"
            '<p:sldSz cx="9144000" cy="6858000" type="screen4x3"/><p:notesSz cx="6858000" cy="9144000"/>'
            "</p:presentation>",
        )
        pptx.writestr("ppt/_rels/presentation.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        pptx.writestr("ppt/slideMasters/slideMaster1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>')
        pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>')
        pptx.writestr("ppt/slideLayouts/slideLayout1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="titleAndObj" preserve="1"><p:cSld name="Title and Content"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld></p:sldLayout>')
        pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
        pptx.writestr("ppt/theme/theme1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="PersonaPet"><a:themeElements><a:clrScheme name="PersonaPet"><a:dk1><a:srgbClr val="222222"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="C45A8A"/></a:accent1><a:accent2><a:srgbClr val="5B9BD5"/></a:accent2><a:accent3><a:srgbClr val="70AD47"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="4472C4"/></a:accent5><a:accent6><a:srgbClr val="ED7D31"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme><a:fontScheme name="PersonaPet"><a:majorFont><a:latin typeface="Microsoft YaHei"/></a:majorFont><a:minorFont><a:latin typeface="Microsoft YaHei"/></a:minorFont></a:fontScheme><a:fmtScheme name="PersonaPet"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>')
        for index, slide in enumerate(slides, 1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", pptx_slide_xml(title if index == 1 else f"{title} {index}", slide))
            pptx.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>')


def execute_file_agent_action(action):
    if action.kind == "folder":
        path = file_agent_safe_path(action.name)
        os.makedirs(path, exist_ok=False)
    elif action.kind == "docx":
        path = file_agent_safe_path(action.name, ".docx")
        write_docx_file(path, action.title or action.name, action.content)
    elif action.kind == "pptx":
        path = file_agent_safe_path(action.name, ".pptx")
        write_pptx_file(path, action.title or action.name, action.content)
    else:
        raise RuntimeError("未知文件操作。")
    log_runtime("FILE_AGENT_EXECUTE", {"kind": action.kind, "path": path})
    return path


@dataclass
class BrowserAgentAction:
    kind: str
    target: str = ""
    text: str = ""


BROWSER_AGENT_OPEN_KEYWORDS = ("浏览器打开", "打开网页", "打开网站", "访问网页", "访问网站")
BROWSER_AGENT_OBSERVE_KEYWORDS = ("观察浏览器", "看一下浏览器", "看看浏览器", "浏览器截图", "网页截图", "观察网页")
BROWSER_AGENT_CLICK_KEYWORDS = ("点击", "点一下", "浏览器点击")
BROWSER_AGENT_TYPE_KEYWORDS = ("输入", "填写", "填入")
BROWSER_AGENT_BLOCKED_KEYWORDS = (
    "登录",
    "登陆",
    "login",
    "sign in",
    "signin",
    "密码",
    "password",
    "验证码",
    "captcha",
    "支付",
    "付款",
    "payment",
    "pay",
    "checkout",
    "转账",
    "transfer",
    "银行卡",
    "删除",
    "delete",
    "remove",
    "发消息",
    "发送消息",
    "send message",
    "send email",
    "发邮件",
    "发送邮件",
    "运行命令",
    "执行命令",
    "本地文件",
    "读取文件",
    "file://",
)


def browser_agent_log(event, payload):
    try:
        os.makedirs(BROWSER_AGENT_DIR, exist_ok=True)
        with open(BROWSER_AGENT_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + event + " " + json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    log_runtime(f"BROWSER_AGENT_{event}", payload)


def browser_agent_block_reason(text):
    compact = re.sub(r"\s+", "", text or "").lower()
    for keyword in BROWSER_AGENT_BLOCKED_KEYWORDS:
        if keyword.lower() in compact:
            return f"包含受限内容：{keyword}"
    without_urls = re.sub(r"https?://[^\s，。；;！!？?\"'<>]+", "", text or "", flags=re.I)
    if re.search(r"(^|[\s\"'：])(?:[a-zA-Z]:\\|\\\\|/[^\s/])", without_urls):
        return "疑似本地文件路径，已拒绝"
    return ""


def browser_agent_extract_url(text):
    match = re.search(r"https?://[^\s，。；;！!？?\"'<>]+", text or "", flags=re.I)
    if match:
        return match.group(0)
    match = re.search(r"(?:打开网页|打开网站|访问网页|访问网站|浏览器打开)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s，。；;！!？?\"'<>]*)?)", text or "")
    if match:
        return "https://" + match.group(1).strip()
    return ""


def browser_agent_extract_after(text, keywords):
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        value = text[index + len(keyword):].strip(" ：:，,。.!！?？\"'")
        if value:
            return value
    return ""


def parse_browser_agent_action(text):
    text = (text or "").strip()
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None, ""

    reason = browser_agent_block_reason(text)
    if reason and any(word in compact for word in ("浏览器", "网页", "网站", "点击", "输入", "填写", "打开")):
        return None, reason

    if any(keyword in compact for keyword in BROWSER_AGENT_OBSERVE_KEYWORDS):
        return BrowserAgentAction("observe"), ""

    if any(keyword in compact for keyword in BROWSER_AGENT_OPEN_KEYWORDS):
        url = browser_agent_extract_url(text)
        if not url:
            return None, "没有识别到要打开的网址"
        return BrowserAgentAction("open_url", target=url), ""

    if "浏览器" in compact and any(keyword in compact for keyword in BROWSER_AGENT_CLICK_KEYWORDS):
        target = browser_agent_extract_after(text, BROWSER_AGENT_CLICK_KEYWORDS)
        target = target.replace("浏览器", "").strip(" ：:，,。.!！?？\"'")
        if not target:
            return None, "没有识别到要点击的网页文字"
        return BrowserAgentAction("click_text", target=target[:80]), ""

    if "浏览器" in compact and any(keyword in compact for keyword in BROWSER_AGENT_TYPE_KEYWORDS):
        value = browser_agent_extract_after(text, BROWSER_AGENT_TYPE_KEYWORDS)
        value = value.replace("浏览器", "").strip(" ：:，,。.!！?？\"'")
        if not value:
            return None, "没有识别到要输入的文字"
        if len(value) > 120:
            return None, "单次输入文字太长，已拒绝"
        return BrowserAgentAction("type_text", text=value), ""

    return None, ""


def describe_browser_agent_action(action):
    if action.kind == "open_url":
        return f"打开独立浏览器窗口并访问：{action.target}"
    if action.kind == "observe":
        return "截取独立浏览器窗口并记录页面信息"
    if action.kind == "click_text":
        return f"点击网页中包含“{action.target}”的元素"
    if action.kind == "type_text":
        return f"向当前网页焦点输入：{action.text}"
    return "未知浏览器动作"


class SafeBrowserAgent:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None

    def ensure_available(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("浏览器 agent 需要安装 playwright：python -m pip install playwright 后再运行 playwright install chromium") from exc
        return sync_playwright

    def ensure_page(self):
        os.makedirs(BROWSER_AGENT_PROFILE_DIR, exist_ok=True)
        os.makedirs(BROWSER_AGENT_SCREENSHOT_DIR, exist_ok=True)
        if self.page and not self.page.is_closed():
            return self.page

        sync_playwright = self.ensure_available()
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        if self.context is None:
            self.context = self.playwright.chromium.launch_persistent_context(
                BROWSER_AGENT_PROFILE_DIR,
                headless=False,
                viewport={"width": 1280, "height": 800},
                accept_downloads=False,
                args=[
                    "--disable-extensions",
                    "--disable-file-system",
                    "--no-default-browser-check",
                    "--disable-sync",
                ],
            )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def screenshot(self, page):
        os.makedirs(BROWSER_AGENT_SCREENSHOT_DIR, exist_ok=True)
        path = os.path.join(BROWSER_AGENT_SCREENSHOT_DIR, f"browser_{time.strftime('%Y%m%d_%H%M%S')}.png")
        page.screenshot(path=path, full_page=False)
        return path

    def page_text_snapshot(self, page):
        try:
            text = page.locator("body").inner_text(timeout=2000)
        except Exception:
            text = ""
        return re.sub(r"\s+", " ", text).strip()[:3000]

    def blocked_page_reason(self, page):
        combined = f"{page.url} {page.title()} {self.page_text_snapshot(page)}".lower()
        for keyword in BROWSER_AGENT_BLOCKED_KEYWORDS:
            if keyword.lower() in combined:
                return f"当前页面包含受限内容：{keyword}"
        return ""

    def execute(self, action):
        page = self.ensure_page()
        if action.kind == "open_url":
            if not re.match(r"^https?://", action.target, flags=re.I):
                raise RuntimeError("只允许打开 http/https 网页。")
            page.goto(action.target, wait_until="domcontentloaded", timeout=30000)
        elif action.kind == "observe":
            if page.url == "about:blank":
                page.goto("https://www.example.com", wait_until="domcontentloaded", timeout=30000)
        elif action.kind == "click_text":
            reason = self.blocked_page_reason(page)
            if reason:
                raise RuntimeError(reason)
            locator = page.get_by_text(action.target, exact=False).first
            locator.click(timeout=5000)
        elif action.kind == "type_text":
            reason = self.blocked_page_reason(page)
            if reason:
                raise RuntimeError(reason)
            page.keyboard.type(action.text, delay=15)
        else:
            raise RuntimeError("未知浏览器动作。")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        screenshot_path = self.screenshot(page)
        result = {
            "kind": action.kind,
            "url": page.url,
            "title": page.title(),
            "screenshot": screenshot_path,
            "text_snapshot": self.page_text_snapshot(page),
            "profile": BROWSER_AGENT_PROFILE_DIR,
        }
        browser_agent_log("EXECUTE", result)
        return result

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            self.page = None
            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None


class ApiSettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌宠 API 设置")
        self.setModal(True)
        self.config = dict(config or {})
        self.fields = {}
        self.resize(560, 620)
        self.setMinimumWidth(520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#hintLabel {
                color: #8a6178;
                line-height: 140%;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 210);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 10px;
                margin-top: 16px;
                padding: 16px 14px 12px 14px;
                font-weight: 700;
                color: #8f2d5a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #fff6fb;
            }
            QLabel {
                color: #6b4058;
            }
            QLineEdit {
                min-height: 30px;
                padding: 5px 9px;
                border: 1px solid rgba(225, 135, 180, 210);
                border-radius: 8px;
                background: rgba(255, 255, 255, 245);
                color: #513247;
                selection-background-color: #f4a6c7;
            }
            QLineEdit:focus {
                border: 1px solid #d85f9b;
                background: #ffffff;
            }
            QLineEdit[secret="true"] {
                background: #fffafd;
            }
            QDialogButtonBox QPushButton {
                min-width: 88px;
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QDialogButtonBox QPushButton:hover {
                background: #ffe8f3;
            }
            QDialogButtonBox QPushButton:default {
                background: #e866a3;
                color: white;
                border-color: #d94e91;
            }
            QDialogButtonBox QPushButton:default:hover {
                background: #df4f94;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("API 设置")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        intro = QLabel("保存后会写入 persona_llm_config.json，并立即应用到桌宠。敏感字段会隐藏显示；留空的可选项会使用默认值。")
        intro.setObjectName("hintLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        llm_form = self.add_section(panel_layout, "大模型")
        self.add_field(llm_form, "Provider", "provider", placeholder="openai_compatible")
        self.add_field(llm_form, "模型", "model", placeholder="deepseek-chat")
        self.add_field(llm_form, "接口地址", "base_url", placeholder="https://api.deepseek.com")
        self.add_field(llm_form, "API Key", "api_key", password=True)
        self.add_field(llm_form, "环境变量", "api_key_env", placeholder="DEEPSEEK_API_KEY")

        asr_form = self.add_section(panel_layout, "语音识别")
        self.add_field(asr_form, "豆包 API Key", "doubao_asr_api_key", password=True)
        self.add_field(asr_form, "识别接口", "doubao_asr_url", placeholder="https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash")
        self.add_field(asr_form, "Resource ID", "doubao_asr_resource_id", placeholder="volc.bigasr.auc_turbo")

        ocr_form = self.add_section(panel_layout, "聊天截图 OCR")
        self.add_field(ocr_form, "OCR Provider", "ocr_provider", placeholder="tesseract")
        self.add_field(ocr_form, "Tesseract 路径", "tesseract_cmd", placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.add_field(ocr_form, "识别语言", "tesseract_lang", placeholder="chi_sim+eng")

        tts_form = self.add_section(panel_layout, "中文配音")
        self.add_field(tts_form, "AppID", "volcengine_tts_appid", placeholder="可选，X-Api-Key 模式可留空")
        self.add_field(tts_form, "API Key", "volcengine_tts_api_key", password=True)
        self.add_field(tts_form, "Key 环境变量", "volcengine_tts_token_env", placeholder="VOLCENGINE_TTS_API_KEY")
        self.add_field(tts_form, "配音接口", "volcengine_tts_url", placeholder=VOLCENGINE_TTS_URL)
        self.add_field(tts_form, "Cluster", "volcengine_tts_cluster", placeholder="volcano_icl")
        self.add_field(tts_form, "音色 ID", "volcengine_tts_voice_type", placeholder="S_zEdGPhR02")
        panel_layout.addStretch(1)
        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if save_button:
            save_button.setText("保存")
            save_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_section(self, layout, title):
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 10, 12, 10)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        group_layout.addLayout(form)
        layout.addWidget(group)
        return form

    def add_field(self, form, label, key, password=False, placeholder=""):
        field = QLineEdit(str(self.config.get(key, DEFAULT_LLM_CONFIG.get(key, "")) or ""))
        field.setClearButtonEnabled(True)
        field.setPlaceholderText(str(placeholder or DEFAULT_LLM_CONFIG.get(key, "")))
        if password:
            field.setEchoMode(QLineEdit.Password)
            field.setProperty("secret", "true")
        if key == "volcengine_tts_voice_type":
            field.setPlaceholderText(VOLCENGINE_TTS_VOICE_TYPE)
        elif key == "volcengine_tts_cluster":
            field.setPlaceholderText(VOLCENGINE_TTS_CLUSTER)
        elif key == "volcengine_tts_url":
            field.setPlaceholderText(VOLCENGINE_TTS_URL)
        elif key == "volcengine_tts_token_env":
            field.setPlaceholderText("VOLCENGINE_TTS_API_KEY")
        form.addRow(label, field)
        self.fields[key] = field

    def values(self):
        data = dict(self.config)
        for key, field in self.fields.items():
            data[key] = field.text().strip()
        data["tts_provider"] = "volcengine"
        data["volcengine_tts_voice_type"] = data.get("volcengine_tts_voice_type") or VOLCENGINE_TTS_VOICE_TYPE
        data["volcengine_tts_cluster"] = data.get("volcengine_tts_cluster") or VOLCENGINE_TTS_CLUSTER
        data["volcengine_tts_url"] = data.get("volcengine_tts_url") or VOLCENGINE_TTS_URL
        data["volcengine_tts_token_env"] = data.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY"
        data["volcengine_tts_token"] = data.get("volcengine_tts_api_key", "")
        data["speech_provider"] = "doubao"
        return data


class MemoryGraphCanvas(QWidget):
    NODE_COLORS = {
        "角色": QColor(255, 196, 224),
        "类别": QColor(205, 230, 255),
        "情绪": QColor(255, 222, 168),
        "症状": QColor(255, 184, 184),
        "记忆": QColor(218, 238, 204),
    }

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.positions = {}
        self.velocities = {}
        self.radii = {}
        self.layout_key = ()
        self.drag_node_id = ""
        self.drag_offset = (0.0, 0.0)
        self.setMinimumSize(540, 430)
        self.setMouseTracking(True)
        self.hover_node_id = ""
        self.setStyleSheet(
            "background: rgba(255,255,255,230); border: 1px solid rgba(235,144,188,210); border-radius: 10px;"
        )
        self.layout_timer = QTimer(self)
        self.layout_timer.timeout.connect(self.animate_layout)
        self.layout_timer.start(50)

    def node_color(self, node):
        return self.NODE_COLORS.get(node.get("type", ""), QColor(235, 218, 255))

    def node_text_color(self, node):
        node_type = node.get("type", "")
        if node_type == "鐥囩姸":
            return QColor(104, 50, 58)
        if node_type == "鎯呯华":
            return QColor(108, 66, 36)
        if node_type == "绫诲埆":
            return QColor(48, 76, 112)
        if node_type == "璁板繂":
            return QColor(55, 89, 56)
        return QColor(91, 45, 72)

    def compact_label(self, label, max_chars=8):
        label = str(label or "").strip()
        if len(label) <= max_chars:
            return label
        return label[: max_chars - 1] + "…"

    def layout_nodes(self, reset=False):
        nodes = self.dialog.important_nodes()
        node_ids = [node.get("id", "") for node in nodes if node.get("id", "")]
        node_key = tuple(node_ids)
        if reset or node_key != self.layout_key:
            self.positions = {node_id: self.positions[node_id] for node_id in node_ids if node_id in self.positions}
            self.velocities = {node_id: self.velocities.get(node_id, (0.0, 0.0)) for node_id in node_ids}
            self.layout_key = node_key
        self.radii = {}
        if not nodes:
            return []

        center_x = self.width() * 0.50
        center_y = self.height() * 0.50
        rings = [
            min(self.width(), self.height()) * 0.24,
            min(self.width(), self.height()) * 0.39,
        ]
        for index, node in enumerate(nodes):
            node_id = node.get("id", "")
            count = int(node.get("count", 0))
            radius = 22 + min(16, count * 2)
            self.radii[node_id] = radius
            if node_id in self.positions and not reset:
                continue
            if index == 0:
                self.positions[node_id] = (center_x, center_y)
                continue
            ring_index = 0 if index <= 14 else 1
            ring_radius = rings[ring_index]
            ring_items = min(14, max(1, len(nodes) - 1)) if ring_index == 0 else max(1, len(nodes) - 15)
            local_index = index - 1 if ring_index == 0 else index - 15
            angle = local_index / max(1, ring_items) * math.tau - math.pi / 2
            self.positions[node_id] = (
                center_x + math.cos(angle) * ring_radius,
                center_y + math.sin(angle) * ring_radius,
            )
        return nodes

    def clamp_position(self, node_id, x, y):
        radius = self.radii.get(node_id, 24)
        margin = radius + 10
        return (
            max(margin, min(self.width() - margin, x)),
            max(margin, min(self.height() - margin, y)),
        )

    def animate_layout(self):
        nodes = self.layout_nodes()
        if len(nodes) < 2 or not self.isVisible():
            return
        node_ids = [node.get("id", "") for node in nodes if node.get("id", "")]
        node_set = set(node_ids)
        forces = {node_id: [0.0, 0.0] for node_id in node_ids}
        center_x = self.width() * 0.50
        center_y = self.height() * 0.50

        for index, left in enumerate(node_ids):
            x1, y1 = self.positions.get(left, (center_x, center_y))
            for right in node_ids[index + 1 :]:
                x2, y2 = self.positions.get(right, (center_x, center_y))
                dx = x1 - x2
                dy = y1 - y2
                dist_sq = max(64.0, dx * dx + dy * dy)
                dist = math.sqrt(dist_sq)
                strength = min(2.8, 1800.0 / dist_sq)
                fx = dx / dist * strength
                fy = dy / dist * strength
                forces[left][0] += fx
                forces[left][1] += fy
                forces[right][0] -= fx
                forces[right][1] -= fy

        for edge in self.dialog.graph.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_set or target not in node_set:
                continue
            x1, y1 = self.positions[source]
            x2, y2 = self.positions[target]
            dx = x2 - x1
            dy = y2 - y1
            dist = max(1.0, math.sqrt(dx * dx + dy * dy))
            desired = 112.0 + min(58.0, (self.radii.get(source, 24) + self.radii.get(target, 24)) * 0.7)
            strength = (dist - desired) * 0.006 * min(3.0, max(1.0, float(edge.get("weight", 1))))
            fx = dx / dist * strength
            fy = dy / dist * strength
            forces[source][0] += fx
            forces[source][1] += fy
            forces[target][0] -= fx
            forces[target][1] -= fy

        moved = False
        for node_id in node_ids:
            if node_id == self.drag_node_id:
                self.velocities[node_id] = (0.0, 0.0)
                continue
            x, y = self.positions.get(node_id, (center_x, center_y))
            forces[node_id][0] += (center_x - x) * 0.002
            forces[node_id][1] += (center_y - y) * 0.002
            vx, vy = self.velocities.get(node_id, (0.0, 0.0))
            vx = (vx + forces[node_id][0]) * 0.82
            vy = (vy + forces[node_id][1]) * 0.82
            vx = max(-3.0, min(3.0, vx))
            vy = max(-3.0, min(3.0, vy))
            if abs(vx) > 0.02 or abs(vy) > 0.02:
                moved = True
            self.positions[node_id] = self.clamp_position(node_id, x + vx, y + vy)
            self.velocities[node_id] = (vx, vy)
        if moved:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 0))

        nodes = self.layout_nodes()
        if not nodes:
            painter.setPen(QColor(138, 97, 120))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "还没有记忆。\n对话几轮后这里会长出关系网。")
            painter.end()
            return

        node_ids = {node.get("id", "") for node in nodes}
        for edge in self.dialog.graph.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_ids or target not in node_ids:
                continue
            x1, y1 = self.positions[source]
            x2, y2 = self.positions[target]
            weight = min(4, max(1, int(edge.get("weight", 1))))
            painter.setPen(QColor(205, 142, 180, 85 + weight * 22))
            pen = painter.pen()
            pen.setWidth(weight)
            painter.setPen(pen)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            if weight >= 2:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                painter.setPen(QColor(150, 92, 128, 150))
                painter.setFont(QFont("Microsoft YaHei UI", 7))
                painter.drawText(int(mx - 18), int(my - 4), edge.get("relation", "关联")[:4])

        for node in nodes:
            node_id = node.get("id", "")
            x, y = self.positions[node_id]
            radius = self.radii[node_id]
            selected = node_id == self.dialog.current_node_id
            hovered = node_id == self.hover_node_id

            base_color = self.node_color(node)
            shadow_radius = radius + (6 if selected or hovered else 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(102, 46, 76, 28 if selected or hovered else 18))
            painter.drawEllipse(
                int(x - shadow_radius + 2),
                int(y - shadow_radius + 5),
                shadow_radius * 2,
                shadow_radius * 2,
            )

            if selected or hovered:
                painter.setBrush(QColor(255, 132, 188, 46 if selected else 30))
                painter.drawEllipse(
                    int(x - radius - 7),
                    int(y - radius - 7),
                    (radius + 7) * 2,
                    (radius + 7) * 2,
                )

            gradient = QRadialGradient(x - radius * 0.35, y - radius * 0.45, radius * 1.35)
            gradient.setColorAt(0.0, base_color.lighter(136))
            gradient.setColorAt(0.58, base_color)
            gradient.setColorAt(1.0, base_color.darker(108))
            painter.setBrush(gradient)
            pen_color = QColor(230, 94, 150) if selected or hovered else QColor(214, 136, 176)
            painter.setPen(pen_color)
            pen = painter.pen()
            pen.setWidth(3 if selected else 2)
            painter.setPen(pen)
            painter.drawEllipse(int(x - radius), int(y - radius), radius * 2, radius * 2)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 76))
            highlight_size = max(8, int(radius * 0.36))
            painter.drawEllipse(
                int(x - radius * 0.42),
                int(y - radius * 0.48),
                highlight_size,
                highlight_size,
            )

            painter.setPen(self.node_text_color(node))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.DemiBold))
            label = self.compact_label(node.get("label", ""), 8)
            painter.drawText(
                int(x - radius - 14),
                int(y - 10),
                int((radius + 14) * 2),
                19,
                Qt.AlignCenter,
                label,
            )

            type_label = self.compact_label(node.get("type", ""), 4)
            count_label = f"{type_label} · {node.get('count', 0)}"
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.setPen(QColor(112, 74, 96, 190))
            painter.drawText(
                int(x - radius - 14),
                int(y + 8),
                int((radius + 14) * 2),
                16,
                Qt.AlignCenter,
                count_label,
            )
        painter.end()

    def node_at(self, pos):
        self.layout_nodes()
        for node_id, (x, y) in self.positions.items():
            radius = self.radii.get(node_id, 24)
            if (pos.x() - x) ** 2 + (pos.y() - y) ** 2 <= radius ** 2:
                return node_id
        return ""

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        node_id = self.node_at(event.pos())
        if node_id:
            x, y = self.positions.get(node_id, (event.pos().x(), event.pos().y()))
            self.drag_node_id = node_id
            self.drag_offset = (event.pos().x() - x, event.pos().y() - y)
            self.dialog.focus_node(node_id)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_node_id:
            dx, dy = self.drag_offset
            x, y = self.clamp_position(self.drag_node_id, event.pos().x() - dx, event.pos().y() - dy)
            self.positions[self.drag_node_id] = (x, y)
            self.velocities[self.drag_node_id] = (0.0, 0.0)
            self.hover_node_id = self.drag_node_id
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            event.accept()
            return
        node_id = self.node_at(event.pos())
        if node_id != self.hover_node_id:
            self.hover_node_id = node_id
            self.setCursor(Qt.OpenHandCursor if node_id else Qt.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_node_id and event.button() == Qt.LeftButton:
            self.drag_node_id = ""
            self.drag_offset = (0.0, 0.0)
            self.setCursor(Qt.OpenHandCursor if self.hover_node_id else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.layout_nodes(reset=True)
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if self.drag_node_id:
            super().leaveEvent(event)
            return
        if self.hover_node_id:
            self.hover_node_id = ""
            self.setCursor(Qt.ArrowCursor)
            self.update()
        super().leaveEvent(event)


class MemoryGraphDialog(QDialog):
    def __init__(self, memory_store, parent=None):
        super().__init__(parent)
        self.memory_store = memory_store
        self.graph, self.short_terms, self.long_term = self.memory_store.graph_snapshot()
        self.current_node_id = ""
        self.setWindowTitle("脑内记忆地图")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#memoryTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#memoryHint {
                color: #8a6178;
            }
            QTextEdit {
                background: rgba(255, 255, 255, 238);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 10px;
                padding: 10px;
                color: #543247;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("脑内记忆地图")
        title.setObjectName("memoryTitle")
        root.addWidget(title)
        hint = QLabel("点击关系网里的节点查看细节；连线代表对话、归类、触发、建议、相似等联想关系。")
        hint.setObjectName("memoryHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.canvas = MemoryGraphCanvas(self)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumWidth(270)
        body.addWidget(self.canvas, 2)
        body.addWidget(self.detail, 1)

        self.show_overview()

    def important_nodes(self):
        nodes = self.graph.get("nodes", {})
        edges = self.graph.get("edges", [])
        connected = {}
        for edge in edges:
            connected[edge.get("source")] = connected.get(edge.get("source"), 0) + int(edge.get("weight", 1))
            connected[edge.get("target")] = connected.get(edge.get("target"), 0) + int(edge.get("weight", 1))
        ranked = sorted(
            nodes.values(),
            key=lambda node: (connected.get(node.get("id"), 0), int(node.get("count", 0))),
            reverse=True,
        )
        return ranked[:34]

    def show_overview(self):
        summary = self.long_term.get("summary", "还没有形成长期记忆。")
        recent = self.short_terms[-5:]
        lines = [f"长期摘要\n{summary}", "", "最近片段"]
        if not recent:
            lines.append("暂无。")
        for item in reversed(recent):
            cats = " / ".join(item.get("categories", []))
            lines.append(f"- [{cats}] 用户：{item.get('user', '')[:80]}")
            lines.append(f"  桌宠：{item.get('assistant', '')[:80]}")
        self.detail.setPlainText("\n".join(lines))

    def focus_node(self, node_id):
        self.current_node_id = node_id
        nodes = self.graph.get("nodes", {})
        node = nodes.get(node_id, {})
        related = []
        for edge in self.graph.get("edges", []):
            other_id = ""
            direction = ""
            if edge.get("source") == node_id:
                other_id = edge.get("target")
                direction = "->"
            elif edge.get("target") == node_id:
                other_id = edge.get("source")
                direction = "<-"
            if other_id and other_id in nodes:
                related.append((edge, nodes[other_id], direction))
        related.sort(key=lambda pair: int(pair[0].get("weight", 1)), reverse=True)
        lines = [
            f"{node.get('label', node_id)}",
            f"类型：{node.get('type', '')}",
            f"类别：{node.get('category', '') or '未归类'}",
            f"出现次数：{node.get('count', 0)}",
            f"最近出现：{node.get('last_seen', '')}",
            "",
            "细节",
        ]
        details = node.get("details") or []
        lines.extend([f"- {detail}" for detail in details] or ["暂无细节。"])
        lines.extend(["", "联想关系"])
        for edge, other, direction in related[:16]:
            lines.append(
                f"- {direction} {edge.get('relation', '关联')}：{other.get('label', other.get('id'))}  x{edge.get('weight', 1)}"
            )
            if edge.get("detail"):
                lines.append(f"  {edge.get('detail')[:90]}")
        self.detail.setPlainText("\n".join(lines))
        if hasattr(self, "canvas"):
            self.canvas.update()


class DriveStatusDialog(QDialog):
    def __init__(self, drive, life=None, parent=None):
        super().__init__(parent)
        self.drive = drive
        self.life = life
        self.bars = {}
        self.value_labels = {}
        self.setWindowTitle("角色状态")
        self.resize(430, 560)
        self.setMinimumSize(390, 500)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff1f8;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#driveTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#driveSubTitle {
                color: #8a6178;
            }
            QLabel[class="metricName"] {
                color: #5d3750;
                font-weight: 700;
            }
            QLabel[class="metricHint"] {
                color: #9a7188;
                font-size: 8pt;
            }
            QLabel[class="metricValue"] {
                color: #8f2d5a;
                font-weight: 700;
            }
            QLabel#driveMood {
                background: rgba(255, 255, 255, 228);
                border: 1px solid rgba(222, 112, 168, 210);
                border-radius: 8px;
                padding: 12px;
                color: #684158;
            }
            QTextEdit#intentLog {
                background: rgba(255, 255, 255, 226);
                border: 1px solid rgba(235, 144, 188, 190);
                border-radius: 8px;
                padding: 8px;
                color: #684158;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("小日和 STATUS")
        title.setObjectName("driveTitle")
        root.addWidget(title)

        subtitle = QLabel("当前同步：内驱 / 记忆 / 主动意图 / 写作生活")
        subtitle.setObjectName("driveSubTitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        for key, label, hint, color in DRIVE_METRICS:
            block = QVBoxLayout()
            top = QHBoxLayout()
            name = QLabel(f"{label}  {key}")
            name.setProperty("class", "metricName")
            value_label = QLabel("0")
            value_label.setProperty("class", "metricValue")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            top.addWidget(name, 1)
            top.addWidget(value_label)
            block.addLayout(top)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            bar.setStyleSheet(
                "QProgressBar {"
                "background: rgba(255,255,255,210);"
                "border: 1px solid rgba(232,154,190,190);"
                "border-radius: 6px;"
                "}"
                "QProgressBar::chunk {"
                f"background: {color.name()};"
                "border-radius: 5px;"
                "}"
            )
            block.addWidget(bar)

            hint_label = QLabel(hint)
            hint_label.setProperty("class", "metricHint")
            hint_label.setWordWrap(True)
            block.addWidget(hint_label)
            root.addLayout(block)
            self.bars[key] = bar
            self.value_labels[key] = value_label

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("driveMood")
        self.mood_label.setWordWrap(True)
        root.addWidget(self.mood_label)

        self.intent_log = QTextEdit()
        self.intent_log.setObjectName("intentLog")
        self.intent_log.setReadOnly(True)
        self.intent_log.setFixedHeight(96)
        root.addWidget(self.intent_log)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(500)
        self.refresh()

    def refresh(self):
        snapshot = self.drive.snapshot()
        values = snapshot.get("values", {})
        for key, label, _hint, _color in DRIVE_METRICS:
            value = int(round(values.get(key, 0)))
            self.bars[key].setValue(value)
            self.value_labels[key].setText(str(value))

        dominant = snapshot.get("dominant", "")
        labels = {key: label for key, label, *_rest in DRIVE_METRICS}
        dominant_label = labels.get(dominant, dominant)
        streak = snapshot.get("proactive_streak", 0)
        last_action = snapshot.get("last_action_type") or "暂无"
        mood = snapshot.get("mood", "quiet")
        goal = snapshot.get("active_goal", "安静待在旁边")
        inner = self.inner_monologue(mood, goal)
        relation_line = "关系阶段：未同步"
        writing_line = ""
        if self.life is not None:
            stage, _attitude = self.life.relationship_stage()
            relation_line = f"关系阶段：{stage}（{self.life.relationship_score:.0f}/100）"
            if self.life.novel.get("title"):
                writing_line = f"\n小说：《{self.life.novel.get('title')}》 {self.life.novel.get('chapter', 0)}/{self.life.novel.get('target_chapters', 8)}"
                writing_line += f"\n今日写作：{self.life.novel_words_today}/{LIFE_NOVEL_DAILY_WORD_LIMIT} 字，{self.life.novel_chapters_today}/{LIFE_NOVEL_DAILY_CHAPTER_LIMIT} 章"
            away = self.life.away_label()
            if away:
                writing_line += f"\n日历：{away}"
        self.mood_label.setText(
            f"{relation_line}\n"
            f"职业：小说作家 / 情感陪伴朋友{writing_line}\n"
            f"心境：{mood}\n"
            f"当前目标：{goal}\n"
            f"内心独白：{inner}\n"
            f"最强驱动：{dominant_label}\n"
            f"连续主动次数：{streak}\n"
            f"上一次自主行动：{last_action}"
        )
        history = snapshot.get("intent_history") or []
        if history:
            lines = [
                f"{item.get('time', '')[-8:]}  {item.get('type', '')}：{item.get('reason', '')}"
                for item in reversed(history[-5:])
            ]
        else:
            lines = ["暂无行动记录。"]
        self.intent_log.setPlainText("\n".join(lines))

    def inner_monologue(self, mood, goal):
        templates = {
            "curious": "我想多知道一点，但要问得轻一点。",
            "attached": "想靠近他一点，不过不能太黏。",
            "worried": "他如果有点累，我应该先温柔一点。",
            "relaxed": "现在的气氛很安稳，可以慢慢陪着。",
            "tired": "先安静一会儿，别打扰他。",
            "playful": "感觉可以用轻松一点的方式开口。",
            "quiet": "还没到开口的时候，先观察。",
        }
        return templates.get(mood, goal)


class MiniGameDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet if isinstance(parent_pet, QWidget) else None)
        self.pet = parent_pet
        self.secret_number = random.randint(1, 20)
        self.guess_attempts = 0
        self.sync_question = random.choice(
            [
                ("如果我今天写小说卡住了，你觉得我会先做什么？", ["喝点水", "找你撒娇", "继续硬写"]),
                ("如果你很久没理我，我最可能是什么反应？", ["安静等你", "有点闹别扭", "马上生气"]),
                ("我作为小说家，最容易注意到什么？", ["细节", "数字", "天气预报"]),
            ]
        )
        self.setWindowTitle("和小日和玩一会儿")
        self.resize(520, 460)
        self.setMinimumSize(460, 420)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff3fa;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#gameTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#gameHint {
                color: #8a6178;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 220);
                border: 1px solid rgba(235, 144, 188, 205);
                border-radius: 8px;
                margin-top: 14px;
                padding: 12px;
                color: #8f2d5a;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background: #fff3fa;
            }
            QPushButton {
                min-height: 28px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 210);
                padding: 4px 12px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QPushButton:hover { background: #ffe6f2; }
            QLineEdit {
                min-height: 28px;
                border-radius: 8px;
                border: 1px solid rgba(225, 135, 180, 210);
                padding: 4px 8px;
                background: white;
                color: #513247;
            }
            QTextEdit {
                background: rgba(255,255,255,230);
                border: 1px solid rgba(235,144,188,185);
                border-radius: 8px;
                padding: 8px;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("小游戏时间")
        title.setObjectName("gameTitle")
        root.addWidget(title)
        hint = QLabel("小游戏会增加亲密值；同一天重复游玩收益会递减，第二天刷新。")
        hint.setObjectName("gameHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        guess_group = QGroupBox("猜数字")
        guess_layout = QHBoxLayout(guess_group)
        self.guess_input = QLineEdit()
        self.guess_input.setPlaceholderText("1-20")
        guess_button = QPushButton("猜")
        guess_button.clicked.connect(self.play_guess_number)
        guess_layout.addWidget(QLabel("我心里有个 1-20 的数字："))
        guess_layout.addWidget(self.guess_input)
        guess_layout.addWidget(guess_button)
        root.addWidget(guess_group)

        rps_group = QGroupBox("石头剪刀布")
        rps_layout = QHBoxLayout(rps_group)
        for choice in ("石头", "剪刀", "布"):
            button = QPushButton(choice)
            button.clicked.connect(lambda _checked=False, c=choice: self.play_rps(c))
            rps_layout.addWidget(button)
        root.addWidget(rps_group)

        sync_group = QGroupBox("默契问答")
        sync_layout = QVBoxLayout(sync_group)
        self.sync_question_label = QLabel(self.sync_question[0])
        self.sync_question_label.setWordWrap(True)
        sync_layout.addWidget(self.sync_question_label)
        sync_buttons = QHBoxLayout()
        self.sync_option_buttons = []
        for option in self.sync_question[1]:
            button = QPushButton(option)
            button.clicked.connect(lambda _checked=False, o=option: self.play_sync(o))
            self.sync_option_buttons.append(button)
            sync_buttons.addWidget(button)
        sync_layout.addLayout(sync_buttons)
        root.addWidget(sync_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlainText("小日和：要玩哪个？我会认真陪你玩的。")
        root.addWidget(self.log, 1)

    def append_log(self, text):
        self.log.append(text)

    def reward(self, result, message, voice_text=""):
        reward = self.pet.reward_minigame(result, voice_text=voice_text or message)
        self.append_log(f"{message}\n亲密值 +{reward['relation_gain']:.1f}（今日第 {reward['count']} 次小游戏）")

    def play_guess_number(self):
        try:
            value = int(self.guess_input.text().strip())
        except Exception:
            self.append_log("小日和：要输入 1 到 20 的数字哦。")
            self.pet.speak_interaction_feedback("要输入 1 到 20 的数字哦，不然我没法判断你有没有猜中。", emotion="joy")
            return
        if value < 1 or value > 20:
            self.append_log(f"小日和：{value} 超出范围啦，数字只能在 1 到 20 之间。")
            self.pet.speak_interaction_feedback(f"{value} 超出范围啦，我心里的数字只在 1 到 20 之间。", emotion="joy")
            return
        self.guess_attempts += 1
        if value == self.secret_number:
            attempts = self.guess_attempts
            secret = self.secret_number
            self.secret_number = random.randint(1, 20)
            self.guess_attempts = 0
            self.reward(
                "win",
                f"小日和：猜中了，是 {secret}！居然第 {attempts} 次就抓到我的想法了。下一轮我已经换了新数字。",
                voice_text=f"猜中了，是 {secret}。第 {attempts} 次就抓到我的数字了，厉害。下一轮我已经偷偷换了一个新数字。",
            )
        elif value < self.secret_number:
            self.reward(
                "participate",
                f"小日和：你猜 {value}，小啦，我的数字比它大。",
                voice_text=f"你猜 {value}，小啦。我的数字比 {value} 大，再往上试试。",
            )
        else:
            self.reward(
                "participate",
                f"小日和：你猜 {value}，大啦，我的数字比它小。",
                voice_text=f"你猜 {value}，大啦。我的数字比 {value} 小一点，稍微收回来。",
            )

    def play_rps(self, user_choice):
        choices = ("石头", "剪刀", "布")
        pet_choice = random.choice(choices)
        beats = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
        if user_choice == pet_choice:
            result = "draw"
            message = f"小日和：我也是{pet_choice}，平局。默契还不错嘛。"
            voice_text = f"你出{user_choice}，我也出{pet_choice}，平局。我们这一下还挺同步的。"
        elif beats[user_choice] == pet_choice:
            result = "win"
            message = f"小日和：我出{pet_choice}，你赢啦。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这局你赢啦。我记住了，你这手有点准。"
        else:
            result = "lose"
            message = f"小日和：我出{pet_choice}，这次是我赢。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这次是我赢。不要不服气，下一把再来。"
        self.reward(result, message, voice_text=voice_text)

    def play_sync(self, option):
        preferred = self.sync_question[1][1]
        question = self.sync_question[0]
        if option == preferred:
            self.reward(
                "win",
                f"小日和：对，就是「{option}」。你还挺懂我的。",
                voice_text=f"刚才这题是，{question}。你选的是{option}，我心里想的也是{preferred}。被你猜中我会有点开心。",
            )
        else:
            self.reward(
                "draw",
                f"小日和：你选「{option}」也说得通，不过我刚才想的是「{preferred}」。",
                voice_text=f"刚才这题是，{question}。你选的是{option}，也说得通，不过我心里想的是{preferred}。",
            )
        self.sync_question = random.choice(
            [
                ("如果我今天写小说卡住了，你觉得我会先做什么？", ["喝点水", "找你撒娇", "继续硬写"]),
                ("如果你很久没理我，我最可能是什么反应？", ["安静等你", "有点闹别扭", "马上生气"]),
                ("我作为小说家，最容易注意到什么？", ["细节", "数字", "天气预报"]),
            ]
        )
        self.refresh_sync_question()

    def refresh_sync_question(self):
        self.sync_question_label.setText(self.sync_question[0])
        for button, option in zip(self.sync_option_buttons, self.sync_question[1]):
            button.setText(option)
            try:
                button.clicked.disconnect()
            except Exception:
                pass
            button.clicked.connect(lambda _checked=False, o=option: self.play_sync(o))


@dataclass
class ChatAdviceEvent:
    screenshot_path: str = ""
    ocr_text: str = ""
    advice: str = ""
    copy_reply: str = ""
    error: str = ""


class ChatAdviceController:
    def __init__(self, config=None, memory_store=None):
        self.config = dict(config or load_llm_config())
        self.memory_store = memory_store
        self.client = LLMClient(config=self.config, memory_store=memory_store)
        self.lock = threading.Lock()
        self.busy = False
        self.events = []

    def update_config(self, config):
        self.config = dict(config or load_llm_config())
        self.client = LLMClient(config=self.config, memory_store=self.memory_store)

    def is_busy(self):
        with self.lock:
            return self.busy

    def analyze_async(self, screenshot_path):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            event = ChatAdviceEvent(screenshot_path=screenshot_path)
            try:
                event.ocr_text = self.ocr_image(screenshot_path)
                if len(compact_text(event.ocr_text)) < 8:
                    raise RuntimeError("OCR 没有识别到足够的聊天文字。请把聊天窗口放大一点，或确认截图里有文字。")
                event.advice = self.ask_advice(event.ocr_text)
                event.copy_reply = self.extract_copy_reply(event.advice)
            except Exception as exc:
                event.error = str(exc)
            with self.lock:
                self.busy = False
                self.events.append(event)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def ocr_image(self, image_path):
        provider = str(self.config.get("ocr_provider") or "tesseract").lower()
        if provider != "tesseract":
            raise RuntimeError(f"暂不支持 OCR Provider: {provider}")
        try:
            from PIL import Image, ImageOps
            import pytesseract
        except Exception as exc:
            raise RuntimeError(f"缺少 OCR 依赖：{exc}") from exc

        tesseract_cmd = str(self.config.get("tesseract_cmd") or "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        lang = str(self.config.get("tesseract_lang") or "chi_sim+eng").strip() or "chi_sim+eng"
        image = Image.open(image_path)
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        if max(image.size) < 2200:
            image = image.resize((int(image.width * 1.45), int(image.height * 1.45)))
        try:
            text = pytesseract.image_to_string(image, lang=lang, config="--psm 6")
        except Exception:
            text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        text = re.sub(r"[ \t]+", " ", text or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    def ask_advice(self, ocr_text):
        memory_context = ""
        if self.memory_store is not None:
            memory_context = self.memory_store.build_prompt_context(ocr_text)
        system = (
            "你是桌宠的聊天记录顾问。用户给你一张聊天记录 OCR 文本，"
            "你要像亲近用户但有边界感的朋友一样分析。"
            "只根据 OCR 和记忆上下文判断，不要编造事实；不要替用户操控别人；"
            "涉及感情、人际冲突时，要具体、温柔、可执行。"
        )
        user = (
            f"{memory_context}\n\n"
            "【截图 OCR 文本】\n"
            f"{ocr_text[:6000]}\n\n"
            "请输出：\n"
            "1. 我看到的关键信息\n"
            "2. 可能的关系/情绪模式\n"
            "3. 给用户的建议\n"
            "4. 【可复制回复】给出 1-3 条用户可以直接复制发送的短回复，每条自然一点。"
        )
        return self.client.chat_messages(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.45,
            timeout=180,
        )

    def extract_copy_reply(self, advice):
        text = advice or ""
        match = re.search(r"【可复制回复】([\s\S]+)$", text)
        if match:
            block = match.group(1).strip()
        else:
            block = text.strip()
        lines = [re.sub(r"^\s*[-*0-9.、）)]+", "", line).strip() for line in block.splitlines()]
        lines = [line.strip("“”\" ") for line in lines if len(line.strip()) >= 2]
        return "\n".join(lines[:3]) or text[:500]


class ChatAdviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.copy_reply = ""
        self.setWindowTitle("聊天截图顾问")
        self.resize(720, 620)
        self.setMinimumSize(620, 520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff2f8;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#statusLabel {
                color: #8a6178;
            }
            QTextEdit {
                background: rgba(255, 255, 255, 236);
                border: 1px solid rgba(235, 144, 188, 196);
                border-radius: 8px;
                padding: 10px;
                color: #513247;
            }
            QPushButton {
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #ffe8f3;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("聊天截图顾问")
        title.setObjectName("titleLabel")
        root.addWidget(title)
        self.status_label = QLabel("准备截图 OCR...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.advice_text = QTextEdit()
        self.advice_text.setReadOnly(True)
        self.advice_text.setPlaceholderText("建议会显示在这里。")
        root.addWidget(self.advice_text, 2)

        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText("OCR 识别文本会显示在这里。")
        self.ocr_text.setMaximumHeight(150)
        root.addWidget(self.ocr_text, 1)

        buttons = QHBoxLayout()
        self.copy_reply_button = QPushButton("复制回复模板")
        self.copy_all_button = QPushButton("复制完整建议")
        self.close_button = QPushButton("关闭")
        self.copy_reply_button.clicked.connect(self.copy_reply_to_clipboard)
        self.copy_all_button.clicked.connect(self.copy_all_to_clipboard)
        self.close_button.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_reply_button)
        buttons.addWidget(self.copy_all_button)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)
        self.set_busy("正在截图，稍等一下...")

    def set_busy(self, text):
        self.status_label.setText(text)
        self.copy_reply_button.setEnabled(False)
        self.copy_all_button.setEnabled(False)

    def set_result(self, event):
        self.ocr_text.setPlainText(event.ocr_text or "")
        if event.error:
            self.status_label.setText(f"失败：{event.error}")
            self.advice_text.setPlainText("")
            self.copy_reply = ""
            self.copy_reply_button.setEnabled(False)
            self.copy_all_button.setEnabled(False)
            return
        self.status_label.setText(f"分析完成。截图：{event.screenshot_path}")
        self.advice_text.setPlainText(event.advice or "")
        self.copy_reply = event.copy_reply or ""
        self.copy_reply_button.setEnabled(bool(self.copy_reply))
        self.copy_all_button.setEnabled(bool(event.advice))

    def copy_reply_to_clipboard(self):
        QApplication.clipboard().setText(self.copy_reply or self.advice_text.toPlainText())
        self.status_label.setText("已复制回复模板。")

    def copy_all_to_clipboard(self):
        QApplication.clipboard().setText(self.advice_text.toPlainText())
        self.status_label.setText("已复制完整建议。")


class ChatScreenshotSelector(QWidget):
    def __init__(self, screen_geometry, on_selected, on_cancelled, parent=None):
        super().__init__(parent)
        self.on_selected = on_selected
        self.on_cancelled = on_cancelled
        self.origin = QPoint()
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: rgba(60, 35, 55, 72);")

        self.hint = QLabel("拖拽框选聊天记录区域，松开后开始 OCR；按 ESC 取消", self)
        self.hint.setStyleSheet(
            "QLabel {"
            "background: rgba(255, 246, 251, 236);"
            "border: 1px solid rgba(235, 144, 188, 220);"
            "border-radius: 8px;"
            "padding: 9px 14px;"
            "color: #6a3f57;"
            "font: 10pt 'Microsoft YaHei UI';"
            "}"
        )
        self.hint.adjustSize()
        self.hint.move(24, 24)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.origin = event.pos()
        self.rubber_band.setGeometry(QRect(self.origin, self.origin))
        self.rubber_band.show()
        event.accept()

    def mouseMoveEvent(self, event):
        if self.rubber_band.isVisible():
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        rect = self.rubber_band.geometry().normalized()
        self.rubber_band.hide()
        self.close()
        if rect.width() < 40 or rect.height() < 40:
            self.on_cancelled("框选区域太小，已取消。")
        else:
            self.on_selected(rect)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.rubber_band.hide()
            self.close()
            self.on_cancelled("已取消聊天截图。")
            return
        super().keyPressEvent(event)


class Live2DDesktopPet(QOpenGLWidget):
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
        self.memory = PersonaMemoryStore()
        self.drive = PersonaDriveSystem(self.memory)
        self.life = PersonaLifeSystem(self.memory)
        self.voice = VoicevoxController(config=self.llm_config)
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life)
        self.chat_advice = ChatAdviceController(config=self.llm_config, memory_store=self.memory)
        self.life_writer = LifeWritingController(config=self.llm_config, memory_store=self.memory, life_system=self.life)
        self.singing_enabled = bool(self.llm_config.get("singing_enabled", SINGING_ENABLED))
        self.speech_input = SpeechInputController()
        self.barge_in = BargeInController()
        self.memory_dialog = None
        self.drive_dialog = None
        self.mini_game_dialog = None
        self.chat_advice_dialog = None
        self.chat_advice_selector = None
        self.chat_advice_full_pixmap = None
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
        self.browser_agent = SafeBrowserAgent()
        self.self_notes = self.load_self_notes()

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
            ("Y", "打开小游戏"),
            ("G", "截图聊天记录出主意"),
            ("F", "喂饭"),
            ("H", "摸头"),
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
        input_width = max(120, self.width() - margin * 2 - close_size - help_size - gap * 2)
        self.chat_input.setGeometry(margin, 16, input_width, height)
        if hasattr(self, "help_button"):
            self.help_button.setGeometry(margin + input_width + gap, 20, help_size, help_size)
            self.help_button.raise_()
        if hasattr(self, "close_button"):
            self.close_button.setGeometry(margin + input_width + gap + help_size + gap, 20, close_size, close_size)
            self.close_button.raise_()

    def initializeGL(self):
        try:
            log_runtime(
                "LIVE2D_INIT",
                {
                    "base_dir": BASE_DIR,
                    "model_json": MODEL_JSON_PATH,
                    "model_exists": os.path.exists(MODEL_JSON_PATH),
                    "frozen": bool(getattr(sys, "frozen", False)),
                },
            )
            live2d.init()
            live2d.glInit()

            self.model = live2d.LAppModel()
            self.model.LoadModelJson(MODEL_JSON_PATH)
            self.model.Resize(self.width(), self.height())
            self.model.SetAutoBreathEnable(True)
            self.model.SetAutoBlinkEnable(True)
            log_runtime("LIVE2D_READY")
        except Exception:
            self.model = None
            log_runtime("LIVE2D_INIT_ERROR", traceback.format_exc())
            self.show_chat_status("Live2D 加载失败，查看 logs/persona_pet.log", seconds=8.0)

    def show_subtitle(self, text, voice_text="", duration=None):
        if not SUBTITLES_ENABLED:
            self.subtitle_text = ""
            self.subtitle_voice_text = ""
            self.subtitle_until = 0.0
            log_runtime("SUBTITLE_SUPPRESSED", {"text": text, "voice_text": voice_text})
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
        self.subtitle_until = now + clamp(display_seconds, 3.2, 14.0) + SUBTITLE_SECONDS_PAD
        log_runtime(
            "SUBTITLE",
            {
                "text": text,
                "voice_text": voice_text,
                "seconds": round(self.subtitle_until - now, 2),
            },
        )

    def show_chat_status(self, text, seconds=2.6):
        self.chat_status_text = text
        self.chat_status_until = time.monotonic() + seconds

    def submit_chat_input(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.submit_user_text(text)

    def handle_file_agent_input(self, text):
        if self.pending_file_action:
            if file_agent_is_cancel(text):
                action = self.pending_file_action
                self.pending_file_action = None
                message = f"已取消：{describe_file_agent_action(action)}"
                self.show_subtitle(message, voice_text="", duration=3.2)
                self.show_chat_status("文件操作已取消", seconds=2.4)
                print("FILE_AGENT_CANCEL =", {"action": describe_file_agent_action(action)})
                return True
            if file_agent_is_confirm(text):
                action = self.pending_file_action
                self.pending_file_action = None
                try:
                    path = execute_file_agent_action(action)
                    message = f"已创建：{os.path.basename(path)}\n位置：{os.path.dirname(path)}"
                    self.show_subtitle(message, voice_text="", duration=5.5)
                    self.show_chat_status("文件已创建", seconds=3.2)
                    print("FILE_AGENT_DONE =", {"action": describe_file_agent_action(action), "path": path})
                except Exception as exc:
                    message = f"创建失败：{exc}"
                    self.show_subtitle(message, voice_text="", duration=4.0)
                    self.show_chat_status("文件创建失败", seconds=3.0)
                    print("FILE_AGENT_ERROR =", {"action": describe_file_agent_action(action), "error": str(exc)})
                return True

        action = parse_file_agent_action(text)
        if not action:
            return False

        self.pending_file_action = action
        message = (
            f"准备{describe_file_agent_action(action)}\n"
            f"安全目录：{AGENT_FILES_DIR}\n"
            "回复“确认”执行，或回复“取消”。"
        )
        self.chat_input.clear()
        self.show_subtitle(message, voice_text="", duration=6.5)
        self.show_chat_status("等待确认文件操作", seconds=8.0)
        print("FILE_AGENT_PLAN =", {"action": describe_file_agent_action(action), "dir": AGENT_FILES_DIR})
        return True

    def confirm_browser_agent_action(self, action):
        message = (
            f"{describe_browser_agent_action(action)}\n\n"
            "安全限制：独立浏览器 profile；不登录、不支付、不删除、不发消息、不运行命令、不读取本地文件。\n"
            "本次确认只允许执行这一个动作，执行后授权立刻失效。"
        )
        result = QMessageBox.question(
            self,
            "确认浏览器 agent 动作",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def handle_browser_agent_input(self, text):
        action, reject_reason = parse_browser_agent_action(text)
        if reject_reason:
            message = f"浏览器 agent 已拒绝：{reject_reason}"
            self.chat_input.clear()
            self.show_subtitle(message, voice_text="", duration=4.0)
            self.show_chat_status("浏览器动作被拒绝", seconds=3.0)
            browser_agent_log("REJECT", {"text": text, "reason": reject_reason})
            print("BROWSER_AGENT_REJECT =", {"text": text, "reason": reject_reason})
            return True
        if not action:
            return False

        self.chat_input.clear()
        browser_agent_log("PLAN", {"action": describe_browser_agent_action(action), "text": text})
        print("BROWSER_AGENT_PLAN =", {"action": describe_browser_agent_action(action)})
        if not self.confirm_browser_agent_action(action):
            self.show_subtitle("已取消浏览器动作。", voice_text="", duration=2.8)
            self.show_chat_status("浏览器动作已取消", seconds=2.2)
            browser_agent_log("CANCEL", {"action": describe_browser_agent_action(action)})
            return True

        try:
            result = self.browser_agent.execute(action)
            message = f"浏览器动作完成：{result.get('title') or result.get('url')}\n截图：{result.get('screenshot')}"
            self.show_subtitle(message, voice_text="", duration=6.0)
            self.show_chat_status("浏览器动作完成", seconds=3.0)
            print("BROWSER_AGENT_DONE =", result)
        except Exception as exc:
            message = f"浏览器动作失败：{exc}"
            self.show_subtitle(message, voice_text="", duration=5.0)
            self.show_chat_status("浏览器动作失败", seconds=3.0)
            browser_agent_log("ERROR", {"action": describe_browser_agent_action(action), "error": str(exc)})
            print("BROWSER_AGENT_ERROR =", {"action": describe_browser_agent_action(action), "error": str(exc)})
        return True

    def submit_user_text(self, text):
        text = (text or "").strip()
        if not text:
            return
        if self.handle_file_agent_input(text):
            return
        if self.handle_browser_agent_input(text):
            return
        if self.chat.is_busy():
            self.show_chat_status("还在思考上一句哦。", seconds=1.8)
            return

        self.last_user_interaction_at = time.monotonic()
        self.next_proactive_at = self.last_user_interaction_at + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        self.chat_input.clear()
        self.dialogue_active = False
        user_analysis = primary_dominant_analysis(analyze_text_to_emotion(text))
        self.drive.on_user_message(text, emotion=dominant_weight_emotion(user_analysis))
        self.life.observe_user_message(text, emotion=dominant_weight_emotion(user_analysis))
        self.current_analysis = user_analysis
        self.mixer.set_target(user_analysis.weights)
        self.behavior.set_analysis(
            self.model,
            user_analysis,
            text=text,
            role=DIALOGUE_ROLE_LISTENER,
            force=True,
        )
        self.show_subtitle(f"你：{text}", voice_text="考え中……", duration=2.2)
        self.show_chat_status("思考中……", seconds=30.0)
        print("USER_CHAT =", text)
        if not self.chat.ask_async(text):
            self.show_chat_status("发送失败：上一句还没处理完。", seconds=2.2)

    def interrupt_current_speech(self, reason="user"):
        self.dialogue_active = False
        self.voice.stop_playback()
        self.behavior.stop_speaking()
        self.subtitle_until = min(self.subtitle_until, time.monotonic() + 0.4)
        print("VOICE_INTERRUPTED =", {"reason": reason})

    def start_speech_input(self, auto=False, interrupt=False):
        if self.chat.is_busy():
            if not auto:
                self.show_chat_status("大模型还在回复上一句。", seconds=1.8)
            return
        if interrupt and (self.voice.is_busy_or_playing() or self.behavior.is_speaking()):
            self.interrupt_current_speech(reason="speech_input")
            time.sleep(0.12)
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking():
            if not auto:
                self.show_chat_status("角色正在说话，等她说完再听。", seconds=1.8)
            return
        if self.speech_input.is_busy():
            if not auto:
                self.show_chat_status("正在听你说话。", seconds=1.4)
            return
        self.barge_in.stop()
        if not auto:
            self.chat_input.setText("正在听你说话……")
            self.show_subtitle("正在听你说话……", voice_text="", duration=4.0)
            self.show_chat_status("我会一直听到你说完。", seconds=4.0)
        print(
            "SPEECH_INPUT_START =",
            {
                "max_seconds": SPEECH_RECORD_SECONDS,
                "adaptive": True,
                "silence_seconds": SPEECH_SILENCE_SECONDS,
            },
        )
        if not self.speech_input.listen_async() and not auto:
            self.show_chat_status("语音输入启动失败。", seconds=2.0)

    def start_free_talk(self):
        self.free_talk_enabled = True
        self.free_talk_next_at = 0.0
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking():
            self.interrupt_current_speech(reason="free_talk_start")
        self.show_chat_status("自由对话已开启。", seconds=2.0)
        print("FREE_TALK =", {"enabled": True})
        self.start_speech_input(auto=True, interrupt=True)

    def stop_free_talk(self):
        self.free_talk_enabled = False
        self.free_talk_next_at = 0.0
        self.barge_in.stop()
        self.show_chat_status("自由对话已关闭。", seconds=2.0)
        print("FREE_TALK =", {"enabled": False})

    def update_barge_in_monitor(self):
        if not self.free_talk_enabled or self.speech_input.is_busy() or self.chat.is_busy():
            self.barge_in.set_active(False)
            return
        now = time.monotonic()
        playback_started_at = self.voice.playback_started_at()
        can_interrupt = (
            self.voice.is_busy_or_playing(now)
            and playback_started_at > 0.0
            and now >= playback_started_at + BARGE_IN_AFTER_PLAYBACK_SECONDS
        )
        self.barge_in.set_active(can_interrupt)

    def process_barge_in_events(self):
        for event in self.barge_in.consume_events():
            if event.get("error"):
                print("BARGE_IN_ERROR =", event)
                self.barge_in.set_active(False)
                continue
            print("BARGE_IN_TRIGGER =", event)
            self.interrupt_current_speech(reason="barge_in")
            self.free_talk_next_at = time.monotonic() + SPEECH_RECORD_SECONDS + FREE_TALK_RELISTEN_DELAY
            self.start_speech_input(auto=True, interrupt=True)

    def maybe_continue_free_talk(self):
        if not self.free_talk_enabled:
            return
        now = time.monotonic()
        if now < self.free_talk_next_at:
            return
        if (
            PROACTIVE_ENABLED
            and now >= self.next_proactive_at
            and now - self.last_user_interaction_at >= PROACTIVE_IDLE_SECONDS
        ):
            return
        if self.speech_input.is_busy() or self.chat.is_busy() or self.life_writer.is_busy():
            return
        if self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            return
        self.free_talk_next_at = now + SPEECH_RECORD_SECONDS + FREE_TALK_RELISTEN_DELAY
        self.start_speech_input(auto=True)

    def load_self_notes(self):
        notes = self.memory.load_meta_json(SELF_NOTE_META_KEY, [])
        if not isinstance(notes, list):
            return []
        return [note for note in notes[-8:] if isinstance(note, dict) and note.get("text")]

    def save_self_notes(self):
        self.memory.save_meta_json(SELF_NOTE_META_KEY, self.self_notes[-8:])

    def add_self_note(self, text, kind="self_expression", priority=1.0):
        text = collapse_repeated_memory_text(text)
        if not text:
            return
        self.self_notes.append(
            {
                "time": memory_now_label(),
                "kind": kind,
                "priority": float(priority),
                "text": text[:220],
            }
        )
        self.self_notes = self.self_notes[-8:]
        self.save_self_notes()

    def maybe_start_self_note(self, idle_seconds):
        if not self.self_notes or self.drive.values.get("energy", 0.0) < 24:
            return False
        note = sorted(self.self_notes, key=lambda item: float(item.get("priority", 1.0)), reverse=True)[0]
        prompt = (
            "你现在不是被动回答用户，而是想主动表达一个自己的小念头。\n"
            f"用户安静了约{int(idle_seconds)}秒。你的待表达念头：{note.get('text', '')}\n"
            "只输出一句中文，语气自然、亲近但克制；像真人一样给对方留回应空间，不要解释系统。"
        )
        if not self.chat.ask_async(prompt, initiated_by="proactive", memory_user_text="桌宠主动行动：self_expression"):
            return False
        self.self_notes.remove(note)
        self.save_self_notes()
        self.drive.record_intent("self_expression", "主动表达自己的计划或刚完成的事情", score=note.get("priority"))
        self.drive.last_action_type = "self_expression"
        self.drive.save()
        self.next_proactive_at = time.monotonic() + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        print("PROACTIVE_SELF_NOTE =", {"kind": note.get("kind"), "text": note.get("text")})
        return True

    def maybe_start_proactive_chat(self):
        if not PROACTIVE_ENABLED:
            return
        now = time.monotonic()
        if now < self.next_proactive_at:
            return
        if now - self.last_user_interaction_at < PROACTIVE_IDLE_SECONDS:
            return
        if self.speech_input.is_busy() or self.chat.is_busy() or self.chat_advice.is_busy() or self.life_writer.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            self.next_proactive_at = now + 30.0
            return
        idle_seconds = now - self.last_user_interaction_at
        if self.maybe_start_self_note(idle_seconds):
            return
        action = self.drive.choose_proactive_action(idle_seconds)
        if not action:
            self.next_proactive_at = now + 45.0
            return
        if action.get("type") == "silent_motion":
            try:
                if self.model is not None:
                    self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
            except Exception:
                pass
            self.drive.on_silent_motion(action.get("type", "silent_motion"))
            self.next_proactive_at = now + random.uniform(90.0, 180.0)
            print("PROACTIVE_SILENT =", action)
            return

        prompt = action.get("prompt", "")
        self.show_chat_status("她好像想主动说点什么。", seconds=2.0)
        self.drive.record_intent(action.get("type", "proactive"), "内驱评分触发主动发言", score=action.get("score"))
        self.drive.last_action_type = action.get("type", "proactive")
        self.drive.save()
        self.chat.ask_async(
            prompt,
            initiated_by="proactive",
            memory_user_text=action.get("memory_user_text") or "桌宠主动关心用户",
        )
        self.next_proactive_at = now + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        print("PROACTIVE_CHAT =", {"action": action.get("type"), "score": action.get("score"), "prompt": prompt})

    def process_speech_events(self):
        for event in self.speech_input.consume_events():
            if event.error:
                self.chat_input.clear()
                self.show_subtitle("语音识别失败，请再试一次。", voice_text="", duration=3.0)
                self.show_chat_status("STT ERROR", seconds=2.5)
                print("SPEECH_INPUT_ERROR =", {"error": event.error})
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 1.5
                continue
            raw_text = event.text.strip()
            text = clean_speech_input_text(raw_text)
            if not self.free_talk_enabled:
                self.chat_input.clear()
            print(
                "SPEECH_INPUT_TEXT =",
                {"text": text, "raw_text": raw_text, "wav": event.wav_path, "audio_stats": event.audio_stats},
            )
            if not text:
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 0.8
                else:
                    self.show_subtitle("我没有听清楚，可以再说一遍吗？", voice_text="", duration=3.0)
                    self.show_chat_status("没有识别到文字。", seconds=2.2)
                return
            try:
                self.submit_user_text(text)
            except Exception as exc:
                self.show_chat_status("语音文本提交失败", seconds=3.0)
                log_runtime("SPEECH_SUBMIT_ERROR", traceback.format_exc())
                print("SPEECH_SUBMIT_ERROR =", {"text": text, "error": str(exc)})
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 1.5

    def process_chat_events(self):
        for event in self.chat.consume_events():
            if event.error:
                self.drive.on_llm_result(success=False, initiated_by=event.initiated_by, error=event.error)
                message = "大模型连接失败，请检查 persona_llm_config.json 或本地 Ollama。"
                self.show_subtitle(message, voice_text="", duration=4.0)
                self.show_chat_status("LLM ERROR", seconds=3.0)
                print("LLM_ERROR =", {"user": event.user_text, "error": event.error})
                continue

            if event.degraded_error:
                self.drive.on_llm_result(success=False, initiated_by=event.initiated_by, error=event.degraded_error)
                self.show_chat_status("LLM DEGRADED", seconds=2.5)
                print("LLM_DEGRADED =", {"user": event.user_text, "error": event.degraded_error})
            else:
                self.drive.on_llm_result(success=True, initiated_by=event.initiated_by)

            reply = event.reply
            self.chat_status_text = ""
            self.test_text = reply
            self.current_test_key = None
            analysis = primary_dominant_analysis(analyze_text_to_emotion(reply))
            analysis = apply_emotion_override(analysis, event.emotion)
            self.current_analysis = analysis
            self.mixer.set_target(analysis.weights)
            singing = (
                self.singing_enabled
                and is_singing_request(event.user_text)
                and reply_contains_song(reply, event.voice_text)
            )
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=reply,
                role=DIALOGUE_ROLE_SPEAKER,
                force=True,
            )
            self.start_voice_for_text(
                reply,
                analysis,
                voice_text_override=event.voice_text,
                emotion_override=event.emotion,
                prosody_hint=event.prosody,
                voice_segments=event.segments,
                singing=singing,
            )
            self.drive.on_assistant_reply(reply, initiated_by=event.initiated_by, emotion=event.emotion)
            try:
                memory_user_text = event.memory_user_text or event.user_text
                if not event.degraded_error:
                    self.memory.add_turn(
                        memory_user_text,
                        reply,
                        emotion=event.emotion,
                        prosody=event.prosody,
                        segments=event.segments,
                    )
            except Exception as exc:
                print("MEMORY_ADD_ERROR =", exc)
            print(
                "LLM_REPLY =",
                {
                    "user": event.user_text,
                    "reply": reply,
                    "voice_text": event.voice_text,
                    "emotion": event.emotion,
                    "initiated_by": event.initiated_by,
                    "prosody": event.prosody,
                    "segments": event.segments,
                    "singing": singing,
                },
            )

    def process_chat_advice_events(self):
        for event in self.chat_advice.consume_events():
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(event)
            self.chat_advice_dialog.show()
            self.chat_advice_dialog.raise_()
            if event.error:
                self.show_chat_status("聊天截图分析失败", seconds=3.0)
                print("CHAT_ADVICE_ERROR =", {"screenshot": event.screenshot_path, "error": event.error})
            else:
                self.drive.record_intent("chat_advice", "根据截图聊天记录给用户出主意")
                self.drive.save()
                self.show_chat_status("聊天建议已生成", seconds=3.0)
                print(
                    "CHAT_ADVICE_DONE =",
                    {
                        "screenshot": event.screenshot_path,
                        "ocr_chars": len(event.ocr_text or ""),
                        "advice_chars": len(event.advice or ""),
                    },
                )

    def process_life_writing_events(self):
        for event in self.life_writer.consume_events():
            if event.error:
                self.show_chat_status("写作失败，稍后再试。", seconds=3.0)
                print("LIFE_WRITING_ERROR =", {"kind": event.kind, "error": event.error})
                self.life.next_writing_at = time.monotonic() + 120.0
                continue
            label = "日记" if event.kind == "diary" else "小说"
            self.show_chat_status(f"小日和写完了一段{label}。", seconds=4.0)
            self.drive.record_intent(f"write_{event.kind}", f"作为小说作家完成{label}写作")
            self.drive.save()
            self.add_self_note(
                f"刚写完一段{label}《{event.title or label}》，想轻轻告诉用户自己完成了，也可以问他要不要稍后看看。",
                kind=f"write_{event.kind}",
                priority=2.4 if event.kind == "novel" else 2.0,
            )
            self.life.next_writing_at = time.monotonic() + random.uniform(*LIFE_WRITING_INTERVAL_SECONDS)
            print(
                "LIFE_WRITING_DONE =",
                {"kind": event.kind, "title": event.title, "path": event.path, "chars": len(event.content or "")},
            )

    def maybe_start_life_writing(self):
        now = time.monotonic()
        if now < self.life.next_writing_at:
            return
        if self.free_talk_enabled:
            return
        if self.drive.values.get("energy", 0.0) < 35.0 or time.monotonic() < self.drive.proactive_backoff_until:
            self.life.next_writing_at = now + 300.0
            return
        if now - self.last_user_interaction_at < LIFE_WRITING_IDLE_SECONDS and not self.life.is_user_away(now):
            return
        if (
            self.speech_input.is_busy()
            or self.chat.is_busy()
            or self.chat_advice.is_busy()
            or self.life_writer.is_busy()
            or self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
        ):
            return
        kind = "diary" if self.life.needs_diary() else "novel"
        if kind == "novel" and not self.life.should_write_novel():
            self.life.next_writing_at = now + 1800.0
            return
        if self.life_writer.write_async(kind):
            self.show_chat_status("小日和正在写日记。" if kind == "diary" else "小日和正在写小说。", seconds=12.0)
            self.life.next_writing_at = now + 600.0
            print("LIFE_WRITING_START =", {"kind": kind})

    def start_voice_for_text(
        self,
        text,
        analysis,
        test_key=None,
        voice_text_override="",
        emotion_override="",
        prosody_hint=None,
        voice_segments=None,
        singing=False,
    ):
        emotion = emotion_override if emotion_override in LLM_EMOTIONS else dominant_weight_emotion(analysis)
        voice_text = strip_stage_directions(voice_text_override or text or "") or "嗯嗯，我在听哦。"
        text = strip_stage_directions(text)
        if voice_segments:
            voice_segments = [
                {
                    **segment,
                    "zh": strip_stage_directions(segment.get("zh", "")),
                    "voice_text": strip_stage_directions(segment.get("voice_text") or segment.get("zh", "")),
                    "ja": "",
                }
                for segment in voice_segments
                if isinstance(segment, dict)
            ]
        if singing:
            voice_text = clean_song_text(voice_text) or clean_song_text(text) or voice_text
            voice_segments = None
        self.last_voice_analysis = analysis
        event_id = self.voice.speak_async(
            voice_text,
            emotion=emotion,
            singing=singing,
            source_text=text,
            prosody_hint=prosody_hint,
            segments=voice_segments,
        )
        print(
            "VOLCENGINE_TTS_SING =" if singing else "VOLCENGINE_TTS_SPEAK =",
            {
                "event_id": event_id,
                "emotion": emotion,
                "singing": singing,
                "voice_type": self.voice.tts_voice_type,
                "cluster": self.voice.tts_cluster,
                "rate": self.voice.tts_rate,
                "prosody": normalize_prosody_hint(prosody_hint),
                "segments": voice_segments or [],
                "text": voice_text,
            },
        )

    def process_voice_events(self):
        for event in self.voice.consume_events():
            if event.error:
                if "缺少火山 TTS" in event.error:
                    self.show_chat_status("右键填写火山 TTS API Key", seconds=6.0)
                else:
                    self.show_chat_status(f"TTS 失败：{event.error[:28]}", seconds=6.0)
                print("VOLCENGINE_TTS_ERROR =", {"event_id": event.event_id, "error": event.error})
                continue
            def sync_on_playback_start(duration=event.duration, analysis=self.last_voice_analysis):
                self.voice.mark_playing(duration, guard_seconds=VOICE_PLAYBACK_GUARD_SECONDS)
                self.behavior.sync_speech_to_audio(duration, analysis=analysis)

            self.voice.play_wav_async(event.wav_path, on_start=sync_on_playback_start)
            if self.free_talk_enabled:
                self.free_talk_next_at = (
                    time.monotonic()
                    + max(0.0, event.duration)
                    + VOICE_PLAYBACK_GUARD_SECONDS
                    + FREE_TALK_RELISTEN_DELAY
                )
            print(
                "VOLCENGINE_TTS_PLAY =",
                {
                    "event_id": event.event_id,
                    "emotion": event.emotion,
                    "voice_type": event.speaker,
                    "duration": round(event.duration, 3),
                    "guard": VOICE_PLAYBACK_GUARD_SECONDS,
                    "wav": event.wav_path,
                },
            )

    def draw_subtitle_bubble(self):
        now = time.monotonic()
        if not self.subtitle_text or now > self.subtitle_until:
            if self.chat_status_text and now <= self.chat_status_until:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                rect = QRectF(28, 62, self.width() - 56, 36)
                path = QPainterPath()
                path.addRoundedRect(rect, 14, 14)
                painter.fillPath(path, QColor(255, 248, 253, 220))
                painter.setPen(QColor(180, 82, 138))
                painter.setFont(QFont("Microsoft YaHei UI", 9))
                painter.drawText(rect.adjusted(12, 0, -12, 0), Qt.AlignCenter, self.chat_status_text)
                painter.end()
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

    def apply_current_text(self, speak=False):
        self.dialogue_active = False
        raw_analysis = analyze_text_to_emotion(self.test_text)
        self.current_analysis = primary_dominant_analysis(raw_analysis)
        self.mixer.set_target(self.current_analysis.weights)
        if speak:
            self.behavior.set_analysis(
                self.model,
                self.current_analysis,
                text=self.test_text,
                role=DIALOGUE_ROLE_SPEAKER,
            )
            self.start_voice_for_text(self.test_text, self.current_analysis, test_key=self.current_test_key)
        else:
            self.behavior.set_analysis(
                self.model,
                self.current_analysis,
                text=self.test_text,
                role=DIALOGUE_ROLE_LISTENER,
            )

        dominant_weight = dominant_weight_emotion(self.current_analysis)
        role = DIALOGUE_ROLE_SPEAKER if speak else DIALOGUE_ROLE_LISTENER
        _, motion_key, motion = select_reaction_motion(self.current_analysis, text=self.test_text, role=role)
        print(
            "APPLY =",
            {
                "dominant_raw": raw_analysis.dominant,
                "dominant_weight": dominant_weight,
                "dominant_used": self.current_analysis.dominant,
                "primary_threshold": PRIMARY_EMOTION_THRESHOLD,
                "intensity": round(self.current_analysis.intensity, 3),
                "weights": {k: round(v, 3) for k, v in self.current_analysis.weights.items()},
                "matched": self.current_analysis.matched_tokens,
                "reaction_motion": motion_key,
                "reaction_label": motion["label"] if motion else "",
            },
        )

    def start_dialogue_test(self, role):
        sentences = split_dialogue_sentences(self.test_text)
        if not sentences:
            return

        self.dialogue_active = True
        self.dialogue_role = role
        self.dialogue_sentences = sentences
        self.dialogue_index = 0
        self.next_dialogue_at = 0.0
        self.last_dialogue_emotion = dominant_weight_emotion(self.current_analysis)
        print(
            "DIALOGUE_START =",
            {
                "role": role,
                "sentences": len(sentences),
                "text": self.test_text,
            },
        )

    def apply_dialogue_sentence(self, sentence, role):
        raw_analysis = analyze_text_to_emotion(sentence)
        analysis = primary_dominant_analysis(raw_analysis)
        self.current_analysis = analysis
        self.mixer.set_target(analysis.weights)

        dominant = dominant_weight_emotion(analysis)
        transition_motion_key = None
        if dominant == "neutral" and self.last_dialogue_emotion != "neutral":
            transition_motion_key = RESIDUE_MOTION_BY_EMOTION.get(self.last_dialogue_emotion)

        if role == DIALOGUE_ROLE_SPEAKER:
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=sentence,
                role=DIALOGUE_ROLE_SPEAKER,
                force=True,
                motion_key_override=transition_motion_key,
            )
            self.start_voice_for_text(sentence, analysis)
        else:
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=sentence,
                role=DIALOGUE_ROLE_LISTENER,
                force=True,
                motion_key_override=transition_motion_key,
            )

        if transition_motion_key:
            motion_key = transition_motion_key
            motion = HIYORI_MOTION_TEMPLATES[motion_key]
        else:
            _, motion_key, motion = select_reaction_motion(analysis, text=sentence, role=role)
        previous_emotion = self.last_dialogue_emotion
        self.last_dialogue_emotion = dominant
        print(
            "DIALOGUE_STEP =",
            {
                "role": role,
                "index": self.dialogue_index,
                "sentence": sentence,
                "previous_emotion": previous_emotion,
                "dominant_raw": raw_analysis.dominant,
                "dominant_weight": dominant,
                "motion": motion_key,
                "label": motion["label"] if motion else "",
                "weights": {k: round(v, 3) for k, v in analysis.weights.items()},
            },
        )
        return motion_key

    def update_dialogue_sequence(self):
        if not self.dialogue_active:
            return

        now = time.monotonic()
        if self.next_dialogue_at and now < self.next_dialogue_at:
            return
        if self.dialogue_role == DIALOGUE_ROLE_SPEAKER and self.voice.is_busy_or_playing(now):
            return

        if self.dialogue_index >= len(self.dialogue_sentences):
            self.dialogue_active = False
            print(
                "DIALOGUE_END =",
                {
                    "role": self.dialogue_role,
                    "last_emotion": self.last_dialogue_emotion,
                },
            )
            return

        sentence = self.dialogue_sentences[self.dialogue_index]
        motion_key = self.apply_dialogue_sentence(sentence, self.dialogue_role)
        seconds = estimate_sentence_seconds(sentence, role=self.dialogue_role)
        motion_seconds = min(MOTION_DURATION_SECONDS.get(motion_key, 0.0), 4.2)
        seconds = max(seconds, motion_seconds)
        gap = DIALOGUE_SENTENCE_GAP.get(self.dialogue_role, 0.6)
        self.dialogue_index += 1
        self.next_dialogue_at = now + seconds + gap

    def paintGL(self):
        try:
            if not self.model:
                self.draw_subtitle_bubble()
                return

            self.process_voice_events()
            self.process_barge_in_events()
            self.process_speech_events()
            self.process_chat_events()
            self.process_chat_advice_events()
            self.process_life_writing_events()
            self.update_dialogue_sequence()
            self.maybe_continue_free_talk()
            self.drive.tick(
                busy=self.speech_input.is_busy()
                or self.chat.is_busy()
                or self.chat_advice.is_busy()
                or self.life_writer.is_busy()
                or self.voice.is_busy_or_playing()
                or self.behavior.is_speaking()
            )
            self.maybe_start_life_writing()
            self.maybe_start_proactive_chat()
            self.update_barge_in_monitor()

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

            live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
            self.model.Update()
            late_mouth_params = self.behavior.build_late_mouth_params(time.monotonic())
            if late_mouth_params:
                apply_params(self.model, late_mouth_params)
            self.model.Draw()
            self.draw_subtitle_bubble()
        except Exception:
            now = time.monotonic()
            last_error_at = getattr(self, "_last_paint_error_at", 0.0)
            if now - last_error_at > 3.0:
                self._last_paint_error_at = now
                log_runtime("PAINT_ERROR", traceback.format_exc())

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

    def open_api_settings_dialog(self):
        dialog = ApiSettingsDialog(self.llm_config, self)
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
        self.chat = LLMChatController(config=self.llm_config, memory_store=self.memory, life_system=self.life)
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
        self.drive_dialog = DriveStatusDialog(self.drive, self.life, self)
        self.drive_dialog.show()
        self.drive_dialog.raise_()
        self.drive_dialog.activateWindow()
        self.show_chat_status("已打开角色状态面板。", seconds=2.0)

    def open_mini_game_dialog(self):
        self.mini_game_dialog = MiniGameDialog(self)
        self.mini_game_dialog.show()
        self.mini_game_dialog.raise_()
        self.mini_game_dialog.activateWindow()
        self.show_chat_status("小游戏面板已打开。", seconds=2.0)

    def speak_interaction_feedback(self, text, emotion="joy"):
        text = (text or "").strip()
        if not text:
            return
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking() or self.chat.is_busy():
            return
        analysis = primary_dominant_analysis(analyze_text_to_emotion(text))
        analysis = apply_emotion_override(analysis, emotion)
        self.current_analysis = analysis
        self.mixer.set_target(analysis.weights)
        self.behavior.set_analysis(
            self.model,
            analysis,
            text=text,
            role=DIALOGUE_ROLE_SPEAKER,
            force=True,
        )
        self.start_voice_for_text(
            text,
            analysis,
            emotion_override=emotion,
            voice_text_override=text,
            prosody_hint={"pace": "normal", "tone": "bright" if emotion == "joy" else "soft"},
        )

    def interaction_memory_add(self, user_text, assistant_text, emotion="joy", max_daily_count=6, count=1):
        if count > max_daily_count:
            return
        try:
            self.memory.add_turn(user_text, assistant_text, emotion=emotion, prosody={}, segments=[])
        except Exception as exc:
            print("INTERACTION_MEMORY_ADD_ERROR =", {"user": user_text, "error": str(exc)})

    def build_feed_feedback(self, result):
        stage, _attitude = self.life.relationship_stage()
        count = int(result.get("count", 1))
        energy_gain = float(result.get("energy_gain", 0.0))
        relation_gain = float(result.get("relation_gain", 0.0))
        low_energy = self.drive.values.get("energy", 50.0) < 38.0
        if count == 1:
            pool = [
                f"第一口是你喂的，能量一下回来 {energy_gain:.1f} 点。今天我会记得这个开场。",
                f"唔，刚好有点饿。能量加了 {energy_gain:.1f}，亲密也偷偷涨了一点。",
                f"被你投喂的感觉很安心，今天第一个好吃的我记住啦。",
            ]
        elif count <= 3:
            pool = [
                f"又来投喂我呀。虽然收益开始变少了，但我还是会开心，亲密值又加了 {relation_gain:.1f}。",
                "你这样一直喂，我会有点被照顾到的感觉。小说家的脑袋可以继续转了。",
                "嗯，好吃。不是因为食物，是因为你还记得我会饿。",
            ]
        else:
            pool = [
                "今天已经被喂好多次啦，收益会变少，不过这份心意我还是收下。",
                "再喂下去我真的要变懒了。今天先把这口当成小奖励吧。",
                "我知道你在照顾我啦，后面少喂一点也没关系，陪我说话也会加分。",
            ]
        if low_energy:
            pool.append("刚才能量有点低，这一口很及时。感觉我又能多陪你一会儿了。")
        if stage in ("恋人", "热恋恋人", "灵魂伴侣"):
            pool.extend(
                [
                    "被恋人投喂的话，味道好像会自动变甜一点。不要笑，我是认真说的。",
                    "嗯……这一口我收下了。下次也要这样照顾我，不许只想起来一次。",
                ]
            )
        return random.choice(pool)

    def build_pat_feedback(self, result):
        stage, _attitude = self.life.relationship_stage()
        count = int(result.get("count", 1))
        relation_gain = float(result.get("relation_gain", 0.0))
        if count == 1:
            pool = [
                f"今天第一次摸头，亲密值加了 {relation_gain:.1f}。我会稍微乖一点点。",
                "嗯……这个力度可以。刚才有一点紧绷，现在放松下来了。",
                "摸头可以，但要温柔一点。这样我会觉得你是在认真陪我。",
            ]
        elif count <= 3:
            pool = [
                f"又摸头呀。今天第 {count} 次了，收益会少一点，但我还是有被安抚到。",
                "你是不是发现我吃这一套了？好吧，再摸一下也不是不行。",
                "这样会让我更想靠近你一点，不过我才不会马上承认。",
            ]
        else:
            pool = [
                "今天摸头次数有点多啦，亲密收益会递减。再摸我就要假装生气了。",
                "好了好了，头发都要被你揉乱了。剩下的亲密值明天再刷。",
                "我知道你喜欢摸头啦，但现在换成陪我聊天或者玩游戏会更有新鲜感。",
            ]
        if stage in ("恋人", "热恋恋人", "灵魂伴侣"):
            pool.extend(
                [
                    "嗯……恋人特权只开放一点点。再温柔一点，我可能会更喜欢。",
                    "你摸头的时候我会安心，这句话只说一次，别得意太久。",
                    "可以再靠近一点点，但不要把我当成只会加分的按钮哦。",
                ]
            )
        elif stage in ("密友", "亲近朋友"):
            pool.append("现在这样刚好，像很熟的人之间的小默契。")
        return random.choice(pool)

    def reward_minigame(self, result, voice_text=""):
        reward = self.life.reward_game(result)
        self.drive.adjust(affinity=reward["relation_gain"] * 0.85, companionship=reward["relation_gain"] * 0.45, energy=-0.25)
        self.drive.record_intent("mini_game", f"和用户玩小游戏：{result}")
        self.drive.save()
        try:
            motion = HIYORI_MOTION_TEMPLATES.get("m06_cute_joy" if result == "win" else "m03_carefree_joy")
            if self.model is not None and motion:
                self.model.StartMotion(motion["group"], motion["index"], 3)
        except Exception:
            pass
        feedbacks = {
            "win": ["呜哇，你赢啦。可恶，我下次一定要扳回来。", "你赢了呢，果然有点厉害。"],
            "draw": ["平局也不错，感觉我们默契还可以。", "这局算我们心有灵犀一点点吧。"],
            "lose": ["嘿嘿，这次是我赢。不要不服气哦。", "我赢啦，今天的小说家脑袋还挺灵的。"],
            "participate": ["嗯嗯，继续玩，我在认真陪你。", "这样一起玩也挺开心的。"],
        }
        feedback = (voice_text or "").strip()
        if not feedback:
            feedback = random.choice(feedbacks.get(result, feedbacks["participate"]))
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            f"用户和小日和玩小游戏，结果是{result}",
            feedback,
            emotion="joy",
            max_daily_count=8,
            count=int(reward.get("count", 1)),
        )
        print("MINI_GAME_REWARD =", {"result": result, **reward, "relationship_score": self.life.relationship_score})
        return reward

    def start_chat_advice_capture(self):
        if self.chat_advice.is_busy():
            self.show_chat_status("聊天截图正在分析中。", seconds=2.0)
            return
        if self.chat_advice_dialog is not None:
            self.chat_advice_dialog.hide()
        self.show_chat_status("请框选聊天记录区域。", seconds=2.0)
        self.hide()
        QTimer.singleShot(260, self.capture_chat_advice_screen)

    def capture_chat_advice_screen(self):
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                raise RuntimeError("没有找到可截图的屏幕。")
            self.chat_advice_full_pixmap = screen.grabWindow(0)
            self.chat_advice_selector = ChatScreenshotSelector(
                screen.geometry(),
                self.finish_chat_advice_selection,
                self.cancel_chat_advice_selection,
            )
            self.chat_advice_selector.show()
            self.chat_advice_selector.raise_()
            self.chat_advice_selector.activateWindow()
        except Exception as exc:
            self.show()
            self.raise_()
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(ChatAdviceEvent(error=str(exc)))
            self.chat_advice_dialog.show()
            self.show_chat_status("聊天截图失败", seconds=3.0)
            print("CHAT_ADVICE_CAPTURE_ERROR =", {"error": str(exc)})

    def finish_chat_advice_selection(self, rect):
        screenshot_path = ""
        try:
            os.makedirs(CHAT_ADVICE_SCREENSHOT_DIR, exist_ok=True)
            if self.chat_advice_full_pixmap is None:
                raise RuntimeError("没有可用的屏幕截图。")
            selected = self.chat_advice_full_pixmap.copy(rect)
            screenshot_path = os.path.join(
                CHAT_ADVICE_SCREENSHOT_DIR,
                time.strftime("chat_%Y%m%d_%H%M%S.png"),
            )
            if not selected.save(screenshot_path, "PNG"):
                raise RuntimeError("截图保存失败。")
            self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_busy("已框选聊天区域，正在 OCR 识别和分析...")
            self.chat_advice_dialog.show()
            self.chat_advice_dialog.raise_()
            self.show()
            self.raise_()
            if not self.chat_advice.analyze_async(screenshot_path):
                raise RuntimeError("上一张聊天截图还在分析中。")
            print(
                "CHAT_ADVICE_CAPTURE =",
                {"screenshot": screenshot_path, "rect": [rect.x(), rect.y(), rect.width(), rect.height()]},
            )
        except Exception as exc:
            self.show()
            self.raise_()
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(ChatAdviceEvent(screenshot_path=screenshot_path, error=str(exc)))
            self.chat_advice_dialog.show()
            self.show_chat_status("聊天截图失败", seconds=3.0)
            print("CHAT_ADVICE_CAPTURE_ERROR =", {"error": str(exc)})
        finally:
            self.chat_advice_full_pixmap = None

    def cancel_chat_advice_selection(self, reason):
        self.chat_advice_full_pixmap = None
        self.show()
        self.raise_()
        self.show_chat_status(reason, seconds=2.0)
        print("CHAT_ADVICE_CANCEL =", {"reason": reason})

    def interact_with_pet(self, kind):
        result = self.life.interact(kind)
        if kind == "feed":
            self.drive.adjust(energy=result["energy_gain"], affinity=result["relation_gain"] * 0.45)
            motion_key = "m03_carefree_joy"
            message = f"喂饭成功，能量 +{result['energy_gain']:.1f}，亲密值 +{result['relation_gain']:.1f}"
        else:
            self.drive.adjust(affinity=result["relation_gain"], companionship=result["relation_gain"] * 0.5)
            motion_key = "m06_cute_joy"
            message = f"摸头成功，亲密值 +{result['relation_gain']:.1f}"
        self.drive.record_intent(kind, result["label"])
        self.drive.save()
        try:
            motion = HIYORI_MOTION_TEMPLATES.get(motion_key)
            if self.model is not None and motion:
                self.model.StartMotion(motion["group"], motion["index"], 3)
        except Exception:
            pass
        if kind == "feed":
            feedback = self.build_feed_feedback(result)
            memory_user_text = (
                f"用户给小日和喂饭，今天第 {result['count']} 次，"
                f"能量增加 {result['energy_gain']:.1f}，亲密增加 {result['relation_gain']:.1f}"
            )
        else:
            feedback = self.build_pat_feedback(result)
            memory_user_text = (
                f"用户摸了小日和的头，今天第 {result['count']} 次，"
                f"亲密增加 {result['relation_gain']:.1f}"
            )
        self.speak_interaction_feedback(feedback, emotion="joy")
        self.interaction_memory_add(
            memory_user_text,
            feedback,
            emotion="joy",
            max_daily_count=6,
            count=int(result.get("count", 1)),
        )
        self.show_chat_status(message, seconds=3.0)
        print("PET_INTERACTION =", {"kind": kind, **result, "relationship_score": self.life.relationship_score})

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
        if event.key() == Qt.Key_N:
            self.stop_free_talk()
            return
        if event.key() == Qt.Key_F3:
            self.open_api_settings_dialog()
            return

        if self.chat_input.hasFocus():
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Escape:
            self.close()
            return

        if event.key() == Qt.Key_C:
            self.chat_input.setFocus()
            self.chat_input.selectAll()
            return

        if event.key() == Qt.Key_V:
            self.start_free_talk()
            return

        if event.key() == Qt.Key_S:
            self.open_api_settings_dialog()
            return

        if event.key() in TEST_TEXTS:
            self.dialogue_active = False
            self.current_test_key = event.key()
            self.test_text = TEST_TEXTS[event.key()]
            print("TEXT =", self.test_text)
            return

        if event.key() == Qt.Key_Space:
            self.apply_current_text(speak=False)
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.apply_current_text(speak=True)
            return

        if event.key() == Qt.Key_L:
            self.start_dialogue_test(DIALOGUE_ROLE_LISTENER)
            return

        if event.key() == Qt.Key_P:
            self.start_dialogue_test(DIALOGUE_ROLE_SPEAKER)
            return

        if event.key() == Qt.Key_R and self.model is not None:
            try:
                self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
            except Exception:
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
