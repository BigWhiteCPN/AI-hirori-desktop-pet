"""Centralized idle behavior scheduler for the desktop pet."""

import random
import threading
import time
from dataclasses import dataclass, field

from persona_pet.runtime import get_default_runtime


@dataclass
class IdleBehavior:
    name: str
    base_priority: float
    cooldown: float
    min_idle: float = 0.0
    energy_floor: float = 0.0
    ready_fn: object = None
    execute_fn: object = None
    boost_per_second: float = 0.02
    last_executed_at: float = -9999.0
    last_starved_since: float = 0.0
    enabled: bool = True
    randomize_cooldown: bool = False
    cooldown_range: tuple = field(default_factory=lambda: (0.0, 0.0))
    resources: tuple = field(default_factory=lambda: ("idle_behavior",))


class IdleScheduler:
    def __init__(self, logger=None, dispatcher=None, runtime=None):
        self.behaviors = []
        self.log_runtime = logger or (lambda *parts: None)
        self.dispatcher = dispatcher
        self.runtime = runtime or get_default_runtime()
        self.last_tick_at = 0.0
        self._running_async = False

    def register(self, behavior):
        self.behaviors.append(behavior)
        return behavior

    def tick(self, now=None, busy=False, energy=50.0, idle_seconds=0.0):
        now = time.monotonic() if now is None else float(now)
        if busy:
            return None
        if self._running_async:
            return None
        candidates = []
        for b in self.behaviors:
            if not b.enabled:
                continue
            elapsed = now - b.last_executed_at
            if elapsed < b.cooldown:
                continue
            if b.min_idle > 0 and idle_seconds < b.min_idle:
                continue
            if b.energy_floor > 0 and energy < b.energy_floor:
                continue
            if b.ready_fn is not None:
                try:
                    if not b.ready_fn():
                        continue
                except Exception:
                    continue
            starved = now - b.last_starved_since
            effective = b.base_priority + b.boost_per_second * starved
            candidates.append((effective, b))
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        best = candidates[0][1]
        best.last_executed_at = now
        best.last_starved_since = now
        if best.randomize_cooldown and best.cooldown_range:
            best.cooldown = random.uniform(*best.cooldown_range)
        for b in self.behaviors:
            if b is not best and b.last_starved_since <= 0:
                b.last_starved_since = now
        self.log_runtime(
            "IDLE_SCHEDULER",
            {
                "selected": best.name,
                "priority": round(candidates[0][0], 1),
                "candidates": [(name, round(pri, 1)) for pri, name in candidates],
            },
        )
        self.runtime.emit(
            "idle.selected",
            {
                "selected": best.name,
                "priority": round(candidates[0][0], 1),
                "idle_seconds": round(idle_seconds, 1),
                "energy": round(float(energy), 1),
            },
        )
        self._run_async(best)
        return best.name

    def _dispatch_sync(self, fn):
        if self.dispatcher is None:
            return fn()
        done = threading.Event()
        result = {"error": None, "value": None}

        def dispatched():
            try:
                result["value"] = fn()
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        self.dispatcher(dispatched)
        done.wait()
        if result["error"] is not None:
            raise result["error"]
        return result["value"]

    def _run_async(self, behavior):
        self._running_async = True

        def run_behavior():
            try:
                with self.runtime.span("idle.behavior", kind="scheduler", payload={"name": behavior.name}):
                    behavior.execute_fn()
            except Exception as exc:
                self.log_runtime("IDLE_SCHEDULER_ERROR", {"name": behavior.name, "error": str(exc)})
                self.runtime.emit("idle.error", {"name": behavior.name, "error": str(exc)}, level="error")
            finally:
                self._running_async = False

        if self.dispatcher is not None:
            self.dispatcher(run_behavior)
            return

        resources = tuple(str(item) for item in (behavior.resources or ("idle_behavior",)) if item)
        self.runtime.run_background(
            "idle_behavior",
            run_behavior,
            kind="scheduler",
            payload={"name": behavior.name, "resources": list(resources)},
            resources=resources,
            timeout=120,
        )

    def reset_cooldown(self, name, now=None):
        now = time.monotonic() if now is None else float(now)
        for b in self.behaviors:
            if b.name == name:
                b.last_executed_at = now
                b.last_starved_since = now
                break

    def enable(self, name):
        for b in self.behaviors:
            if b.name == name:
                b.enabled = True
                break

    def disable(self, name):
        for b in self.behaviors:
            if b.name == name:
                b.enabled = False
                break
