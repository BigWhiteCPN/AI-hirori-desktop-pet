"""Metacognition system - self-reflection on behavior patterns."""

import re
import time
from datetime import datetime


REFLECTION_CATEGORIES = {
    "response_quality": {
        "triggers": ("too short", "didn't understand", "wrong", "not what I meant"),
        "thought": "我刚才的回应可能没有真正理解她的意思，下次应该多问一句确认。",
    },
    "emotional_mismatch": {
        "triggers": ("why are you", "don't be", "stop being", "I'm not"),
        "thought": "我判断的情绪可能不对，应该更仔细地感受她真正的心情。",
    },
    "boundary_crossed": {
        "triggers": ("too much", "too far", "don't", "stop", "enough"),
        "thought": "我可能越界了，应该更注意她的舒适度。",
    },
    "neglect_detected": {
        "triggers": ("you forgot", "you don't remember", "you never", "you always"),
        "thought": "我好像忽略了她在意的事情，应该更认真地记住她说过的话。",
    },
    "repetitive_pattern": {
        "triggers": ("again", "same thing", "every time", "always the same"),
        "thought": "我发现自己在重复同样的模式，应该尝试不同的回应方式。",
    },
}


class MetacognitionEngine:
    def __init__(self, memory_store, meta_key="metacognition", logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.insights = []
        self.behavior_patterns = {}
        self.last_reflection_at = 0.0
        self._dirty = False
        self._load()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if isinstance(data, dict):
            self.insights = data.get("insights", [])[-20:]
            self.behavior_patterns = data.get("behavior_patterns", {})

    def _save(self):
        if not self._dirty:
            return
        self._dirty = False
        self.memory_store.save_meta_json(self.meta_key, {
            "insights": self.insights[-20:],
            "behavior_patterns": self.behavior_patterns,
        })

    def observe_interaction(self, user_text="", assistant_text="", emotion="neutral", user_reaction=""):
        compact_user = re.sub(r"\s+", "", user_text or "")
        compact_reply = re.sub(r"\s+", "", assistant_text or "")
        compact_reaction = re.sub(r"\s+", "", user_reaction or "")
        if not compact_user:
            return

        pattern_key = f"{emotion}_{len(compact_reply) // 20}"
        self.behavior_patterns[pattern_key] = self.behavior_patterns.get(pattern_key, 0) + 1

        if compact_reaction:
            for category, info in REFLECTION_CATEGORIES.items():
                for trigger in info["triggers"]:
                    if trigger in compact_reaction.lower() or trigger in compact_user:
                        self._add_insight(category, info["thought"], user_text[:80])
                        break

        if emotion in ("sadness", "anger", "fear") and len(compact_reply) < 10:
            self._add_insight(
                "response_quality",
                "她刚才情绪不好，但我的回应太简短了，应该更温柔、更有耐心。",
                user_text[:80],
            )

        self._dirty = True

    def observe_stimulus(self, stimulus, reaction=None):
        if stimulus is None:
            return
        reaction = reaction or {}
        description = ""
        try:
            description = stimulus.describe()
        except Exception:
            description = str(getattr(stimulus, "type", "") or "")
        self.observe_interaction(
            user_text=description,
            assistant_text=str(reaction.get("prompt_direction") or ""),
            emotion=str(reaction.get("emotion_tag") or getattr(stimulus, "emotion_hint", "neutral")),
            user_reaction=str(reaction.get("name") or ""),
        )

    def _add_insight(self, category, thought, context=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.insights.append({
            "time": now,
            "category": category,
            "thought": thought,
            "context": context[:80],
        })
        self.log_runtime("METACOGNITION_INSIGHT", {"category": category, "thought": thought[:60]})

    def reflect_on_recent(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.last_reflection_at < 600.0:
            return None
        self.last_reflection_at = now

        with self.memory_store.lock:
            recent = list(self.memory_store.data.get("short_terms", []))[-10:]
        if len(recent) < 3:
            return None

        negative_count = sum(1 for t in recent if t.get("emotion") in ("sadness", "anger", "fear"))
        if negative_count >= 4:
            thought = "最近她的情绪整体偏低，我应该更温柔一些，少开玩笑，多倾听。"
            self._add_insight("emotional_momentum", thought)
            return thought

        short_replies = sum(1 for t in recent if len(t.get("assistant", "")) < 15)
        if short_replies >= 5:
            thought = "我最近回复都比较短，她可能觉得我不够用心，下次多说几句。"
            self._add_insight("response_quality", thought)
            return thought

        topics = set()
        for t in recent:
            for term in (t.get("terms") or [])[:3]:
                topics.add(term)
        if len(topics) < 4:
            thought = "我们话题有点单一，可以试着引导她聊一些新的话题。"
            self._add_insight("topic_diversity", thought)
            return thought

        return None

    def get_recent_insights(self, limit=5):
        return self.insights[-limit:]

    def build_metacognition_context(self):
        if not self.insights:
            return ""
        recent = self.insights[-3:]
        lines = ["[自我反思]"]
        for insight in recent:
            lines.append(f"- {insight['thought']}")
        return "\n".join(lines)

    def should_adjust_behavior(self):
        if not self.insights:
            return None
        recent = self.insights[-5:]
        categories = {}
        for insight in recent:
            cat = insight.get("category", "")
            categories[cat] = categories.get(cat, 0) + 1
        if not categories:
            return None
        dominant = max(categories, key=categories.get)
        if categories[dominant] >= 2:
            return {
                "category": dominant,
                "count": categories[dominant],
                "insight": self.insights[-1]["thought"],
            }
        return None
