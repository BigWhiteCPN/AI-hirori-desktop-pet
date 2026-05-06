import json
import math
import os
import random
import re
import time
from dataclasses import dataclass, field

import live2d.v3 as live2d
from PyQt5.QtCore import Qt
from live2d.v3.params import StandardParams

from persona_pet.speech import normalize_speech_piece

DIALOGUE_ROLE_LISTENER = "listener"
DIALOGUE_ROLE_SPEAKER = "speaker"
IDLE_MOTION_INTERVAL = (3.0, 5.6)
EMOTION_MOTION_COOLDOWN = 0.9
PRIMARY_EMOTION_THRESHOLD = 0.30
LLM_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
SINGING_MAX_TEXT_CHARS = 72
MOUTH_ENABLE_FOR_SPEAKER = True
MOUTH_OPEN_SCALE = 0.92
MOUTH_FORM_SCALE = 0.14

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


def llm_emotion_from_text(text):
    return dominant_weight_emotion(primary_dominant_analysis(analyze_text_to_emotion(text)))



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
















































