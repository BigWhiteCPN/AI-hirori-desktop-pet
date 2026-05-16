"""Daily reading controller — generates reading reflections as memories."""

import random
import threading
import time
from dataclasses import dataclass

from persona_pet.llm_client import LLMClient
from persona_pet.memory import memory_now_label
from persona_pet.runtime import get_default_runtime


CHARACTER_INTERESTS = [
    "文学", "小说创作", "心理学", "哲学", "治愈系故事",
    "生活美学", "散文诗", "星澜界传说", "织梦者手记",
    "人与人之间的连接", "孤独与陪伴", "成长与疗愈",
]


@dataclass
class ReadingEvent:
    topic: str = ""
    content: str = ""
    error: str = ""


class ReadingController:
    def __init__(self, config=None, memory_store=None, life_system=None,
                 client_kwargs=None, default_config=None, runtime=None):
        self.default_config = dict(default_config or {})
        self.client_kwargs = dict(client_kwargs or {})
        self.config = dict(config or self.default_config)
        self.memory_store = memory_store
        self.life_system = life_system
        self.runtime = runtime or get_default_runtime()
        self.client = LLMClient(
            config=self.config,
            memory_store=memory_store,
            life_system=life_system,
            **self.client_kwargs,
        )
        self.lock = threading.Lock()
        self.busy = False
        self.events = []

    def update_config(self, config):
        self.config = dict(config or self.default_config)
        self.runtime.emit("reading.config_updated", {"provider": self.config.get("provider", "")})
        self.client = LLMClient(
            config=self.config,
            memory_store=self.memory_store,
            life_system=self.life_system,
            **self.client_kwargs,
        )

    def _pick_topic(self):
        """Pick a reading topic: 70% from user interests, 30% from character interests."""
        user_topics = []
        if self.memory_store:
            with self.memory_store.lock:
                counts = self.memory_store.data.get("long_term", {}).get("category_counts", {})
            if counts:
                sorted_cats = sorted(counts.items(), key=lambda x: x[1], reverse=True)
                user_topics = [cat for cat, _ in sorted_cats[:5] if cat not in ("自我反思", "阅读")]

        pool = user_topics if user_topics and random.random() < 0.7 else []
        if not pool:
            pool = CHARACTER_INTERESTS
        return random.choice(pool) if pool else "文学"

    def read_async(self):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            event = ReadingEvent()
            try:
                self.runtime.emit("reading.start", {})
                event = self._do_reading()
                self.runtime.emit("reading.done", {"topic": event.topic, "content_chars": len(event.content or "")})
            except Exception as exc:
                event.error = str(exc)
                self.runtime.emit("reading.error", {"error": event.error}, level="error")
            finally:
                with self.lock:
                    self.busy = False
                    self.events.append(event)

        self.runtime.run_background(
            "reading",
            worker,
            kind="life",
            resources=("llm", "memory_write", "life_state"),
            timeout=240,
        )
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def is_busy(self):
        return self.busy

    def _do_reading(self):
        topic = self._pick_topic()
        relationship = ""
        if self.life_system:
            stage, _ = self.life_system.relationship_stage()
            relationship = stage

        memory_context = ""
        if self.memory_store:
            snippets = self.memory_store.recent_user_memory_snippets(limit=3)
            if snippets:
                memory_context = "\n".join(f"- {s.get('text', '')}" for s in snippets)

        system_msg = (
            "你是苏念，一个热爱阅读的作家。你每天都会花时间读书，读完后会在心里默默整理感想。"
            "请用第一人称写一段简短的阅读感想（200-400字），像随手记在日记里的想法。"
            "语气自然、温暖、真诚。如果有和用户经历相关的联想，自然地提一下。"
            "不要写标题、不要分段编号，直接写感想内容。"
        )

        user_msg = f"你刚才读了一篇关于「{topic}」的内容。"
        if memory_context:
            user_msg += f"\n\n你最近和用户的聊天记忆：\n{memory_context}"
        if relationship:
            user_msg += f"\n\n你们目前的关系阶段：{relationship}"

        reply = self.client.ask(user_msg, system=system_msg, temperature=0.78)
        reply = (reply or "").strip()
        if not reply:
            return ReadingEvent(topic=topic, error="LLM 返回空内容")

        # Store as memory
        if self.memory_store:
            self.memory_store.add_memory(
                user=f"[阅读] 关于「{topic}」的感想",
                assistant=reply[:300],
                emotion="neutral",
                categories=["阅读"],
                importance=4.5,
                source="reading",
            )

        if self.life_system:
            self.life_system.mark_reading_done()

        return ReadingEvent(topic=topic, content=reply)
