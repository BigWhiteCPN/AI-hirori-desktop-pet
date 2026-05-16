"""Non-explicit physiology needs for the desktop pet."""

import math
import random
import time
from datetime import date, datetime

from persona_pet.memory import memory_now_label


PHYSIOLOGY_STATE_META_KEY = "physiology_state"


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def _approach_target(current, target, tau_minutes, dt_minutes):
    if tau_minutes <= 0:
        return target
    alpha = 1.0 - math.exp(-dt_minutes / tau_minutes)
    return current + (target - current) * alpha


def _soft_limit(x, delta):
    if delta > 0 and x > 85:
        delta *= max(0.0, (100.0 - x)) / 15.0
    if delta < 0 and x < 15:
        delta *= max(0.0, x) / 15.0
    return delta


def _soft_cap(value, low=6.0, high=94.0):
    """Keep long-running body meters out of hard 0/100 unless a direct cheat sets them."""
    value = float(value)
    if value < low:
        return low + (value - low) * 0.25
    if value > high:
        return high + (value - high) * 0.25
    return value


def _circadian_hour():
    return time.localtime().tm_hour + time.localtime().tm_min / 60.0


class PersonaPhysiology:
    """Human-like daily body state.

    Hunger and thirst are discomfort meters: higher means more hungry/thirsty.
    Satiety and hydration are derived as 100 - hunger/thirst for UI display.
    """

    DEFAULT_VALUES = {
        "hunger": 24.0,
        "thirst": 22.0,
        "fatigue": 28.0,
        "sleepiness": 18.0,
        "comfort": 68.0,
        "stress": 20.0,
        "closeness_need": 40.0,
    }
    LABELS = {
        "hunger": "饥饿",
        "thirst": "口渴",
        "fatigue": "疲劳",
        "sleepiness": "困意",
        "comfort": "舒适",
        "stress": "压力",
        "closeness_need": "亲近",
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
        # Migrate from older linear models: cap values that were stuck at extremes.
        if saved.get("model_version") != 3:
            print("PHYSIO_MODEL_MIGRATION: resetting stuck values to defaults")
            for key, cap in [("hunger", 46), ("thirst", 40), ("fatigue", 42), ("sleepiness", 45), ("stress", 26), ("closeness_need", 48), ("comfort", 72)]:
                if self.values.get(key, 0) > cap:
                    self.values[key] = float(cap)
            for key, floor in [("comfort", 54), ("hunger", 12), ("thirst", 12), ("fatigue", 12), ("sleepiness", 8), ("stress", 8), ("closeness_need", 18)]:
                if self.values.get(key, 0) < floor:
                    self.values[key] = float(floor)

        now = time.monotonic()
        wall_now = time.time()
        today = date.today().isoformat()
        self.last_tick_at = now
        self.last_saved_at = 0.0
        self._dirty = False
        self.last_need_note_at = float(saved.get("last_need_note_at") or 0.0)
        self.last_need_note_key = str(saved.get("last_need_note_key") or "")

        self.height_cm = float(saved.get("height_cm") or 162.0)
        self.weight_kg = float(saved.get("weight_kg") or 48.0)
        self.birth_month = int(saved.get("birth_month") or 6)
        self.birth_day = int(saved.get("birth_day") or 1)
        self.birth_year = int(saved.get("birth_year") or self._default_birth_year())
        self.life_expectancy_years = float(saved.get("life_expectancy_years") or 80.0)

        self.daily_date = str(saved.get("daily_date") or today)
        self.meals_today = int(saved.get("meals_today") or 0)
        self.water_today = int(saved.get("water_today") or 0)
        self.last_wall_at = float(saved.get("last_wall_at") or wall_now)
        self.last_auto_meal_at = float(saved.get("last_auto_meal_at") or 0.0)
        self.last_auto_water_at = float(saved.get("last_auto_water_at") or saved.get("last_wall_at") or wall_now)
        self.last_auto_rest_at = float(saved.get("last_auto_rest_at") or 0.0)
        self.last_user_seen_at = now
        self.last_weight_update_date = str(saved.get("last_weight_update_date") or today)

        self.body_cycle = None
        self.drive = None
        self._reset_daily_if_needed()
        self._apply_offline_progress(wall_now)

    def _default_birth_year(self):
        today = date.today()
        before_birthday = (today.month, today.day) < (6, 1)
        return today.year - 23 if before_birthday else today.year - 22

    def _reset_daily_if_needed(self):
        today = date.today().isoformat()
        if self.daily_date == today:
            return
        self.daily_date = today
        self.meals_today = 0
        self.water_today = 0
        self._update_weight_for_new_day()
        self._dirty = True

    def _update_weight_for_new_day(self):
        today = date.today().isoformat()
        if self.last_weight_update_date == today:
            return
        satiety = self.satiety()
        stress = self.values.get("stress", 0.0)
        comfort = self.values.get("comfort", 50.0)
        delta = 0.0
        if satiety > 78:
            delta += 0.04
        elif satiety < 35:
            delta -= 0.035
        if stress > 65:
            delta -= 0.015
        if comfort > 78 and 45 <= satiety <= 75:
            delta += 0.006
        self.weight_kg = round(clamp(self.weight_kg + delta, 44.0, 54.0), 2)
        self.last_weight_update_date = today

    def _apply_offline_progress(self, wall_now):
        elapsed = max(0.0, min(float(wall_now) - float(self.last_wall_at), 86400.0 * 7))
        if elapsed <= 0.0:
            return
        minutes = elapsed / 60.0
        hours = minutes / 60.0
        # Offline time should feel like she lived through the day, not like every need
        # charged linearly until it hit 100.
        self.values["hunger"] = clamp(_approach_target(self.values["hunger"], 58.0, 9.0, hours), 8.0, 82.0)
        self.values["thirst"] = clamp(_approach_target(self.values["thirst"], 52.0, 7.0, hours), 8.0, 78.0)
        self.values["fatigue"] = clamp(_approach_target(self.values["fatigue"], 42.0, 16.0, hours), 8.0, 74.0)
        sleep_target = 36.0 if 7 <= _circadian_hour() < 22 else 62.0
        self.values["sleepiness"] = clamp(_approach_target(self.values["sleepiness"], sleep_target, 6.0, hours), 6.0, 82.0)
        self.values["stress"] = clamp(_approach_target(self.values["stress"], 18.0, 12.0, hours), 6.0, 70.0)
        self.values["comfort"] = clamp(_approach_target(self.values["comfort"], 66.0, 10.0, hours), 35.0, 86.0)
        self._auto_routine(wall_now)
        self.last_wall_at = wall_now
        self._dirty = True

    def tick(self, now=None, busy=False):
        now = time.monotonic() if now is None else float(now)
        wall_now = time.time()
        self._reset_daily_if_needed()
        self.last_wall_at = wall_now
        elapsed = max(0.0, now - self.last_tick_at)
        if elapsed < 1.0:
            return
        dt = min(6.0, elapsed / 60.0)
        self.last_tick_at = now
        v = self.values
        hour = _circadian_hour()
        is_night = hour >= 23 or hour < 6

        # --- hunger: target + time constant model ---
        hunger_target = 48.0
        if 6 <= hour < 10 or 11 <= hour < 14 or 17 <= hour < 20:
            hunger_target = 56.0
        if is_night:
            hunger_target = 30.0
        hunger_target *= self.appetite_multiplier()
        hunger_target = clamp(hunger_target, 24.0, 68.0)
        tau_hunger = 150.0 if v["hunger"] < hunger_target else 90.0
        v["hunger"] = clamp(_approach_target(v["hunger"], hunger_target, tau_hunger, dt), 6.0, 88.0)

        # --- thirst: target + time constant model ---
        thirst_target = 45.0
        if 7 <= hour < 22:
            thirst_target = 50.0
        if busy:
            thirst_target += 12.0
        if is_night:
            thirst_target = 25.0
        tau_thirst = 180.0 if v["thirst"] < thirst_target else 20.0
        v["thirst"] = clamp(_approach_target(v["thirst"], thirst_target, tau_thirst, dt))

        # --- fatigue: target + time constant, auto-rest ---
        fatigue_target = 30.0
        if busy:
            fatigue_target = 55.0
        if is_night:
            fatigue_target = 40.0
        tau_fatigue = 120.0 if v["fatigue"] < fatigue_target else 480.0
        # sleep accelerates recovery
        if is_night and not busy:
            tau_fatigue = min(tau_fatigue, 120.0)
        v["fatigue"] = clamp(_approach_target(v["fatigue"], fatigue_target, tau_fatigue, dt))
        # auto-rest: if fatigue > 65 and idle > 30 min
        if v["fatigue"] > 65 and not busy and (now - self.last_user_seen_at > 1800.0):
            if now - self.last_auto_rest_at > 2700.0:
                v["fatigue"] = clamp(v["fatigue"] - 8.0)
                self.last_auto_rest_at = now

        # --- sleepiness: circadian target ---
        sleep_target = 20.0
        if 7 <= hour < 12:
            sleep_target = 12.0
        elif 13 <= hour < 15:
            sleep_target = 30.0
        elif 22 <= hour or hour < 2:
            sleep_target = 55.0
        elif 2 <= hour < 6:
            sleep_target = 75.0
        tau_sleep = 60.0 if v["sleepiness"] < sleep_target else 90.0
        v["sleepiness"] = clamp(_approach_target(v["sleepiness"], sleep_target, tau_sleep, dt))

        # --- closeness_need: target from interaction recency ---
        closeness_target = 40.0
        idle_min = max(0.0, now - self.last_user_seen_at) / 60.0
        if idle_min > 60:
            closeness_target = 60.0
        if idle_min > 180:
            closeness_target = 75.0
        if is_night:
            closeness_target += 8.0
        if hasattr(self, 'drive') and self.drive is not None:
            sec = self.drive.values.get("security", 64.0)
            if sec > 70:
                closeness_target -= 5.0
            elif sec < 40:
                closeness_target += 8.0
        tau_closeness = 360.0 if v["closeness_need"] < closeness_target else 45.0
        v["closeness_need"] = clamp(_approach_target(v["closeness_need"], closeness_target, tau_closeness, dt), 10.0, 82.0)

        # --- stress: target from workload + coupling ---
        stress_target = 15.0
        if busy:
            stress_target = 45.0
        if is_night:
            stress_target -= 5.0
        if v.get("comfort", 50) > 70:
            stress_target -= 8.0
        if v["thirst"] > 60:
            stress_target += 5.0
        if v["fatigue"] > 60:
            stress_target += 5.0
        if hasattr(self, 'drive') and self.drive is not None:
            sec = self.drive.values.get("security", 64.0)
            if sec < 40:
                stress_target += 10.0
        tau_stress = 120.0 if v["stress"] < stress_target else 300.0
        v["stress"] = clamp(_approach_target(v["stress"], stress_target, tau_stress, dt))

        # --- comfort: target from context ---
        comfort_target = 65.0
        if not busy:
            comfort_target = 75.0
        if v["thirst"] > 60:
            comfort_target -= 8.0
        if v["fatigue"] > 60:
            comfort_target -= 6.0
        if v["stress"] > 50:
            comfort_target -= 8.0
        if is_night:
            comfort_target += 3.0
        tau_comfort = 180.0 if v["comfort"] < comfort_target else 120.0
        v["comfort"] = clamp(_approach_target(v["comfort"], comfort_target, tau_comfort, dt))

        # --- auto routine (meals/water) ---
        self._auto_routine(wall_now)
        self._normalize_values()

        if now - self.last_saved_at > 15.0:
            self.save()

    def appetite_multiplier(self):
        multiplier = 1.0
        phase = getattr(getattr(self, "body_cycle", None), "phase", "")
        if phase == "menstrual":
            multiplier *= 0.82
        elif phase == "luteal":
            multiplier *= 1.18
        elif phase == "ovulation":
            multiplier *= 1.06
        mood = "quiet"
        try:
            if self.drive is not None and hasattr(self.drive, "compute_mood"):
                mood = self.drive.compute_mood()
        except Exception:
            mood = "quiet"
        if mood in ("worried", "tired"):
            multiplier *= 0.88
        elif mood in ("relaxed", "playful"):
            multiplier *= 1.06
        return clamp(multiplier, 0.65, 1.35)

    def _auto_routine(self, wall_now):
        now_dt = datetime.fromtimestamp(wall_now)
        meal_hours = (8, 13, 19)
        while self.meals_today < 3:
            target_hour = meal_hours[self.meals_today]
            if now_dt.hour < target_hour or self.values.get("hunger", 0.0) < 42.0:
                break
            self.values["hunger"] = clamp(self.values["hunger"] - 38.0)
            self.values["comfort"] = clamp(self.values["comfort"] + 2.0)
            self.meals_today += 1
            self.last_auto_meal_at = wall_now
        # Smart water: trigger when thirst > 65 and >= 90 min since last drink
        water_interval = 90 * 60  # 90 minutes
        if wall_now - self.last_auto_water_at >= water_interval and self.values.get("thirst", 0.0) >= 65.0:
            self.values["thirst"] = clamp(self.values["thirst"] - 26.0)
            self.values["comfort"] = clamp(self.values["comfort"] + 1.5)
            self.water_today += 1
            self.last_auto_water_at = wall_now

    def adjust(self, **changes):
        for key, delta in changes.items():
            if key in self.values:
                delta = _soft_limit(self.values[key], float(delta))
                self.values[key] = clamp(self.values[key] + delta)
        self._normalize_values()
        self.save()

    def _normalize_values(self):
        ranges = {
            "hunger": (6.0, 88.0),
            "thirst": (6.0, 86.0),
            "fatigue": (6.0, 86.0),
            "sleepiness": (4.0, 90.0),
            "stress": (4.0, 82.0),
            "closeness_need": (10.0, 82.0),
            "comfort": (24.0, 92.0),
        }
        for key, (low, high) in ranges.items():
            if key in self.values:
                self.values[key] = clamp(_soft_cap(self.values[key], low, high), low, high)

    def on_user_message(self, text=""):
        text = str(text or "")
        self.last_user_seen_at = time.monotonic()
        self.adjust(stress=-0.6, closeness_need=-0.8, comfort=1.0)
        if any(token in text for token in ("吃", "饭", "饿", "喂")):
            self.adjust(hunger=-2.0)
        if any(token in text for token in ("睡", "困", "休息", "晚安")):
            self.adjust(sleepiness=2.5, fatigue=-1.0, stress=-1.5)

    def on_assistant_reply(self):
        self.adjust(fatigue=0.6, thirst=0.4)

    def on_feed(self):
        self.adjust(hunger=-34.0, thirst=-3.0, comfort=4.0, closeness_need=-3.0)

    def on_pat(self):
        self.adjust(stress=-8.0, comfort=7.0, closeness_need=-8.0, sleepiness=2.0)

    def on_drink(self):
        self.adjust(thirst=-30.0, comfort=2.5)

    def on_rest(self):
        self.adjust(fatigue=-24.0, sleepiness=-20.0, stress=-5.0, comfort=7.0)

    def on_max_intimacy(self):
        self.adjust(stress=-12.0, comfort=14.0, closeness_need=-18.0)

    def satiety(self):
        return round(100.0 - self.values.get("hunger", 0.0), 1)

    def hydration(self):
        return round(100.0 - self.values.get("thirst", 0.0), 1)

    def feed_refusal_threshold(self):
        threshold = 84.0
        phase = getattr(getattr(self, "body_cycle", None), "phase", "")
        if phase == "luteal":
            threshold += 7.0
        elif phase == "menstrual":
            threshold -= 6.0
        mood = "quiet"
        try:
            if self.drive is not None and hasattr(self.drive, "compute_mood"):
                mood = self.drive.compute_mood()
        except Exception:
            mood = "quiet"
        if mood in ("worried", "tired"):
            threshold -= 4.0
        elif mood in ("playful", "relaxed"):
            threshold += 3.0
        return clamp(threshold, 72.0, 92.0)

    def drink_refusal_threshold(self):
        return 82.0

    def try_user_feed(self):
        if self.satiety() > self.feed_refusal_threshold():
            message = random.choice(
                [
                    "我现在真的吃不下啦。你是想把我喂成圆滚滚的吗？先陪我说会儿话就好。",
                    "不要再投喂了，我已经很饱了。等我真的饿了再接受你的照顾。",
                    "这份心意我收到了，但肚子已经满了。再吃会不舒服的。",
                ]
            )
            self.adjust(comfort=-0.8, stress=0.8)
            return {"accepted": False, "message": message}
        self.on_feed()
        self.meals_today = min(3, self.meals_today + 1)
        self.last_auto_meal_at = time.time()
        self.save()
        return {"accepted": True, "message": ""}

    def try_user_drink(self):
        if self.hydration() >= self.drink_refusal_threshold():
            message = random.choice(
                [
                    "我现在不渴啦，再喝就有点勉强了。",
                    "水先放旁边吧。你这样一直催我喝，我会有点抗议的。",
                    "已经够了，我会自己记得喝水的。",
                ]
            )
            self.adjust(comfort=-0.4, stress=0.4)
            return {"accepted": False, "message": message}
        self.on_drink()
        self.water_today = min(6, self.water_today + 1)
        self.last_auto_water_at = time.time()
        self.save()
        return {"accepted": True, "message": ""}

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

    def age_years(self):
        today = date.today()
        age = today.year - self.birth_year
        if (today.month, today.day) < (self.birth_month, self.birth_day):
            age -= 1
        return max(0, age)

    def life_progress_years(self):
        born = date(self.birth_year, self.birth_month, self.birth_day)
        return max(0.0, (date.today() - born).days / 365.2425)

    def body_profile(self):
        return {
            "height_cm": round(self.height_cm, 1),
            "weight_kg": round(self.weight_kg, 2),
            "age_years": self.age_years(),
            "life_progress_years": round(self.life_progress_years(), 2),
            "life_expectancy_years": round(self.life_expectancy_years, 1),
            "birthday": f"{self.birth_month:02d}-{self.birth_day:02d}",
            "satiety": self.satiety(),
            "hydration": self.hydration(),
            "meals_today": self.meals_today,
            "water_today": self.water_today,
        }

    def snapshot(self):
        key, value = self.dominant_need()
        body = self.body_profile()
        return {
            "values": {key: round(value, 1) for key, value in self.values.items()},
            "dominant": key,
            "dominant_value": round(value, 1),
            "status": self.status_phrase(),
            "body": body,
            "summary": " / ".join(
                f"{self.LABELS[key]}{value:.0f}"
                for key, value in self.values.items()
                if key != "comfort"
            )
            + f" / 舒适{self.values['comfort']:.0f} / 饱食{body['satiety']:.0f} / 水分{body['hydration']:.0f}",
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
            "hunger": "身体有点空，可能会更想被照顾；如果已经自己吃过饭，她会自然恢复。",
            "thirst": "有点口渴，她会自己按大约四小时一次的节奏喝水，也会接受合适的提醒。",
            "fatigue": "身体有点累，语气可能更软，也更想安静地靠近。",
            "sleepiness": "有点困，说话会更慢更低声，也可能更依赖稳定陪伴。",
            "stress": "有点紧张，会更在意自己有没有被理解。",
            "closeness_need": "想靠近用户一点，这种需要会随关系、情绪和刚才的互动自然表达。",
            "comfort": "身体有点不舒服，可能需要更温柔的回应和照顾。",
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
        self._dirty = True
        now = time.monotonic()
        if now - self.last_saved_at < 15.0:
            return
        self.flush_dirty()

    def flush_dirty(self):
        if not getattr(self, "_dirty", False):
            return
        self._dirty = False
        self.last_saved_at = time.monotonic()
        self.memory_store.save_meta_json(
            self.meta_key,
            {
                "values": self.values,
                "last_need_note_at": self.last_need_note_at,
                "last_need_note_key": self.last_need_note_key,
                "height_cm": self.height_cm,
                "weight_kg": self.weight_kg,
                "birth_year": self.birth_year,
                "birth_month": self.birth_month,
                "birth_day": self.birth_day,
                "life_expectancy_years": self.life_expectancy_years,
                "daily_date": self.daily_date,
                "meals_today": self.meals_today,
                "water_today": self.water_today,
                "last_wall_at": self.last_wall_at,
                "last_auto_meal_at": self.last_auto_meal_at,
                "last_auto_water_at": self.last_auto_water_at,
                "last_auto_rest_at": self.last_auto_rest_at,
                "last_weight_update_date": self.last_weight_update_date,
                "model_version": 3,
            },
        )


class PhysiologyMixin:
    def setup_physiology_module(self):
        self.physiology = PersonaPhysiology(self.memory, logger=getattr(self, "runtime_logger", None))
        if hasattr(self, "body_cycle"):
            self.physiology.body_cycle = self.body_cycle
        if hasattr(self, "drive"):
            self.physiology.drive = self.drive
            self.drive._physiology_ref = self.physiology

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
