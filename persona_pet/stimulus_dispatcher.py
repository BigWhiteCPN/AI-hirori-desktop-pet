from __future__ import annotations

import time

from PyQt5.QtCore import QObject, Qt, pyqtSignal


class StimulusDispatcher(QObject):
    dispatch_signal = pyqtSignal(object)

    DEFAULT_COOLDOWNS = {
        "touch": 0.4,
        "touch_dialogue": 6.0,
        "stare": 90.0,
        "drag": 2.0,
        "env_change": 60.0,
        "work_overtime": 1800.0,
        "late_night": 3600.0,
    }

    def __init__(self, owner, logger=None):
        super().__init__(owner)
        self.owner = owner
        self.logger = logger or (lambda *parts: None)
        self._last_dispatch_at = {}
        self.dispatch_signal.connect(self._deliver, Qt.QueuedConnection)

    def submit(self, stimulus) -> bool:
        if stimulus is None:
            return False
        stimulus = stimulus.normalized()
        if self._is_rate_limited(stimulus):
            return False
        try:
            self.owner.on_stimulus(stimulus)
            return True
        except Exception as exc:
            self.logger("STIMULUS_DISPATCH_ERROR", {"type": stimulus.type, "error": str(exc)})
            return False

    def submit_from_thread(self, stimulus) -> bool:
        if stimulus is None:
            return False
        self.dispatch_signal.emit(stimulus)
        return True

    def _deliver(self, stimulus):
        self.submit(stimulus)

    def _is_rate_limited(self, stimulus) -> bool:
        now = time.monotonic()
        key = str(stimulus.cooldown_key or stimulus.type or "").strip().lower()
        if not key:
            return False
        cooldown = self._cooldown_for(stimulus, key)
        last_at = float(self._last_dispatch_at.get(key, 0.0) or 0.0)
        if cooldown > 0 and last_at > 0 and now - last_at < cooldown:
            return True
        self._last_dispatch_at[key] = now
        return False

    def _cooldown_for(self, stimulus, key) -> float:
        custom = 0.0
        if isinstance(stimulus.meta, dict):
            try:
                custom = float(stimulus.meta.get("cooldown_seconds", 0.0) or 0.0)
            except Exception:
                custom = 0.0
        if custom > 0:
            return custom
        if key.startswith("touch_dialogue"):
            return self.DEFAULT_COOLDOWNS["touch_dialogue"]
        if key.startswith("touch"):
            return self.DEFAULT_COOLDOWNS["touch"]
        if key.startswith("drag"):
            return self.DEFAULT_COOLDOWNS["drag"]
        return float(self.DEFAULT_COOLDOWNS.get(stimulus.type, 0.0) or 0.0)
