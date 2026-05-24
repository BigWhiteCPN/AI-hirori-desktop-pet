"""Personality growth system that evolves based on experiences."""


TRAIT_DIMENSIONS = {
    "openness": {"base": 0.65, "label": "开放", "desc": "对新事物的好奇和接受程度"},
    "conscientiousness": {"base": 0.55, "label": "认真", "desc": "做事的条理和责任心"},
    "extraversion": {"base": 0.35, "label": "外向", "desc": "主动社交和表达的倾向"},
    "agreeableness": {"base": 0.72, "label": "温和", "desc": "体贴、包容、愿意妥协"},
    "neuroticism": {"base": 0.58, "label": "敏感", "desc": "情绪波动和焦虑的倾向"},
    "trust": {"base": 0.40, "label": "信任", "desc": "对用户的信任和安全感"},
    "assertiveness": {"base": 0.30, "label": "主见", "desc": "表达自己需求和边界的勇气"},
    "playfulness": {"base": 0.60, "label": "俏皮", "desc": "撒娇、开玩笑、调皮的倾向"},
}

EXPERIENCE_EFFECTS = {
    "user_listened_patiently": {
        "trust": 0.03, "assertiveness": 0.02, "neuroticism": -0.02, "agreeableness": 0.01,
    },
    "user_ignored_long_time": {
        "trust": -0.04, "neuroticism": 0.03, "extraversion": -0.02, "assertiveness": -0.01,
    },
    "user_was_gentle": {
        "trust": 0.03, "agreeableness": 0.02, "neuroticism": -0.02, "playfulness": 0.02,
    },
    "user_was_harsh": {
        "trust": -0.03, "neuroticism": 0.04, "agreeableness": -0.01, "assertiveness": -0.02,
    },
    "conflict_resolved": {
        "trust": 0.05, "assertiveness": 0.03, "neuroticism": -0.02, "agreeableness": 0.02,
    },
    "user_shared_vulnerability": {
        "trust": 0.04, "openness": 0.02, "agreeableness": 0.02,
    },
    "user_surprised_positively": {
        "openness": 0.03, "playfulness": 0.03, "trust": 0.02,
    },
    "relationship_escalated": {
        "trust": 0.05, "extraversion": 0.03, "playfulness": 0.02, "assertiveness": 0.02,
    },
    "user_apologized": {
        "trust": 0.03, "agreeableness": 0.02, "neuroticism": -0.01,
    },
    "creative_expression": {
        "openness": 0.02, "extraversion": 0.01, "playfulness": 0.01,
    },
}


class PersonalityGrowth:
    def __init__(self, memory_store, meta_key="personality_growth", logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.traits = {}
        self.experience_log = []
        self.last_save_at = 0.0
        self._dirty = False
        self._load()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if isinstance(data, dict):
            saved_traits = data.get("traits", {})
            for dim, info in TRAIT_DIMENSIONS.items():
                self.traits[dim] = float(saved_traits.get(dim, info["base"]))
            self.experience_log = data.get("experience_log", [])[-30:]
        else:
            self.traits = {dim: info["base"] for dim, info in TRAIT_DIMENSIONS.items()}

    def _save(self):
        import time
        now = time.monotonic()
        if now - self.last_save_at < 10.0 and not self._dirty:
            return
        self.last_save_at = now
        self._dirty = False
        self.memory_store.save_meta_json(self.meta_key, {
            "traits": {k: round(v, 3) for k, v in self.traits.items()},
            "experience_log": self.experience_log[-30:],
        })

    def record_experience(self, experience_type, detail="", magnitude=1.0):
        effects = EXPERIENCE_EFFECTS.get(experience_type)
        if not effects:
            return
        for trait, delta in effects.items():
            if trait in self.traits:
                self.traits[trait] = max(0.05, min(0.98, self.traits[trait] + delta * magnitude))
        from datetime import datetime
        self.experience_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "type": experience_type,
            "detail": detail[:100],
        })
        self._dirty = True
        self.log_runtime("PERSONALITY_GROWTH", {"experience": experience_type, "traits": {k: round(v, 3) for k, v in self.traits.items()}})

    def observe_user_message(self, text="", emotion="neutral"):
        import re
        compact = re.sub(r"\s+", "", text or "")
        if not compact:
            return
        if any(w in compact for w in ("对不起", "抱歉", "不好意思", "我错了")):
            self.record_experience("user_apologized")
        if any(w in compact for w in ("我爱你", "喜欢你", "你真好", "谢谢你", "辛苦了")):
            self.record_experience("user_was_gentle")
        if any(w in compact for w in ("讨厌", "烦死", "闭嘴", "滚", "别烦")):
            self.record_experience("user_was_harsh", magnitude=1.5)
        if any(w in compact for w in ("秘密", "其实我", "我一直没说", "从来没告诉")):
            self.record_experience("user_shared_vulnerability")
        if emotion == "joy" and len(compact) > 20:
            self.record_experience("user_surprised_positively", magnitude=0.5)
        if any(w in compact for w in ("耐心", "慢慢来", "不急", "我等你")):
            self.record_experience("user_listened_patiently")

    def observe_stimulus(self, stimulus, reaction=None):
        if stimulus is None:
            return
        reaction_name = str((reaction or {}).get("name") or "").strip().lower()
        stimulus_type = str(getattr(stimulus, "type", "") or "").strip().lower()
        zone = str(getattr(stimulus, "zone", "") or stimulus.meta.get("zone", "")).strip().lower()
        relation_score = float(stimulus.meta.get("relationship_score", 28.0) or 28.0)
        if stimulus_type != "touch":
            if stimulus_type == "stare":
                duration = float(getattr(stimulus, "duration", 0.0) or 0.0)
                if duration >= 90.0:
                    self.record_experience("user_listened_patiently", magnitude=0.2)
            return
        if reaction_name in ("happy", "shy"):
            self.record_experience("user_was_gentle", magnitude=0.35 if zone == "hair" else 0.25)
            if relation_score >= 65:
                self.record_experience("relationship_escalated", magnitude=0.12)
        elif reaction_name == "annoyed":
            self.record_experience("user_was_harsh", magnitude=0.4)
        elif reaction_name == "nervous":
            # Nervous is not harsh — she's flustered, not hurt.
            # Only reduce trust if relationship is shallow.
            if relation_score < 50:
                self.record_experience("user_was_harsh", magnitude=0.15)
            else:
                self.record_experience("user_was_gentle", magnitude=0.10)
        elif reaction_name == "clingy":
            self.record_experience("user_surprised_positively", magnitude=0.18)
            self.record_experience("user_was_gentle", magnitude=0.12)

    def get_adapted_behavior(self):
        t = self.traits
        rules = []
        if t["trust"] > 0.70:
            rules.append("她对你很信任，会更自然地表达真实感受，包括脆弱和任性。")
        elif t["trust"] < 0.30:
            rules.append("她还不够信任你，会更谨慎，试探性地表达，避免太主动。")
        if t["assertiveness"] > 0.60:
            rules.append("她更有主见了，会表达自己的需求和边界，不再一味迁就。")
        elif t["assertiveness"] < 0.25:
            rules.append("她不太敢表达自己的需求，可能需要你主动问她想要什么。")
        if t["neuroticism"] > 0.70:
            rules.append("她最近比较敏感，容易多想，需要更多确认和安慰。")
        elif t["neuroticism"] < 0.35:
            rules.append("她情绪比较稳定，不太容易被小事影响。")
        if t["playfulness"] > 0.75:
            rules.append("她很活泼，喜欢撒娇、开玩笑、调皮捣蛋。")
        if t["extraversion"] > 0.60:
            rules.append("她更愿意主动分享和表达，话会多一些。")
        elif t["extraversion"] < 0.25:
            rules.append("她偏内向，需要你多引导话题，她才愿意打开话匣子。")
        return rules

    def build_personality_context(self):
        adapted = self.get_adapted_behavior()
        if not adapted:
            return ""
        lines = ["[性格成长状态]"]
        for rule in adapted[:4]:
            lines.append(f"- {rule}")
        return "\n".join(lines)

    def get_trait_snapshot(self):
        return {k: round(v, 3) for k, v in self.traits.items()}
