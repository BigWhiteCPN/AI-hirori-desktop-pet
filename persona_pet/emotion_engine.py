"""Advanced emotion engine with mixed emotions, inertia, and contagion."""

import time

EMOTION_DIMENSIONS = {
    "joy": {"opposite": "sadness", "decay_rate": 0.08},
    "sadness": {"opposite": "joy", "decay_rate": 0.06},
    "anger": {"opposite": "joy", "decay_rate": 0.05},
    "fear": {"opposite": "joy", "decay_rate": 0.07},
    "surprise": {"opposite": "neutral", "decay_rate": 0.12},
    "neutral": {"opposite": None, "decay_rate": 0.0},
}

MOOD_INFLUENCE = {
    "tired": {"joy": -0.06, "sadness": 0.04, "anger": 0.02},
    "lonely": {"sadness": 0.05, "fear": 0.03, "joy": -0.04},
    "worried": {"fear": 0.06, "anger": 0.02, "joy": -0.03},
    "relaxed": {"joy": 0.04, "sadness": -0.03, "anger": -0.02},
    "curious": {"surprise": 0.04, "joy": 0.02},
    "attached": {"joy": 0.03, "sadness": 0.02},
    "playful": {"joy": 0.05, "surprise": 0.02},
    "quiet": {},
}


class EmotionalState:
    def __init__(self):
        self.values = {dim: 0.0 for dim in EMOTION_DIMENSIONS}
        self.values["neutral"] = 1.0
        self.momentum = {dim: 0.0 for dim in EMOTION_DIMENSIONS}
        self.last_update_at = time.monotonic()
        self.history = []

    def snapshot(self):
        active = {k: round(v, 3) for k, v in self.values.items() if v > 0.05}
        dominant = max(self.values, key=self.values.get)
        mixed = []
        for dim, val in sorted(self.values.items(), key=lambda x: -x[1]):
            if val > 0.15 and dim != "neutral":
                mixed.append((dim, round(val, 2)))
        return {
            "dominant": dominant,
            "values": active,
            "mixed": mixed[:3],
            "intensity": round(1.0 - self.values["neutral"], 3),
        }


class EmotionEngine:
    def __init__(self, inertia=0.78, contagion_strength=0.25, decay_speed=1.0):
        self.state = EmotionalState()
        self.inertia = float(inertia)
        self.contagion_strength = float(contagion_strength)
        self.decay_speed = float(decay_speed)
        self.last_user_emotion = "neutral"
        self.consecutive_user_emotions = {}

    def update(self, target_emotion, intensity=0.5, user_text="", user_emotion="neutral", mood="quiet", now=None):
        now = time.monotonic() if now is None else float(now)
        elapsed = min(2.0, now - self.state.last_update_at)
        self.state.last_update_at = now

        targets = self._build_targets(target_emotion, intensity, user_emotion, mood)

        for dim in EMOTION_DIMENSIONS:
            if dim == "neutral":
                continue
            target = targets.get(dim, 0.0)
            current = self.state.values[dim]
            diff = target - current
            momentum = self.state.momentum[dim]
            new_momentum = momentum * self.inertia + diff * (1.0 - self.inertia) * 0.45
            self.state.momentum[dim] = new_momentum
            new_value = current + new_momentum * elapsed * 2.5
            self.state.values[dim] = max(0.0, min(1.0, new_value))

        decay_info = EMOTION_DIMENSIONS
        for dim, info in decay_info.items():
            if dim == "neutral":
                continue
            rate = info["decay_rate"] * self.decay_speed * elapsed
            self.state.values[dim] = max(0.0, self.state.values[dim] - rate * 0.15)

        self.state.values["neutral"] = max(0.05, 1.0 - sum(
            v for k, v in self.state.values.items() if k != "neutral"
        ))
        self.state.values["neutral"] = min(1.0, self.state.values["neutral"])

        self._record_history(target_emotion, user_emotion, mood, now)
        return self.state.snapshot()

    def _build_targets(self, target_emotion, intensity, user_emotion, mood):
        targets = {}
        if target_emotion in EMOTION_DIMENSIONS and target_emotion != "neutral":
            targets[target_emotion] = max(0.0, min(1.0, float(intensity)))

        if user_emotion in EMOTION_DIMENSIONS and user_emotion != "neutral":
            contagion = self.contagion_strength
            if user_emotion == self.last_user_emotion:
                count = self.consecutive_user_emotions.get(user_emotion, 0) + 1
                self.consecutive_user_emotions[user_emotion] = count
                contagion *= min(2.0, 1.0 + count * 0.2)
            else:
                self.consecutive_user_emotions = {}
            contagion *= float(intensity)
            opposite = EMOTION_DIMENSIONS.get(user_emotion, {}).get("opposite")
            if opposite and opposite in targets:
                targets[opposite] = max(0.0, targets[opposite] - contagion * 0.3)
            targets[user_emotion] = targets.get(user_emotion, 0.0) + contagion
        self.last_user_emotion = user_emotion

        mood_effects = MOOD_INFLUENCE.get(mood, {})
        for dim, effect in mood_effects.items():
            targets[dim] = targets.get(dim, 0.0) + effect

        for dim in targets:
            targets[dim] = max(0.0, min(1.0, targets[dim]))
        return targets

    def _record_history(self, target_emotion, user_emotion, mood, now):
        dominant = max(
            ((k, v) for k, v in self.state.values.items() if k != "neutral"),
            key=lambda x: x[1],
            default=("neutral", 0.0),
        )
        entry = {
            "time": now,
            "dominant": dominant[0],
            "intensity": round(dominant[1], 2),
            "trigger": target_emotion,
            "user_emo": user_emotion,
            "mood": mood,
        }
        self.state.history.append(entry)
        if len(self.state.history) > 30:
            self.state.history = self.state.history[-30:]

    def get_mixed_emotion_label(self):
        s = self.state
        active = [(k, v) for k, v in s.values.items() if v > 0.15 and k != "neutral"]
        if not active:
            return "平静"
        active.sort(key=lambda x: -x[1])
        labels = {
            "joy": "开心", "sadness": "低落", "anger": "紧绷",
            "fear": "不安", "surprise": "惊讶",
        }
        if len(active) == 1:
            return labels.get(active[0][0], active[0][0])
        primary = labels.get(active[0][0], active[0][0])
        secondary = labels.get(active[1][0], active[1][0])
        combos = {
            ("joy", "sadness"): "又开心又有点遗憾",
            ("joy", "surprise"): "惊喜",
            ("joy", "fear"): "紧张的期待",
            ("sadness", "anger"): "委屈",
            ("sadness", "fear"): "无助",
            ("anger", "fear"): "又气又怕",
            ("anger", "surprise"): "震惊",
            ("fear", "surprise"): "惊慌",
        }
        key = (active[0][0], active[1][0])
        reverse_key = (active[1][0], active[0][0])
        return combos.get(key) or combos.get(reverse_key) or f"{primary}中带着{secondary}"

    def get_emotion_for_llm(self):
        s = self.state
        dominant = max(s.values, key=s.values.get)
        if s.values["neutral"] > 0.65:
            return "neutral"
        return dominant

    def get_expression_params(self):
        s = self.state
        joy = s.values.get("joy", 0.0)
        sadness = s.values.get("sadness", 0.0)
        anger = s.values.get("anger", 0.0)
        fear = s.values.get("fear", 0.0)
        surprise = s.values.get("surprise", 0.0)
        return {
            "eye_open": 0.88 + joy * 0.05 + surprise * 0.28 + fear * 0.12 - sadness * 0.24 - anger * 0.08,
            "mouth_form": 0.12 + joy * 0.78 - sadness * 0.78 - anger * 0.62 - fear * 0.26,
            "brow_form": joy * 0.18 + anger * 0.78 + surprise * 0.16 - fear * 0.58 - sadness * 0.34,
            "cheek": joy * (0.30 + (1.0 - s.values["neutral"]) * 0.40),
        }
