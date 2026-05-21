"""Female body cycle and intimacy-needs system."""

import calendar
import time
from datetime import date, datetime, timedelta


CYCLE_PHASES = {
    "menstrual": {
        "label": "月影期",
        "mood_effect": {"sensitivity": 0.35, "irritability": 0.20, "fatigue": 0.25, "appetite": -0.12},
        "comfort_effect": -15.0,
        "energy_effect": -10.0,
        "description": "身体不太舒服，更敏感，也更需要温柔和稳定感。",
    },
    "follicular": {
        "label": "新芽期",
        "mood_effect": {"sensitivity": -0.10, "energy_boost": 0.15, "openness": 0.10},
        "comfort_effect": 5.0,
        "energy_effect": 5.0,
        "description": "状态逐渐恢复，心情更轻快。",
    },
    "ovulation": {
        "label": "花信期",
        "mood_effect": {"sensitivity": 0.05, "affection_boost": 0.20, "playfulness": 0.15},
        "comfort_effect": 8.0,
        "energy_effect": 8.0,
        "description": "精力更好，更愿意靠近和互动。",
    },
    "luteal": {
        "label": "微澜期",
        "mood_effect": {"sensitivity": 0.20, "irritability": 0.15, "craving": 0.25, "appetite": 0.18},
        "comfort_effect": -5.0,
        "energy_effect": -3.0,
        "description": "容易烦躁或想吃东西，需要更多耐心和安抚。",
    },
}

SEXUAL_NEED_DECAY = {
    "base_rate": 0.15,
    "cycle_multiplier": {
        "menstrual": 0.3,
        "follicular": 0.8,
        "ovulation": 1.8,
        "luteal": 1.0,
    },
    "intimacy_boost": {
        "touch": 5.0,
        "kiss": 8.0,
        "embrace": 6.0,
        "verbal": 3.0,
    },
    "phase_target": {
        "menstrual": 24.0,
        "follicular": 34.0,
        "ovulation": 58.0,
        "luteal": 42.0,
    },
}


class BodyCycleSystem:
    def __init__(self, memory_store, meta_key="body_cycle", logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.phase = "follicular"
        self.phase_day = 1
        self.cycle_length = 28
        self.menstrual_duration = 5
        self.last_period_start_date = ""
        self.sexual_need = 25.0
        self.last_sexual_tick_at = 0.0
        self.last_intimate_contact_at = 0.0
        self.last_proactive_intimacy_at = 0.0
        self._dirty = False
        self._load()
        self._sync_to_date()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if not isinstance(data, dict):
            data = {}
        self.phase = data.get("phase", "follicular")
        self.phase_day = int(data.get("phase_day", 1))
        self.cycle_length = max(24, min(35, int(data.get("cycle_length", 28))))
        self.menstrual_duration = max(3, min(7, int(data.get("menstrual_duration", 5))))
        self.sexual_need = max(12.0, min(82.0, float(data.get("sexual_need", 25.0))))
        if data.get("model_version") != 2 and self.sexual_need > 70.0:
            self.sexual_need = 58.0
        self.last_period_start_date = str(data.get("last_period_start_date") or "")
        self.last_intimate_contact_at = float(data.get("last_intimate_contact_at", 0.0))
        self.last_proactive_intimacy_at = float(data.get("last_proactive_intimacy_at", 0.0))
        self.last_sexual_tick_at = float(data.get("last_sexual_tick_at", 0.0))
        if not self.last_period_start_date:
            today = date.today()
            self.last_period_start_date = (today - timedelta(days=max(0, self.current_cycle_day() - 1))).isoformat()

    def _save(self):
        if not self._dirty:
            return
        self._dirty = False
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "phase": self.phase,
                "phase_day": self.phase_day,
                "cycle_length": self.cycle_length,
                "menstrual_duration": self.menstrual_duration,
                "last_period_start_date": self.last_period_start_date,
                "sexual_need": round(self.sexual_need, 1),
                "last_sexual_tick_at": self.last_sexual_tick_at,
                "last_intimate_contact_at": self.last_intimate_contact_at,
                "last_proactive_intimacy_at": self.last_proactive_intimacy_at,
                "model_version": 2,
            },
        )

    def flush_dirty(self):
        self._save()

    def _period_start(self):
        try:
            return datetime.strptime(self.last_period_start_date[:10], "%Y-%m-%d").date()
        except Exception:
            start = date.today() - timedelta(days=max(0, int(self.phase_day) - 1))
            self.last_period_start_date = start.isoformat()
            return start

    def cycle_day_for_date(self, target):
        elapsed = (target - self._period_start()).days
        return elapsed % self.cycle_length + 1

    def phase_for_cycle_day(self, day):
        day = max(1, min(self.cycle_length, int(day)))
        if day <= self.menstrual_duration:
            return "menstrual"
        if day <= 13:
            return "follicular"
        if day <= 16:
            return "ovulation"
        return "luteal"

    def _phase_day_for_cycle_day(self, cycle_day, phase):
        starts = {
            "menstrual": 1,
            "follicular": self.menstrual_duration + 1,
            "ovulation": 14,
            "luteal": 17,
        }
        return max(1, int(cycle_day) - starts.get(phase, 1) + 1)

    def _sync_to_date(self):
        cycle_day = self.cycle_day_for_date(date.today())
        phase = self.phase_for_cycle_day(cycle_day)
        phase_day = self._phase_day_for_cycle_day(cycle_day, phase)
        if phase != self.phase or phase_day != self.phase_day:
            self.phase = phase
            self.phase_day = phase_day
            self._dirty = True

    def set_cycle_day_for_testing(self, cycle_day):
        cycle_day = max(1, min(self.cycle_length, int(cycle_day)))
        self.last_period_start_date = (date.today() - timedelta(days=cycle_day - 1)).isoformat()
        self.phase = self.phase_for_cycle_day(cycle_day)
        self.phase_day = self._phase_day_for_cycle_day(cycle_day, self.phase)
        self._dirty = True
        self._save()
        return self.get_phase_info()

    def set_phase_for_testing(self, phase):
        phase_days = {
            "menstrual": 1,
            "follicular": self.menstrual_duration + 1,
            "ovulation": 14,
            "luteal": 17,
        }
        return self.set_cycle_day_for_testing(phase_days.get(phase, 1))

    def tick(self, now=None):
        now = time.monotonic() if now is None else float(now)
        self._sync_to_date()
        sexual_elapsed = now - self.last_sexual_tick_at
        if sexual_elapsed >= 60.0:
            self.last_sexual_tick_at = now
            self._tick_sexual_need(sexual_elapsed)
            self._dirty = True
        if now - getattr(self, "_last_save_at", 0.0) > 15.0:
            self._last_save_at = now
            self._save()

    def _tick_sexual_need(self, elapsed_seconds):
        minutes = elapsed_seconds / 60.0
        multiplier = SEXUAL_NEED_DECAY["cycle_multiplier"].get(self.phase, 1.0)
        target = SEXUAL_NEED_DECAY["phase_target"].get(self.phase, 38.0)
        # Recent contact lowers the target for a while, then it slowly returns.
        if self.last_intimate_contact_at:
            hours_since_contact = max(0.0, (time.monotonic() - self.last_intimate_contact_at) / 3600.0)
            if hours_since_contact < 6.0:
                target -= 10.0 * (1.0 - hours_since_contact / 6.0)
        tau = 480.0 / max(0.35, multiplier)
        alpha = 1.0 - pow(2.718281828, -minutes / tau)
        self.sexual_need += (target - self.sexual_need) * alpha
        if self.sexual_need > 82.0:
            self.sexual_need = 82.0 + (self.sexual_need - 82.0) * 0.18
        self.sexual_need = max(12.0, min(90.0, self.sexual_need))

    def on_intimate_contact(self, contact_type="touch"):
        boost = SEXUAL_NEED_DECAY["intimacy_boost"].get(contact_type, 3.0)
        self.sexual_need = max(12.0, self.sexual_need - boost)
        self.last_intimate_contact_at = time.monotonic()
        self._dirty = True

    def on_user_message(self, text="", emotion="neutral"):
        compact = "".join(str(text or "").split())
        intimate_words = ("亲", "抱", "摸", "贴贴", "想你", "爱你", "喜欢你")
        if any(w in compact for w in intimate_words):
            self.on_intimate_contact("verbal")
        touch_words = ("亲亲", "抱抱", "摸摸", "牵手", "靠近")
        if any(w in compact for w in touch_words):
            self.on_intimate_contact("touch")

    def current_cycle_day(self):
        return self.cycle_day_for_date(date.today())

    def get_phase_info(self):
        self._sync_to_date()
        info = CYCLE_PHASES.get(self.phase, {})
        return {
            "phase": self.phase,
            "label": info.get("label", self.phase),
            "day": self.phase_day,
            "cycle_day": self.current_cycle_day(),
            "cycle_length": self.cycle_length,
            "description": info.get("description", ""),
            "mood_effect": info.get("mood_effect", {}),
            "comfort_effect": info.get("comfort_effect", 0.0),
            "energy_effect": info.get("energy_effect", 0.0),
        }

    def get_mood_modifiers(self):
        self._sync_to_date()
        info = CYCLE_PHASES.get(self.phase, {})
        return info.get("mood_effect", {})

    def get_sexual_status(self):
        level = self.sexual_need
        if level < 20:
            label = "平静"
        elif level < 45:
            label = "微微在意"
        elif level < 70:
            label = "有点想靠近"
        elif level < 90:
            label = "比较想亲近"
        else:
            label = "很想亲近"
        return {
            "level": round(level, 1),
            "label": label,
            "phase": self.phase,
            "growth_multiplier": self.get_sexual_growth_multiplier(),
        }

    def get_sexual_growth_multiplier(self):
        self._sync_to_date()
        return float(SEXUAL_NEED_DECAY["cycle_multiplier"].get(self.phase, 1.0))

    def build_cycle_calendar(self, days=None):
        today = date.today()
        month_days = calendar.monthrange(today.year, today.month)[1]
        if days is not None:
            month_days = min(month_days, int(days))
        items = []
        for day in range(1, month_days + 1):
            current_date = date(today.year, today.month, day)
            cycle_day = self.cycle_day_for_date(current_date)
            phase = self.phase_for_cycle_day(cycle_day)
            info = CYCLE_PHASES.get(phase, {})
            items.append(
                {
                    "day": day,
                    "date": current_date.isoformat(),
                    "cycle_day": cycle_day,
                    "phase": phase,
                    "label": info.get("label", phase),
                    "is_current": current_date == today,
                    "growth_multiplier": float(SEXUAL_NEED_DECAY["cycle_multiplier"].get(phase, 1.0)),
                }
            )
        return items

    def build_status_text(self):
        phase_info = self.get_phase_info()
        sexual = self.get_sexual_status()
        today = date.today()
        month_days = calendar.monthrange(today.year, today.month)[1]
        lines = [
            f"身体节律：{phase_info['label']}（阶段第{phase_info['day']}天 / 节律第{phase_info['cycle_day']}天）",
            f"本月日历：{today.year}-{today.month:02d}，共 {month_days} 天；生日 06-01。",
            f"状态：{phase_info['description']}",
            f"亲近需求：{sexual['label']}（{sexual['level']}%，变化 x{sexual['growth_multiplier']:.1f}）",
        ]
        return "\n".join(lines)

    def maybe_build_proactive_intimacy_action(self, relationship_score=0.0, idle_seconds=0.0, recent_memories=None, now=None):
        now = time.monotonic() if now is None else float(now)
        sexual = self.get_sexual_status()
        if sexual["level"] < 72.0:
            return None
        if float(relationship_score or 0.0) < 65.0:
            return None
        if float(idle_seconds or 0.0) < 600.0:
            return None
        if now - self.last_proactive_intimacy_at < 1800.0:
            return None
        self.last_proactive_intimacy_at = now
        self._dirty = True
        phase_info = self.get_phase_info()
        memory_hint = ""
        if recent_memories:
            memory_hint = "她能想起的最近相处片段：\n" + "\n".join(f"- {item}" for item in recent_memories[:3]) + "\n"
        prompt = (
            "你现在是桌宠自己主动开口，不是在回答用户。\n"
            f"当前生理周期：{phase_info['label']}，亲近需求：{sexual['label']}（{sexual['level']}%）。\n"
            f"{memory_hint}"
            "把这种需要表达成真实关系里的自然靠近：可以是想被抱一下、想听他认真回应、想靠近一会儿、撒娇、试探，或者也可以因为当下身体状态而更安静。"
        )
        return {
            "type": "intimacy_need",
            "score": round(sexual["level"], 1),
            "prompt": prompt,
            "memory_user_text": "桌宠主动行动：亲近需求",
        }

    def build_prompt_context(self):
        phase_info = self.get_phase_info()
        sexual = self.get_sexual_status()
        today = date.today()
        month_days = calendar.monthrange(today.year, today.month)[1]
        lines = [f"当前日历：{today.year}年{today.month}月{today.day}日，本月共{month_days}天。"]
        if self.phase == "menstrual":
            lines.append(f"她正处于经期第{phase_info['day']}天，身体不太舒服，情绪更敏感，食欲可能下降，需要更温柔的关心。")
        elif self.phase == "ovulation":
            lines.append(f"她正处于排卵期第{phase_info['day']}天，精力更好，更愿意自然靠近和互动。")
        elif self.phase == "luteal":
            lines.append(f"她正处于黄体期第{phase_info['day']}天，容易烦躁或想吃东西，心情和饭量会更波动。")
        if sexual["level"] >= 60:
            lines.append(f"她有{sexual['label']}的感觉，可能会更主动靠近或暗示。")
        elif sexual["level"] >= 40:
            lines.append(f"她{sexual['label']}，对亲近话题会更敏感。")
        return "\n".join(lines)
