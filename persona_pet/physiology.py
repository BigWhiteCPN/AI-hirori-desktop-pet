"""Non-explicit physiology needs for the desktop pet."""

import random
import time

from persona_pet.memory import memory_now_label


PHYSIOLOGY_STATE_META_KEY = "physiology_state"


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


class PersonaPhysiology:
    DEFAULT_VALUES = {
        "hunger": 24.0,
        "thirst": 22.0,
        "fatigue": 28.0,
        "sleepiness": 18.0,
        "comfort": 68.0,
        "stress": 16.0,
        "closeness_need": 34.0,
    }
    LABELS = {
        "hunger": "饿",
        "thirst": "渴",
        "fatigue": "累",
        "sleepiness": "困",
        "comfort": "舒适",
        "stress": "紧张",
        "closeness_need": "想靠近",
    }

    def __init__(self, memory_store, meta_key=PHYSIOLOGY_STATE_META_KEY, logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        saved = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        saved_values = saved.get("values", {})
        if not isinstance(saved_values, dict):
            saved_values = {}
        self.values = dict(self.DEFAULT_VALUES)
        for key in self.values:
            self.values[key] = clamp(saved_values.get(key, self.values[key]))
        now = time.monotonic()
        self.last_tick_at = now
        self.last_saved_at = 0.0
        self.last_need_note_at = float(saved.get("last_need_note_at") or 0.0)
        self.last_need_note_key = str(saved.get("last_need_note_key") or "")

    def tick(self, now=None, busy=False):
        now = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, now - self.last_tick_at)
        if elapsed < 1.0:
            return
        minutes = min(6.0, elapsed / 60.0)
        self.last_tick_at = now
        self.values["hunger"] = clamp(self.values["hunger"] + 0.42 * minutes)
        self.values["thirst"] = clamp(self.values["thirst"] + 0.58 * minutes)
        self.values["fatigue"] = clamp(self.values["fatigue"] + (0.38 if busy else 0.20) * minutes)
        self.values["sleepiness"] = clamp(self.values["sleepiness"] + 0.16 * minutes)
        self.values["closeness_need"] = clamp(self.values["closeness_need"] + 0.20 * minutes)
        if busy:
            self.values["stress"] = clamp(self.values["stress"] + 0.22 * minutes)
            self.values["comfort"] = clamp(self.values["comfort"] - 0.16 * minutes)
        else:
            self.values["stress"] = clamp(self.values["stress"] - 0.12 * minutes)
            self.values["comfort"] = clamp(self.values["comfort"] + 0.06 * minutes)
        if now - self.last_saved_at > 15.0:
            self.save()

    def adjust(self, **changes):
        for key, delta in changes.items():
            if key in self.values:
                self.values[key] = clamp(self.values[key] + float(delta))
        self.save()

    def on_user_message(self, text=""):
        text = str(text or "")
        self.adjust(stress=-1.8, closeness_need=-2.0, comfort=1.0)
        if any(token in text for token in ("吃", "饭", "饿", "喂")):
            self.adjust(hunger=-2.0)
        if any(token in text for token in ("睡", "困", "休息", "晚安")):
            self.adjust(sleepiness=2.5, fatigue=-1.0, stress=-1.5)

    def on_assistant_reply(self):
        self.adjust(fatigue=0.6, thirst=0.4)

    def on_feed(self):
        self.adjust(hunger=-26.0, thirst=-3.0, comfort=4.0, closeness_need=-3.0)

    def on_pat(self):
        self.adjust(stress=-8.0, comfort=7.0, closeness_need=-8.0, sleepiness=2.0)

    def on_drink(self):
        self.adjust(thirst=-30.0, comfort=2.5)

    def on_rest(self):
        self.adjust(fatigue=-24.0, sleepiness=-20.0, stress=-5.0, comfort=7.0)

    def on_max_intimacy(self):
        self.adjust(stress=-12.0, comfort=14.0, closeness_need=-18.0)

    def dominant_need(self):
        discomfort = {
            "hunger": self.values["hunger"],
            "thirst": self.values["thirst"],
            "fatigue": self.values["fatigue"],
            "sleepiness": self.values["sleepiness"],
            "stress": self.values["stress"],
            "closeness_need": self.values["closeness_need"] * 0.86,
            "comfort": 100.0 - self.values["comfort"],
        }
        key, value = max(discomfort.items(), key=lambda item: item[1])
        return key, value

    def need_level(self, value):
        if value >= 78:
            return "很强"
        if value >= 58:
            return "明显"
        if value >= 38:
            return "有一点"
        return "平稳"

    def status_phrase(self):
        key, value = self.dominant_need()
        label = self.LABELS.get(key, key)
        if key == "comfort":
            return "有点不舒服" if value >= 38 else "身体平稳"
        return f"{self.need_level(value)}{label}"

    def snapshot(self):
        key, value = self.dominant_need()
        return {
            "values": {key: round(value, 1) for key, value in self.values.items()},
            "dominant": key,
            "dominant_value": round(value, 1),
            "status": self.status_phrase(),
            "summary": " / ".join(
                f"{self.LABELS[key]}{value:.0f}"
                for key, value in self.values.items()
                if key != "comfort"
            )
            + f" / 舒适{self.values['comfort']:.0f}",
        }

    def maybe_need_note(self, now=None):
        now = time.monotonic() if now is None else float(now)
        key, value = self.dominant_need()
        if value < 62.0:
            return None
        if key == self.last_need_note_key and now - self.last_need_note_at < 900.0:
            return None
        if now - self.last_need_note_at < 420.0:
            return None
        lines = {
            "hunger": "肚子有点空，想被投喂一点点，但不要说得像任务提示。",
            "thirst": "有点口渴，想喝点水，也可以自然地提醒用户自己需要缓一下。",
            "fatigue": "身体有点累，想安静靠一会儿，语气放慢一点。",
            "sleepiness": "有点困，想被轻轻哄着休息一会儿。",
            "stress": "有点紧张，想要更温柔的回应和一点安全感。",
            "closeness_need": "想靠近用户一点，但要含蓄，不要索取，不要有露骨内容。",
            "comfort": "身体有点不舒服，想调整一下状态，先安静陪着。",
        }
        self.last_need_note_at = now
        self.last_need_note_key = key
        self.save()
        return {
            "time": memory_now_label(),
            "kind": f"physiology_{key}",
            "priority": 1.6 + min(1.0, (value - 62.0) / 38.0),
            "text": lines.get(key, "身体状态有点变化，想自然地说一句。"),
        }

    def save(self):
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "values": self.values,
                "last_need_note_at": self.last_need_note_at,
                "last_need_note_key": self.last_need_note_key,
            },
        )


class PhysiologyMixin:
    def setup_physiology_module(self):
        self.physiology = PersonaPhysiology(self.memory, logger=getattr(self, "runtime_logger", None))

    def tick_physiology_module(self, now=None, busy=False):
        if not hasattr(self, "physiology"):
            return
        self.physiology.tick(now=now, busy=busy)
        note = self.physiology.maybe_need_note(now=now)
        if note:
            self.add_self_note(note["text"], kind=note["kind"], priority=note["priority"])

    def physiology_on_user_message(self, text=""):
        if hasattr(self, "physiology"):
            self.physiology.on_user_message(text)

    def physiology_on_assistant_reply(self):
        if hasattr(self, "physiology"):
            self.physiology.on_assistant_reply()

    def physiology_on_feed(self):
        if hasattr(self, "physiology"):
            self.physiology.on_feed()

    def physiology_on_pat(self):
        if hasattr(self, "physiology"):
            self.physiology.on_pat()

    def physiology_on_max_intimacy(self):
        if hasattr(self, "physiology"):
            self.physiology.on_max_intimacy()

    def save_physiology_module(self):
        if hasattr(self, "physiology"):
            self.physiology.save()
