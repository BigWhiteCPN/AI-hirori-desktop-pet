import json
import re
import threading
import time
from dataclasses import dataclass

from persona_pet.file_agent import write_docx_file
from persona_pet.llm_client import LLMClient
from persona_pet.memory import memory_now_label


@dataclass
class LifeWritingEvent:
    kind: str = ""
    path: str = ""
    title: str = ""
    content: str = ""
    error: str = ""


class LifeWritingController:
    def __init__(
        self,
        config=None,
        memory_store=None,
        life_system=None,
        client_kwargs=None,
        default_config=None,
        diary_daily_word_limit=700,
    ):
        self.default_config = dict(default_config or {})
        self.client_kwargs = dict(client_kwargs or {})
        self.diary_daily_word_limit = int(diary_daily_word_limit)
        self.config = dict(config or self.default_config)
        self.memory_store = memory_store
        self.life_system = life_system
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
        self.client = LLMClient(
            config=self.config,
            memory_store=self.memory_store,
            life_system=self.life_system,
            **self.client_kwargs,
        )

    def is_busy(self):
        with self.lock:
            return self.busy

    def write_async(self, kind):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            event = LifeWritingEvent(kind=kind)
            try:
                if kind == "diary":
                    event = self.write_diary()
                else:
                    event = self.write_novel()
            except Exception as exc:
                event.error = str(exc)
            with self.lock:
                self.busy = False
                self.events.append(event)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def write_diary(self):
        today = time.strftime("%Y-%m-%d")
        stage, _attitude = self.life_system.relationship_stage()
        max_words = self.diary_daily_word_limit
        prompt = (
            "你是小日和，一名小说作家，也是用户的情感陪伴朋友。"
            "请写一篇今天的私人日记，像真正的人一样记录今天的心情、和用户的关系、自己的写作状态。"
            f"不要写成报告，不要提系统或代码。字数 {max(350, max_words - 250)}-{max_words} 中文字。"
            f"\n日期：{today}\n当前关系：{stage}\n{self.life_system.build_prompt_context()}"
        )
        content = self.client.chat_messages(
            [{"role": "system", "content": "你只写日记正文。"}, {"role": "user", "content": prompt}],
            temperature=0.72,
            timeout=180,
        )
        path = self.life_system.diary_path()
        write_docx_file(path, f"小日和日记 {today}", content)
        self.life_system.mark_diary_written()
        return LifeWritingEvent(kind="diary", path=path, title=f"小日和日记 {today}", content=content)

    def write_novel(self):
        novel = self.life_system.novel
        remaining_words = self.life_system.remaining_novel_words_today()
        if remaining_words <= 0:
            raise RuntimeError("今天的小说写作字数额度已用完。")
        if not novel.get("title"):
            setup_prompt = (
                "你是小日和，一名小说作家。请为你接下来要独立连载的一部长篇小说设计题目和简介。"
                "题材可以是轻小说、都市情感、治愈、奇幻之一，必须温柔、有连续写作空间。"
                "输出 JSON：{\"title\":\"书名\",\"premise\":\"一句话简介\",\"target_chapters\":8}"
            )
            raw = self.client.chat_messages(
                [{"role": "user", "content": setup_prompt}],
                temperature=0.8,
                timeout=120,
            )
            match = re.search(r"\{.*\}", raw, flags=re.S)
            data = {}
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = {}
            novel["title"] = str(data.get("title") or "雨停之后的来信")[:40]
            novel["premise"] = str(data.get("premise") or "一个习惯隐藏心事的女孩，在陪伴他人的过程中慢慢学会理解自己。")[:160]
            try:
                novel["target_chapters"] = int(data.get("target_chapters") or 8)
            except Exception:
                novel["target_chapters"] = 8
            novel["target_chapters"] = max(4, min(16, int(novel["target_chapters"])))

        chapter = int(novel.get("chapter", 0)) + 1
        target = int(novel.get("target_chapters", 8))
        ending_hint = "这一章推进故事，不要完结。" if chapter < target else "这是最终章，请给故事一个完整但余韵温柔的结尾。"
        max_words = max(450, min(remaining_words, 900))
        min_words = max(260, min(520, max_words - 160))
        prompt = (
            f"你是小说作家小日和，正在写长篇小说《{novel.get('title')}》。\n"
            f"小说简介：{novel.get('premise')}\n"
            f"当前要写第 {chapter}/{target} 章。{ending_hint}\n"
            f"请输出本章正文，包含章节标题。字数 {min_words}-{max_words} 中文字。风格细腻、情感真实、有画面感。"
            "不要写大纲，不要解释。"
        )
        content = self.client.chat_messages(
            [{"role": "system", "content": "你只写小说章节正文。"}, {"role": "user", "content": prompt}],
            temperature=0.82,
            timeout=240,
        )
        existing = novel.get("content", "")
        separator = "\n\n" if existing else ""
        novel["content"] = f"{existing}{separator}{content}".strip()
        novel["chapter"] = chapter
        novel["last_written_at"] = memory_now_label()
        if chapter >= target:
            novel["complete"] = True
        path = self.life_system.novel_path()
        novel["path"] = path
        write_docx_file(path, novel.get("title") or "小日和的小说", novel["content"])
        self.life_system.mark_novel_written(content)
        self.life_system.save()
        return LifeWritingEvent(kind="novel", path=path, title=novel.get("title", ""), content=content)
