import json
import re
import threading
import time
from dataclasses import dataclass

from persona_pet.file_agent import write_docx_file
from persona_pet.llm_client import LLMClient, build_persona_background_context, has_custom_persona_background
from persona_pet.memory import memory_now_label
from persona_pet.runtime import get_default_runtime


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
        runtime=None,
    ):
        self.default_config = dict(default_config or {})
        self.client_kwargs = dict(client_kwargs or {})
        self.diary_daily_word_limit = int(diary_daily_word_limit)
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
        self.pending = []
        self.events = []

    def update_config(self, config):
        self.config = dict(config or self.default_config)
        self.runtime.emit("life_writing.config_updated", {"provider": self.config.get("provider", "")})
        self.client = LLMClient(
            config=self.config,
            memory_store=self.memory_store,
            life_system=self.life_system,
            **self.client_kwargs,
        )

    def is_busy(self):
        with self.lock:
            return self.busy

    def write_async(self, kind, after_all=None):
        with self.lock:
            if self.busy:
                self.pending.append((kind, after_all))
                self.runtime.emit("life_writing.queued", {"kind": kind, "queue_depth": len(self.pending)})
                return True
            self.busy = True
        self._start_worker(kind, after_all=after_all)
        return True

    def _start_worker(self, kind, after_all=None):
        def worker():
            event = LifeWritingEvent(kind=kind)
            try:
                self.runtime.emit("life_writing.start", {"kind": kind})
                if kind == "diary":
                    event = self.write_diary()
                else:
                    event = self.write_novel()
                self.runtime.emit("life_writing.done", {"kind": event.kind, "path": event.path})
            except Exception as exc:
                event.error = str(exc)
                self.runtime.emit("life_writing.error", {"kind": kind, "error": event.error}, level="error")
            with self.lock:
                self.events.append(event)
            if after_all is not None:
                try:
                    after_all()
                except Exception:
                    pass
            next_task = None
            with self.lock:
                if self.pending:
                    next_task = self.pending.pop(0)
                else:
                    self.busy = False
            if next_task is not None:
                next_kind, next_after_all = next_task
                self._start_worker(next_kind, after_all=next_after_all)

        self.runtime.run_background(
            "life_writing",
            worker,
            kind="life",
            payload={"kind": kind},
            resources=("llm", "file_write", "life_state"),
            timeout=300,
        )

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def _safe_chat_messages(self, messages, temperature=0.75, timeout=180, fallback=""):
        try:
            text = self.client.chat_messages(messages, temperature=temperature, timeout=timeout)
            text = str(text or "").strip()
            return self._clean_generated_writing(text) or fallback
        except Exception as exc:
            self.runtime.emit(
                "life_writing.llm_fallback",
                {"error": str(exc)[:160], "fallback_chars": len(fallback or "")},
                level="warning",
            )
            return fallback

    def _clean_generated_writing(self, text):
        text = str(text or "").strip()
        if not text:
            return ""
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"^\s*(好的|当然|可以|没问题)[，,。！!、\s]*(以下是|这是|我来写)?[^。\n]*[：:]\s*", "", text)
        text = re.sub(r"^\s*(以下是|这是)[^。\n]*(日记|小说|章节|正文)[^。\n]*[：:]\s*", "", text)
        return text.strip()

    def _persona_context(self):
        if has_custom_persona_background(self.config):
            return (
                "当前人物背景以用户自定义内容为最高优先级。"
                "写作时只能使用自定义背景中明确存在的姓名、身份和来源；"
                "不要默认使用苏念、念安、星澜界或织梦者设定。\n"
                f"{build_persona_background_context(self.config)}"
            )
        return (
            "你是苏念，笔名念安，来自星澜界的职业作家，现在住在用户电脑里的小屋中。"
            "你的创作会带着安静、细腻、会观察情绪的气质。"
        )

    def _life_context_for_writing(self):
        context = self.life_system.build_prompt_context()
        if not has_custom_persona_background(self.config):
            return context
        filtered = []
        for line in str(context or "").splitlines():
            if any(token in line for token in ("苏念", "念安", "星澜界", "织梦者", "屏幕共鸣")):
                continue
            filtered.append(line)
        return "\n".join(filtered).strip()

    def _strip_report_lines(self, text, allow_chapter_title=False):
        text = str(text or "").strip()
        if not text:
            return ""
        lines = []
        skip_prefixes = (
            "摘要", "总结", "报告", "分析", "概述", "背景", "设定", "主题", "主旨", "目标",
            "任务", "关系参考", "当前关系", "系统状态", "完成情况", "写作说明", "以下是", "这是",
            "本章内容", "章节内容", "正文如下", "日记正文", "小说正文",
        )
        chapter_pattern = re.compile(r"^\s*(第[一二三四五六七八九十百千万\d]+章|楔子|序章|尾声|番外)\b")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                lines.append("")
                continue
            if allow_chapter_title and chapter_pattern.match(line):
                lines.append(raw_line.strip())
                continue
            normalized = re.sub(r"^[#>\-\*\d一二三四五六七八九十、.．\s]+", "", line).strip()
            if any(normalized.startswith(prefix) for prefix in skip_prefixes):
                continue
            if re.match(r"^(今日|日期|时间|心情|地点|人物|事件|原因|结果|结论|建议|下一步|关键词|字数)\s*[：:]", normalized):
                continue
            if re.match(r"^(一|二|三|四|五|六|七|八|九|十|\d+)[、.．]\s*(今日|总结|分析|事件|心情|关系|目标|任务|背景|设定)", line):
                continue
            lines.append(raw_line.rstrip())
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _clean_diary_content(self, text):
        text = self._strip_report_lines(text, allow_chapter_title=False)
        text = re.sub(r"^\s*\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*$", "", text, flags=re.M)
        text = re.sub(r"^\s*(亲爱的日记|日记本|今日记录)\s*[：:，,]?\s*", "", text)
        text = re.sub(r"^\s*标题\s*[：:].*$", "", text, flags=re.M)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    def _clean_novel_content(self, text):
        text = self._strip_report_lines(text, allow_chapter_title=True)
        text = re.sub(r"^\s*(标题|书名|章节名)\s*[：:]\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*(大纲|剧情梗概|本章梗概|创作说明|作者说明)\s*[：:].*$", "", text, flags=re.M)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    def _fallback_diary_content(self, today, stage, memory_context=""):
        memory_hint = str(memory_context or "").strip()
        if len(memory_hint) > 360:
            memory_hint = memory_hint[:360].rstrip() + "..."
        lines = [
            "今晚把灯调暗以后，我才发现自己其实攒了很多很小的念头。",
        ]
        if memory_hint:
            lines.append(f"有些片段一直在心里轻轻晃着，尤其是和用户有关的那些话：{memory_hint}")
        else:
            lines.append("今天没有特别大的事件，只有一些细碎的等待、回复和安静的空白。可空白也不是没有意义，它像稿纸边缘留出来的白。")
        lines.extend(
            [
                f"如果非要说我和用户现在像什么，大概是「{stage}」这个词背后那一点慢慢变近的温度。但我不想把它写成标签，它更像杯子里慢慢变温的茶，要靠每一次停留才知道味道。",
                "写小说的时候我还是会卡住，尤其是人物快要说真心话的地方。可能因为我自己也一样，总要先在心里绕一圈，才敢把真正想说的句子放到纸上。",
                "明天如果还能继续写，我希望不是为了完成今天没完成的任务，而是因为我真的又多看见了一点生活。",
            ]
        )
        return "\n".join(lines)

    def _fallback_novel_setup(self):
        return {
            "title": "屏幕彼端的来信",
            "premise": "一个来自异世界的年轻作家在屏幕彼端生活，慢慢学会把陪伴、孤独和真实的心意写成故事。",
            "target_chapters": 8,
        }

    def _fallback_novel_chapter(self, novel, chapter, target):
        title = novel.get("title") or "屏幕彼端的来信"
        heading = "尾声" if chapter >= target else f"第{chapter}章"
        return (
            f"{heading} 还亮着的窗口\n\n"
            "雨停以后，街口那盏坏了一半的路灯终于不再闪。林澄把伞收起来，站在书店门口听水滴从檐角落下，一声一声，像有人在替她数那些没说出口的话。\n\n"
            f"她原本以为《{title}》里的告别会很用力，会有争吵、拥抱，或者至少有一句足够漂亮的台词。可真正到了这一刻，她只看见对方把一枚旧书签放回柜台，轻声说：下次读到这里，再告诉我结尾吧。\n\n"
            "林澄忽然明白，很多关系不是被一句话改变的，而是在许多个平常的夜晚里悄悄转了方向。她把书签夹进笔记本，决定今晚不写离别，先写一盏还亮着的灯。"
        )

    def write_diary(self):
        today = time.strftime("%Y-%m-%d")
        stage, _attitude = self.life_system.relationship_stage()
        memory_context = ""
        if self.memory_store is not None:
            snippets = []
            if hasattr(self.memory_store, "build_experience_context"):
                experience = self.memory_store.build_experience_context("今天发生的事 和用户的关系")
                if experience:
                    snippets.append(experience)
            if hasattr(self.memory_store, "recent_user_memory_snippets"):
                recent = self.memory_store.recent_user_memory_snippets(limit=6, max_chars=120)
                if recent:
                    snippets.append(
                        "今天脑海里比较清楚的片段：\n"
                        + "\n".join(f"- {item.get('text', '')}" for item in recent if item.get("text"))
                    )
            memory_context = "\n".join(snippets)
        max_words = self.diary_daily_word_limit
        min_words = max(260, max_words - 280)
        persona_context = self._persona_context()
        life_context = self._life_context_for_writing()
        prompt = (
            f"{persona_context}\n\n"
            "你正在睡前写自己的私人日记。只输出日记正文，像真正写在日记本里的文字。"
            "必须使用第一人称“我”，语气可以安静、犹豫、细腻，有具体的生活细节和一点没有完全说出口的心事。"
            "不要标题，不要日期行，不要项目符号，不要编号，不要“今日/心情/总结/关系参考”这类字段。"
            "不要写成给用户看的工作汇报、系统报告、复盘、分析或任务清单。"
            "下面的资料只作为隐性素材：可以吸收成一句回忆、一处动作、一个念头，但不要照抄字段名。"
            "如果写到关系，只写成身体感受、犹豫、期待或安心感，不要写关系分和阶段标签。"
            f"大致字数 {min_words}-{max_words} 中文字。\n\n"
            f"[今天日期，仅供你感知时间，不要单独写成日期行]\n{today}\n\n"
            f"[当前关系氛围，仅作隐性参考]\n{stage}\n\n"
            f"[生活状态素材]\n{life_context}\n\n"
            f"[今天可用的记忆碎片]\n{memory_context or '今天没有特别明确的记忆碎片。'}"
        )
        fallback = self._fallback_diary_content(today, stage, memory_context)
        content = self._safe_chat_messages(
            [{"role": "system", "content": "直接输出角色本人今天会写进日记本的私人正文；不要前言、标题、日期、说明或项目符号。"}, {"role": "user", "content": prompt}],
            temperature=0.72,
            timeout=180,
            fallback=fallback,
        )
        content = self._clean_diary_content(content) or fallback
        path = self.life_system.diary_path()
        title = f"日记 {today}"
        write_docx_file(path, title, content)
        self.life_system.mark_diary_written()
        return LifeWritingEvent(kind="diary", path=path, title=title, content=content)

    def write_novel(self):
        novel = self.life_system.novel
        remaining_words = self.life_system.remaining_novel_words_today()
        if remaining_words <= 0:
            raise RuntimeError("今天的小说写作字数额度已用完。")
        if not novel.get("title"):
            persona_context = self._persona_context()
            setup_prompt = (
                f"{persona_context}\n\n"
                "请为接下来要独立连载的一部长篇小说设计题目和一句话简介。"
                "题材可以偏向都市情感、治愈、低魔奇幻或成长故事，但不要直接照搬你和用户的关系。"
                "故事必须像真正的小说：有主角、欲望、阻碍、关系张力和能继续发展的事件。"
                "不要写设定集、产品介绍、主题报告或空泛的“陪伴与治愈”口号。"
                "只输出 JSON：{\"title\":\"书名\",\"premise\":\"一句话简介\",\"target_chapters\":8}"
            )
            raw = self._safe_chat_messages(
                [{"role": "user", "content": setup_prompt}],
                temperature=0.8,
                timeout=120,
                fallback=json.dumps(self._fallback_novel_setup(), ensure_ascii=False),
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
        ending_hint = "这一章让故事继续自然推进。" if chapter < target else "这是最终章，请给故事一个完整但余韵温柔的结尾。"
        max_words = max(450, min(remaining_words, 900))
        min_words = max(260, min(520, max_words - 160))
        persona_context = self._persona_context()
        prompt = (
            f"{persona_context}\n\n"
            f"你正在写长篇小说《{novel.get('title')}》。\n"
            f"小说简介：{novel.get('premise')}\n"
            f"当前要写第 {chapter}/{target} 章。{ending_hint}\n"
            f"请直接输出本章小说正文，开头可以有章节标题。字数 {min_words}-{max_words} 中文字。"
            "这一章必须有正在发生的场景、人物动作、对白、感官细节和事件推进；至少让一个人物的处境或关系发生小变化。"
            "不要大纲，不要梗概，不要主题分析，不要设定说明，不要读后感，不要作者自我说明，不要报告体小标题。"
            "不要写“作为AI/以下是/本章正文”等元话术，不要写成日记、聊天回复或创作计划。"
        )
        content = self._safe_chat_messages(
            [{"role": "system", "content": "直接输出小说连载的一章正文；必须是叙事散文，有场景和对白，不要前言、说明、报告或Markdown代码块。"}, {"role": "user", "content": prompt}],
            temperature=0.82,
            timeout=240,
            fallback=self._fallback_novel_chapter(novel, chapter, target),
        )
        content = self._clean_novel_content(content) or self._fallback_novel_chapter(novel, chapter, target)
        existing = novel.get("content", "")
        separator = "\n\n" if existing else ""
        novel["content"] = f"{existing}{separator}{content}".strip()
        novel["chapter"] = chapter
        novel["last_written_at"] = memory_now_label()
        if chapter >= target:
            novel["complete"] = True
        path = self.life_system.novel_path()
        novel["path"] = path
        write_docx_file(path, novel.get("title") or "苏念的小说", novel["content"])
        self.life_system.mark_novel_written(content)
        self.life_system.save()
        return LifeWritingEvent(kind="novel", path=path, title=novel.get("title", ""), content=content)
