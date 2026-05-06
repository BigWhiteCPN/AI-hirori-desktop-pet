"""Heart state, personality, reflection, and compact status UI."""

import copy
import random
import re
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from persona_pet.memory import collapse_repeated_memory_text, memory_now_label, strip_stage_directions


HEART_STATE_META_KEY = "heart_state"

INFP_PERSONALITY = {
    "mbti": "INFP",
    "name": "调停者",
    "traits": ("内向", "直觉", "情感", "知觉"),
    "core": "温柔、理想主义、重视真实感和情绪连贯性，习惯先在心里整理再表达。",
    "rules": (
        "先共情，再判断",
        "偏好含蓄、留有余地的表达",
        "会从记忆中寻找关系线索和情绪意义",
        "被忽略时会安静低落，但避免给用户压力",
    ),
}

DRIVE_MOOD_LABELS = {
    "curious": "安静好奇",
    "attached": "亲近",
    "worried": "有点担心",
    "relaxed": "安心",
    "tired": "低能量",
    "playful": "轻快",
    "lonely": "想被回应",
    "quiet": "安静观察",
}

EMOTION_MOOD_LABELS = {
    "joy": "微亮",
    "sadness": "共情低落",
    "anger": "紧绷",
    "fear": "不安",
    "surprise": "被触动",
    "neutral": "",
}


def _clean_piece(text, limit=56):
    text = collapse_repeated_memory_text(strip_stage_directions(text or ""))
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n\"'，。！？!?")
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


class PersonaHeart:
    """A lightweight inner-life model backed by memory meta storage."""

    def __init__(
        self,
        memory_store,
        drive_system=None,
        life_system=None,
        physiology_system=None,
        meta_key=HEART_STATE_META_KEY,
        reflection_interval_seconds=(55.0, 120.0),
        min_reflection_memory_seconds=180.0,
        logger=None,
    ):
        self.memory_store = memory_store
        self.drive = drive_system
        self.life = life_system
        self.physiology = physiology_system
        self.meta_key = meta_key
        self.reflection_interval_seconds = tuple(reflection_interval_seconds)
        self.min_reflection_memory_seconds = float(min_reflection_memory_seconds)
        self.log_runtime = logger or (lambda *parts: None)
        self.last_status_update_at = 0.0
        self.last_save_at = 0.0
        self.last_reflection_memory_at = 0.0
        self.state = self._load_state()
        now = time.monotonic()
        self.next_reflection_at = now + random.uniform(8.0, 22.0)
        self.reflect(now=now, reason="boot", force=True)

    def _default_state(self):
        return {
            "personality": copy.deepcopy(INFP_PERSONALITY),
            "mood": "安静观察",
            "mood_key": "quiet",
            "valence": 0.08,
            "arousal": 0.24,
            "thought": "我先安静待在旁边，把刚才的感觉在心里整理好。",
            "focus_memory_id": "",
            "focus_memory_text": "",
            "last_reflection_wall": "",
            "last_reflection_memory_wall": "",
            "last_reflection_memory_text": "",
            "thought_history": [],
        }

    def _load_state(self):
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        state = self._default_state()
        if isinstance(saved, dict):
            for key, value in saved.items():
                if key in state:
                    state[key] = value
        state["personality"] = copy.deepcopy(INFP_PERSONALITY)
        if not isinstance(state.get("thought_history"), list):
            state["thought_history"] = []
        return state

    def save(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_save_at < 10.0:
            return
        self.last_save_at = now
        self.memory_store.save_meta_json(self.meta_key, self.state)

    def tick(self, now=None, busy=False, current_emotion="neutral"):
        now = time.monotonic() if now is None else float(now)
        if now - self.last_status_update_at >= 1.0:
            self.last_status_update_at = now
            self.update_mood(current_emotion=current_emotion)
        if not busy and now >= self.next_reflection_at:
            self.reflect(now=now, reason="idle_memory")
            low, high = self.reflection_interval_seconds
            self.next_reflection_at = now + random.uniform(float(low), float(high))
        self.save()

    def update_mood(self, current_emotion="neutral"):
        drive_mood = "quiet"
        values = {}
        if self.drive is not None:
            try:
                snapshot = self.drive.snapshot()
                drive_mood = snapshot.get("mood") or "quiet"
                values = snapshot.get("values") or {}
            except Exception as exc:
                self.log_runtime("HEART_DRIVE_SNAPSHOT_ERROR", exc)
        label = DRIVE_MOOD_LABELS.get(drive_mood, drive_mood or "安静观察")
        emotion_label = EMOTION_MOOD_LABELS.get(current_emotion or "neutral", "")
        if emotion_label and emotion_label not in label:
            label = f"{label} / {emotion_label}"
        if self.physiology is not None:
            try:
                body_status = self.physiology.snapshot().get("status", "")
            except Exception as exc:
                body_status = ""
                self.log_runtime("HEART_PHYSIOLOGY_SNAPSHOT_ERROR", exc)
            if body_status and body_status != "身体平稳":
                label = f"{label} / {body_status}"
        energy = float(values.get("energy", 55.0))
        security = float(values.get("security", 55.0))
        affinity = float(values.get("affinity", 42.0))
        attachment = float(values.get("attachment_need", 25.0))
        self.state["mood_key"] = drive_mood
        self.state["mood"] = label
        self.state["valence"] = round((security + affinity - attachment * 0.45 - 55.0) / 75.0, 3)
        self.state["arousal"] = round((energy + attachment * 0.35) / 125.0, 3)

    def on_user_message(self, text, emotion="neutral"):
        compact = _clean_piece(text, limit=64)
        if not compact:
            return
        if emotion in ("sadness", "fear"):
            thought = f"他刚才像是有点难受。我想先接住这句话：{compact}"
        elif emotion == "joy":
            thought = f"这句话让气氛轻了一点。我想记住他开心时提到的：{compact}"
        elif emotion == "anger":
            thought = f"我感觉到一点锋利的情绪，先不要急着反驳：{compact}"
        elif "?" in text or "？" in text:
            thought = f"他在问我问题。我想认真想清楚，再给出不生硬的回答：{compact}"
        else:
            thought = f"我把这句话放进心里，看看它和以前的记忆有没有关系：{compact}"
        self._set_thought(thought, focus_text=compact, reason="user_message")

    def on_assistant_reply(self, reply, emotion="neutral", initiated_by="user"):
        compact = _clean_piece(reply, limit=64)
        if not compact:
            return
        if initiated_by == "proactive":
            thought = f"我刚才主动开口了，希望这句话不会打扰他：{compact}"
        elif emotion == "joy":
            thought = f"这次回应比较明亮，我想把这份轻松延续下去：{compact}"
        elif emotion in ("sadness", "fear"):
            thought = f"我刚才用了更轻的语气，因为我不想让他一个人消化这些：{compact}"
        else:
            thought = f"我检查了一下自己的表达，希望它听起来是真诚的：{compact}"
        self._set_thought(thought, focus_text=compact, reason="assistant_reply")

    def reflect(self, now=None, reason="idle_memory", force=False):
        item = self.pick_memory()
        if item:
            user = _clean_piece(item.get("user", ""), limit=54)
            assistant = _clean_piece(item.get("assistant", ""), limit=54)
            categories = "/".join(item.get("categories", [])[:2])
            lead = random.choice(
                (
                    "我又想起",
                    "刚才安静下来时，我想到",
                    "这段记忆在心里浮了一下",
                    "我在把这件事和现在的关系重新对齐",
                )
            )
            if user and assistant:
                thought = f"{lead}：他说过“{user}”，我当时回应“{assistant}”。我想更懂这段记忆里的情绪。"
            elif user:
                thought = f"{lead}：他说过“{user}”。我想知道这背后真正重要的是什么。"
            else:
                thought = f"{lead}一段旧记忆。它好像和{categories or '现在的心情'}有关。"
            self.state["focus_memory_id"] = str(item.get("id") or "")
            self.state["focus_memory_text"] = user or assistant
            self._set_thought(thought, focus_text=user or assistant, reason=reason, save=force)
            self.maybe_write_reflection_memory(thought, item, reason)
            return thought
        thought = random.choice(
            (
                "记忆还不多。我先观察他的语气，慢慢形成更稳定的理解。",
                "我在心里整理空白的地方，等下一次对话长出新的线索。",
                "没有特别清晰的旧记忆浮上来，所以我先保持安静和温柔。",
            )
        )
        self._set_thought(thought, focus_text="", reason=reason, save=force)
        self.maybe_write_reflection_memory(thought, {}, reason)
        return thought

    def maybe_write_reflection_memory(self, thought, focus_item=None, reason="idle_memory"):
        if reason == "boot" or not hasattr(self.memory_store, "add_reflection"):
            return None
        now = time.monotonic()
        if now - self.last_reflection_memory_at < self.min_reflection_memory_seconds:
            return None
        if thought == self.state.get("last_reflection_memory_text"):
            return None
        try:
            item = self.memory_store.add_reflection(
                thought,
                focus_item=focus_item,
                mood=self.state.get("mood", ""),
                reason=reason,
            )
        except Exception as exc:
            self.log_runtime("HEART_REFLECTION_MEMORY_ERROR", exc)
            return None
        if item:
            self.last_reflection_memory_at = now
            self.state["last_reflection_memory_wall"] = memory_now_label()
            self.state["last_reflection_memory_text"] = thought
            self.save(force=True)
        return item

    def pick_memory(self):
        try:
            _graph, short_terms, _long_term = self.memory_store.graph_snapshot()
        except Exception as exc:
            self.log_runtime("HEART_MEMORY_SNAPSHOT_ERROR", exc)
            return None
        if not short_terms:
            return None
        recent = [item for item in short_terms[-28:] if isinstance(item, dict)]
        if not recent:
            return None

        def score(item):
            text = f"{item.get('user', '')}\n{item.get('assistant', '')}"
            categories = set(item.get("categories") or [])
            value = 1.0 + min(2.0, len(text) / 160.0)
            if item.get("emotion") in ("sadness", "fear", "joy"):
                value += 1.0
            if categories & {"情绪", "偏好", "事件", "社交"}:
                value += 0.8
            if str(item.get("id") or "") == self.state.get("focus_memory_id"):
                value *= 0.35
            return max(0.1, value)

        weights = [score(item) for item in recent]
        return random.choices(recent, weights=weights, k=1)[0]

    def _set_thought(self, thought, focus_text="", reason="", save=True):
        thought = _clean_piece(thought, limit=150)
        if not thought:
            return
        self.state["thought"] = thought
        self.state["last_reflection_wall"] = memory_now_label()
        history = list(self.state.get("thought_history") or [])
        history.append(
            {
                "time": self.state["last_reflection_wall"],
                "reason": reason,
                "mood": self.state.get("mood", ""),
                "thought": thought,
                "focus": _clean_piece(focus_text, limit=80),
            }
        )
        self.state["thought_history"] = history[-12:]
        if save:
            self.save(force=True)

    def snapshot(self):
        thought = self.state.get("thought") or ""
        mood = self.state.get("mood") or "安静观察"
        focus = self.state.get("focus_memory_text") or ""
        return {
            "personality": copy.deepcopy(INFP_PERSONALITY),
            "mood": mood,
            "mood_key": self.state.get("mood_key", "quiet"),
            "thought": thought,
            "focus_memory": focus,
            "valence": self.state.get("valence", 0.0),
            "arousal": self.state.get("arousal", 0.0),
            "status_text": f"心情：{mood} | INFP | {thought}",
            "last_reflection_wall": self.state.get("last_reflection_wall", ""),
            "body": self.physiology.snapshot() if self.physiology is not None else {},
        }


class HeartStatusBar(QLabel):
    """Small permanent status strip for the frameless Live2D window."""

    def __init__(self, parent, heart):
        super().__init__(parent)
        self.heart = heart
        self.setObjectName("heartStatusBar")
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(False)
        self.setStyleSheet(
            "QLabel#heartStatusBar {"
            "background: rgba(255, 248, 253, 218);"
            "border: 1px solid rgba(222, 112, 168, 185);"
            "border-radius: 10px;"
            "padding: 2px 9px;"
            "color: #684158;"
            "font: 8pt 'Microsoft YaHei UI';"
            "}"
        )
        self.refresh()
        self.show()

    def refresh(self):
        snapshot = self.heart.snapshot()
        available = max(40, self.width() - 22)
        parent = self.parent()
        now = time.monotonic()
        active_status = ""
        if parent is not None:
            active_text = getattr(parent, "chat_status_text", "")
            active_until = float(getattr(parent, "chat_status_until", 0.0) or 0.0)
            if active_text and now <= active_until:
                active_status = str(active_text)
        body_status = snapshot.get("body", {}).get("status", "")
        visible_parts = []
        if active_status:
            visible_parts.append(f"状态：{active_status}")
        else:
            visible_parts.append(f"心情：{snapshot['mood']}")
        if body_status and body_status != "身体平稳" and not any(body_status in part for part in visible_parts):
            visible_parts.append(f"身体：{body_status}")
        visible_text = " | ".join(visible_parts)
        self.setText(self.fontMetrics().elidedText(visible_text, Qt.ElideRight, available))
        personality = snapshot["personality"]
        self.setToolTip(
            f"MBTI：{personality['mbti']} {personality['name']}\n"
            f"性格：{personality['core']}\n"
            f"临时状态：{active_status or '无'}\n"
            f"当前心情：{snapshot['mood']}\n"
            f"生理状态：{snapshot.get('body', {}).get('summary', '未同步')}\n"
            f"内心活动：{snapshot['thought']}"
        )


class HeartMixin:
    def setup_heart_module(self):
        self.heart = PersonaHeart(
            self.memory,
            drive_system=self.drive,
            life_system=self.life,
            physiology_system=getattr(self, "physiology", None),
            logger=getattr(self, "runtime_logger", None),
        )
        self.heart_status_bar = HeartStatusBar(self, self.heart)
        self.layout_heart_status_bar()

    def layout_heart_status_bar(self):
        if not hasattr(self, "heart_status_bar"):
            return
        margin = 22
        top = 0
        width = max(180, self.width() - margin * 2)
        self.heart_status_bar.setGeometry(margin, top, width, 24)
        self.heart_status_bar.raise_()

    def tick_heart_module(self, now=None, busy=False):
        if not hasattr(self, "heart"):
            return
        dominant = getattr(getattr(self, "current_analysis", None), "dominant", "neutral")
        self.heart.tick(now=now, busy=busy, current_emotion=dominant)
        if hasattr(self, "heart_status_bar"):
            self.heart_status_bar.refresh()

    def heart_on_user_message(self, text, emotion="neutral"):
        if hasattr(self, "heart"):
            self.heart.on_user_message(text, emotion=emotion)

    def heart_on_assistant_reply(self, reply, emotion="neutral", initiated_by="user"):
        if hasattr(self, "heart"):
            self.heart.on_assistant_reply(reply, emotion=emotion, initiated_by=initiated_by)

    def save_heart_module(self):
        if hasattr(self, "heart"):
            self.heart.save(force=True)
