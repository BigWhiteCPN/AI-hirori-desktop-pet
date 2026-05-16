"""Behavioral pattern detector that notices anomalies in user behavior."""

import time
from datetime import datetime


class BehaviorBaseline:
    def __init__(self):
        self.avg_session_gap_hours = 0.0
        self.avg_message_length = 0.0
        self.common_active_hours = []
        self.common_emotions = {}
        self.message_frequency_per_hour = 0.0
        self.last_calculated_at = 0.0
        self.sample_count = 0


class PatternDetector:
    def __init__(self, memory_store, life_system, meta_key="pattern_baseline", logger=None):
        self.memory_store = memory_store
        self.life_system = life_system
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.baseline = BehaviorBaseline()
        self.anomalies = []
        self.last_check_at = 0.0
        self.last_anomaly_at = 0.0
        self._dirty = False
        self._load()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if isinstance(data, dict):
            self.baseline.avg_session_gap_hours = float(data.get("avg_session_gap_hours", 0.0))
            self.baseline.avg_message_length = float(data.get("avg_message_length", 0.0))
            self.baseline.common_active_hours = data.get("common_active_hours", [])
            self.baseline.common_emotions = data.get("common_emotions", {})
            self.baseline.message_frequency_per_hour = float(data.get("message_frequency_per_hour", 0.0))
            self.baseline.sample_count = int(data.get("sample_count", 0))
        anomalies_data = self.memory_store.load_meta_json(f"{self.meta_key}_anomalies", [])
        if isinstance(anomalies_data, list):
            self.anomalies = anomalies_data[-20:]

    def _save(self):
        self.memory_store.save_meta_json(self.meta_key, {
            "avg_session_gap_hours": self.baseline.avg_session_gap_hours,
            "avg_message_length": self.baseline.avg_message_length,
            "common_active_hours": self.baseline.common_active_hours,
            "common_emotions": self.baseline.common_emotions,
            "message_frequency_per_hour": self.baseline.message_frequency_per_hour,
            "sample_count": self.baseline.sample_count,
        })
        self.memory_store.save_meta_json(f"{self.meta_key}_anomalies", self.anomalies[-20:])

    def update_baseline(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.last_check_at < 300.0:
            return
        self.last_check_at = now
        with self.memory_store.lock:
            turns = list(self.memory_store.data.get("short_terms", []))
        if len(turns) < 10:
            return
        recent = turns[-80:]
        lengths = []
        emotions = {}
        hours = []
        for t in recent:
            user = t.get("user", "")
            if user:
                lengths.append(len(user))
            emo = t.get("emotion", "neutral")
            emotions[emo] = emotions.get(emo, 0) + 1
            created = t.get("created_at", "")
            if created:
                try:
                    dt = datetime.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
                    hours.append(dt.hour)
                except Exception:
                    pass
        if lengths:
            self.baseline.avg_message_length = sum(lengths) / len(lengths)
        self.baseline.common_emotions = dict(sorted(emotions.items(), key=lambda x: -x[1])[:5])
        if hours:
            hour_counts = {}
            for h in hours:
                hour_counts[h] = hour_counts.get(h, 0) + 1
            self.baseline.common_active_hours = sorted(hour_counts, key=hour_counts.get, reverse=True)[:6]
        self.baseline.sample_count = len(recent)
        self.baseline.last_calculated_at = now
        self._save()

    def detect_anomalies(self, current_text="", current_emotion="neutral", now=None):
        now = time.monotonic() if now is None else now
        if now - self.last_anomaly_at < 600.0:
            return []
        detected = []
        if current_text and self.baseline.avg_message_length > 0:
            current_len = len(current_text)
            avg = self.baseline.avg_message_length
            if avg > 15 and current_len < avg * 0.35 and current_len > 0:
                detected.append({
                    "type": "message_length_drop",
                    "detail": f"消息突然变短（平时{avg:.0f}字，现在{current_len}字），可能心情不好或在忙。",
                    "priority": 0.6,
                    "suggestion": "可以轻轻问一句是不是在忙或者心情不太好。",
                })
            elif current_len > avg * 2.5 and avg > 10:
                detected.append({
                    "type": "message_length_spike",
                    "detail": f"消息突然变长（平时{avg:.0f}字，现在{current_len}字），可能有很多话想说。",
                    "priority": 0.4,
                    "suggestion": "认真看完她的话，给出有分量的回应。",
                })
        if current_emotion != "neutral" and self.baseline.common_emotions:
            top_emotion = max(self.baseline.common_emotions, key=self.baseline.common_emotions.get)
            if current_emotion != top_emotion and current_emotion in ("sadness", "anger", "fear"):
                detected.append({
                    "type": "emotion_shift",
                    "detail": f"她平时多数时候是{top_emotion}，现在是{current_emotion}，可能发生了什么。",
                    "priority": 0.7,
                    "suggestion": "留意她的情绪变化，温柔地关心一下。",
                })
        if self.baseline.common_active_hours:
            current_hour = datetime.now().hour
            if current_hour not in self.baseline.common_active_hours:
                if current_hour >= 1 and current_hour <= 5:
                    detected.append({
                        "type": "unusual_hour",
                        "detail": "她现在还在，平时这个时间应该在睡觉。",
                        "priority": 0.8,
                        "suggestion": "可以温柔地问她怎么还没睡，是不是睡不着或者有心事。",
                    })
        if detected:
            for anomaly in detected:
                anomaly["time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.anomalies.append(anomaly)
            self.last_anomaly_at = now
            self._dirty = True
            self.log_runtime("PATTERN_ANOMALY", {"count": len(detected), "types": [a["type"] for a in detected]})
        return detected

    def build_pattern_context(self, anomalies=None):
        if not anomalies:
            return ""
        lines = ["[行为模式观察]"]
        for a in anomalies[:2]:
            lines.append(f"- {a['detail']}")
            lines.append(f"  建议：{a['suggestion']}")
        return "\n".join(lines)

    def flush_if_dirty(self):
        if self._dirty:
            self._dirty = False
            self._save()

    def get_baseline_summary(self):
        b = self.baseline
        if b.sample_count < 5:
            return "数据还不够，还在观察中。"
        hours = ", ".join(f"{h}点" for h in b.common_active_hours[:3]) if b.common_active_hours else "不确定"
        top_emo = max(b.common_emotions, key=b.common_emotions.get) if b.common_emotions else "平静"
        emo_labels = {"joy": "开心", "sadness": "低落", "anger": "紧绷", "neutral": "平静", "surprise": "惊讶"}
        return f"平时活跃时段：{hours}。多数时候{emo_labels.get(top_emo, top_emo)}。平均消息{b.avg_message_length:.0f}字。"
