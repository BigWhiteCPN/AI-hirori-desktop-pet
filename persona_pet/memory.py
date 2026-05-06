"""Memory storage, retrieval, and text cleanup for the desktop pet."""

import copy
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid

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
    def __init__(self, path, db_path, short_term_limit=DEFAULT_MEMORY_SHORT_TERM_LIMIT, logger=None):
        self.path = path
        self.db_path = db_path
        self.short_term_limit = int(short_term_limit)
        self.log_runtime = logger or (lambda *parts: None)
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
            self.repair_graph_connectivity()
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
        try:
            conn.execute("ALTER TABLE turns ADD COLUMN extra_json TEXT")
        except sqlite3.OperationalError:
            pass

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
                                )
                                if key in item
                            }
                        ),
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
            if len(self.data["short_terms"]) > self.short_term_limit:
                self.data["short_terms"] = self.data["short_terms"][-self.short_term_limit:]
            if item.get("quality", 1.0) >= 0.6:
                self.update_long_term(item)
                self.update_graph(item)
            try:
                self.save()
            except Exception as exc:
                self.log_runtime("MEMORY_SAVE_ERROR", exc)
        print("MEMORY_ADD =", {"categories": categories, "terms": item["terms"][:6], "id": item["id"]})
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

    def retrieve(self, query, limit=4):
        query_vector = self.embedding(query)
        boundary_query = is_intimate_boundary_query(query)
        query_categories = set(self.classify(query))
        with self.lock:
            items = list(self.data.get("short_terms", []))
        scored = []
        for item in items:
            score = self.cosine(query_vector, item.get("embedding") or {})
            category_bonus = 0.08 * len(query_categories & set(item.get("categories", [])))
            score += category_bonus
            if boundary_query and is_hard_boundary_memory(item):
                score *= 0.35
            if score > 0.05:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in scored[:limit]]

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
        query_categories = self.classify(query)
        steps = []
        if query_categories:
            steps.append(f"输入归类到：{' / '.join(query_categories[:3])}")
        for item in memories[:4]:
            cats = " / ".join(item.get("categories", [])[:2]) or "日常"
            text = collapse_repeated_memory_text(strip_stage_directions(item.get("user", "") or item.get("assistant", "")))
            if text:
                steps.append(f"联想到[{cats}]：{text[:70]}")
        if not memories:
            steps.append("没有命中旧记忆，先用当前语气和关系状态回应。")
        trace = {
            "time": memory_now_label(),
            "source": str(source or "memory")[:40],
            "role": str(role or "input")[:24],
            "query": str(query or "")[:160],
            "steps": steps[:6],
            "memory_ids": [item.get("id", "") for item in memories[:4] if item.get("id")],
        }
        self.save_meta_json(LAST_ASSOCIATION_META_KEY, trace)
        return trace

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

    def build_prompt_context(self, query):
        memories = self.retrieve(query, limit=4)
        association = self.associative_trace(query, memories=memories)
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
                "亲密边界记忆提醒：过去的强硬边界回复只代表当时心情，不是永久规则；"
                "这次要结合当前关系阶段、语气和安全感重新判断，避免机械复读旧拒绝。"
            )
        for index, item in enumerate(memories, 1):
            cats = "/".join(item.get("categories", []))
            lines.append(
                f"短期记忆{index}（{cats}）：用户说“{item.get('user', '')[:70]}”，你回应“{item.get('assistant', '')[:70]}”。"
            )
        if association.get("steps"):
            lines.append("本次联想链：先参考这些线索，再自然组织语言，不要机械复述。")
            for step in association.get("steps", [])[:4]:
                lines.append(f"- {step}")
        if not lines:
            return ""
        return "以下是可参考的记忆，只在相关时自然使用，不要生硬复述：\n" + "\n".join(lines[:10])

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
