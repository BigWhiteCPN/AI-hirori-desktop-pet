import base64
import json
import math
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass

from persona_pet.memory import compact_text, contains_any, normalize_prosody_hint, strip_stage_directions

DIALOGUE_ROLE_LISTENER = "listener"
DIALOGUE_ROLE_SPEAKER = "speaker"
LLM_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
PRIMARY_EMOTION_THRESHOLD = 0.30
EMOTION_ORDER = ("fear", "joy", "sadness", "anger", "surprise")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "voice")
_runtime_logger = None


def log_runtime(*parts):
    if _runtime_logger is None:
        return
    try:
        _runtime_logger(*parts)
    except Exception:
        pass


def configure_voice_runtime(base_dir=None, voice_output_dir=None, voicevox_engine_exe=None, logger=None):
    global BASE_DIR, VOICE_OUTPUT_DIR, VOICEVOX_ENGINE_EXE, _runtime_logger
    if base_dir:
        BASE_DIR = str(base_dir)
    if voice_output_dir:
        VOICE_OUTPUT_DIR = str(voice_output_dir)
    if voicevox_engine_exe:
        VOICEVOX_ENGINE_EXE = str(voicevox_engine_exe)
    if logger is not None:
        _runtime_logger = logger


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def dominant_weight_emotion(analysis):
    weights = getattr(analysis, "weights", {}) or {}
    emotion_weights = {emotion: weights.get(emotion, 0.0) for emotion in EMOTION_ORDER}
    dominant = max(emotion_weights, key=emotion_weights.get)
    if emotion_weights[dominant] < PRIMARY_EMOTION_THRESHOLD:
        return "neutral"
    return dominant

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


VOICEVOX_LINES_BY_EMOTION = {
    "joy": "えへへっ！すっごくうれしいのだー！",
    "sadness": "うう……ちょっとかなしいのだ……。",
    "anger": "むむっ！ちょっと怒ってるのだ！",
    "fear": "ひゃあっ……こ、こわいのだ……！",
    "surprise": "わあっ！？びっくりしたのだー！",
    "neutral": "うんうん、そうなのだ。",
}
TEST_VOICEVOX_LINES = {
    49: "ひゃあっ……こ、ここは危ないのだ……！",
    50: "えへへっ！今日はすっごく楽しいのだー！",
    51: "うう……ちょっと悲しくなっちゃったのだ……。",
    52: "むむっ！これはさすがに怒っちゃうのだ！",
    53: "わあっ！？びっくりしたのだー！",
    54: "うんうん、今日はのんびりできそうなのだ。",
    55: "むむっ……ちょっと怒ったけど、もう大丈夫なのだ。",
    56: "うん……少し考えてから、ゆっくり話すのだ。",
}
VOICEVOX_STOCK_LINES = set(VOICEVOX_LINES_BY_EMOTION.values())


def split_voicevox_label(label):
    parts = [part.strip() for part in str(label or "").split("/", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0] if parts else ""







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
    def __init__(self, config=None, base_dir=None, voice_output_dir=None, voicevox_engine_exe=None, logger=None):
        configure_voice_runtime(
            base_dir=base_dir,
            voice_output_dir=voice_output_dir,
            voicevox_engine_exe=voicevox_engine_exe,
            logger=logger,
        )
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



