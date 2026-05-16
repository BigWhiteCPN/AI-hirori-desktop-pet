"""Episodic memory system that groups related turns into complete events."""

import re
import time
from datetime import datetime, timedelta


EPISODE_SIGNALS = {
    "location": ("去", "到", "在", "从", "回家", "出门", "公园", "餐厅", "电影院", "超市", "学校", "公司", "医院", "机场", "车站", "商场", "海边", "山上"),
    "activity": ("吃", "喝", "玩", "看", "买", "做", "写", "画", "唱", "跳", "跑", "走", "睡", "聊", "打", "学", "教", "试", "拍", "录"),
    "social": ("和", "跟", "一起", "约", "见面", "聚会", "约会", "请", "陪"),
    "emotion_shift": ("开心", "难过", "生气", "害怕", "惊讶", "感动", "失望", "兴奋", "紧张", "放松"),
    "time_marker": ("昨天", "今天", "刚才", "上次", "那次", "早上", "中午", "下午", "晚上", "凌晨"),
}


def extract_episode_keywords(text):
    compact = re.sub(r"\s+", "", text or "")
    keywords = []
    for category, signals in EPISODE_SIGNALS.items():
        for signal in signals:
            if signal in compact:
                keywords.append((category, signal))
    return keywords


def turns_are_related(turn_a, turn_b, max_gap_seconds=300):
    time_a = turn_a.get("created_at", "")
    time_b = turn_b.get("created_at", "")
    if time_a and time_b:
        try:
            dt_a = datetime.strptime(time_a[:19], "%Y-%m-%d %H:%M:%S")
            dt_b = datetime.strptime(time_b[:19], "%Y-%m-%d %H:%M:%S")
            gap = abs((dt_b - dt_a).total_seconds())
            if gap > max_gap_seconds:
                return False, 0.0
        except Exception:
            pass
    text_a = f"{turn_a.get('user', '')} {turn_a.get('assistant', '')}"
    text_b = f"{turn_b.get('user', '')} {turn_b.get('assistant', '')}"
    kw_a = set(k for _, k in extract_episode_keywords(text_a))
    kw_b = set(k for _, k in extract_episode_keywords(text_b))
    if not kw_a and not kw_b:
        return False, 0.0
    overlap = kw_a & kw_b
    score = len(overlap) * 0.3
    terms_a = set(turn_a.get("terms") or [])
    terms_b = set(turn_b.get("terms") or [])
    term_overlap = terms_a & terms_b
    score += len(term_overlap) * 0.15
    if turn_a.get("emotion") == turn_b.get("emotion") and turn_a.get("emotion") != "neutral":
        score += 0.2
    return score >= 0.3, score


class Episode:
    def __init__(self):
        self.id = ""
        self.created_at = ""
        self.turns = []
        self.summary = ""
        self.emotion = "neutral"
        self.keywords = []
        self.location = ""
        self.activity = ""
        self.people = []
        self.importance = 0.5

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at,
            "turn_count": len(self.turns),
            "summary": self.summary,
            "emotion": self.emotion,
            "keywords": self.keywords[:10],
            "location": self.location,
            "activity": self.activity,
            "people": self.people,
            "importance": self.importance,
            "user_texts": [t.get("user", "")[:80] for t in self.turns if t.get("user")],
            "assistant_texts": [t.get("assistant", "")[:80] for t in self.turns if t.get("assistant")],
        }

    @staticmethod
    def from_dict(data):
        ep = Episode()
        ep.id = data.get("id", "")
        ep.created_at = data.get("created_at", "")
        ep.summary = data.get("summary", "")
        ep.emotion = data.get("emotion", "neutral")
        ep.keywords = data.get("keywords", [])
        ep.location = data.get("location", "")
        ep.activity = data.get("activity", "")
        ep.people = data.get("people", [])
        ep.importance = data.get("importance", 0.5)
        return ep


class EpisodicMemoryStore:
    def __init__(self, memory_store, meta_key="episodic_memory", logger=None):
        self.memory_store = memory_store
        self.meta_key = meta_key
        self.log_runtime = logger or (lambda *parts: None)
        self.episodes = []
        self.pending_buffer = []
        self.last_processed_index = 0
        self.last_processed_turn_id = ""
        self.last_processed_at = ""
        self._load()

    def _load(self):
        data = self.memory_store.load_meta_json(self.meta_key, {})
        if isinstance(data, dict):
            raw_episodes = data.get("episodes", [])
            self.episodes = [Episode.from_dict(ep) for ep in raw_episodes if isinstance(ep, dict)]
            self.last_processed_index = int(data.get("last_processed_index", 0))
            self.last_processed_turn_id = str(data.get("last_processed_turn_id") or "")
            self.last_processed_at = str(data.get("last_processed_at") or "")
            pending = data.get("pending_buffer", [])
            self.pending_buffer = [turn for turn in pending if isinstance(turn, dict)]

    def _save(self):
        self.memory_store.save_meta_json(self.meta_key, {
            "episodes": [ep.to_dict() for ep in self.episodes[-50:]],
            "last_processed_index": self.last_processed_index,
            "last_processed_turn_id": self.last_processed_turn_id,
            "last_processed_at": self.last_processed_at,
            "pending_buffer": self.pending_buffer[-4:],
        })

    def process_new_turns(self):
        with self.memory_store.lock:
            all_turns = list(self.memory_store.data.get("short_terms", []))
        start_index = None
        if self.last_processed_turn_id:
            for index, turn in enumerate(all_turns):
                if str(turn.get("id") or "") == self.last_processed_turn_id:
                    start_index = index + 1
                    break
        if start_index is None and self.last_processed_at:
            new_turns = [
                turn for turn in all_turns
                if str(turn.get("created_at") or "") > self.last_processed_at
            ]
        else:
            if start_index is None:
                start_index = min(max(0, self.last_processed_index), len(all_turns))
            new_turns = all_turns[start_index:]
        if not new_turns:
            return 0
        episodes_created = 0
        for turn in new_turns:
            if turn.get("reflection"):
                continue
            if self.pending_buffer:
                related, score = turns_are_related(self.pending_buffer[-1], turn)
                if related:
                    self.pending_buffer.append(turn)
                    continue
                if len(self.pending_buffer) >= 2:
                    episode = self._finalize_episode(self.pending_buffer)
                    if episode:
                        self.episodes.append(episode)
                        episodes_created += 1
            self.pending_buffer = [turn]
        if len(self.pending_buffer) >= 3:
            episode = self._finalize_episode(self.pending_buffer)
            if episode:
                self.episodes.append(episode)
                episodes_created += 1
                self.pending_buffer = self.pending_buffer[-1:]
        last_turn = new_turns[-1]
        self.last_processed_index = len(all_turns)
        self.last_processed_turn_id = str(last_turn.get("id") or self.last_processed_turn_id)
        self.last_processed_at = str(last_turn.get("created_at") or self.last_processed_at)
        self._save()
        if episodes_created > 0:
            self.log_runtime("EPISODE_CREATED", {"count": episodes_created, "total": len(self.episodes)})
        return episodes_created

    def _finalize_episode(self, turns):
        if not turns:
            return None
        episode = Episode()
        import uuid
        episode.id = str(uuid.uuid4())
        episode.created_at = turns[0].get("created_at", "")
        episode.turns = turns
        all_text = " ".join(
            f"{t.get('user', '')} {t.get('assistant', '')}" for t in turns
        )
        all_keywords = []
        for t in turns:
            all_keywords.extend(t.get("terms", []))
        seen = set()
        unique_keywords = []
        for kw in all_keywords:
            if kw not in seen and len(kw) >= 2:
                seen.add(kw)
                unique_keywords.append(kw)
        episode.keywords = unique_keywords[:15]
        episode.emotion = self._dominant_emotion(turns)
        episode.location = self._extract_location(all_text)
        episode.activity = self._extract_activity(all_text)
        episode.people = self._extract_people(all_text)
        episode.importance = self._compute_importance(turns)
        episode.summary = self._generate_summary(turns)
        return episode

    def _dominant_emotion(self, turns):
        emotions = {}
        for t in turns:
            emo = t.get("emotion", "neutral")
            if emo != "neutral":
                emotions[emo] = emotions.get(emo, 0) + 1
        if not emotions:
            return "neutral"
        return max(emotions, key=emotions.get)

    def _extract_location(self, text):
        compact = re.sub(r"\s+", "", text)
        locations = ("公园", "餐厅", "电影院", "超市", "学校", "公司", "医院", "机场", "车站", "商场", "海边", "山上", "家里", "卧室", "客厅", "厨房", "浴室", "阳台", "咖啡厅", "图书馆", "民政局")
        for loc in locations:
            if loc in compact:
                return loc
        return ""

    def _extract_activity(self, text):
        compact = re.sub(r"\s+", "", text)
        activities = {
            "吃饭": "吃饭", "看电影": "看电影", "散步": "散步", "逛街": "逛街",
            "旅行": "旅行", "领证": "领证", "结婚": "结婚", "约会": "约会",
            "写小说": "写作", "写日记": "写作", "玩游戏": "游戏", "聊天": "聊天",
        }
        for keyword, activity in activities.items():
            if keyword in compact:
                return activity
        return ""

    def _extract_people(self, text):
        compact = re.sub(r"\s+", "", text)
        people = []
        if any(w in compact for w in ("我们", "一起", "和你", "跟你")):
            people.append("用户")
        if any(w in compact for w in ("朋友", "闺蜜", "同事", "同学")):
            people.append("朋友")
        if any(w in compact for w in ("妈妈", "爸爸", "家人", "父母")):
            people.append("家人")
        return people

    def _compute_importance(self, turns):
        score = 0.3
        score += min(0.3, len(turns) * 0.06)
        emotions = set(t.get("emotion", "neutral") for t in turns)
        emotions.discard("neutral")
        score += len(emotions) * 0.1
        all_text = " ".join(f"{t.get('user', '')} {t.get('assistant', '')}" for t in turns)
        important_keywords = ("喜欢", "爱", "讨厌", "害怕", "重要", "秘密", "承诺", "记住", "永远", "第一次", "最后一次", "结婚", "分手", "告白")
        for kw in important_keywords:
            if kw in all_text:
                score += 0.1
        return min(1.0, score)

    def _generate_summary(self, turns):
        if not turns:
            return ""
        user_texts = [t.get("user", "") for t in turns if t.get("user")]
        if not user_texts:
            return ""
        first = user_texts[0][:40]
        if len(user_texts) == 1:
            return f"用户说：{first}"
        last = user_texts[-1][:40]
        return f"从「{first}」到「{last}」，共{len(turns)}轮对话"

    def search_episodes(self, query, limit=3):
        compact = re.sub(r"\s+", "", query or "")
        if not compact:
            return []
        scored = []
        for ep in self.episodes:
            score = 0.0
            for kw in ep.keywords:
                if kw in compact or compact in kw:
                    score += 0.3
            if ep.location and ep.location in compact:
                score += 0.4
            if ep.activity and ep.activity in compact:
                score += 0.3
            for turn in ep.turns:
                user = turn.get("user", "")
                if any(chunk in compact for chunk in [user[i:i+4] for i in range(max(0, len(user)-3))]):
                    score += 0.2
                    break
            score += ep.importance * 0.2
            if score > 0.1:
                scored.append((score, ep))
        scored.sort(key=lambda x: -x[0])
        return [ep for _, ep in scored[:limit]]

    def build_episode_context(self, query):
        episodes = self.search_episodes(query, limit=2)
        if not episodes:
            return ""
        lines = []
        for ep in episodes:
            parts = []
            if ep.activity:
                parts.append(ep.activity)
            if ep.location:
                parts.append(f"在{ep.location}")
            if ep.people:
                parts.append(f"和{'、'.join(ep.people)}")
            context = "，".join(parts) if parts else ""
            line = f"事件回忆（{ep.created_at[:10]}）：{context}。{ep.summary}"
            lines.append(line)
        return "\n".join(lines)

    def get_recent_episodes(self, limit=5):
        return [ep.to_dict() for ep in self.episodes[-limit:]]
