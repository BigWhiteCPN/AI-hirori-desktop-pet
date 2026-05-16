"""Memory storage, retrieval, and text cleanup for the desktop pet."""

import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid

from persona_pet.error_reporter import report_exception
from persona_pet.lexicon import (
    HARD_BOUNDARY_REPLY_TERMS,
    INTIMATE_BOUNDARY_ACTION_TERMS,
    INTIMATE_BOUNDARY_BODY_TERMS,
    INTIMATE_BOUNDARY_SOFT_TERMS,
)

LLM_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
STRUCTURED_REPLY_MARKERS = ('"zh"', '"emotion"', '"segments"', '"prosody"', '"voice_text"')
DEFAULT_MEMORY_MAX_TEXT_CHARS = 420
DEFAULT_MEMORY_MIN_SIGNAL_CHARS = 4
DEFAULT_MEMORY_SHORT_TERM_LIMIT = 300
LAST_ASSOCIATION_META_KEY = "last_association"
EXPERIENCE_MEMORY_META_KEY = "experience_memory"
SEMANTIC_MEMORY_META_KEY = "semantic_memory"
CORE_MEMORY_META_KEY = "core_memory"
FTS_TOKENIZER_META_KEY = "turns_fts_tokenizer"
EMBEDDING_PROVIDER_META_KEY = "embedding_provider"
DEFAULT_DENSE_EMBEDDING_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "third_party",
    "embedding_model",
)
RELATION_STATUS_RANK = {
    "朋友": 1,
    "亲近朋友": 2,
    "好朋友": 2,
    "闺蜜": 3,
    "亲密闺蜜": 4,
    "灵魂闺蜜": 5,
    "密友": 3,
    "暧昧中的朋友": 4,
    "重要的人": 4,
    "恋人": 4,
    "热恋恋人": 5,
    "未婚夫妻": 6,
    "灵魂伴侣": 7,
}

BRAIN_MODULES = {
    "relation": {
        "label": "关系脑区",
        "detail": "用户、桌宠、社交关系、偏好和亲密距离。",
        "types": {"角色"},
        "categories": {"社交", "偏好"},
    },
    "emotion": {
        "label": "情绪脑区",
        "detail": "情绪、心情、被冷落后的感受和语气倾向。",
        "types": {"情绪", "心情"},
        "categories": {"情绪", "心理状态"},
    },
    "event": {
        "label": "事件脑区",
        "detail": "发生过的事、计划、行为和时间线。",
        "types": {"记忆"},
        "categories": {"事件", "行为"},
    },
    "needs": {
        "label": "需求脑区",
        "detail": "身体、生理需求、饮食、健康和照顾线索。",
        "types": {"症状"},
        "categories": {"医疗健康", "饮食"},
    },
    "creation": {
        "label": "创作脑区",
        "detail": "日记、小说、自我表达和长期创作目标。",
        "types": set(),
        "categories": {"写作", "创作", "自我反思"},
    },
    "reflection": {
        "label": "反思脑区",
        "detail": "她把旧记忆重新解释后形成的新想法。",
        "types": {"思考"},
        "categories": {"被反思的记忆"},
    },
    "concept": {
        "label": "概念脑区",
        "detail": "类别、关键词和还没归档的概念节点。",
        "types": {"类别"},
        "categories": {"未归档", "日常对话"},
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
    "anxious": "urgent",
}

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
    if len(user_text) > DEFAULT_MEMORY_MAX_TEXT_CHARS:
        user_text = user_text[:DEFAULT_MEMORY_MAX_TEXT_CHARS].rstrip() + "..."
    if len(assistant_text) > DEFAULT_MEMORY_MAX_TEXT_CHARS:
        assistant_text = assistant_text[:DEFAULT_MEMORY_MAX_TEXT_CHARS].rstrip() + "..."
    compact = compact_text(f"{user_text}{assistant_text}")
    report = {
        "keep": True,
        "reason": "ok",
        "quality": 1.0,
        "user": user_text,
        "assistant": assistant_text,
    }
    if len(compact) < DEFAULT_MEMORY_MIN_SIGNAL_CHARS:
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
    third_person_intro = re.match(r"^\s*(她|苏念|小日和)[^“”「」\"']{0,120}[：:]\s*[“「\"']?(.+?)[”」\"']?\s*$", text, flags=re.S)
    if third_person_intro:
        text = third_person_intro.group(2)
    third_person_quote = re.match(r"^\s*(她|苏念|小日和)[^“”「」\"']{0,120}(?:说|问|回答|开口|呢喃|笑道|说道)[^“”「」\"']{0,40}[“「\"'](.+?)[”」\"']\s*$", text, flags=re.S)
    if third_person_quote:
        text = third_person_quote.group(2)
    patterns = (
        r"\*[^*]{0,80}\*",
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
    text = re.sub(r"^\s*(苏念|小日和|她)\s*[：:]\s*", "", text)
    text = re.sub(r"^\s*(她|苏念|小日和)[^。！？!?]{0,80}(?:说|问|回答|开口|呢喃|笑道|说道)\s*[：:，,]\s*", "", text)
    text = re.sub(r"\s+([。！？!?、，,.])", r"\1", text)
    text = re.sub(r"([「『])\s+", r"\1", text)
    text = re.sub(r"\s+([」』])", r"\1", text)
    return text.strip()

ORAL_NARRATION_MARKERS = (
    "声音软下来",
    "声音低下来",
    "声音轻下来",
    "语气软",
    "语气低",
    "语气放轻",
    "语气温柔",
    "眼睛",
    "眼神",
    "脸红",
    "脸颊",
    "耳朵红",
    "尾音",
    "轻轻笑",
    "笑了笑",
    "蹭了蹭",
    "蹭蹭",
    "伸手",
    "抬手",
    "低头",
    "抬头",
    "歪头",
    "眨眼",
    "眨了眨",
    "点点头",
    "点了点头",
    "摇摇头",
    "摇了摇头",
    "凑近",
    "靠近",
    "贴近",
    "抱住",
    "握住",
    "摸了摸",
    "揉了揉",
    "缩了缩",
    "躲开",
    "退开",
    "眉毛",
    "眉头",
    "嘴角",
    "抿嘴",
    "抿起来",
    "皱眉",
    "压低",
    "嘴巴",
    "撅嘴",
    "嘟嘴",
    "咧嘴",
    "龇牙",
    "瞪眼",
    "翻白眼",
)

ORAL_NARRATION_STARTS = (
    "我轻轻",
    "我慢慢",
    "我悄悄",
    "我伸手",
    "我抬手",
    "我低头",
    "我抬头",
    "我歪头",
    "我眨",
    "我点头",
    "我摇头",
    "我靠近",
    "我凑近",
    "我贴近",
    "我蹭",
    "我抱住",
    "我握住",
    "我抓住",
    "我摸了摸",
    "我揉了揉",
    "我缩",
    "我躲",
    "我退",
)


def looks_like_oral_narration_sentence(sentence):
    compact = compact_text(sentence)
    if not compact:
        return True
    if any(compact.startswith(prefix) for prefix in ORAL_NARRATION_STARTS):
        return True
    marker_hits = sum(1 for marker in ORAL_NARRATION_MARKERS if marker in compact)
    if marker_hits >= 2:
        return True
    if marker_hits and any(token in compact for token in ("下来", "起来", "了一下", "了蹭", "了摸", "了揉")):
        return True
    # Catch "给你看看/给你看看...：...description..." patterns
    if re.search(r"给你看看.{0,10}[：:].{2,}", compact) and marker_hits:
        return True
    return False


def clean_spoken_reply_text(text):
    """Keep only words the character would actually say aloud."""
    text = strip_stage_directions(text)
    if not text:
        return ""
    parts = re.findall(r"[^。！？!?\n]+[。！？!?]*", text)
    kept = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if looks_like_oral_narration_sentence(part):
            continue
        kept.append(part)
    cleaned = "".join(kept).strip()
    return cleaned or text


MEMORY_CATEGORY_KEYWORDS = {
    "医疗健康": ("症状", "疼", "痛", "咳嗽", "发烧", "药", "医院", "医生", "过敏", "睡眠", "头晕", "难受", "不舒服"),
    "饮食": ("吃", "喝", "饭", "水", "零食", "奶", "水果", "肉", "鱼", "营养", "食欲", "喂"),
    "行为": ("训练", "习惯", "叫", "咬", "抓", "跑", "玩", "睡", "洗澡", "散步", "上厕所"),
    "社交": ("朋友", "家人", "同学", "同事", "聊天", "见面", "关系", "喜欢", "讨厌", "陪"),
    "用品": ("玩具", "猫砂", "狗粮", "笼子", "窝", "项圈", "牵引绳", "碗", "垫子", "用品"),
    "事件": ("今天", "昨天", "明天", "刚才", "发生", "计划", "提醒", "约", "开始", "结束"),
    "偏好": ("喜欢", "不喜欢", "想要", "希望", "偏好", "最爱", "讨厌", "习惯"),
    "情绪": ("开心", "难过", "生气", "害怕", "焦虑", "紧张", "惊讶", "孤单", "舒服"),
    "阅读": ("读", "书", "文章", "故事", "小说", "感想", "阅读", "作者", "写"),
}

MEMORY_RELATION_KEYWORDS = {
    "触发": ("因为", "导致", "一", "就", "触发", "引起"),
    "建议": ("建议", "可以", "最好", "应该", "记得", "试试", "避免"),
    "因果": ("所以", "因此", "导致", "原因", "结果"),
    "相似": ("像", "类似", "一样", "也", "同样"),
}

MEMORY_RECALL_HINTS = (
    "记得", "还记得", "想起来", "想起", "忘了", "忘记", "昨天", "前天", "刚才",
    "上次", "那次", "那件事", "这件事", "那个", "这个", "当时", "之前", "后来",
    "发生什么", "发生过", "有没有", "是不是", "为什么说没",
)

MEMORY_STOP_TERMS = {
    "我", "你", "她", "他", "它", "我们", "你们", "他们", "这个", "那个", "这些", "那些",
    "现在", "就是", "什么", "怎么", "为什么", "是不是", "有没有", "可以", "应该", "感觉",
    "事情", "东西", "问题", "一下", "一个", "这个事", "那个事", "真的", "还是", "如果",
}

MEMORY_CONCEPT_CLUES = {
    "gift": ("送", "礼物", "给你", "收到", "收下", "买给", "花束", "新书", "书", "东西"),
    "book": ("书", "新书", "小说", "阅读", "纸质书", "书签"),
    "food": ("吃", "饭", "喂", "投喂", "牛排", "面包", "饭团", "饿", "饱"),
    "drink": ("喝", "水", "口渴", "不渴", "果汁", "咖啡"),
    "money": ("金币", "钱", "余额", "钱包", "买", "花费", "收入"),
    "inventory": ("背包", "物品", "库存", "拥有", "买了什么"),
    "time": ("昨天", "今天", "前天", "刚才", "上次", "那次", "当时", "之前", "后来"),
    "relationship": ("朋友", "闺蜜", "喜欢", "在乎", "关系", "陪", "想你", "吃醋"),
    "promise": ("答应", "约定", "说好", "承诺", "提醒", "记得"),
    "body": ("身体", "生理期", "经期", "身高", "体重", "年龄", "生日", "难受"),
}

EVENT_ACTION_CLUES = {
    "give": ("送", "给", "买给", "赠", "礼物", "收到", "收下"),
    "buy": ("买", "购买", "花费"),
    "use": ("用", "使用", "打开", "放进", "拿出"),
    "eat": ("吃", "喂", "投喂", "饭"),
    "drink": ("喝", "饮", "水"),
    "ask": ("问", "聊", "说", "告诉", "提到"),
    "promise": ("答应", "约定", "说好", "提醒"),
}

EVENT_OBJECT_CLUES = {
    "book": ("书", "新书", "小说", "纸质书", "书签"),
    "flower": ("花", "花束"),
    "food": ("饭", "面包", "饭团", "牛排", "零食", "水果"),
    "drink": ("水", "果汁", "咖啡"),
    "money": ("金币", "钱", "余额"),
    "backpack": ("背包", "物品", "库存"),
}

EVENT_TIME_CLUES = ("昨天", "今天", "前天", "刚才", "上次", "那次", "当时", "之前", "后来", "明天")

def memory_now_label():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def memory_clean_label(text, limit=30):
    text = re.sub(r"\s+", "", str(text or ""))
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text[:limit]

class PersonaMemoryStore:
    def __init__(self, path, db_path, short_term_limit=DEFAULT_MEMORY_SHORT_TERM_LIMIT, logger=None):
        self.path = path
        self.db_path = db_path
        self.short_term_limit = int(short_term_limit)
        self.log_runtime = logger or (lambda *parts: None)
        self.lock = threading.Lock()
        self.embedding_provider = str(os.environ.get("PERSONA_EMBEDDING_PROVIDER") or "auto").strip().lower()
        self.embedding_model_path = str(os.environ.get("PERSONA_EMBEDDING_MODEL") or DEFAULT_DENSE_EMBEDDING_MODEL_DIR).strip()
        self.embedding_allow_remote = str(os.environ.get("PERSONA_EMBEDDING_ALLOW_REMOTE") or "").strip().lower() in ("1", "true", "yes", "on")
        self._dense_embedding_model = None
        self._dense_embedding_failed = False
        self.data = self.load()

    def load(self):
        if os.path.exists(self.db_path):
            try:
                data = self.load_db()
                if not self.is_empty_memory(data) or not os.path.exists(self.path):
                    self.data = data
                    repaired_timestamps = self.repair_memory_timestamps()
                    edge_count_before = len(self.data.get("graph", {}).get("edges", []))
                    self.repair_graph_connectivity()
                    if repaired_timestamps or len(self.data.get("graph", {}).get("edges", [])) > edge_count_before:
                        try:
                            self.save()
                        except Exception as exc:
                            report_exception(logger=self.log_runtime, component="memory", operation="repair_save_after_db_load", exc=exc)
                    data = self.data
                    return data
            except Exception as exc:
                self.log_runtime("MEMORY_DB_LOAD_ERROR", exc)
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
                self.log_runtime("MEMORY_DB_MIGRATE_ERROR", exc)
            self.data = base
            repaired_timestamps = self.repair_memory_timestamps()
            self.repair_graph_connectivity()
            if repaired_timestamps:
                try:
                    self.save()
                except Exception as exc:
                    report_exception(logger=self.log_runtime, component="memory", operation="repair_save_after_json_load", exc=exc)
            base = self.data
            return base
        except Exception as exc:
            self.log_runtime("MEMORY_LOAD_ERROR", exc)
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
            "semantic_memory": {
                "facts": [],
                "last_updated": "",
            },
            "core_memory": {
                "profile": {},
                "stable_facts": [],
                "last_updated": "",
            },
            "graph": {"nodes": {}, "edges": []},
        }

    def repair_memory_timestamps(self):
        """Ensure every short-term memory has an explicit timestamp field.

        For old rows that did not store time, use a stable migration timestamp and
        mark it as repaired so prompts do not treat it as a precise event time.
        """
        repaired = 0
        migration_time = memory_now_label()
        items = self.data.get("short_terms", [])
        if not isinstance(items, list):
            self.data["short_terms"] = []
            return 0
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            created_at = str(item.get("created_at") or "").strip()
            if not created_at:
                created_at = migration_time
                item["created_at"] = created_at
                item["timestamp_source"] = "repaired_unknown"
                item["timestamp_note"] = "旧记忆缺少原始时间；这是迁移补写时间，不代表真实发生时间。"
                repaired += 1
            item.setdefault("time_label", created_at)
            if not item.get("timeline_text"):
                user = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "")))
                assistant = collapse_repeated_memory_text(strip_stage_directions(item.get("assistant", "")))
                facts = item.get("facts") if isinstance(item.get("facts"), list) else []
                if user or assistant:
                    item["timeline_text"] = f"[{created_at}] 用户：{user} / 苏念：{assistant}"
                elif facts:
                    item["timeline_text"] = f"[{created_at}] 事实：{'; '.join(str(f) for f in facts[:3])}"
                else:
                    item["timeline_text"] = f"[{created_at}] 旧记忆条目 {index + 1}"
                repaired += 1
        return repaired

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
            CREATE TABLE IF NOT EXISTS embedding_cache (
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                created_at TEXT,
                PRIMARY KEY (provider, model, text_hash)
            );
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                    id UNINDEXED,
                    user,
                    assistant,
                    categories,
                    terms,
                    tokenize='trigram'
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (FTS_TOKENIZER_META_KEY, "trigram"),
            )
        except sqlite3.OperationalError:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                    id UNINDEXED,
                    user,
                    assistant,
                    categories,
                    terms
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (FTS_TOKENIZER_META_KEY, "unicode61"),
            )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (
                EMBEDDING_PROVIDER_META_KEY,
                self.embedding_provider if self.can_try_dense_embedding() else "ngram",
            ),
        )
        try:
            conn.execute("ALTER TABLE turns ADD COLUMN extra_json TEXT")
        except sqlite3.OperationalError:
            pass
        self.ensure_fts_index(conn)

    def json_text(self, value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def parse_json_text(self, value, fallback):
        try:
            return json.loads(value or "")
        except Exception:
            return copy.deepcopy(fallback)

    def fts_text_fields(self, item):
        categories = item.get("categories", [])
        terms = item.get("terms", [])
        if isinstance(categories, (list, tuple)):
            categories = " ".join(str(value) for value in categories)
        if isinstance(terms, (list, tuple)):
            terms = " ".join(str(value) for value in terms)
        return (
            item.get("id") or str(uuid.uuid4()),
            collapse_repeated_memory_text(strip_stage_directions(item.get("user", ""))),
            collapse_repeated_memory_text(strip_stage_directions(item.get("assistant", ""))),
            str(categories or ""),
            str(terms or ""),
        )

    def upsert_fts_turns(self, conn, items):
        rows = []
        ids = []
        for item in items:
            row = self.fts_text_fields(item)
            ids.append(row[0])
            rows.append(row)
        if not rows:
            return
        conn.executemany("DELETE FROM turns_fts WHERE id = ?", [(item_id,) for item_id in ids])
        conn.executemany(
            "INSERT INTO turns_fts(id, user, assistant, categories, terms) VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    def ensure_fts_index(self, conn):
        try:
            turn_count = int(conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0] or 0)
            fts_count = int(conn.execute("SELECT COUNT(DISTINCT id) FROM turns_fts").fetchone()[0] or 0)
        except sqlite3.OperationalError:
            return
        if turn_count <= 0 or fts_count >= turn_count:
            return
        rows = conn.execute(
            "SELECT id, user, assistant, categories_json, terms_json FROM turns"
        ).fetchall()
        items = []
        for row in rows:
            items.append(
                {
                    "id": row[0],
                    "user": row[1] or "",
                    "assistant": row[2] or "",
                    "categories": self.parse_json_text(row[3], []),
                    "terms": self.parse_json_text(row[4], []),
                }
            )
        conn.execute("DELETE FROM turns_fts")
        self.upsert_fts_turns(conn, items)

    def load_db(self):
        data = self.empty_data()
        with self.connect_db() as conn:
            self.init_db(conn)
            for key, value in conn.execute("SELECT key, value FROM meta"):
                if key == "long_term":
                    data["long_term"] = self.parse_json_text(value, data["long_term"])
                elif key == SEMANTIC_MEMORY_META_KEY:
                    data["semantic_memory"] = self.parse_json_text(value, data["semantic_memory"])
                elif key == CORE_MEMORY_META_KEY:
                    data["core_memory"] = self.parse_json_text(value, data["core_memory"])
                elif key == "version":
                    try:
                        data["version"] = int(value)
                    except Exception:
                        data["version"] = 2

            turns = []
            rows = conn.execute(
                """
                SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                       prosody_json, segments_json, embedding_json, extra_json
                FROM turns
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.short_term_limit,),
            ).fetchall()
            for row in reversed(rows):
                item = {
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
                extra = self.parse_json_text(row[10], {})
                if isinstance(extra, dict):
                    item.update(extra)
                turns.append(item)
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
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (SEMANTIC_MEMORY_META_KEY, self.json_text(data.get("semantic_memory", {}))),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (CORE_MEMORY_META_KEY, self.json_text(data.get("core_memory", {}))),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO turns(
                    id, created_at, user, assistant, emotion, categories_json, terms_json,
                    prosody_json, segments_json, embedding_json, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        self.json_text(
                            {
                                key: item.get(key)
                                for key in (
                                    "reflection",
                                    "reflection_reason",
                                    "focus_memory_id",
                                    "focus_memory_text",
                                    "mood",
                                    "importance",
                                    "retention",
                                    "facts",
                                    "access_count",
                                    "time_label",
                                    "timeline_text",
                                    "timestamp_source",
                                    "timestamp_note",
                                    "event_frame",
                                )
                                if key in item
                            }
                        ),
                    )
                    for item in data.get("short_terms", [])
                ],
            )
            self.upsert_fts_turns(conn, data.get("short_terms", []))
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

    def is_memory_recall_query(self, query):
        compact = compact_text(query)
        if not compact:
            return False
        return any(hint in compact for hint in MEMORY_RECALL_HINTS)

    def memory_clues(self, text):
        compact = compact_text(text)
        clues = {}

        def add(kind, value, weight):
            value = str(value or "").strip()
            if not value or value in MEMORY_STOP_TERMS:
                return
            key = f"{kind}:{value}"
            clues[key] = max(float(weight), clues.get(key, 0.0))

        for concept, words in MEMORY_CONCEPT_CLUES.items():
            if any(word in compact for word in words):
                add("concept", concept, 1.6)
        for category, keywords in MEMORY_CATEGORY_KEYWORDS.items():
            if any(keyword in compact for keyword in keywords):
                add("category", category, 1.1)
            for keyword in keywords:
                if keyword in compact:
                    add("keyword", keyword, 1.0)
        for phrase in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", text or ""):
            if phrase.isdigit() or phrase in MEMORY_STOP_TERMS:
                continue
            weight = 0.45
            if any(marker in phrase for marker in ("送", "买", "书", "饭", "水", "金币", "背包", "喜欢", "生日", "昨天", "上次")):
                weight = 0.9
            add("term", phrase, weight)
        return clues

    def clue_similarity(self, query_clues, item_clues):
        if not query_clues or not item_clues:
            return 0.0
        shared = set(query_clues) & set(item_clues)
        if not shared:
            return 0.0
        score = sum(min(query_clues[key], item_clues[key]) for key in shared)
        norm = max(1.0, sum(query_clues.values()) * 0.55)
        return min(1.2, score / norm)

    def extract_event_frame(self, user_text, assistant_text="", created_at=""):
        combined = f"{user_text or ''} {assistant_text or ''}"
        compact = compact_text(combined)
        if not compact:
            return {}

        def collect(mapping):
            found = []
            for label, words in mapping.items():
                if any(word in compact for word in words):
                    found.append(label)
            return found

        actors = []
        if "用户" in compact or "我" in compact:
            actors.append("user")
        if any(name in compact for name in ("苏念", "小日和", "你")):
            actors.append("sunian")
        actions = collect(EVENT_ACTION_CLUES)
        objects = collect(EVENT_OBJECT_CLUES)
        time_refs = [word for word in EVENT_TIME_CLUES if word in compact]
        emotions = [emo for emo in LLM_EMOTIONS if emo in compact]
        for zh, emo in (("开心", "joy"), ("高兴", "joy"), ("难过", "sadness"), ("生气", "anger"), ("害怕", "fear"), ("惊讶", "surprise")):
            if zh in compact and emo not in emotions:
                emotions.append(emo)

        if not any((actions, objects, time_refs, emotions)):
            return {}

        result_markers = ("收到", "收下", "接受", "拒绝", "放进", "买了", "喜欢", "记住", "答应")
        outcome = ""
        for marker in result_markers:
            idx = compact.find(marker)
            if idx >= 0:
                outcome = compact[max(0, idx - 10): idx + 24]
                break
        summary_parts = []
        if time_refs:
            summary_parts.append("/".join(time_refs[:2]))
        if actions:
            summary_parts.append("动作:" + "/".join(actions[:3]))
        if objects:
            summary_parts.append("对象:" + "/".join(objects[:3]))
        if outcome:
            summary_parts.append("结果:" + outcome[:36])
        return {
            "actors": actors[:3],
            "actions": actions[:4],
            "objects": objects[:4],
            "time_refs": time_refs[:3],
            "emotions": emotions[:3],
            "outcome": outcome[:60],
            "summary": "；".join(summary_parts),
            "created_at": created_at,
        }

    def event_frame_similarity(self, query_frame, item_frame):
        if not query_frame or not item_frame:
            return 0.0
        score = 0.0
        weights = {
            "actors": 0.12,
            "actions": 0.34,
            "objects": 0.42,
            "time_refs": 0.18,
            "emotions": 0.10,
        }
        for key, weight in weights.items():
            left = set(query_frame.get(key) or [])
            right = set(item_frame.get(key) or [])
            if not left or not right:
                continue
            overlap = len(left & right)
            if overlap:
                score += weight * overlap / max(1, len(left))
        return min(1.2, score)

    def can_try_dense_embedding(self):
        if self.embedding_provider in ("off", "none", "ngram"):
            return False
        if os.path.exists(self.embedding_model_path):
            return True
        return self.embedding_allow_remote and self.embedding_provider in ("sentence_transformers", "sentence-transformer", "auto")

    def embedding_cache_key(self, text):
        cleaned = collapse_repeated_memory_text(strip_stage_directions(text or ""))
        digest = hashlib.sha256(cleaned.encode("utf-8", errors="ignore")).hexdigest()
        return cleaned, digest

    def load_embedding_cache(self, provider, model, text_hash):
        if not os.path.exists(self.db_path):
            return None
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                row = conn.execute(
                    """SELECT embedding_json FROM embedding_cache
                       WHERE provider = ? AND model = ? AND text_hash = ?""",
                    (provider, model, text_hash),
                ).fetchone()
            if not row:
                return None
            value = self.parse_json_text(row[0], None)
            return value if isinstance(value, list) else None
        except Exception:
            return None

    def save_embedding_cache(self, provider, model, text_hash, embedding):
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                conn.execute(
                    """INSERT OR REPLACE INTO embedding_cache(
                           provider, model, text_hash, embedding_json, created_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (provider, model, text_hash, self.json_text(embedding), memory_now_label()),
                )
        except Exception as exc:
            self.log_runtime("EMBEDDING_CACHE_SAVE_ERROR", exc)

    def load_dense_embedding_model(self):
        if self._dense_embedding_failed:
            return None
        if self._dense_embedding_model is not None:
            return self._dense_embedding_model
        if not self.can_try_dense_embedding():
            self._dense_embedding_failed = True
            return None
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_TORCH", "1")
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            self._dense_embedding_failed = True
            self.log_runtime("EMBEDDING_PROVIDER_UNAVAILABLE", str(exc))
            return None
        try:
            kwargs = {}
            if not self.embedding_allow_remote:
                kwargs["local_files_only"] = True
            self._dense_embedding_model = SentenceTransformer(self.embedding_model_path, **kwargs)
            self.log_runtime("EMBEDDING_PROVIDER_READY", {"provider": "sentence_transformers", "model": self.embedding_model_path})
            return self._dense_embedding_model
        except TypeError:
            if not os.path.exists(self.embedding_model_path):
                self._dense_embedding_failed = True
                return None
            try:
                self._dense_embedding_model = SentenceTransformer(self.embedding_model_path)
                return self._dense_embedding_model
            except Exception as exc:
                self._dense_embedding_failed = True
                self.log_runtime("EMBEDDING_PROVIDER_LOAD_ERROR", str(exc))
                return None
        except Exception as exc:
            self._dense_embedding_failed = True
            self.log_runtime("EMBEDDING_PROVIDER_LOAD_ERROR", str(exc))
            return None

    def dense_embedding(self, text):
        cleaned, text_hash = self.embedding_cache_key(text)
        if not cleaned:
            return None
        provider = "sentence_transformers"
        model_key = self.embedding_model_path
        cached = self.load_embedding_cache(provider, model_key, text_hash)
        if cached is not None:
            return cached
        model = self.load_dense_embedding_model()
        if model is None:
            return None
        try:
            vector = model.encode(cleaned, normalize_embeddings=True)
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            vector = [float(value) for value in list(vector)]
            self.save_embedding_cache(provider, model_key, text_hash, vector)
            return vector
        except Exception as exc:
            self._dense_embedding_failed = True
            self.log_runtime("EMBEDDING_ENCODE_ERROR", str(exc))
            return None

    def rerank_memory_candidate(self, query, item, query_terms=None, query_clues=None, query_frame=None, query_temporal=None):
        """Local reranker hook for hybrid retrieval candidates.

        This is intentionally dependency-free. A future cross-encoder can replace
        this method while preserving retrieve()'s candidate flow and evals.
        """
        query_terms = set(query_terms or [])
        query_clues = query_clues or {}
        query_temporal = set(query_temporal or [])
        item_text = f"{item.get('user', '')} {item.get('assistant', '')}"
        query_compact = compact_text(query)
        item_compact = compact_text(item_text)
        score = 0.0

        if query_compact and item_compact:
            max_size = min(8, len(query_compact))
            chunk_hits = 0
            for size in range(max_size, 2, -1):
                for index in range(0, max(0, len(query_compact) - size + 1)):
                    if query_compact[index:index + size] in item_compact:
                        chunk_hits += 1
                        score += 0.08 * size
                        break
                if chunk_hits >= 3:
                    break

        item_terms = set(item.get("terms") or [])
        if query_terms and item_terms:
            overlap = len(query_terms & item_terms)
            score += min(0.5, overlap * 0.12)

        if query_clues:
            score += 0.35 * self.clue_similarity(query_clues, self.memory_clues(item_text))

        item_frame = item.get("event_frame") if isinstance(item.get("event_frame"), dict) else {}
        if query_frame and item_frame:
            score += 0.45 * self.event_frame_similarity(query_frame, item_frame)

        fts_score = float(item.get("_fts_score") or 0.0)
        if fts_score:
            score += 0.25 * fts_score

        for kw in query_temporal:
            if kw and kw in item_compact:
                score += 0.16

        item["_rerank_score"] = round(score, 4)
        return score

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
        dense = self.dense_embedding(text)
        if dense:
            for index, value in enumerate(dense):
                if abs(float(value)) > 1e-9:
                    vector[f"dense:{index:04d}"] = float(value)
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
        if len(edges) > 1200:
            edges.sort(key=lambda e: int(e.get("weight", 1)), reverse=True)
            del edges[800:]
            edges.sort(key=lambda e: str(e.get("last_seen", "")))

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
        if item.get("reflection"):
            self.update_reflection_graph(item)
            return
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

    def link_temporal(self, item):
        """Connect this turn to the most recent previous turn with a temporal edge."""
        with self.lock:
            terms = list(self.data.get("short_terms", []))
        prev = None
        for t in reversed(terms[:-1]):
            if not t.get("reflection") and t.get("id") != item.get("id"):
                prev = t
                break
        if not prev:
            return
        prev_id = prev.get("id", "")
        curr_id = item.get("id", "")
        if not prev_id or not curr_id:
            return
        prev_node = self.ensure_node("记忆", prev_id[:36], "时间线", prev.get("user", "")[:60])
        curr_node = self.ensure_node("记忆", curr_id[:36], "时间线", item.get("user", "")[:60])
        self.add_edge(prev_node, curr_node, "后续", item.get("user", "")[:60])
        self.add_edge(curr_node, prev_node, "之前", prev.get("user", "")[:60])

    def link_co_occurrence(self, item):
        """Connect this turn to recent turns that share significant keywords."""
        curr_terms = set(item.get("terms") or [])
        if len(curr_terms) < 2:
            return
        with self.lock:
            terms = list(self.data.get("short_terms", []))
        curr_id = item.get("id", "")
        curr_node = self.ensure_node("记忆", curr_id[:36], "共现", item.get("user", "")[:60])
        checked = 0
        linked = 0
        for t in reversed(terms[:-1]):
            if checked >= 10 or linked >= 3:
                break
            if t.get("id") == curr_id or t.get("reflection"):
                continue
            checked += 1
            other_terms = set(t.get("terms") or [])
            overlap = curr_terms & other_terms
            if len(overlap) >= 2:
                other_id = t.get("id", "")
                if not other_id:
                    continue
                other_node = self.ensure_node("记忆", other_id[:36], "共现", t.get("user", "")[:60])
                detail = "、".join(list(overlap)[:3])
                self.add_edge(curr_node, other_node, "相关", detail)
                linked += 1

    def link_emotion_continuity(self, item):
        """Connect this turn to the most recent turn with the same dominant emotion."""
        emotion = item.get("emotion", "neutral")
        if emotion == "neutral":
            return
        with self.lock:
            terms = list(self.data.get("short_terms", []))
        curr_id = item.get("id", "")
        checked = 0
        for t in reversed(terms[:-1]):
            if checked >= 8:
                break
            if t.get("id") == curr_id or t.get("reflection"):
                continue
            checked += 1
            if t.get("emotion") == emotion:
                other_id = t.get("id", "")
                if not other_id:
                    continue
                curr_node = self.ensure_node("记忆", curr_id[:36], "情绪连续", item.get("user", "")[:60])
                other_node = self.ensure_node("记忆", other_id[:36], "情绪连续", t.get("user", "")[:60])
                self.add_edge(curr_node, other_node, f"同{emotion}", "")
                emotion_node = self.ensure_node("情绪", emotion, "情绪")
                self.add_edge(curr_node, emotion_node, "感受", "")
                break

    def consolidate_graph(self, limit=60, max_edges=0):
        """Periodically scan recent memories and create missing links between them.
        max_edges=0 means no per-call limit (full consolidation pass)."""
        with self.lock:
            terms = list(self.data.get("short_terms", []))
        recent = [t for t in terms[-limit:] if not t.get("reflection") and t.get("id")]
        if len(recent) < 3:
            return 0
        edges_added = 0
        existing_edges = set()
        with self.lock:
            for edge in self.data.get("graph", {}).get("edges", []):
                existing_edges.add((edge.get("source", ""), edge.get("target", ""), edge.get("relation", "")))
        for i, item_a in enumerate(recent):
            if max_edges > 0 and edges_added >= max_edges:
                break
            terms_a = set(item_a.get("terms") or [])
            if len(terms_a) < 2:
                continue
            id_a = item_a.get("id", "")
            node_a = self.ensure_node("记忆", id_a[:36], "巩固", item_a.get("user", "")[:60])
            for item_b in recent[i+1:]:
                id_b = item_b.get("id", "")
                if not id_b:
                    continue
                terms_b = set(item_b.get("terms") or [])
                overlap = terms_a & terms_b
                if len(overlap) < 2:
                    continue
                node_b = self.ensure_node("记忆", id_b[:36], "巩固", item_b.get("user", "")[:60])
                if (node_a, node_b, "相关") in existing_edges or (node_b, node_a, "相关") in existing_edges:
                    continue
                detail = "、".join(list(overlap)[:3])
                self.add_edge(node_a, node_b, "相关", detail)
                existing_edges.add((node_a, node_b, "相关"))
                edges_added += 1
        emotion_groups = {}
        for item in recent:
            emo = item.get("emotion", "neutral")
            if emo != "neutral":
                emotion_groups.setdefault(emo, []).append(item)
        for emo, items in emotion_groups.items():
            if len(items) < 2:
                continue
            if max_edges > 0 and edges_added >= max_edges:
                continue
            for i in range(len(items) - 1):
                id_a = items[i].get("id", "")
                id_b = items[i+1].get("id", "")
                if not id_a or not id_b:
                    continue
                node_a = self.ensure_node("记忆", id_a[:36], "情绪连续", items[i].get("user", "")[:60])
                node_b = self.ensure_node("记忆", id_b[:36], "情绪连续", items[i+1].get("user", "")[:60])
                if (node_a, node_b, f"同{emo}") in existing_edges:
                    continue
                self.add_edge(node_a, node_b, f"同{emo}", "")
                existing_edges.add((node_a, node_b, f"同{emo}"))
                edges_added += 1
        # 语义相似度关联：用 embedding 向量计算相似度
        for i, item_a in enumerate(recent):
            if max_edges > 0 and edges_added >= max_edges:
                break
            vec_a = item_a.get("embedding") or {}
            if not vec_a:
                continue
            id_a = item_a.get("id", "")
            node_a = self.ensure_node("记忆", id_a[:36], "语义", item_a.get("user", "")[:60])
            for item_b in recent[i+1:]:
                id_b = item_b.get("id", "")
                if not id_b:
                    continue
                node_b = self.ensure_node("记忆", id_b[:36], "语义", item_b.get("user", "")[:60])
                if (node_a, node_b, "相似") in existing_edges or (node_b, node_a, "相似") in existing_edges:
                    continue
                vec_b = item_b.get("embedding") or {}
                if not vec_b:
                    continue
                sim = self.cosine(vec_a, vec_b)
                if sim >= 0.45:
                    self.add_edge(node_a, node_b, "相似", f"相似度{sim:.2f}")
                    existing_edges.add((node_a, node_b, "相似"))
                    edges_added += 1
        if edges_added > 0:
            try:
                self.save()
            except Exception as exc:
                self.log_runtime("MEMORY_CONSOLIDATE_SAVE_ERROR", exc)
            print("MEMORY_CONSOLIDATE =", {"edges_added": edges_added, "recent_count": len(recent)})
        return edges_added

    def update_reflection_graph(self, item):
        thought = item.get("assistant", "")
        focus = item.get("focus_memory_text") or item.get("user", "")
        mood = item.get("mood", "")
        reason = item.get("reflection_reason", "memory_reflection")
        pet_node = self.ensure_node("角色", "桌宠", "社交", thought)
        thought_node = self.ensure_node("思考", thought[:36] or "内心反思", "自我反思", thought)
        reflection_node = self.ensure_node("类别", "自我反思", "自我反思", reason)
        self.add_edge(pet_node, thought_node, "正在思考", thought)
        self.add_edge(thought_node, reflection_node, "归类", reason)
        if focus:
            focus_node = self.ensure_node("记忆", focus[:36], "被反思的记忆", focus)
            self.add_edge(focus_node, thought_node, "触发反思", thought)
            self.add_edge(thought_node, focus_node, "重新解释", focus)
        if mood:
            mood_node = self.ensure_node("心情", mood, "心理状态", thought)
            self.add_edge(mood_node, thought_node, "影响思路", thought)

        previous_term_node = ""
        relation = self.infer_relation(f"{focus} {thought}")
        for term in item.get("terms", [])[:8]:
            term_node = self.ensure_node("记忆", term, ",".join(item.get("categories", [])), thought)
            self.add_edge(thought_node, term_node, "联想到", thought)
            if previous_term_node:
                self.add_edge(previous_term_node, term_node, relation, thought)
            previous_term_node = term_node

    def update_long_term(self, item):
        long_term = self.data["long_term"]
        counts = long_term.setdefault("category_counts", {})
        for category in item.get("categories", []):
            counts[category] = int(counts.get(category, 0)) + 1
        # 记录重要事件（importance >= 6 的对话）
        importance = float(item.get("importance", 5.0))
        if importance >= 6.0:
            key_events = long_term.setdefault("key_events", [])
            event_text = item.get("user", "")[:60] or "；".join(item.get("facts", [])[:2])[:60]
            if event_text:
                key_events.append({
                    "time": item.get("created_at", ""),
                    "text": event_text,
                    "emotion": item.get("emotion", "neutral"),
                })
                if len(key_events) > 20:
                    long_term["key_events"] = key_events[-20:]
        # 生成摘要
        top = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:5]
        key_events = long_term.get("key_events", [])
        if top:
            top_text = "，".join(f"{name}{count}次" for name, count in top)
            recent_events = key_events[-3:]
            event_text = "；".join(e.get("text", "")[:30] for e in recent_events if e.get("text"))
            summary_parts = [f"近期话题：{top_text}"]
            if event_text:
                summary_parts.append(f"重要事件：{event_text}")
            long_term["summary"] = "。".join(summary_parts)
        long_term["last_updated"] = memory_now_label()

    def score_importance(self, user_text, assistant_text, emotion):
        """参考 Stanford Generative Agents 的 importance scoring，1-10 分"""
        score = 3.0
        combined = f"{user_text} {assistant_text}"
        # 情绪加权
        if emotion in ("joy", "sadness", "anger", "fear"):
            score += 2.0
        # 关系关键词
        relation_words = ("喜欢", "爱", "想你", "在乎", "讨厌", "生气", "害怕", "开心", "难过", "担心", "感动", "委屈", "吃醋", "撒娇", "结婚", "分手", "在一起")
        if any(w in combined for w in relation_words):
            score += 2.5
        # 用户个人信息
        personal_words = ("我叫", "我是", "我在", "我家", "我的工作", "我的名字", "我今年", "我生日")
        if any(w in user_text for w in personal_words):
            score += 2.0
        # 问句
        if "?" in user_text or "？" in user_text:
            score += 1.0
        # 长对话
        if len(user_text) > 30:
            score += 1.0
        # 重复/闲聊降权
        if len(user_text) > 0 and len(set(user_text)) < max(1, len(user_text)) * 0.3:
            score -= 2.0
        # 极短回复降权
        if len(user_text.strip()) <= 2:
            score -= 1.5
        return min(10.0, max(1.0, score))

    def extract_facts(self, user_text, assistant_text, emotion):
        """从对话中提取关键事实"""
        facts = []
        if emotion in ("joy", "sadness", "anger", "fear"):
            emo_labels = {"joy": "开心", "sadness": "难过", "anger": "生气", "fear": "害怕"}
            facts.append(f"用户当时{emo_labels.get(emotion, '有情绪')}")
        # 提取用户表达的偏好/事实
        preference_markers = ("我喜欢", "我不喜欢", "我想要", "我讨厌", "我最爱", "我不爱")
        for marker in preference_markers:
            if marker in user_text:
                idx = user_text.index(marker)
                snippet = user_text[idx:idx + 30].split("。")[0].split("，")[0].split("！")[0]
                if len(snippet) > 3:
                    facts.append(snippet)
        return facts

    def _semantic_memory(self):
        data = self.data.setdefault("semantic_memory", {})
        facts = data.get("facts")
        if not isinstance(facts, list):
            facts = []
            data["facts"] = facts
        data.setdefault("last_updated", "")
        return data

    def _semantic_object_text(self, text, marker):
        if marker not in text:
            return ""
        value = text.split(marker, 1)[1]
        value = re.split(r"[。！？!?；;\n，,]", value, maxsplit=1)[0]
        value = collapse_repeated_memory_text(strip_stage_directions(value))
        value = re.sub(r"[了啦呢吧啊哦呀]+$", "", value).strip()
        return value[:48].strip()

    def extract_semantic_facts(self, user_text, assistant_text, item):
        """Extract long-lived typed facts with source and validity windows."""
        user = collapse_repeated_memory_text(strip_stage_directions(user_text or ""))
        assistant = collapse_repeated_memory_text(strip_stage_directions(assistant_text or ""))
        combined = f"{user}\n{assistant}"
        facts = []
        source_id = str(item.get("id") or "")
        source_time = str(item.get("created_at") or memory_now_label())

        def add(kind, subject, predicate, obj, confidence=0.78, polarity=""):
            obj = collapse_repeated_memory_text(strip_stage_directions(obj or "")).strip()
            if not obj:
                return
            text = f"{subject}{predicate}{obj}"
            conflict_key = f"{subject}:{kind}:{predicate}:{memory_clean_label(obj, 32)}"
            if kind == "preference":
                conflict_key = f"{subject}:preference:{memory_clean_label(obj, 32)}"
            facts.append(
                {
                    "id": str(uuid.uuid4()),
                    "kind": kind,
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj[:80],
                    "polarity": polarity,
                    "text": text[:140],
                    "conflict_key": conflict_key,
                    "source_turn_id": source_id,
                    "source_time": source_time,
                    "valid_from": source_time,
                    "valid_to": "",
                    "status": "active",
                    "confidence": round(float(confidence), 2),
                    "last_seen": source_time,
                }
            )

        for pattern in (
            r"(?:我叫|我的名字是|叫我)([\u4e00-\u9fffA-Za-z0-9_·]{1,24})",
            r"(?:我是)([\u4e00-\u9fffA-Za-z0-9_·]{1,24})(?:。|，|,|！|!|$)",
        ):
            match = re.search(pattern, user)
            if match:
                add("profile", "用户", "名字是", match.group(1), confidence=0.92)
                break

        for pattern in (
            r"(?:我的生日是|我生日是|生日是)([\u4e00-\u9fffA-Za-z0-9年月日./\-]{2,24})",
            r"(?:我.*?)(\d{1,2}月\d{1,2}日)(?:生日)?",
        ):
            match = re.search(pattern, user)
            if match:
                add("profile", "用户", "生日是", match.group(1), confidence=0.9)
                break

        negative_markers = ("我不喜欢", "我讨厌", "我不爱", "我不想要")
        positive_markers = ("我喜欢", "我爱", "我最爱", "我想要", "我偏好")
        for marker in negative_markers:
            obj = self._semantic_object_text(user, marker)
            if obj:
                add("preference", "用户", "不喜欢", obj, confidence=0.84, polarity="negative")
        for marker in positive_markers:
            obj = self._semantic_object_text(user, marker)
            if obj and not any(obj == fact.get("object") and fact.get("polarity") == "negative" for fact in facts):
                add("preference", "用户", "喜欢", obj, confidence=0.82, polarity="positive")

        if any(word in user for word in ("别这样", "不要这样", "我不舒服", "太快了", "边界")):
            add("boundary", "用户", "边界提醒", user[:80], confidence=0.86)
        if any(word in combined for word in ("答应", "约定", "承诺", "下次", "明天", "记得提醒")):
            add("commitment", "双方", "约定", user[:90] or assistant[:90], confidence=0.72)
        return facts[:8]

    def update_semantic_memory(self, item):
        if not isinstance(item, dict):
            return []
        extracted = self.extract_semantic_facts(item.get("user", ""), item.get("assistant", ""), item)
        if not extracted:
            return []
        memory = self._semantic_memory()
        active_facts = [fact for fact in memory.get("facts", []) if isinstance(fact, dict)]
        updated = []
        now_label = str(item.get("created_at") or memory_now_label())
        for new_fact in extracted:
            conflict_key = new_fact.get("conflict_key", "")
            duplicate = None
            for old in reversed(active_facts):
                if old.get("status") != "active":
                    continue
                if old.get("conflict_key") != conflict_key:
                    continue
                if old.get("polarity") == new_fact.get("polarity") and old.get("object") == new_fact.get("object"):
                    duplicate = old
                    break
                old["status"] = "superseded"
                old["valid_to"] = now_label
                old["superseded_by"] = new_fact["id"]
            if duplicate:
                duplicate["last_seen"] = now_label
                duplicate["confidence"] = max(float(duplicate.get("confidence", 0.0)), float(new_fact.get("confidence", 0.0)))
                continue
            active_facts.append(new_fact)
            updated.append(new_fact)
        memory["facts"] = active_facts[-240:]
        memory["last_updated"] = now_label
        self.rebuild_core_memory()
        return updated

    def rebuild_core_memory(self):
        semantic = self._semantic_memory()
        facts = [fact for fact in semantic.get("facts", []) if isinstance(fact, dict) and fact.get("status") == "active"]
        priority = {"profile": 0, "boundary": 1, "commitment": 2, "preference": 3}
        facts.sort(key=lambda fact: (priority.get(fact.get("kind"), 9), str(fact.get("last_seen") or fact.get("source_time") or "")))
        profile = {}
        stable = []
        for fact in facts:
            kind = fact.get("kind", "")
            predicate = fact.get("predicate", "")
            obj = fact.get("object", "")
            if kind == "profile" and "名字" in predicate:
                profile["user_name"] = obj
            elif kind == "profile" and "生日" in predicate:
                profile["user_birthday"] = obj
            if kind in ("profile", "boundary", "commitment") or float(fact.get("confidence", 0.0)) >= 0.82:
                stable.append(
                    {
                        "kind": kind,
                        "text": fact.get("text", ""),
                        "source_turn_id": fact.get("source_turn_id", ""),
                        "valid_from": fact.get("valid_from", ""),
                        "confidence": fact.get("confidence", 0.0),
                    }
                )
        self.data["core_memory"] = {
            "profile": profile,
            "stable_facts": stable[-24:],
            "last_updated": memory_now_label(),
        }

    def decay_memories(self):
        """模拟 Ebbinghaus 遗忘曲线"""
        now = time.time()
        with self.lock:
            for item in self.data.get("short_terms", []):
                created_str = str(item.get("created_at") or "")
                try:
                    from datetime import datetime
                    created = datetime.strptime(created_str[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    created = now
                age_hours = max(0.0, (now - created) / 3600.0)
                importance = float(item.get("importance", 5.0))
                access_count = int(item.get("access_count", 0))
                strength = importance + access_count * 2.0
                retention = math.exp(-age_hours / max(1.0, strength * 8.0))
                item["retention"] = round(retention, 4)
            original_count = len(self.data["short_terms"])
            self.data["short_terms"] = [
                item for item in self.data["short_terms"]
                if item.get("retention", 1.0) >= 0.08
            ]
            removed = original_count - len(self.data["short_terms"])
        if removed > 0:
            try:
                self.save()
            except Exception as exc:
                report_exception(logger=self.log_runtime, component="memory", operation="decay_save", exc=exc)
        return removed

    def add_turn(self, user_text, assistant_text, emotion="neutral", prosody=None, segments=None):
        signal = memory_signal_report(user_text, assistant_text)
        user_text = signal["user"]
        assistant_text = signal["assistant"]
        if not user_text and not assistant_text:
            return None
        if not signal["keep"]:
            return None
        created_at = memory_now_label()
        importance = max(3.0, self.score_importance(user_text, assistant_text, emotion))
        combined = f"{user_text}\n{assistant_text}"
        categories = self.classify(combined)
        terms = self.extract_terms(combined, categories)
        facts = self.extract_facts(user_text, assistant_text, emotion)
        event_frame = self.extract_event_frame(user_text, assistant_text, created_at=created_at)
        item = {
            "id": str(uuid.uuid4()),
            "created_at": created_at,
            "time_label": created_at,
            "timeline_text": f"[{created_at}] 用户：{user_text} / 苏念：{assistant_text}",
            "timestamp_source": "created",
            "user": user_text,
            "assistant": assistant_text,
            "facts": facts,
            "event_frame": event_frame,
            "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
            "categories": categories,
            "terms": terms,
            "quality": signal["quality"],
            "memory_reason": signal["reason"],
            "importance": round(importance, 1),
            "access_count": 0,
            "retention": 1.0,
            "prosody": normalize_prosody_hint(prosody or {}),
            "segments": segments or [],
            "embedding": self.embedding(combined),
        }
        with self.lock:
            self.data["short_terms"].append(item)
            if len(self.data["short_terms"]) > self.short_term_limit:
                self.data["short_terms"] = self.data["short_terms"][-self.short_term_limit:]
        if item.get("quality", 1.0) >= 0.6:
            self.update_long_term(item)
            self.update_semantic_memory(item)
            # 高重要性才立即更新图谱
            if importance >= 7.0:
                self.update_graph(item)
                self.link_temporal(item)
                self.link_co_occurrence(item)
                self.link_emotion_continuity(item)
        try:
            self.save()
        except Exception as exc:
            self.log_runtime("MEMORY_SAVE_ERROR", exc)
        return item

    def add_reflection(self, thought, focus_item=None, mood="", reason="memory_reflection"):
        thought = collapse_repeated_memory_text(clean_structured_reply_leak(strip_stage_directions(thought or "")))
        if len(compact_text(thought)) < DEFAULT_MEMORY_MIN_SIGNAL_CHARS:
            return None
        focus_item = focus_item if isinstance(focus_item, dict) else {}
        focus_text = collapse_repeated_memory_text(
            strip_stage_directions(
                focus_item.get("user")
                or focus_item.get("assistant")
                or focus_item.get("focus")
                or ""
            )
        )
        combined = f"{focus_text}\n{thought}"
        categories = ["自我反思"]
        for category in self.classify(combined):
            if category not in categories:
                categories.append(category)
        item = {
            "id": str(uuid.uuid4()),
            "created_at": memory_now_label(),
            "user": f"内心反思触发：{focus_text[:120] or reason}",
            "assistant": thought[:DEFAULT_MEMORY_MAX_TEXT_CHARS],
            "emotion": "neutral",
            "categories": categories[:5],
            "terms": self.extract_terms(combined, categories),
            "quality": 0.92,
            "memory_reason": "self_reflection",
            "importance": 6.0,
            "access_count": 0,
            "retention": 1.0,
            "prosody": {},
            "segments": [],
            "embedding": self.embedding(combined),
            "reflection": True,
            "reflection_reason": reason,
            "focus_memory_id": str(focus_item.get("id") or ""),
            "focus_memory_text": focus_text[:DEFAULT_MEMORY_MAX_TEXT_CHARS],
            "mood": str(mood or ""),
        }
        with self.lock:
            self.data["short_terms"].append(item)
            if len(self.data["short_terms"]) > self.short_term_limit:
                self.data["short_terms"] = self.data["short_terms"][-self.short_term_limit:]
        self.update_long_term(item)
        self.update_graph(item)
        try:
            self.save()
        except Exception as exc:
            self.log_runtime("MEMORY_REFLECTION_SAVE_ERROR", exc)
        print("MEMORY_REFLECTION_ADD =", {"reason": reason, "mood": mood, "id": item["id"]})
        return item

    def _db_row_to_item(self, row):
        item = {
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
        extra = self.parse_json_text(row[10], {})
        if isinstance(extra, dict):
            item.update(extra)
        return item

    def _load_db_turns_between(self, start_date_str, end_date_str, limit=80):
        results = []
        if not os.path.exists(self.db_path):
            return results
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                rows = conn.execute(
                    """SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                              prosody_json, segments_json, embedding_json, extra_json
                       FROM turns
                       WHERE created_at >= ? AND created_at < ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (start_date_str, end_date_str, int(limit)),
                ).fetchall()
            return [self._db_row_to_item(row) for row in rows]
        except Exception:
            return results

    def _load_db_archival_candidates(self, query="", limit=600):
        results = []
        if not os.path.exists(self.db_path):
            return results
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                rows = conn.execute(
                    """SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                              prosody_json, segments_json, embedding_json, extra_json
                       FROM turns ORDER BY created_at DESC LIMIT ?""",
                    (int(limit),),
                ).fetchall()
            return [self._db_row_to_item(row) for row in rows]
        except Exception:
            return results

    def _fts_match_query(self, query):
        terms = []
        raw = collapse_repeated_memory_text(strip_stage_directions(query or ""))
        compact = compact_text(raw)
        if compact:
            terms.append(compact[:64])
            max_size = min(8, len(compact))
            for size in range(max_size, 2, -1):
                for index in range(0, max(0, len(compact) - size + 1)):
                    chunk = compact[index:index + size]
                    if chunk not in terms:
                        terms.append(chunk)
                    if len(terms) >= 18:
                        break
                if len(terms) >= 18:
                    break
        for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,24}", raw):
            if term not in terms:
                terms.append(term)
        terms = [term for term in terms[:18] if len(term) >= 3]
        if not terms:
            return ""
        quoted = []
        for term in terms:
            escaped = term.replace('"', '""')
            quoted.append(f'"{escaped}"')
        return " OR ".join(quoted)

    def _load_db_fts_candidates(self, query="", limit=80):
        results = []
        if not os.path.exists(self.db_path):
            return results
        match_query = self._fts_match_query(query)
        if not match_query:
            return results
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                rows = conn.execute(
                    """SELECT t.id, t.created_at, t.user, t.assistant, t.emotion,
                              t.categories_json, t.terms_json, t.prosody_json,
                              t.segments_json, t.embedding_json, t.extra_json,
                              bm25(turns_fts) AS rank
                       FROM turns_fts
                       JOIN turns t ON t.id = turns_fts.id
                       WHERE turns_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (match_query, int(limit)),
                ).fetchall()
            for row in rows:
                item = self._db_row_to_item(row[:11])
                try:
                    item["_fts_score"] = round(max(0.0, 1.0 / (1.0 + abs(float(row[11] or 0.0)))), 4)
                except Exception:
                    item["_fts_score"] = 0.5
                results.append(item)
        except Exception:
            return results
        return results

    def _load_db_turns_by_date(self, target_date_str, limit=20):
        """Load turns from the database for a specific date (YYYY-MM-DD)."""
        results = []
        if not os.path.exists(self.db_path):
            return results
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                rows = conn.execute(
                    """SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                              prosody_json, segments_json, embedding_json, extra_json
                       FROM turns WHERE created_at LIKE ? ORDER BY created_at DESC LIMIT ?""",
                    (f"{target_date_str}%", limit),
                ).fetchall()
            for row in rows:
                item = {
                    "id": row[0], "created_at": row[1] or "", "user": row[2] or "",
                    "assistant": clean_structured_reply_leak(row[3] or ""),
                    "emotion": row[4] or "neutral",
                    "categories": self.parse_json_text(row[5], []),
                    "terms": self.parse_json_text(row[6], []),
                    "prosody": self.parse_json_text(row[7], {}),
                    "segments": self.parse_json_text(row[8], []),
                    "embedding": self.parse_json_text(row[9], {}),
                }
                extra = self.parse_json_text(row[10], {})
                if isinstance(extra, dict):
                    item.update(extra)
                results.append(item)
        except Exception as exc:
            report_exception(logger=self.log_runtime, component="memory", operation="load_db_turns_for_date", exc=exc, target_date=target_date_str)
        return results

    def _load_db_recent_turns(self, limit=80):
        results = []
        if not os.path.exists(self.db_path):
            return results
        try:
            with self.connect_db() as conn:
                self.init_db(conn)
                rows = conn.execute(
                    """SELECT id, created_at, user, assistant, emotion, categories_json, terms_json,
                              prosody_json, segments_json, embedding_json, extra_json
                       FROM turns ORDER BY created_at DESC LIMIT ?""",
                    (int(limit),),
                ).fetchall()
            for row in rows:
                item = {
                    "id": row[0], "created_at": row[1] or "", "user": row[2] or "",
                    "assistant": clean_structured_reply_leak(row[3] or ""),
                    "emotion": row[4] or "neutral",
                    "categories": self.parse_json_text(row[5], []),
                    "terms": self.parse_json_text(row[6], []),
                    "prosody": self.parse_json_text(row[7], {}),
                    "segments": self.parse_json_text(row[8], []),
                    "embedding": self.parse_json_text(row[9], {}),
                }
                extra = self.parse_json_text(row[10], {})
                if isinstance(extra, dict):
                    item.update(extra)
                results.append(item)
        except Exception as exc:
            report_exception(logger=self.log_runtime, component="memory", operation="load_db_recent_turns", exc=exc, limit=limit)
        return results

    def retrieve(self, query, limit=4):
        query_vector = self.embedding(query)
        boundary_query = is_intimate_boundary_query(query)
        query_categories = set(self.classify(query))
        query_compact = compact_text(query)
        query_terms = set(re.findall(r"[一-鿿A-Za-z0-9]{2,12}", query or ""))
        query_terms = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", query or ""))
        query_clues = self.memory_clues(query)
        query_frame = self.extract_event_frame(query)
        temporal_keywords = {"昨天", "今天", "明天", "前天", "后天", "刚才", "上周", "这周", "下周", "上次", "那次", "当时", "之前", "后来", "以前"}
        temporal_keywords = set(temporal_keywords) | {
            "昨天", "今天", "明天", "前天", "后天", "刚才", "上周", "这周", "下周",
            "上个月", "这个月", "上次", "那次", "当时", "之前", "后来", "以前", "第一次", "最后一次",
        }
        query_temporal = query_compact & temporal_keywords if isinstance(query_compact, set) else set()
        for kw in temporal_keywords:
            if kw in (query or ""):
                query_temporal.add(kw)
        broad_recall = self.is_memory_recall_query(query) or bool(query_temporal)
        with self.lock:
            items = list(self.data.get("short_terms", []))
        existing_ids = {item.get("id") for item in items}

        for t in self._load_db_fts_candidates(query, limit=160 if broad_recall else 80):
            if t.get("id") not in existing_ids:
                items.append(t)
                existing_ids.add(t.get("id"))
            else:
                for item in items:
                    if item.get("id") == t.get("id"):
                        item["_fts_score"] = max(float(item.get("_fts_score") or 0.0), float(t.get("_fts_score") or 0.0))
                        break

        # If query has temporal keywords, also load matching turns from DB
        if query_temporal:
            from datetime import datetime, timedelta
            date_map = {"昨天": 1, "前天": 2, "今天": 0}
            date_map.update({"昨天": 1, "前天": 2, "今天": 0})
            today = datetime.now().date()
            range_map = {
                "这周": (today - timedelta(days=today.weekday()), today + timedelta(days=1)),
                "上周": (today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday())),
                "这个月": (today.replace(day=1), today + timedelta(days=1)),
            }
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month
            last_month_start = (first_this_month - timedelta(days=1)).replace(day=1)
            range_map["上个月"] = (last_month_start, last_month_end)
            for kw, (start_date, end_date) in range_map.items():
                if kw in query_temporal:
                    db_turns = self._load_db_turns_between(start_date.isoformat(), end_date.isoformat(), limit=120)
                    for t in db_turns:
                        if t.get("id") not in existing_ids:
                            items.append(t)
                            existing_ids.add(t.get("id"))
            for kw, delta in date_map.items():
                if kw in query_temporal:
                    target_date = (datetime.now().date() - timedelta(days=delta)).isoformat()
                    db_turns = self._load_db_turns_by_date(target_date, limit=20)
                    for t in db_turns:
                        if t.get("id") not in existing_ids:
                            items.append(t)
                            existing_ids.add(t.get("id"))
        if broad_recall:
            for t in self._load_db_archival_candidates(query, limit=600):
                if t.get("id") not in existing_ids:
                    items.append(t)
                    existing_ids.add(t.get("id"))

        scored = []
        total_items = max(1, len(items))
        for item_index, item in enumerate(items):
            score = self.cosine(query_vector, item.get("embedding") or {})
            category_bonus = 0.08 * len(query_categories & set(item.get("categories", [])))
            score += category_bonus
            item_text = f"{item.get('user', '')} {item.get('assistant', '')}"
            item_compact = compact_text(item_text)
            item_clues = self.memory_clues(item_text)
            clue_score = self.clue_similarity(query_clues, item_clues)
            if clue_score:
                score += 0.55 * clue_score
            item_frame = item.get("event_frame") if isinstance(item.get("event_frame"), dict) else {}
            if not item_frame:
                item_frame = self.extract_event_frame(item.get("user", ""), item.get("assistant", ""), created_at=item.get("created_at", ""))
                if item_frame:
                    item["event_frame"] = item_frame
            frame_score = self.event_frame_similarity(query_frame, item_frame)
            if frame_score:
                score += 0.75 * frame_score
            item_terms = set(item.get("terms") or [])
            if item_terms and query_terms:
                overlap = len(query_terms & item_terms)
                if overlap:
                    score += 0.18 * overlap
            fts_score = float(item.get("_fts_score") or 0.0)
            if fts_score:
                score += 0.45 * fts_score
                item["_retrieval_mode"] = "hybrid_fts"
            if query_compact and len(query_compact) >= 4:
                for i in range(len(query_compact) - 3):
                    chunk = query_compact[i:i+4]
                    if chunk in item_compact:
                        score += 0.15
                        break
            if query_temporal:
                for kw in query_temporal:
                    if kw in item_compact:
                        score += 0.20
                    item_time = str(item.get("created_at") or "")
                    if kw == "昨天" and item_time:
                        try:
                            item_date = datetime.strptime(item_time[:10], "%Y-%m-%d").date()
                            yesterday = datetime.now().date() - timedelta(days=1)
                            if item_date == yesterday:
                                score += 0.35
                        except Exception:
                            pass
            if broad_recall:
                recency = (item_index + 1) / total_items
                score += 0.12 * recency
                if item.get("emotion") in ("joy", "sadness", "fear", "anger"):
                    score += 0.05
            # if boundary_query and is_hard_boundary_memory(item):
            #     score *= 0.35
            # 重要性加权
            importance = float(item.get("importance", 5.0))
            score *= 0.7 + importance * 0.06
            # 遗忘曲线权重
            retention = float(item.get("retention", 1.0))
            score *= max(0.15, retention)
            access_count = int(item.get("access_count") or 0)
            if access_count > 0:
                score += min(0.15, access_count * 0.03)
            threshold = 0.015 if broad_recall else 0.05
            if score > threshold:
                score += self.rerank_memory_candidate(
                    query,
                    item,
                    query_terms=query_terms,
                    query_clues=query_clues,
                    query_frame=query_frame,
                    query_temporal=query_temporal,
                )
                item["_retrieval_score"] = round(score, 4)
                item["_retrieval_mode"] = item.get("_retrieval_mode") or ("broad_recall" if broad_recall else "focused")
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        result = [item for _score, item in scored[:limit]]
        for item in result:
            item["access_count"] = int(item.get("access_count") or 0) + 1
        return result

    def node_module_key(self, node):
        node_type = str(node.get("type") or "")
        category_text = str(node.get("category") or "")
        label_text = str(node.get("label") or "")
        categories = {part.strip() for part in re.split(r"[,/，、\s]+", category_text) if part.strip()}
        text = f"{category_text} {label_text}"
        if node_type == "思考" or "自我反思" in text or "被反思" in text:
            return "reflection"
        if any(word in text for word in ("小说", "日记", "写作", "创作", "稿子")):
            return "creation"
        for key, module in BRAIN_MODULES.items():
            if node_type in module.get("types", set()):
                return key
            if categories & module.get("categories", set()):
                return key
        return "concept"

    def brain_module_snapshot(self):
        with self.lock:
            graph = copy.deepcopy(self.data.get("graph", {"nodes": {}, "edges": []}))
        nodes = graph.get("nodes", {})
        module_data = {
            key: {
                "id": f"脑区:{key}",
                "key": key,
                "type": "脑区",
                "label": module["label"],
                "category": module["detail"],
                "count": 0,
                "details": [module["detail"]],
                "last_seen": "",
                "node_ids": [],
            }
            for key, module in BRAIN_MODULES.items()
        }
        node_to_module = {}
        for node_id, node in nodes.items():
            key = self.node_module_key(node)
            node_to_module[node_id] = key
            module = module_data[key]
            module["count"] += max(1, int(node.get("count", 1)))
            module["node_ids"].append(node_id)
            if str(node.get("last_seen") or "") > str(module.get("last_seen") or ""):
                module["last_seen"] = node.get("last_seen", "")
        edge_map = {}
        for edge in graph.get("edges", []):
            source_module = node_to_module.get(edge.get("source"))
            target_module = node_to_module.get(edge.get("target"))
            if not source_module or not target_module or source_module == target_module:
                continue
            pair = tuple(sorted((source_module, target_module)))
            item = edge_map.setdefault(
                pair,
                {
                    "source": f"脑区:{pair[0]}",
                    "target": f"脑区:{pair[1]}",
                    "relation": "协同",
                    "weight": 0,
                    "detail": "",
                    "last_seen": "",
                },
            )
            item["weight"] += int(edge.get("weight", 1))
            if edge.get("detail"):
                item["detail"] = edge.get("detail", "")[:120]
            if str(edge.get("last_seen") or "") > str(item.get("last_seen") or ""):
                item["last_seen"] = edge.get("last_seen", "")
        modules = [module for module in module_data.values() if module.get("node_ids")]
        modules.sort(key=lambda item: (int(item.get("count", 0)), item.get("last_seen", "")), reverse=True)
        for left, right in zip(modules, modules[1:]):
            pair = tuple(sorted((left.get("key", ""), right.get("key", ""))))
            if not pair[0] or not pair[1] or pair in edge_map:
                continue
            edge_map[pair] = {
                "source": f"脑区:{pair[0]}",
                "target": f"脑区:{pair[1]}",
                "relation": "互相影响",
                "weight": 1,
                "detail": "脑区之间会在检索、表达和反思时互相激活。",
                "last_seen": max(str(left.get("last_seen") or ""), str(right.get("last_seen") or "")),
            }
        return {"modules": modules, "edges": list(edge_map.values()), "node_to_module": node_to_module}

    def associative_trace(self, query, memories=None, source="memory", role="input"):
        memories = list(memories or self.retrieve(query, limit=4))
        memories.sort(key=lambda item: str(item.get("created_at") or ""))
        query_categories = self.classify(query)
        steps = []
        if query_categories:
            steps.append(f"输入归类到：{' / '.join(query_categories[:3])}")
        for item in memories[:4]:
            cats = " / ".join(item.get("categories", [])[:2]) or "日常"
            time_label = self._format_memory_time(item.get("created_at", ""))
            text = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "") or item.get("assistant", "")))
            if text:
                steps.append(f"{time_label} 联想到[{cats}]：{text[:70]}")
        if not memories:
            steps.append("没有命中旧记忆：只能依据当前输入、稳定设定和当下状态回应，不要虚构过去发生过的事。")
        second_hop = self._multi_hop_associate(memories)
        second_hop.sort(key=lambda item: str(item.get("created_at") or ""))
        for item in second_hop[:3]:
            cats = " / ".join(item.get("categories", [])[:2]) or "日常"
            time_label = self._format_memory_time(item.get("created_at", ""))
            text = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "") or item.get("assistant", "")))
            if text:
                steps.append(f"{time_label} 进一步想到[{cats}]：{text[:70]}")
        all_ids = [item.get("id", "") for item in memories[:4] if item.get("id")]
        all_ids.extend(item.get("id", "") for item in second_hop[:3] if item.get("id"))
        trace = {
            "time": memory_now_label(),
            "source": str(source or "memory")[:40],
            "role": str(role or "input")[:24],
            "query": str(query or "")[:160],
            "steps": steps[:9],
            "memory_ids": all_ids[:7],
        }
        self.save_meta_json(LAST_ASSOCIATION_META_KEY, trace)
        return trace

    def _multi_hop_associate(self, first_hop_memories):
        """Follow graph edges from first-hop memories to find second-hop related memories."""
        if not first_hop_memories:
            return []
        with self.lock:
            graph = self.data.get("graph", {"nodes": {}, "edges": []})
            all_terms = list(self.data.get("short_terms", []))
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        first_hop_ids = {item.get("id", "") for item in first_hop_memories}
        first_hop_node_ids = set()
        for item in first_hop_memories:
            mid = item.get("id", "")
            if mid:
                first_hop_node_ids.add(f"记忆:{mid[:36]}")
        connected_node_ids = set()
        relation_labels = {}
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            rel = edge.get("relation", "")
            if src in first_hop_node_ids and tgt not in first_hop_node_ids:
                connected_node_ids.add(tgt)
                relation_labels[tgt] = rel
            elif tgt in first_hop_node_ids and src not in first_hop_node_ids:
                connected_node_ids.add(src)
                relation_labels[src] = rel
        second_hop_ids = set()
        for node_id in connected_node_ids:
            parts = node_id.split(":", 1)
            if len(parts) == 2 and parts[0] == "记忆":
                second_hop_ids.add(parts[1])
        if not second_hop_ids:
            return []
        second_hop = []
        for item in all_terms:
            mid = item.get("id", "")
            if mid and mid[:36] in second_hop_ids and mid not in first_hop_ids:
                second_hop.append(item)
        def score(item):
            s = 1.0
            if item.get("emotion") in ("sadness", "fear", "joy"):
                s += 0.5
            s += len(compact_text(item.get("user", "") + item.get("assistant", ""))) / 200.0
            return s
        second_hop.sort(key=score, reverse=True)
        return second_hop[:3]

    def recent_user_memory_snippets(self, limit=4, max_chars=90):
        """Return real non-reflection memories for proactive prompts."""
        with self.lock:
            items = list(self.data.get("short_terms", []))
        snippets = []
        for item in reversed(items):
            if item.get("reflection"):
                continue
            user = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "")))
            assistant = collapse_repeated_memory_text(strip_stage_directions(item.get("assistant", "")))
            if user.startswith("桌宠主动行动") or user.startswith("桌宠主动关心用户"):
                continue
            if not user and not assistant:
                continue
            text = user or assistant
            if len(text) > max_chars:
                text = text[:max_chars].rstrip() + "..."
            snippets.append(
                {
                    "id": item.get("id", ""),
                    "created_at": item.get("created_at", ""),
                    "categories": list(item.get("categories", [])),
                    "text": text,
                }
            )
            if len(snippets) >= int(limit):
                break
        return snippets

    def build_core_memory_context(self, query=""):
        core = self.data.get("core_memory") if isinstance(self.data.get("core_memory"), dict) else {}
        semantic = self.data.get("semantic_memory") if isinstance(self.data.get("semantic_memory"), dict) else {}
        facts = [fact for fact in semantic.get("facts", []) if isinstance(fact, dict) and fact.get("status") == "active"]
        if not core.get("stable_facts") and facts:
            self.rebuild_core_memory()
            core = self.data.get("core_memory", {})
        lines = []
        profile = core.get("profile") if isinstance(core.get("profile"), dict) else {}
        if profile.get("user_name"):
            lines.append(f"核心事实：用户名字是「{profile.get('user_name')}」。")
        if profile.get("user_birthday"):
            lines.append(f"核心事实：用户生日是「{profile.get('user_birthday')}」。")
        stable = [item for item in core.get("stable_facts", []) if isinstance(item, dict) and item.get("text")]
        query_compact = compact_text(query)
        relevant = []
        for item in stable:
            text = str(item.get("text") or "")
            if any(chunk and chunk in compact_text(text) for chunk in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", query or "")):
                relevant.append(item)
        chosen = relevant[:4] or stable[-6:]
        for item in chosen:
            text = str(item.get("text") or "").strip()
            if text and text not in lines:
                lines.append(f"长期事实({item.get('valid_from', '')[:10]}): {text}")
        if not lines:
            return ""
        return "核心记忆层：这些是长期稳定事实；如果与候选对话记忆冲突，以有效期更新后的事实为准。\n" + "\n".join(lines[:8])

    def build_semantic_memory_context(self, query=""):
        semantic = self.data.get("semantic_memory") if isinstance(self.data.get("semantic_memory"), dict) else {}
        facts = [fact for fact in semantic.get("facts", []) if isinstance(fact, dict) and fact.get("status") == "active"]
        if not facts:
            return ""
        query_terms = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", query or ""))
        scored = []
        for fact in facts:
            text = str(fact.get("text") or "")
            score = float(fact.get("confidence", 0.0))
            compact = compact_text(text)
            for term in query_terms:
                if term in compact:
                    score += 0.45
            if fact.get("kind") in ("profile", "boundary", "commitment"):
                score += 0.2
            if score >= 0.72:
                scored.append((score, fact))
        scored.sort(key=lambda pair: (pair[0], str(pair[1].get("last_seen") or pair[1].get("source_time") or "")), reverse=True)
        lines = []
        for _score, fact in scored[:8]:
            valid = fact.get("valid_from", "")[:10] or "time-unknown"
            source = fact.get("source_turn_id", "")[:8]
            lines.append(f"事实({fact.get('kind', 'fact')},{valid},source={source}): {fact.get('text', '')}")
        if not lines:
            return ""
        return "语义事实层：这是从对话中抽取并带来源的事实；不要使用已过期或被替代的旧事实。\n" + "\n".join(lines)

    def build_prompt_context(self, query):
        recall_query = self.is_memory_recall_query(query)
        memories = self.retrieve(query, limit=14 if recall_query else 6)
        memories.sort(key=lambda item: str(item.get("created_at") or ""))
        association = self.associative_trace(query, memories=memories)
        boundary_query = is_intimate_boundary_query(query)
        with self.lock:
            summary = self.data.get("long_term", {}).get("summary", "")
        lines = []
        lines.append(
            "记忆使用规则：只能把下面列出的记忆、长期摘要和当前输入当作依据；"
            "如果记忆没有覆盖某件事，就说不确定或按当下感受回应，不要编造过去经历。"
        )
        core_context = self.build_core_memory_context(query)
        if core_context:
            lines.append(core_context)
        semantic_context = self.build_semantic_memory_context(query)
        if semantic_context:
            lines.append(semantic_context)
        if recall_query:
            lines.append(
                "当前是宽松回忆模式：下面的候选记忆只是可能相关，不等于一定就是用户指的那件事；"
                "如果证据不足，要说“我有点想不清楚/我不能确定”，不要断言没发生过，也不要强行认领。"
            )
        experience_context = self.build_experience_context(query)
        if experience_context:
            lines.append(experience_context)
        if summary:
            if any(marker in summary for marker in STRUCTURED_REPLY_MARKERS):
                repaired = clean_structured_reply_leak(summary)
                if repaired and repaired != summary:
                    summary = re.sub(r"->.*$", f"-> {repaired}", summary)
            lines.append(f"长期记忆摘要：{summary}")
        if boundary_query:
            lines.append(
                "亲密记忆提醒：过去的回应只是当时的心情和关系距离；"
                "这次可以结合当前关系、语气、安全感和最近经历重新感受。"
            )
        max_memory_lines = 8 if recall_query else 6
        rendered = 0
        for item in memories:
            if rendered >= max_memory_lines:
                break
            if item.get("reflection"):
                continue
            cats = "/".join(item.get("categories", []))
            time_label = self._format_memory_time(item.get("created_at", ""))
            if item.get("timestamp_source") == "repaired_unknown":
                time_label = f"{time_label}/旧记忆补时"
            score = float(item.get("_retrieval_score") or 0.0)
            confidence = "可能相关"
            if score >= 0.75:
                confidence = "较相关"
            elif score >= 0.35:
                confidence = "弱相关"
            user_text = item.get("user", "")
            assistant_text = item.get("assistant", "")
            rendered += 1
            index = rendered
            facts = item.get("facts", [])
            frame = item.get("event_frame") if isinstance(item.get("event_frame"), dict) else {}
            frame_text = ""
            if frame.get("summary"):
                frame_text = f" 事件线索：{frame.get('summary', '')[:80]}。"
            if user_text or assistant_text:
                lines.append(
                    f"记忆{index}({time_label},{cats},{confidence}): 用户说\"{user_text[:80]}\"；苏念回应\"{assistant_text[:80]}\"。{frame_text}"
                )
            elif facts:
                lines.append(f"记忆{index}({time_label},{cats},{confidence}): {'; '.join(facts[:3])}.{frame_text}")
        if association.get("steps"):
            lines.append("本次联想链：这些线索像脑海里浮起的记忆，可以自然影响她的回应。")
            for step in association.get("steps", [])[:4]:
                lines.append(f"- {step}")
        if not lines:
            return ""
        return "以下是她此刻能想起的记忆和联想：\n" + "\n".join(lines[:12])

    def _format_memory_time(self, created_at):
        if not created_at:
            return "时间不详"
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            delta = now - dt
            weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
            wd = weekdays[dt.weekday()]
            time_str = dt.strftime("%H:%M")
            if delta.days == 0:
                return f"今天{time_str} {wd}"
            elif delta.days == 1:
                return f"昨天{time_str} {wd}"
            elif delta.days == 2:
                return f"前天{time_str} {wd}"
            elif delta.days <= 7:
                return f"{delta.days}天前{time_str} {wd}"
            else:
                return dt.strftime(f"%m月%d日{time_str} {wd}")
        except Exception:
            return created_at[:16]

    def load_experience_memory(self):
        data = self.load_meta_json(EXPERIENCE_MEMORY_META_KEY, {})
        if not isinstance(data, dict):
            data = {}
        events = data.get("events") if isinstance(data.get("events"), list) else []
        experience = {
            "relation_status": str(data.get("relation_status") or ""),
            "events": [item for item in events if isinstance(item, dict) and item.get("text")][-12:],
        }
        if not experience["relation_status"] and not experience["events"]:
            inferred = self.infer_experience_from_recent_turns()
            if inferred.get("relation_status") or inferred.get("events"):
                self.save_experience_memory(inferred)
                return inferred
        return experience

    def infer_experience_from_recent_turns(self):
        with self.lock:
            items = list(self.data.get("short_terms", []))[-80:]
        experience = {"relation_status": "", "events": []}
        for item in items:
            user = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "")))
            assistant = collapse_repeated_memory_text(strip_stage_directions(item.get("assistant", "")))
            compact_user = compact_text(user)
            compact_assistant = compact_text(assistant)
            if not compact_user or not compact_assistant:
                continue
            proposal_user = any(term in compact_user for term in ("求婚", "嫁给我", "单膝跪地", "钻戒"))
            proposal_accept = any(term in compact_assistant for term in ("我愿意", "愿意嫁给你", "答应你", "未婚夫妻"))
            if proposal_user and proposal_accept:
                self.update_relation_status(experience, "未婚夫妻")
                experience["events"].append(
                    {
                        "time": item.get("created_at") or memory_now_label(),
                        "kind": "relationship_milestone",
                        "text": "用户向她求婚，她明确答应了；两人的关系进入未婚夫妻阶段。",
                        "user": user[:160],
                        "assistant": assistant[:180],
                    }
                )
            elif any(term in compact_user for term in ("什么关系", "现在是", "为什么还是")):
                if "未婚夫妻" in compact_assistant:
                    self.update_relation_status(experience, "未婚夫妻")
                    status = "未婚夫妻"
                elif any(term in compact_assistant for term in ("恋人", "男朋友", "女朋友")):
                    self.update_relation_status(experience, "恋人")
                    status = "恋人"
                else:
                    status = ""
                if status:
                    experience["events"].append(
                        {
                            "time": item.get("created_at") or memory_now_label(),
                            "kind": "relationship_status",
                            "text": f"她在对话中确认当前关系是{status}。",
                            "user": user[:160],
                            "assistant": assistant[:180],
                        }
                    )
        experience["events"] = experience["events"][-12:]
        return experience

    def save_experience_memory(self, data):
        if not isinstance(data, dict):
            return False
        data["events"] = [item for item in data.get("events", []) if isinstance(item, dict) and item.get("text")][-12:]
        return self.save_meta_json(EXPERIENCE_MEMORY_META_KEY, data)

    def relation_status_rank(self, status):
        return RELATION_STATUS_RANK.get(str(status or ""), 0)

    def update_relation_status(self, experience, status):
        current = str(experience.get("relation_status") or "")
        if self.relation_status_rank(status) >= self.relation_status_rank(current):
            experience["relation_status"] = status

    def add_experience_event(self, kind, text, user_text="", assistant_text="", relation_status=""):
        kind = str(kind or "").strip()
        text = collapse_repeated_memory_text(strip_stage_directions(text or ""))
        if not kind or not text:
            return False
        experience = self.load_experience_memory()
        if relation_status:
            self.update_relation_status(experience, relation_status)
        events = list(experience.get("events", []))
        compact_new = compact_text(text)
        for item in reversed(events[-4:]):
            if item.get("kind") == kind and compact_text(item.get("text", "")) == compact_new:
                return False
        events.append(
            {
                "time": memory_now_label(),
                "kind": kind,
                "text": text[:180],
                "user": collapse_repeated_memory_text(strip_stage_directions(user_text or ""))[:160],
                "assistant": collapse_repeated_memory_text(strip_stage_directions(assistant_text or ""))[:180],
            }
        )
        experience["events"] = events[-12:]
        saved = self.save_experience_memory(experience)
        if saved:
            print("EXPERIENCE_MEMORY_ADD =", {"kind": kind, "status": experience.get("relation_status", ""), "text": text})
        return saved

    def observe_experience(self, user_text, assistant_text, initiated_by="user"):
        if str(initiated_by or "user") != "user":
            return []
        user = collapse_repeated_memory_text(strip_stage_directions(user_text or ""))
        assistant = collapse_repeated_memory_text(strip_stage_directions(assistant_text or ""))
        compact_user = compact_text(user)
        compact_assistant = compact_text(assistant)
        if not compact_user or not compact_assistant:
            return []
        added = []
        proposal_user = any(term in compact_user for term in ("求婚", "嫁给我", "单膝跪地", "钻戒"))
        proposal_accept = any(term in compact_assistant for term in ("我愿意", "愿意嫁给你", "答应你", "未婚夫妻"))
        if proposal_user and proposal_accept:
            if self.add_experience_event(
                "relationship_milestone",
                "用户向她求婚，她明确答应了；两人的关系进入未婚夫妻阶段。",
                user_text=user,
                assistant_text=assistant,
                relation_status="未婚夫妻",
            ):
                added.append("proposal_accepted")
        relation_question = any(term in compact_user for term in ("什么关系", "现在是", "是不是", "为什么还是"))
        if relation_question:
            status = ""
            if "未婚夫妻" in compact_assistant:
                status = "未婚夫妻"
            elif any(term in compact_assistant for term in ("恋人", "男朋友", "女朋友")):
                status = "恋人"
            if status and self.add_experience_event(
                "relationship_status",
                f"她在对话中确认当前关系是{status}。",
                user_text=user,
                assistant_text=assistant,
                relation_status=status,
            ):
                added.append(f"status_{status}")
        return added

    def build_experience_context(self, query):
        experience = self.load_experience_memory()
        status = str(experience.get("relation_status") or "")
        events = list(experience.get("events", []))
        if not status and not events:
            return ""
        compact_query = compact_text(query)
        relation_related = any(
            term in compact_query
            for term in ("关系", "求婚", "结婚", "嫁给", "未婚", "恋人", "男朋友", "女朋友", "记得", "发生")
        )
        if not relation_related:
            events = events[-2:]
        lines = []
        if status:
            lines.append(f"经历记忆：当前双方已确认的关系是「{status}」。")
        seen = set()
        for item in events[-4:]:
            text = str(item.get("text") or "").strip()
            if status and self.relation_status_rank(status) > self.relation_status_rank("恋人") and "确认当前关系是恋人" in text:
                continue
            key = compact_text(text)
            if key in seen:
                continue
            seen.add(key)
            if text:
                lines.append(f"经历片段：{text}")
        return "\n".join(lines[:5])

    def graph_snapshot(self):
        with self.lock:
            edge_count_before = len(self.data.get("graph", {}).get("edges", []))
            self.repair_graph_connectivity()
            edge_count_after = len(self.data.get("graph", {}).get("edges", []))
            if edge_count_after > edge_count_before:
                try:
                    self.save()
                except Exception as exc:
                    report_exception(logger=self.log_runtime, component="memory", operation="load_experience_save", exc=exc)
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
            self.log_runtime("MEMORY_META_LOAD_ERROR", key, exc)
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
            self.log_runtime("MEMORY_META_SAVE_ERROR", key, exc)
            return False
