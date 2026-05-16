from __future__ import annotations

import time
from dataclasses import dataclass, field


STIMULUS_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}


@dataclass
class Stimulus:
    type: str
    intensity: float = 0.5
    emotion_hint: str = "neutral"
    zone: str = ""
    duration: float = 0.0
    source: str = "interaction"
    created_at: float = field(default_factory=time.monotonic)
    meta: dict = field(default_factory=dict)
    memory_worthy: bool = False
    should_talk: bool = False
    cooldown_key: str = ""

    def normalized(self) -> "Stimulus":
        self.type = str(self.type or "").strip().lower() or "unknown"
        self.zone = str(self.zone or "").strip().lower()
        self.source = str(self.source or "interaction").strip().lower() or "interaction"
        self.intensity = max(0.0, min(1.0, float(self.intensity or 0.0)))
        self.duration = max(0.0, float(self.duration or 0.0))
        self.emotion_hint = str(self.emotion_hint or "neutral").strip().lower()
        if self.emotion_hint not in STIMULUS_EMOTIONS:
            self.emotion_hint = "neutral"
        if not isinstance(self.meta, dict):
            self.meta = {}
        if not self.cooldown_key:
            zone_part = f":{self.zone}" if self.zone else ""
            self.cooldown_key = f"{self.type}{zone_part}"
        return self

    def describe(self) -> str:
        parts = [f"事件={self.type}"]
        if self.zone:
            parts.append(f"区域={self.zone}")
        parts.append(f"强度={self.intensity:.2f}")
        if self.duration > 0:
            parts.append(f"持续={self.duration:.1f}秒")
        safe_meta = {}
        for key, value in self.meta.items():
            if key in {"pos", "window_title", "url", "text"}:
                continue
            safe_meta[str(key)] = value
        for key, value in safe_meta.items():
            parts.append(f"{key}={value}")
        return "，".join(parts)
