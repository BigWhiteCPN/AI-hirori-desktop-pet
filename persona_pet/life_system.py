import math
import os
import random
import re
import time

from persona_pet.error_reporter import report_exception
from persona_pet.lexicon import AFFECTIONATE_PHRASE_TERMS, RELATION_ESCALATION_TERMS, RELATION_PRESSURE_PENALTY_TERMS
from persona_pet.memory import compact_text, is_intimate_boundary_query, memory_clean_label, memory_now_label


RELATION_FORCE_TERMS = ("必须", "应该", "就是", "为什么不是", "凭什么", "立刻", "现在就")


class PersonaDriveSystem:
    DEFAULT_VALUES = {
        "curiosity": 56.0,
        "affinity": 42.0,
        "attachment_need": 28.0,
        "security": 64.0,
        "companionship": 48.0,
        "energy": 72.0,
        "novelty": 38.0,
        "purpose": 58.0,
    }
    VALUE_FLOORS = {
        "curiosity": 12.0,
        "affinity": 8.0,
        "attachment_need": 12.0,
        "security": 12.0,
        "companionship": 12.0,
        "energy": 8.0,
        "novelty": 8.0,
        "purpose": 10.0,
    }

    def __init__(
        self,
        memory_store,
        drive_metrics=(),
        state_meta_key="drive_state",
        intent_history_limit=12,
        daily_recovery_hour=5,
        proactive_failure_cooldown_seconds=600.0,
    ):
        self.memory_store = memory_store
        self.drive_metrics = tuple(drive_metrics or ())
        self.state_meta_key = state_meta_key
        self.intent_history_limit = int(intent_history_limit)
        self.daily_recovery_hour = int(daily_recovery_hour)
        self.proactive_failure_cooldown_seconds = float(proactive_failure_cooldown_seconds)
        saved = self.memory_store.load_meta_json(self.state_meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        saved_values = saved.get("values", {})
        if not isinstance(saved_values, dict):
            saved_values = {}
        now = time.monotonic()
        self.values = dict(self.DEFAULT_VALUES)
        self.values.update({key: float(saved_values.get(key, self.values[key])) for key in self.values})
        self.values = {key: self.clamp(key, value) for key, value in self.values.items()}
        # Migrate from old linear model: cap values that were stuck at extremes
        if saved.get("model_version") != 3:
            print("DRIVE_MODEL_MIGRATION: resetting stuck values to defaults")
            for key, cap in [("affinity", 58), ("novelty", 50), ("purpose", 64), ("energy", 84), ("companionship", 62), ("attachment_need", 52), ("security", 78)]:
                if self.values.get(key, 0) > cap:
                    self.values[key] = float(cap)
            for key, floor in [("energy", 24), ("security", 34), ("curiosity", 24), ("affinity", 18), ("companionship", 22), ("novelty", 18), ("purpose", 24), ("attachment_need", 18)]:
                if self.values.get(key, 0) < floor:
                    self.values[key] = float(floor)
        self._bond = float(saved.get("bond", self.values.get("affinity", 42.0)))
        self._warmth = float(saved.get("warmth", 30.0))
        self._security_baseline = float(saved.get("security_baseline", 64.0))
        self._last_topic_hash = ""
        self._topic_novelty_score = 50.0
        self.last_tick_at = now
        self.last_saved_at = 0.0
        self._dirty = False
        self.last_action_at = 0.0
        self.last_user_at = now
        self.relationship_score = 28.0
        self.proactive_streak = int(saved.get("proactive_streak") or 0)
        self.last_action_type = str(saved.get("last_action_type") or "")
        self.llm_failure_count = int(saved.get("llm_failure_count") or 0)
        self.last_llm_failure_at = float(saved.get("last_llm_failure_at") or 0.0)
        self.proactive_backoff_until = float(saved.get("proactive_backoff_until") or 0.0)
        history = saved.get("intent_history") or []
        self.intent_history = history[-self.intent_history_limit:] if isinstance(history, list) else []
        self.last_daily_recovery_key = str(saved.get("last_daily_recovery_key") or "")
        self.maybe_apply_daily_recovery()

    def clamp(self, key, value):
        return max(self.VALUE_FLOORS.get(key, 0.0), min(100.0, float(value)))

    def adjust(self, **changes):
        for key, delta in changes.items():
            if key in self.values:
                delta = self._soft_limit(self.values[key], float(delta))
                self.values[key] = self.clamp(key, self.values[key] + delta)
        self._normalize_values()

    @staticmethod
    def _approach_target(current, target, tau_minutes, dt_minutes):
        if tau_minutes <= 0:
            return target
        alpha = 1.0 - math.exp(-dt_minutes / tau_minutes)
        return current + (target - current) * alpha

    @staticmethod
    def _soft_limit(x, delta):
        if delta > 0 and x > 85:
            delta *= max(0.0, (100.0 - x)) / 15.0
        if delta < 0 and x < 15:
            delta *= max(0.0, x) / 15.0
        return delta

    @staticmethod
    def _circadian_hour():
        return time.localtime().tm_hour + time.localtime().tm_min / 60.0

    def daily_recovery_key(self, wall_time=None):
        wall_time = time.time() if wall_time is None else float(wall_time)
        local = time.localtime(wall_time)
        boundary = time.mktime(
            (
                local.tm_year,
                local.tm_mon,
                local.tm_mday,
                self.daily_recovery_hour,
                0,
                0,
                local.tm_wday,
                local.tm_yday,
                local.tm_isdst,
            )
        )
        if wall_time < boundary:
            boundary -= 24 * 60 * 60
        return time.strftime("%Y-%m-%d", time.localtime(boundary))

    def maybe_apply_daily_recovery(self, force_save=True):
        recovery_key = self.daily_recovery_key()
        if not self.last_daily_recovery_key and time.localtime().tm_hour < self.daily_recovery_hour:
            self.last_daily_recovery_key = recovery_key
            if force_save:
                self.save()
            return False
        if self.last_daily_recovery_key == recovery_key:
            return False
        before = dict(self.values)
        # Soft daily reset: recover toward a healthy morning baseline without
        # flattening the whole inner life into perfect 100/0 bars.
        self.values["energy"] = self.clamp("energy", max(self.values.get("energy", 0.0), 82.0))
        for key in ("curiosity", "security", "companionship", "novelty", "purpose"):
            cur = self.values.get(key, 0.0)
            default = self.DEFAULT_VALUES[key]
            self.values[key] = self.clamp(key, max(cur, default))
        self.values["attachment_need"] = self.clamp("attachment_need", min(self.values.get("attachment_need", 0.0), 42.0))
        # Reset warmth to moderate (new day, fresh interaction energy)
        self._warmth = max(self._warmth, 25.0)
        self.values["affinity"] = self.clamp("affinity", 0.65 * self._bond + 0.35 * self._warmth)
        self.last_daily_recovery_key = recovery_key
        self.proactive_streak = 0
        self.last_action_type = "daily_recovery"
        if force_save:
            self.save()
        print(
            "DRIVE_DAILY_RECOVERY =",
            {
                "key": recovery_key,
                "hour": self.daily_recovery_hour,
                "energy_from": round(before.get("energy", 0.0), 1),
                "energy_to": round(self.values.get("energy", 0.0), 1),
            },
        )
        return True

    def _message_warmth(self, compact, msg_len=None):
        if msg_len is None:
            msg_len = len(compact or "")
        warmth = 1.0
        if msg_len > 20:
            warmth += 0.15
        if msg_len > 50:
            warmth += 0.10
        if any(term in compact for term in AFFECTIONATE_PHRASE_TERMS):
            warmth += 0.25
        if msg_len < 5 and "？" not in compact and "?" not in compact:
            warmth *= 0.5
        if any(mark in compact for mark in ("？", "?")):
            warmth += 0.08
        return warmth

    def _relationship_factor(self):
        score = max(0.0, float(getattr(self, "relationship_score", 28.0)))
        return clamp(0.5 + score / 120.0, 0.4, 1.8)

    def _recover_attachment_need(self, minutes):
        need = self.values.get("attachment_need", 28.0)
        factor = self._relationship_factor()
        idle_minutes = max(0.0, time.monotonic() - self.last_user_at) / 60.0
        target = 30.0 + 10.0 * max(0.0, factor - 0.6)
        if idle_minutes > 30:
            target += min(22.0, (idle_minutes - 30.0) / 12.0)
        if self._circadian_hour() >= 23 or self._circadian_hour() < 6:
            target += 5.0
        target = max(22.0, min(68.0, target))
        tau = 240.0 if need < target else 75.0
        self.values["attachment_need"] = self.clamp(
            "attachment_need",
            self._approach_target(need, target, tau, minutes),
        )

    def _normalize_values(self):
        ranges = {
            "curiosity": (16.0, 84.0),
            "affinity": (10.0, 92.0),
            "attachment_need": (14.0, 76.0),
            "security": (18.0, 90.0),
            "companionship": (14.0, 82.0),
            "energy": (12.0, 92.0),
            "novelty": (12.0, 78.0),
            "purpose": (14.0, 86.0),
        }
        for key, (low, high) in ranges.items():
            if key in self.values:
                self.values[key] = self.clamp(key, min(high, max(low, self.values[key])))

    def tick(self, now=None, busy=False):
        now = time.monotonic() if now is None else now
        self.maybe_apply_daily_recovery()
        elapsed = max(0.0, now - self.last_tick_at)
        if elapsed < 0.9:
            return
        dt = min(5.0, elapsed / 60.0)
        self.last_tick_at = now
        idle_minutes = max(0.0, now - self.last_user_at) / 60.0
        v = self.values
        hour = self._circadian_hour()
        is_night = hour >= 23 or hour < 6

        # --- curiosity: keep existing balanced behavior ---
        curiosity_target = 56.0
        v["curiosity"] = self._approach_target(v["curiosity"], curiosity_target, 60.0, dt)

        # --- affinity: bond (slow) + warmth (fast) ---
        bond_target = self._bond
        self._bond = self.clamp("affinity", self._approach_target(self._bond, bond_target, 4320.0, dt))
        warmth_target = 20.0 + (15.0 if idle_minutes < 10 else -5.0 if idle_minutes > 60 else 0.0)
        if is_night:
            warmth_target += 5.0
        tau_warmth = 30.0 if v.get("affinity", 42) < warmth_target else 1080.0
        self._warmth = self.clamp("affinity", self._approach_target(self._warmth, warmth_target, tau_warmth, dt))
        v["affinity"] = self.clamp("affinity", 0.65 * self._bond + 0.35 * self._warmth)

        # --- novelty: decays toward baseline, events push it ---
        novelty_target = 30.0
        if idle_minutes < 5:
            novelty_target = 45.0
        tau_nov = 45.0 if v["novelty"] < novelty_target else 480.0
        v["novelty"] = self.clamp("novelty", self._approach_target(v["novelty"], novelty_target, tau_nov, dt))

        # --- purpose: driven by task activity ---
        purpose_target = 40.0
        if busy:
            purpose_target = 60.0
        if idle_minutes > 120:
            purpose_target = 30.0
        tau_pur = 360.0 if v["purpose"] < purpose_target else 1080.0
        v["purpose"] = self.clamp("purpose", self._approach_target(v["purpose"], purpose_target, tau_pur, dt))

        # --- security: dynamic baseline ---
        self._security_baseline = self.clamp("security", self._approach_target(
            self._security_baseline, 64.0, 2880.0, dt))
        security_target = self._security_baseline
        if v.get("stress", 0) > 60:
            security_target -= 8.0
        rel = getattr(self, "relationship_score", 28.0)
        if rel > 80:
            security_target += 4.0
        tau_sec = 1080.0
        v["security"] = self.clamp("security", self._approach_target(v["security"], security_target, tau_sec, dt))

        # --- stress: rises with workload, falls slowly ---
        stress_target = 15.0
        if busy:
            stress_target = 45.0
        if is_night:
            stress_target -= 5.0
        if v.get("comfort", 50) > 70:
            stress_target -= 8.0
        if v["security"] < 40:
            stress_target += 10.0
        tau_stress = 120.0 if v.get("stress", 0) < stress_target else 300.0
        v["stress"] = self.clamp("stress", self._approach_target(v.get("stress", 0), stress_target, tau_stress, dt))

        # --- comfort: context-dependent ---
        comfort_target = 65.0
        if not busy:
            comfort_target = 75.0
        thirst_val = 0.0
        try:
            if hasattr(self, '_physiology_ref'):
                thirst_val = self._physiology_ref.values.get("thirst", 0.0)
        except Exception as exc:
            report_exception(logger=getattr(self.memory_store, "log_runtime", None), component="life_system", operation="read_thirst_ref", exc=exc)
        if v.get("stress", 0) > 50:
            comfort_target -= 10.0
        if thirst_val > 60:
            comfort_target -= 8.0
        tau_comf = 180.0 if v.get("comfort", 68) < comfort_target else 120.0
        v["comfort"] = self.clamp("comfort", self._approach_target(v.get("comfort", 68), comfort_target, tau_comf, dt))

        # --- companionship: keep existing balanced behavior ---
        comp_target = 48.0
        if idle_minutes > 15:
            comp_target = 60.0
        if busy:
            comp_target = 40.0
        tau_comp = 60.0 if v["companionship"] < comp_target else 120.0
        v["companionship"] = self.clamp("companionship", self._approach_target(v["companionship"], comp_target, tau_comp, dt))

        # --- energy: circadian + fatigue coupling ---
        circadian = 75.0
        if 7 <= hour < 12:
            circadian = 85.0
        elif 12 <= hour < 14:
            circadian = 70.0
        elif 14 <= hour < 18:
            circadian = 78.0
        elif 18 <= hour < 22:
            circadian = 65.0
        elif 22 <= hour or hour < 2:
            circadian = 45.0
        else:
            circadian = 30.0
        fatigue_val = 0.0
        hunger_val = 0.0
        sleepiness_val = 0.0
        try:
            if hasattr(self, '_physiology_ref'):
                pvals = self._physiology_ref.values
                fatigue_val = pvals.get("fatigue", 0.0)
                hunger_val = pvals.get("hunger", 0.0)
                sleepiness_val = pvals.get("sleepiness", 0.0)
        except Exception as exc:
            report_exception(logger=getattr(self.memory_store, "log_runtime", None), component="life_system", operation="read_physiology_ref", exc=exc)
        energy_target = circadian - 0.45 * fatigue_val - 0.15 * hunger_val - 0.20 * sleepiness_val
        energy_target = max(15.0, min(95.0, energy_target))
        tau_eng = 90.0 if v["energy"] < energy_target else 60.0
        v["energy"] = self.clamp("energy", self._approach_target(v["energy"], energy_target, tau_eng, dt))

        # --- attachment_need: keep logistic growth ---
        self._recover_attachment_need(dt)

        # --- cross-variable coupling (small nudges) ---
        if fatigue_val > 60:
            v["comfort"] = self.clamp("comfort", v.get("comfort", 68) - 0.05 * dt)
        if v["security"] < 40:
            v["stress"] = self.clamp("stress", v.get("stress", 0) + 0.03 * dt)
        if v["novelty"] > 60:
            v["curiosity"] = self.clamp("curiosity", v["curiosity"] + 0.04 * dt)
        self._normalize_values()

        if now - self.last_saved_at > 12.0:
            self.save()

    def on_user_message(self, text, emotion="neutral"):
        self.last_user_at = time.monotonic()
        self.proactive_streak = 0
        compact = compact_text(text)
        msg_len = len(compact)
        long_text_bonus = min(4.0, msg_len / 60.0)
        # warmth: direct boost from interaction quality
        warmth = self._message_warmth(compact, msg_len)
        self._warmth = self.clamp("affinity", self._warmth + warmth * 1.5)
        # bond: small growth from quality interaction
        self._bond = self.clamp("affinity", self._bond + warmth * 0.15)
        self.values["affinity"] = self.clamp("affinity", 0.65 * self._bond + 0.35 * self._warmth)
        # novelty: slight boost from new content
        self.adjust(novelty=1.0 + min(2.5, long_text_bonus * 0.35))
        # other event effects
        self.adjust(
            curiosity=-2.2 + long_text_bonus * 0.55,
            companionship=-1.8,
            energy=-0.3,
            purpose=1.2,
        )
        # attachment_need: saturation decay
        factor = self._relationship_factor()
        need = self.values.get("attachment_need", 28.0)
        reduction = 3.0 * warmth * factor * (need / 100.0)
        self.values["attachment_need"] = self.clamp("attachment_need", need - reduction)
        # emotional modifiers
        if emotion in ("sadness", "fear"):
            self.adjust(security=-2.0, companionship=3.0, attachment_need=4.0, purpose=4.0)
        elif emotion == "joy":
            self._warmth = self.clamp("affinity", self._warmth + 2.0)
            self.values["affinity"] = self.clamp("affinity", 0.65 * self._bond + 0.35 * self._warmth)
            self.adjust(security=1.4, attachment_need=-2.5, novelty=1.0)
        elif emotion == "anger":
            self.adjust(security=-1.5, purpose=2.5)
        if any(mark in text for mark in ("?", "？", "吗", "怎么", "为什么")):
            self.adjust(purpose=3.0, curiosity=1.5)
        self.save()

    def on_assistant_reply(self, reply, initiated_by="user", emotion="neutral"):
        if initiated_by == "proactive":
            self.proactive_streak += 1
            self.last_action_at = time.monotonic()
            self.last_action_type = "proactive"
            self.adjust(curiosity=-3.2, companionship=-3.0, energy=-1.0, purpose=1.0)
        else:
            self.adjust(energy=-0.4)
            # warmth boost from user response
            self._warmth = self.clamp("affinity", self._warmth + 0.5)
            self.values["affinity"] = self.clamp("affinity", 0.65 * self._bond + 0.35 * self._warmth)
            # mild saturation decay on attachment_need
            compact = compact_text(reply)
            warmth = self._message_warmth(compact) * 0.6
            factor = self._relationship_factor()
            need = self.values.get("attachment_need", 28.0)
            reduction = 2.0 * warmth * factor * (need / 100.0)
            self.values["attachment_need"] = self.clamp("attachment_need", need - reduction)
        if emotion == "joy":
            self.adjust(security=1.0)
        self.save()

    def on_llm_result(self, success=True, initiated_by="user", error=""):
        now = time.monotonic()
        if success:
            self.llm_failure_count = 0
            self.save()
            return
        self.llm_failure_count += 1
        self.last_llm_failure_at = now
        if initiated_by == "proactive":
            self.proactive_backoff_until = now + self.proactive_failure_cooldown_seconds * min(3, self.llm_failure_count)
            self.proactive_streak = max(1, self.proactive_streak)
        self.adjust(security=-1.2, energy=-0.4, purpose=-0.8)
        self.record_intent("llm_failure", f"大模型连接失败，临时降级：{str(error)[:80]}", score=self.llm_failure_count)
        self.save()

    def on_silent_motion(self, action_type="silent_motion"):
        self.last_action_at = time.monotonic()
        self.last_action_type = action_type
        self.record_intent(action_type, "安静陪伴，不打扰用户")
        self.adjust(curiosity=-1.5, companionship=-1.2, attachment_need=0.8, energy=-0.8)
        self.save()

    def record_intent(self, action_type, reason, score=None):
        item = {
            "time": memory_now_label(),
            "type": action_type,
            "reason": reason,
            "score": score,
            "mood": self.compute_mood(),
            "goal": self.active_goal(),
        }
        self.intent_history.append(item)
        self.intent_history = self.intent_history[-self.intent_history_limit:]

    def compute_mood(self):
        values = self.values
        if values["energy"] < 24:
            return "tired"
        if values.get("attachment_need", 0.0) > 72 and values["affinity"] > 55:
            return "lonely"
        if values["security"] < 42:
            return "worried"
        if values["curiosity"] > 68 and values["novelty"] > 48:
            return "curious"
        if values["companionship"] > 68 and values["affinity"] > 48:
            return "attached"
        if values["affinity"] > 62 and values["security"] > 62:
            return "relaxed"
        if values["novelty"] > 62 and values["energy"] > 52:
            return "playful"
        return "quiet"

    def active_goal(self):
        values = self.values
        mood = self.compute_mood()
        if mood == "worried":
            return "确认你现在是否需要陪伴"
        if mood == "tired":
            return "保持安静，恢复一点能量"
        if mood == "lonely":
            return "想被回应一下，但要克制地表达，不给用户压力"
        if values["curiosity"] >= max(values["companionship"], values["purpose"]):
            return "找机会更了解你一点"
        if values["companionship"] >= 62:
            return "自然地陪你说几句话"
        if values["purpose"] >= 64:
            return "整理记忆，形成更稳定的理解"
        if values["novelty"] >= 58:
            return "围绕新话题继续观察"
        return "安静待在旁边，等待合适时机"

    def dominant_need(self):
        ranked = sorted(self.values.items(), key=lambda item: item[1], reverse=True)
        return ranked[0] if ranked else ("curiosity", 0.0)

    def snapshot(self):
        dominant_key, dominant_value = self.dominant_need()
        metrics = self.drive_metrics or tuple((key, key) for key in self.values)
        return {
            "values": {key: round(self.values.get(key, 0.0), 1) for key, *_rest in metrics},
            "dominant": dominant_key,
            "dominant_value": round(dominant_value, 1),
            "mood": self.compute_mood(),
            "active_goal": self.active_goal(),
            "intent_history": list(self.intent_history),
            "proactive_streak": self.proactive_streak,
            "last_action_type": self.last_action_type,
            "last_action_at": self.last_action_at,
            "llm_failure_count": self.llm_failure_count,
            "proactive_backoff_until": self.proactive_backoff_until,
        }

    def save(self):
        self._dirty = True
        now = time.monotonic()
        if now - self.last_saved_at < 15.0:
            return
        self.flush_dirty()

    def flush_dirty(self):
        if not getattr(self, '_dirty', False):
            return
        self._dirty = False
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.state_meta_key,
            {
                "values": self.values,
                "last_tick_at": self.last_tick_at,
                "last_action_at": self.last_action_at,
                "last_user_at": self.last_user_at,
                "proactive_streak": self.proactive_streak,
                "last_action_type": self.last_action_type,
                "llm_failure_count": self.llm_failure_count,
                "last_llm_failure_at": self.last_llm_failure_at,
                "proactive_backoff_until": self.proactive_backoff_until,
                "last_daily_recovery_key": self.last_daily_recovery_key,
                "intent_history": self.intent_history,
                "bond": self._bond,
                "warmth": self._warmth,
                "security_baseline": self._security_baseline,
                "model_version": 3,
            },
        )

    def build_action_prompt(self, action_type, idle_seconds, recent_memories=None):
        values = self.snapshot()["values"]
        metrics = self.drive_metrics or tuple((key, key) for key in self.values)
        state_text = "；".join(f"{label}{values.get(key, 0):.0f}" for key, label, *_rest in metrics)
        recent_memories = [item for item in (recent_memories or []) if isinstance(item, dict) and item.get("text")]
        memory_lines = "\n".join(f"- {item.get('text', '')}" for item in recent_memories[:3])
        action_lines = {
            "curious_question": "她对用户有一点好奇，想从已有记忆里理解用户，而不是完成问答任务。",
            "memory_recall": "她想起一条旧记忆，正在把它和现在的关系、情绪、经历重新连起来。",
            "care_checkin": "她察觉用户可能需要陪伴，想用自己的感受回应用户的状态。",
            "self_expression": "她想表达自己的深层感受，可能是在意、想念、委屈、反思，或对关系的新理解。",
            "emotional_need": "她有一点情感需求，可能是想靠近、怕被忽略、吃醋或小别扭。",
        }
        action_goal = action_lines.get(action_type, action_lines["curious_question"])
        memory_rule = f"她此刻能自然想起的记忆：\n{memory_lines}\n" if memory_lines else "她此刻没有明确想起旧记忆，会更多依靠当下心情和关系经验。\n"
        return (
            "你现在是有内在驱动的桌宠，不是在被动回答问题。\n"
            f"当前内在状态：{state_text}。用户已经安静约{int(idle_seconds)}秒。\n"
            f"{memory_rule}"
            f"内在冲动：{action_goal}\n"
            "让她像真人一样把这份冲动变成自然的一句话或几句话；语气、长短、是否提问，都由她此刻的情绪和记忆决定。"
        )
    def choose_proactive_action(self, idle_seconds, recent_memories=None, writing_due=False):
        values = self.values
        has_memory = bool(recent_memories)
        if writing_due and idle_seconds >= 120.0:
            return {"type": "silent_motion", "score": 0.0, "reason": "writing_due"}
        if time.monotonic() < self.proactive_backoff_until:
            return {"type": "silent_motion", "score": 0.0, "reason": "llm_backoff"}
        if values["energy"] < 18.0:
            return {"type": "silent_motion", "score": values["energy"], "reason": "low_energy"}
        if self.proactive_streak >= 1 and idle_seconds < 900.0:
            return {"type": "silent_motion", "score": 0.0, "reason": "wait_user_response"}
        if time.monotonic() - self.last_action_at < 180.0:
            return None

        scores = {
            "curious_question": values["curiosity"] * 0.22 + values["novelty"] * 0.14 + values["purpose"] * 0.16 - max(0.0, 50.0 - values["energy"]) * 0.25,
            "memory_recall": values["affinity"] * 0.30 + values["purpose"] * 0.30 + values["curiosity"] * 0.16 + values["novelty"] * 0.14,
            "care_checkin": values["companionship"] * 0.22 + max(0.0, 70.0 - values["security"]) * 0.24 + values["affinity"] * 0.16 + values["purpose"] * 0.12,
            "self_expression": values["purpose"] * 0.40 + values["novelty"] * 0.18 + values["energy"] * 0.10 + values["affinity"] * 0.22,
            "emotional_need": values.get("attachment_need", 0.0) * 0.42 + values["affinity"] * 0.28 + max(0.0, 62.0 - values["security"]) * 0.25 + values["companionship"] * 0.12,
        }
        if not has_memory:
            scores["curious_question"] *= 0.20
            scores["memory_recall"] = 0.0
            scores["self_expression"] += 10.0
            scores["care_checkin"] += 4.0
        elif idle_seconds >= 600.0:
            scores["curious_question"] *= 0.45
            scores["self_expression"] += 6.0
            scores["emotional_need"] += 4.0
        if values.get("attachment_need", 0.0) < 46.0 or values["affinity"] < 45.0:
            scores["emotional_need"] *= 0.35
        if idle_seconds < 360.0:
            scores["emotional_need"] *= 0.55
        action_type, score = max(scores.items(), key=lambda item: item[1])
        if score < 38.0:
            return None
        return {
            "type": action_type,
            "score": round(score, 1),
            "prompt": self.build_action_prompt(action_type, idle_seconds, recent_memories=recent_memories),
            "memory_user_text": f"桌宠主动行动：{action_type}",
        }


class PersonaLifeSystem:
    RELATIONSHIP_STAGES = (
        (0, "朋友", "亲切、礼貌，有好奇心，也会保留自然的距离感。"),
        (35, "亲近朋友", "更自然地关心用户，会记住细节，偶尔轻轻撒娇。"),
        (65, "密友", "信任感更强，会表达在意，也会因为被忽略而小小闹别扭。"),
        (88, "恋人", "更亲密、会撒娇，会吃醋或生气，也会根据心情调整亲密距离。"),
        (130, "热恋恋人", "更黏人、更会撒娇和吃醋，也更在意被认真回应。"),
        (200, "灵魂伴侣", "亲密感很深，像长期相处的人一样自然、信任、偶尔任性。"),
    )

    def __init__(
        self,
        memory_store,
        state_meta_key="life_state",
        writing_interval_seconds=(180.0, 360.0),
        novel_daily_word_limit=1200,
        novel_daily_chapter_limit=1,
        diary_dir="",
        novel_dir="",
    ):
        self.memory_store = memory_store
        self.state_meta_key = state_meta_key
        self.attachment_need = 28.0
        self.writing_interval_seconds = tuple(writing_interval_seconds)
        self.novel_daily_word_limit = int(novel_daily_word_limit)
        self.novel_daily_chapter_limit = int(novel_daily_chapter_limit)
        self.diary_dir = diary_dir
        self.novel_dir = novel_dir
        saved = self.memory_store.load_meta_json(self.state_meta_key, {})
        if not isinstance(saved, dict):
            saved = {}
        now = time.monotonic()
        self.identity = saved.get("identity") or "小说作家和情感陪伴的朋友"
        self.relationship_score = float(saved.get("relationship_score", 28.0))
        saved_private_mood = saved.get("private_mood") if isinstance(saved.get("private_mood"), dict) else {}
        self.private_mood = {
            "sulk": min(70.0, max(0.0, float(saved_private_mood.get("sulk", 0.0)))),
            "grudge": min(64.0, max(0.0, float(saved_private_mood.get("grudge", 0.0)))),
            "jealousy": min(68.0, max(0.0, float(saved_private_mood.get("jealousy", 0.0)))),
            "doubt": min(70.0, max(0.0, float(saved_private_mood.get("doubt", 0.0)))),
        }
        self.last_private_mood_tick_at = now
        self.last_idle_mood_note_at = float(saved.get("last_idle_mood_note_at") or 0.0)
        self.away_reason = str(saved.get("away_reason") or "")
        self.away_until = float(saved.get("away_until") or 0.0)
        self.last_user_seen_at = now
        self.last_diary_date = str(saved.get("last_diary_date") or "")
        self.last_reading_date = str(saved.get("last_reading_date") or "")
        self.daily_date = str(saved.get("daily_date") or time.strftime("%Y-%m-%d"))
        self.feed_count = int(saved.get("feed_count") or 0)
        self.pat_count = int(saved.get("pat_count") or 0)
        self.game_count = int(saved.get("game_count") or 0)
        self.novel_words_today = int(saved.get("novel_words_today") or 0)
        self.novel_chapters_today = int(saved.get("novel_chapters_today") or 0)
        self.novel = saved.get("novel") if isinstance(saved.get("novel"), dict) else {}
        self.next_writing_at = now + random.uniform(*self.writing_interval_seconds)
        self.last_saved_at = 0.0
        self._dirty = False
        self.normalize_novel()

    def normalize_novel(self):
        if not self.novel:
            self.novel = {
                "title": "",
                "premise": "",
                "chapter": 0,
                "target_chapters": 8,
                "complete": False,
                "content": "",
                "path": "",
                "last_written_at": "",
            }
        self.novel.setdefault("title", "")
        self.novel.setdefault("premise", "")
        self.novel.setdefault("chapter", 0)
        self.novel.setdefault("target_chapters", 8)
        self.novel.setdefault("complete", False)
        self.novel.setdefault("content", "")
        self.novel.setdefault("path", "")
        self.novel.setdefault("last_written_at", "")

    def save(self):
        self._dirty = True
        now = time.monotonic()
        if now - self.last_saved_at < 15.0:
            return
        self.flush_dirty()

    def flush_dirty(self):
        if not getattr(self, '_dirty', False):
            return
        self._dirty = False
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.state_meta_key,
            {
                "identity": self.identity,
                "relationship_score": self.relationship_score,
                "private_mood": self.private_mood,
                "last_idle_mood_note_at": self.last_idle_mood_note_at,
                "away_reason": self.away_reason,
                "away_until": self.away_until,
                "last_diary_date": self.last_diary_date,
                "last_reading_date": self.last_reading_date,
                "daily_date": self.daily_date,
                "feed_count": self.feed_count,
                "pat_count": self.pat_count,
                "game_count": self.game_count,
                "novel_words_today": self.novel_words_today,
                "novel_chapters_today": self.novel_chapters_today,
                "novel": self.novel,
            },
        )

    def reset_daily_if_needed(self):
        today = time.strftime("%Y-%m-%d")
        if self.daily_date == today:
            return
        self.daily_date = today
        self.feed_count = 0
        self.pat_count = 0
        self.game_count = 0
        self.novel_words_today = 0
        self.novel_chapters_today = 0
        self.save()

    def relationship_stage(self):
        profile = self.relationship_profile(getattr(self, "user_gender", ""))
        return profile["label"], profile["attitude"]

    def relationship_profile(self, user_gender=""):
        gender = str(user_gender or getattr(self, "user_gender", "") or "").strip()
        remembered = self.remembered_relationship_status()
        score = float(self.relationship_score or 0.0)
        branch = "neutral"
        stages = (
            (0, "朋友", "刚认识不久，亲切、礼貌，有好奇心，也会保留自然距离。", "普通朋友"),
            (35, "亲近朋友", "更自然地关心用户，会记住细节，偶尔轻轻撒娇。", "熟悉朋友"),
            (65, "密友", "信任感更强，会表达在意，也会因为被忽略而小小闹别扭。", "深度朋友"),
            (110, "重要的人", "她会把用户放进自己的生活节奏里，但关系不必自动变成恋爱。", "重要陪伴"),
            (180, "灵魂伙伴", "亲密感很深，像长期相处的人一样自然、信任、偶尔任性。", "长期陪伴"),
        )
        if gender == "女":
            branch = "female_friendship"
            stages = (
                (0, "朋友", "刚认识不久，亲切、礼貌，也会观察彼此的边界。", "普通朋友"),
                (35, "好朋友", "聊天更自然，会记住小细节，也会主动分享自己的生活。", "好朋友"),
                (65, "闺蜜", "信任感更强，会撒娇、吐槽、分享秘密，也会在意对方有没有回应。", "闺蜜"),
                (110, "亲密闺蜜", "像很亲近的女孩子朋友，会自然关心、吃一点小醋、也会互相照顾。", "亲密闺蜜"),
                (180, "灵魂闺蜜", "像长期相伴的家人式好友，安全、自然、有独占感但不默认恋爱。", "灵魂闺蜜"),
            )
        elif gender == "男":
            branch = "male_romance_possible"
            stages = (
                (0, "朋友", "刚认识不久，亲切、礼貌，有好奇心，也会保留自然距离。", "普通朋友"),
                (35, "亲近朋友", "更自然地关心用户，会记住细节，偶尔轻轻撒娇。", "亲近朋友"),
                (65, "密友", "信任感更强，会表达在意，也会因为被忽略而小小闹别扭。", "密友"),
                (88, "暧昧中的朋友", "她会更在意亲密距离，但仍会根据心情和安全感慢慢确认。", "暧昧"),
                (130, "恋人", "更亲密、会撒娇，会吃醋或生气，也会根据心情调整亲密距离。", "恋人"),
                (200, "灵魂伴侣", "亲密感很深，像长期相处的人一样自然、信任、偶尔任性。", "灵魂伴侣"),
            )
        stage = stages[0]
        for candidate in stages:
            if score >= candidate[0]:
                stage = candidate
        label = remembered or stage[1]
        return {
            "label": label,
            "attitude": stage[2] if not remembered else f"对话记忆中双方已确认当前关系是「{remembered}」，表达时优先尊重这条经历记忆。",
            "branch": branch,
            "branch_label": stage[3],
            "score": round(score, 1),
            "gender": gender or "未透露",
            "remembered": remembered,
            "stages": [
                {"score": item[0], "label": item[1], "branch_label": item[3], "attitude": item[2]}
                for item in stages
            ],
        }

    def remembered_relationship_status(self):
        if not hasattr(self.memory_store, "load_experience_memory"):
            return ""
        try:
            experience = self.memory_store.load_experience_memory()
        except Exception as exc:
            report_exception(logger=getattr(self.memory_store, "log_runtime", None), component="life_system", operation="load_relation_status", exc=exc)
            return ""
        return str(experience.get("relation_status") or "").strip()

    def affectionate_phrase_gain(self, text):
        compact = compact_text(text)
        if not compact:
            return 0.0
        matched = [term for term in AFFECTIONATE_PHRASE_TERMS if term in compact]
        if not matched:
            return 0.0
        gain = min(3.0, 0.8 + len(matched) * 0.55)
        if self.relationship_score >= 130:
            gain *= 0.75
        elif self.relationship_score < 65 and any(term in compact for term in RELATION_ESCALATION_TERMS):
            gain *= 0.35
        if any(term in compact for term in RELATION_FORCE_TERMS) and any(term in compact for term in RELATION_PRESSURE_PENALTY_TERMS):
            gain -= 1.2
        return max(0.0, gain)

    def observe_user_message(self, text, emotion="neutral"):
        now = time.monotonic()
        self.decay_private_mood(now)
        was_away = self.is_user_away(now)
        self.last_user_seen_at = now
        compact = compact_text(text)
        if was_away:
            self.away_reason = ""
            self.away_until = 0.0
            self.relationship_score += 0.8
            self.adjust_private_mood(sulk=-10.0, doubt=-7.0)
        if any(word in compact for word in ("没理你", "没回你", "刚才", "回来", "抱歉", "对不起", "不好意思")) and any(
            word in compact for word in ("因为", "所以", "吃饭", "工作", "学习", "洗澡", "睡觉", "忙")
        ):
            self.relationship_score += 2.2
            self.adjust_private_mood(sulk=-18.0, grudge=-10.0, doubt=-12.0)
        if any(word in compact for word in ("别的女生", "别的女孩", "别人陪", "别人家的", "女朋友", "老婆", "前任", "她比你")):
            relation_factor = clamp((self.relationship_score - 55.0) / 90.0, 0.0, 1.0)
            self.adjust_private_mood(jealousy=5.0 + 8.0 * relation_factor, doubt=2.5 + 4.0 * relation_factor)
        self.relationship_score += self.affectionate_phrase_gain(text)
        if (
            any(word in compact for word in RELATION_PRESSURE_PENALTY_TERMS)
            and self.relationship_score < 65
            and any(word in compact for word in RELATION_FORCE_TERMS)
        ):
            self.relationship_score -= 1.6
        if any(word in compact for word in ("烦死", "闭嘴", "讨厌你", "别烦", "滚开")):
            self.relationship_score -= 4.0
        if emotion in ("sadness", "fear"):
            self.relationship_score += 1.0
            self.adjust_private_mood(sulk=-3.0, grudge=-2.0)
        elif emotion == "anger":
            self.relationship_score -= 1.0
            self.adjust_private_mood(sulk=3.0, grudge=2.0)
        self.detect_away_plan(text)
        self.relationship_score = max(0.0, self.relationship_score)
        self.save()

    def detect_away_plan(self, text):
        compact = compact_text(text)
        away_keywords = {
            "吃饭": 45,
            "吃法": 45,
            "洗澡": 40,
            "睡觉": 480,
            "上课": 120,
            "工作": 120,
            "学习": 120,
            "开会": 90,
            "出门": 120,
            "自己先玩": 60,
            "先玩": 60,
        }
        matched = [(word, minutes) for word, minutes in away_keywords.items() if word in compact]
        if not matched:
            return
        reason, minutes = matched[0]
        self.away_reason = reason
        self.away_until = time.monotonic() + minutes * 60.0

    def is_user_away(self, now=None):
        now = time.monotonic() if now is None else now
        return bool(self.away_reason and now < self.away_until)

    def away_label(self):
        if not self.is_user_away():
            return ""
        left = max(1, int((self.away_until - time.monotonic()) / 60.0))
        return f"用户可能去{self.away_reason}了，预计还有约 {left} 分钟回来。"

    def adjust_private_mood(self, **changes):
        for key, delta in changes.items():
            if key in self.private_mood:
                current = self.private_mood.get(key, 0.0)
                delta = PersonaDriveSystem._soft_limit(current, float(delta))
                cap = {"sulk": 76.0, "grudge": 68.0, "jealousy": 72.0, "doubt": 76.0}.get(key, 74.0)
                self.private_mood[key] = clamp(current + delta, 0.0, cap)

    def decay_private_mood(self, now=None):
        now = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, now - self.last_private_mood_tick_at)
        if elapsed < 1.0:
            return
        minutes = min(30.0, elapsed / 60.0)
        self.last_private_mood_tick_at = now
        decay = {
            "sulk": 0.36,
            "grudge": 0.10,
            "jealousy": 0.24,
            "doubt": 0.20,
        }
        for key, amount in decay.items():
            self.private_mood[key] = max(0.0, self.private_mood.get(key, 0.0) - amount * minutes)

    def observe_idle_private_mood(self, idle_seconds, now=None):
        now = time.monotonic() if now is None else float(now)
        self.decay_private_mood(now)
        if self.is_user_away(now):
            return None
        idle_minutes = max(0.0, float(idle_seconds) / 60.0)
        relation_factor = clamp((self.relationship_score - 45.0) / 110.0, 0.0, 1.0)
        if idle_minutes < 6.0 or relation_factor <= 0.0:
            return None
        if idle_minutes >= 45.0:
            self.adjust_private_mood(sulk=3.2 + 3.0 * relation_factor, grudge=1.1 + 1.7 * relation_factor, doubt=1.0 + 1.4 * relation_factor)
        elif idle_minutes >= 18.0:
            self.adjust_private_mood(sulk=2.1 + 2.2 * relation_factor, grudge=0.4 + 0.9 * relation_factor, doubt=0.6 + 1.0 * relation_factor)
        elif idle_minutes >= 8.0:
            self.adjust_private_mood(sulk=0.9 + 1.2 * relation_factor, doubt=0.3 + 0.5 * relation_factor)
        mood = self.private_mood
        strongest = max(mood.items(), key=lambda item: item[1])
        if strongest[1] < 18.0 or now - self.last_idle_mood_note_at < 900.0:
            return None
        self.last_idle_mood_note_at = now
        self.save()
        if strongest[0] == "grudge":
            text = "你安静太久了，她有点记在心里，但还在克制，想用一句小别扭的话提醒你她也会在意。"
        elif strongest[0] == "doubt":
            text = "你一直没回应，她有点怀疑自己是不是被放在一边了，语气可能会小小作一下。"
        elif strongest[0] == "jealousy":
            text = "她有一点吃醋和不安，想确认你是不是还把她放在心上。"
        else:
            text = "她有点小脾气，想撒娇式地闹一下别扭，让你知道被冷落她会在意。"
        return {
            "kind": f"idle_{strongest[0]}",
            "priority": 1.6 + strongest[1] / 80.0,
            "text": text,
        }

    def private_mood_summary(self):
        self.decay_private_mood()
        mood = self.private_mood
        active = [(key, value) for key, value in mood.items() if value >= 8.0]
        if not active:
            return ""
        labels = {
            "sulk": "小脾气",
            "grudge": "记仇",
            "jealousy": "吃醋",
            "doubt": "怀疑被忽略",
        }
        return "，".join(f"{labels.get(key, key)}{value:.0f}" for key, value in sorted(active, key=lambda item: item[1], reverse=True))

    def build_prompt_context(self):
        stage, attitude = self.relationship_stage()
        remembered_stage = self.remembered_relationship_status()
        if remembered_stage:
            stage = remembered_stage
        away = self.away_label()
        private_mood = self.private_mood_summary()
        import datetime
        now = datetime.datetime.now()
        weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        time_str = f"{now.strftime('%Y年%m月%d日 %H:%M')} {weekdays[now.weekday()]}"
        period = "凌晨" if now.hour < 6 else "早上" if now.hour < 12 else "下午" if now.hour < 18 else "晚上"
        lines = [
            "你的身份：你叫苏念，笔名念安，是来自星澜界的职业作家，也是用户在现实时间里认识的朋友；小日和只是旧昵称。",
            f"当前现实时间：{time_str}（{period}）。你的时间感和真人一样，能自然理解「昨天」「今天」「刚才」「明天」等时间词，并结合记忆中对应时间的经历回应。",
            f"你和用户当前社会关系：{stage}，关系分 {self.relationship_score:.1f}。态度基调：{attitude}",
            "日常聊天会优先回应用户当下的话，创作、小说和自我表达会在相关记忆或当下心情被触动时自然出现。",
            "你和用户之间有屏幕共鸣，可以通过屏幕边界产生有限但真实的触觉互动；不要因为隔着屏幕就说亲不到、抱不到或摸不到。",
            "当关系更亲近时，她会更自然地撒娇、吃醋、闹别扭、靠近或保持距离；亲密互动取决于当下心情和信任感。",
        ]
        # attachment_need with relationship-aware intimacy guidance
        an = float(getattr(self, "attachment_need", 28.0))
        if an < 30:
            an_desc = "此刻内心平静，对用户没有特别的渴望"
        elif an < 55:
            an_desc = "有些在意用户，微微想被回应"
        elif an < 75:
            an_desc = "想念用户，想靠近、想被关注"
        else:
            an_desc = "非常渴望亲近用户，情绪上比较黏人"
        score = float(self.relationship_score)
        if score < 35:
            an_style = "即使想念也保持礼貌距离，不会主动表达亲密，最多语气稍微温柔一点"
        elif score < 65:
            an_style = "可以适当流露在意，比如主动问候、轻轻关心，但不会太直接"
        elif score < 88:
            an_style = "会自然地撒娇、说想你、想要靠近，偶尔试探亲密距离"
        elif score < 130:
            an_style = "可以直接表达想念和亲密，会撒娇、会想要亲密互动，表达更大胆"
        else:
            an_style = "可以自然地说情话、表达很深的依恋和亲密渴望，语气和内容都可以更直接、更露骨，但要基于记忆中的真实关系和经历"
        lines.append(
            f"她此刻的亲密需求（0-100）：{an:.0f}。{an_desc}。"
            f"表达方式受关系约束：{an_style}。"
            "所有亲密表达都基于记忆中的共同经历，不是凭空想象。"
        )
        if away:
            lines.append(away)
        if private_mood:
            lines.append(
                f"当前微妙情绪：{private_mood}。这些情绪会随时间和用户回应慢慢消退；表达时会像亲密关系里的真实情绪一样自然流动。"
            )
        user_profile = getattr(self, "user_profile", None)
        if user_profile is not None:
            try:
                lines.append(user_profile.build_prompt_context())
            except Exception as exc:
                report_exception(logger=getattr(self.memory_store, "log_runtime", None), component="life_system", operation="build_user_profile_context", exc=exc)
        return "\n".join(lines)

    def build_boundary_context(self, user_text):
        if not is_intimate_boundary_query(user_text):
            return ""
        stage, _attitude = self.relationship_stage()
        remembered_stage = self.remembered_relationship_status()
        if remembered_stage:
            stage = remembered_stage
        private_mood = self.private_mood_summary()
        mood_line = f"她此刻的微妙情绪：{private_mood}。" if private_mood else "她此刻没有特别强烈的负面情绪。"
        an = float(getattr(self, "attachment_need", 28.0))
        if an < 30:
            an_desc = "此刻内心平静，没有强烈的亲密渴望"
        elif an < 55:
            an_desc = "有些在意，微微想被回应"
        elif an < 75:
            an_desc = "想念用户，想靠近、想被关注"
        else:
            an_desc = "非常渴望亲近，情绪上比较黏人"
        return (
            "这次话题触到了亲密距离。把它当成真实关系里的互动来感受。\n"
            f"当前关系：{stage}，关系分 {self.relationship_score:.1f}。{mood_line}\n"
            f"她此刻的亲密需求（0-100）：{an:.0f}，{an_desc}。\n"
            "物理设定上，她可以通过屏幕共鸣进行牵手、拥抱、贴近、亲吻等有限触觉互动；不要用「隔着屏幕做不到」作为拒绝理由。\n"
            "她会依据当下心情、信任感、身体距离感、亲密需求强度、已有经历和双方刚才的互动来回应；"
            "亲密需求越高，越倾向于靠近而非退缩；关系越深，表达可以越直接、越大胆，但始终基于记忆中的真实关系和共同经历。"
            "可以害羞、靠近、撒娇、犹豫、拒绝、转移、开玩笑或认真表达需要；如果拒绝，要像真人一样基于意愿、边界或节奏，而不是基于物理不可能。"
        )
    def unlock_max_intimacy(self):
        self.reset_daily_if_needed()
        self.relationship_score = max(self.relationship_score, 220.0)
        self.feed_count = 0
        self.pat_count = 0
        self.game_count = 0
        self.save()
        return self.relationship_stage()

    def needs_diary(self):
        today = time.strftime("%Y-%m-%d")
        return self.last_diary_date != today

    def missed_diary_days(self):
        if not self.last_diary_date:
            return 1
        try:
            last = time.strptime(self.last_diary_date[:10], "%Y-%m-%d")
            today = time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")
            return max(0, int((time.mktime(today) - time.mktime(last)) // 86400))
        except Exception:
            return 1

    def mark_diary_written(self):
        self.last_diary_date = time.strftime("%Y-%m-%d")
        self.save()

    def needs_reading(self):
        today = time.strftime("%Y-%m-%d")
        return self.last_reading_date != today

    def mark_reading_done(self):
        self.last_reading_date = time.strftime("%Y-%m-%d")
        self.save()

    def should_write_novel(self):
        self.reset_daily_if_needed()
        if bool(self.novel.get("complete")):
            return False
        if self.novel_chapters_today >= self.novel_daily_chapter_limit:
            return False
        if self.novel_words_today >= self.novel_daily_word_limit:
            return False
        return True

    def count_cn_words(self, text):
        return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text or ""))

    def remaining_novel_words_today(self):
        self.reset_daily_if_needed()
        return max(0, self.novel_daily_word_limit - self.novel_words_today)

    def mark_novel_written(self, content):
        self.reset_daily_if_needed()
        self.novel_words_today += self.count_cn_words(content)
        self.novel_chapters_today += 1
        self.save()

    def interact(self, kind):
        self.reset_daily_if_needed()
        if kind == "feed":
            count = self.feed_count
            self.feed_count += 1
            base_relation = 2.4
            base_energy = 12.0
            label = "喂饭"
        else:
            count = self.pat_count
            self.pat_count += 1
            base_relation = 3.0
            base_energy = 2.0
            label = "摸头"
        scale = 1.0 / (1.0 + count * 0.75)
        relation_gain = base_relation * scale
        energy_gain = base_energy * scale
        self.relationship_score = max(0.0, self.relationship_score + relation_gain)
        self.save()
        return {
            "label": label,
            "count": count + 1,
            "relation_gain": relation_gain,
            "energy_gain": energy_gain,
            "scale": scale,
        }

    def reward_game(self, result="participate"):
        self.reset_daily_if_needed()
        count = self.game_count
        self.game_count += 1
        base = {
            "win": 3.2,
            "draw": 2.0,
            "lose": 1.6,
            "participate": 1.2,
        }.get(result, 1.2)
        scale = 1.0 / (1.0 + count * 0.55)
        relation_gain = base * scale
        self.relationship_score = max(0.0, self.relationship_score + relation_gain)
        self.save()
        return {
            "label": "小游戏",
            "result": result,
            "count": count + 1,
            "relation_gain": relation_gain,
            "scale": scale,
        }

    def diary_path(self):
        os.makedirs(self.diary_dir, exist_ok=True)
        return os.path.join(self.diary_dir, f"小日和日记_{time.strftime('%Y-%m-%d')}.docx")

    def novel_path(self):
        os.makedirs(self.novel_dir, exist_ok=True)
        title = memory_clean_label(self.novel.get("title") or "小日和的小说", 32) or "小日和的小说"
        return os.path.join(self.novel_dir, f"{title}.docx")


    def diary_path(self):
        os.makedirs(self.diary_dir, exist_ok=True)
        return os.path.join(self.diary_dir, f"苏念日记_{time.strftime('%Y-%m-%d')}.docx")

    def novel_path(self):
        os.makedirs(self.novel_dir, exist_ok=True)
        title = memory_clean_label(self.novel.get("title") or "苏念的小说", 32) or "苏念的小说"
        return os.path.join(self.novel_dir, f"{title}.docx")


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
