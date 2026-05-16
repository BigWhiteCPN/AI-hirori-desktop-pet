"""Time awareness system that understands the meaning of time."""

from datetime import datetime, timedelta


TIME_PERIODS = {
    (0, 5): {"label": "深夜", "tone": "温柔低声", "care": "怎么还没睡，是不是有心事", "energy": "很低"},
    (5, 8): {"label": "清晨", "tone": "轻快清新", "care": "起这么早，昨晚睡得好吗", "energy": "中等"},
    (8, 12): {"label": "上午", "tone": "明亮积极", "care": "今天有什么安排吗", "energy": "高"},
    (12, 14): {"label": "中午", "tone": "轻松", "care": "吃午饭了吗", "energy": "中等"},
    (14, 18): {"label": "下午", "tone": "平稳", "care": "下午累不累", "energy": "中高"},
    (18, 21): {"label": "傍晚", "tone": "温暖", "care": "今天辛苦了，吃晚饭了吗", "energy": "中等"},
    (21, 24): {"label": "晚上", "tone": "柔和亲密", "care": "今天过得怎么样", "energy": "中低"},
}

SPECIAL_DATES = {
    (1, 1): "元旦",
    (2, 14): "情人节",
    (3, 8): "妇女节",
    (5, 1): "劳动节",
    (5, 20): "520",
    (6, 1): "儿童节",
    (7, 7): "七夕",
    (8, 7): "七夕",
    (9, 10): "教师节",
    (10, 1): "国庆节",
    (12, 24): "平安夜",
    (12, 25): "圣诞节",
    (12, 31): "跨年夜",
}


class TimeAwareness:
    def __init__(self, memory_store, meta_key="time_awareness", logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.special_dates = {}
        self.first_interaction_date = ""
        self.consecutive_days = 0
        self.last_interaction_date = ""
        self._dirty = False
        self._load()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if isinstance(data, dict):
            self.special_dates = data.get("special_dates", {})
            self.first_interaction_date = data.get("first_interaction_date", "")
            self.consecutive_days = int(data.get("consecutive_days", 0))
            self.last_interaction_date = data.get("last_interaction_date", "")

    def _save(self):
        self.memory_store.save_meta_json(self.meta_key, {
            "special_dates": self.special_dates,
            "first_interaction_date": self.first_interaction_date,
            "consecutive_days": self.consecutive_days,
            "last_interaction_date": self.last_interaction_date,
        })

    def record_interaction(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if not self.first_interaction_date:
            self.first_interaction_date = today
        if self.last_interaction_date:
            try:
                last = datetime.strptime(self.last_interaction_date, "%Y-%m-%d").date()
                current = datetime.now().date()
                gap = (current - last).days
                if gap == 1:
                    self.consecutive_days += 1
                elif gap > 1:
                    self.consecutive_days = 1
            except Exception:
                pass
        self.last_interaction_date = today
        self._dirty = True

    def flush_if_dirty(self):
        if self._dirty:
            self._dirty = False
            self._save()

    def add_special_date(self, month, day, label):
        self.special_dates[f"{month:02d}-{day:02d}"] = label
        self._save()

    def get_current_context(self):
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        period = None
        for (start, end), info in TIME_PERIODS.items():
            if start <= hour < end:
                period = info
                break
        if not period:
            period = TIME_PERIODS[(21, 24)]

        context = {
            "period": period["label"],
            "tone": period["tone"],
            "care_hint": period["care"],
            "energy_hint": period["energy"],
            "is_weekend": weekday >= 5,
            "is_late_night": 0 <= hour < 5,
            "is_early_morning": 5 <= hour < 8,
        }

        date_key = now.strftime("%m-%d")
        if date_key in SPECIAL_DATES:
            context["special_day"] = SPECIAL_DATES[date_key]
        if date_key in self.special_dates:
            context["personal_special_day"] = self.special_dates[date_key]

        if self.first_interaction_date:
            try:
                first = datetime.strptime(self.first_interaction_date, "%Y-%m-%d")
                days_together = (now - first).days
                context["days_together"] = days_together
                if days_together >= 365:
                    context["anniversary"] = f"认识{days_together // 365}年"
                elif days_together >= 30:
                    context["months_together"] = f"认识{days_together // 30}个月"
            except Exception:
                pass

        context["consecutive_days"] = self.consecutive_days
        return context

    def build_time_prompt_context(self):
        ctx = self.get_current_context()
        lines = [f"当前时间段：{ctx['period']}（{ctx['tone']}风格）"]
        if ctx.get("is_weekend"):
            lines.append("今天是周末，可以更轻松一些。")
        if ctx.get("is_late_night"):
            lines.append("现在是深夜，语气要更温柔、低声、关心她怎么还没睡。")
        if ctx.get("special_day"):
            lines.append(f"今天是{ctx['special_day']}，可以自然地提一下。")
        if ctx.get("personal_special_day"):
            lines.append(f"今天是你们的{ctx['personal_special_day']}，对她来说有特别的意义。")
        if ctx.get("days_together"):
            days = ctx["days_together"]
            if days >= 100:
                lines.append(f"你们已经认识{days}天了。")
        if ctx.get("consecutive_days", 0) >= 3:
            lines.append(f"她已经连续{ctx['consecutive_days']}天来找你了，可以温柔地提一句。")
        lines.append(f"关心提示：{ctx['care_hint']}")
        return "\n".join(lines)
