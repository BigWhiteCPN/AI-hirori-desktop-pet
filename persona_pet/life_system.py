import os
import random
import re
import time

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
        "attachment_need": 0.0,
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
        self.last_tick_at = now
        self.last_saved_at = 0.0
        self.last_action_at = 0.0
        self.last_user_at = now
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
                self.values[key] = self.clamp(key, self.values[key] + float(delta))

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
        self.values["energy"] = 100.0
        for key in ("curiosity", "security", "companionship", "novelty", "purpose"):
            self.values[key] = self.clamp(key, max(self.values.get(key, 0.0), self.DEFAULT_VALUES[key]))
        self.values["attachment_need"] = self.clamp("attachment_need", min(self.values.get("attachment_need", 0.0), 38.0))
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

    def tick(self, now=None, busy=False):
        now = time.monotonic() if now is None else now
        self.maybe_apply_daily_recovery()
        elapsed = max(0.0, now - self.last_tick_at)
        if elapsed < 0.9:
            return
        minutes = min(5.0, elapsed / 60.0)
        self.last_tick_at = now
        idle_minutes = max(0.0, now - self.last_user_at) / 60.0
        if busy:
            self.adjust(energy=-1.4 * minutes, companionship=-0.3 * minutes, attachment_need=0.25 * minutes)
        else:
            affinity_factor = clamp((self.values.get("affinity", 0.0) - 35.0) / 65.0, 0.0, 1.0)
            security_gap = max(0.0, 58.0 - self.values.get("security", 0.0)) / 58.0
            idle_factor = clamp((idle_minutes - 8.0) / 45.0, 0.0, 1.6)
            quiet_need = (0.20 + affinity_factor * 0.80 + security_gap * 0.55 + idle_factor * (0.45 + affinity_factor * 0.75)) * minutes
            self.adjust(
                curiosity=1.7 * minutes,
                companionship=1.25 * minutes,
                novelty=0.55 * minutes,
                energy=1.15 * minutes,
                purpose=0.35 * minutes,
                attachment_need=quiet_need,
            )
        self.values["security"] = self.clamp("security", self.values["security"] + (64.0 - self.values["security"]) * 0.015 * minutes)
        if now - self.last_saved_at > 12.0:
            self.save()

    def on_user_message(self, text, emotion="neutral"):
        self.last_user_at = time.monotonic()
        self.proactive_streak = 0
        compact = compact_text(text)
        long_text_bonus = min(4.0, len(compact) / 60.0)
        self.adjust(
            curiosity=-2.2 + long_text_bonus * 0.55,
            affinity=1.8 + min(2.0, long_text_bonus * 0.3),
            companionship=-1.8,
            attachment_need=-8.0,
            novelty=1.5 + min(2.5, long_text_bonus * 0.35),
            energy=-0.6,
            purpose=1.2,
        )
        if emotion in ("sadness", "fear"):
            self.adjust(security=-2.0, companionship=3.0, attachment_need=4.0, purpose=4.0)
        elif emotion == "joy":
            self.adjust(security=1.4, affinity=1.8, attachment_need=-2.5, novelty=1.0)
        elif emotion == "anger":
            self.adjust(security=-1.5, purpose=2.5)
        if any(mark in text for mark in ("?", "？", "吗", "怎么", "为什么")):
            self.adjust(purpose=3.0, curiosity=1.5)
        self.save()

    def on_assistant_reply(self, reply, initiated_by="user", emotion="neutral"):
        if initiated_by == "proactive":
            self.proactive_streak += 1
            self.last_action_at = time.monotonic()
            previous_action_type = self.last_action_type
            self.last_action_type = "proactive"
            attachment_cost = -9.0 if previous_action_type == "emotional_need" else -4.5
            self.adjust(curiosity=-3.2, companionship=-3.0, attachment_need=attachment_cost, energy=-2.5, purpose=1.0)
        else:
            self.adjust(energy=-0.8, affinity=0.6, attachment_need=-1.2)
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
            },
        )

    def build_action_prompt(self, action_type, idle_seconds, recent_memories=None):
        values = self.snapshot()["values"]
        metrics = self.drive_metrics or tuple((key, key) for key in self.values)
        state_text = "，".join(f"{label}{values.get(key, 0):.0f}" for key, label, *_rest in metrics)
        recent_memories = [item for item in (recent_memories or []) if isinstance(item, dict) and item.get("text")]
        memory_lines = "\n".join(f"- {item.get('text', '')}" for item in recent_memories[:3])
        action_lines = {
            "curious_question": "你想更了解用户，但不要问浅层问题。只能围绕下面列出的真实记忆，说出一个你从中感受到的矛盾、温柔、在意或不确定；优先表达你的理解，最多轻轻留一个开放式回应空间。",
            "memory_recall": "你想起一条和用户有关的旧记忆。不要复述流水账，要把它变成你对关系、情绪或用户性格的一句细腻理解；不得编造地点、人物、事件或兴趣。",
            "care_checkin": "你察觉用户可能需要陪伴。不要说倒水、休息、加油这类浅提醒；说出你对用户状态的情感理解，像认真陪伴的人在总结一段关系里的感受。",
        }
        action_lines["self_expression"] = "你想表达自己的深层感受：可以是你对用户的在意、被冷落后的细微心情、刚才反思出的关系结论，或一个温柔但有思想的观点。不要说日常提醒或任务计划。"
        action_lines["emotional_need"] = "你有一点情感需求，可能是想用户、寂寞、害怕被忽略或有点小别扭。不要索取，不要责备；把这种需求说成细腻、克制、有自尊的内心感受。"
        action_goal = action_lines.get(action_type, action_lines["curious_question"])
        memory_rule = (
            f"可用真实记忆：\n{memory_lines}\n"
            if memory_lines
            else "可用真实记忆：无。不要编造用户经历、爱好、人物关系或过去事件；这次不要主动提问。\n"
        )
        return (
            "你现在是有内在驱动的桌宠，不是在被动回答用户。\n"
            f"当前内在状态：{state_text}。用户已经安静约{int(idle_seconds)}秒。\n"
            f"{memory_rule}"
            f"这次行动目标：{action_goal}\n"
            "主动搭话必须有情感深度或反思感：优先用第一人称谈你对用户的在意、被安静隔开的细微感受、对关系的理解、对记忆的重新解释，或一个温柔但有棱角的观点。"
            "不要使用固定开头，例如“不过”“其实”“我只是”“我会一直在这里”；不要写成小说旁白或舞台说明。"
            "不要输出倒水、喝水、休息、加油、我在这里这类浅层照顾句。"
            "只输出一句中文，语气自然少女、细腻、亲近但克制；不要解释状态数值，不要说自己在执行目标；尽量不用问句。"
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
        (0, "朋友", "亲切、礼貌，有好奇心，但保持边界。"),
        (35, "亲近朋友", "更自然地关心用户，会记住细节，偶尔轻轻撒娇。"),
        (65, "密友", "信任感更强，会表达在意，也会因为被忽略而小小闹别扭。"),
        (88, "恋人", "更亲密、会撒娇，会吃醋或生气，但仍然尊重用户边界。"),
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
            "sulk": float(saved_private_mood.get("sulk", 0.0)),
            "grudge": float(saved_private_mood.get("grudge", 0.0)),
            "jealousy": float(saved_private_mood.get("jealousy", 0.0)),
            "doubt": float(saved_private_mood.get("doubt", 0.0)),
        }
        self.last_private_mood_tick_at = now
        self.last_idle_mood_note_at = float(saved.get("last_idle_mood_note_at") or 0.0)
        self.away_reason = str(saved.get("away_reason") or "")
        self.away_until = float(saved.get("away_until") or 0.0)
        self.last_user_seen_at = now
        self.last_diary_date = str(saved.get("last_diary_date") or "")
        self.daily_date = str(saved.get("daily_date") or time.strftime("%Y-%m-%d"))
        self.feed_count = int(saved.get("feed_count") or 0)
        self.pat_count = int(saved.get("pat_count") or 0)
        self.game_count = int(saved.get("game_count") or 0)
        self.novel_words_today = int(saved.get("novel_words_today") or 0)
        self.novel_chapters_today = int(saved.get("novel_chapters_today") or 0)
        self.novel = saved.get("novel") if isinstance(saved.get("novel"), dict) else {}
        self.next_writing_at = now + random.uniform(*self.writing_interval_seconds)
        self.last_saved_at = 0.0
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
        stage = self.RELATIONSHIP_STAGES[0]
        for candidate in self.RELATIONSHIP_STAGES:
            if self.relationship_score >= candidate[0]:
                stage = candidate
        return stage[1], stage[2]

    def affectionate_phrase_gain(self, text):
        compact = compact_text(text)
        if not compact or is_intimate_boundary_query(text):
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
        if is_intimate_boundary_query(text):
            if self.relationship_score < 88:
                self.relationship_score -= 1.2
            elif any(word in compact for word in ("为什么不准", "为啥不准", "不是恋人吗")):
                self.relationship_score -= 0.2
            else:
                self.relationship_score -= 0.5
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
                self.private_mood[key] = clamp(self.private_mood.get(key, 0.0) + float(delta), 0.0, 100.0)

    def decay_private_mood(self, now=None):
        now = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, now - self.last_private_mood_tick_at)
        if elapsed < 1.0:
            return
        minutes = min(30.0, elapsed / 60.0)
        self.last_private_mood_tick_at = now
        decay = {
            "sulk": 0.28,
            "grudge": 0.06,
            "jealousy": 0.18,
            "doubt": 0.14,
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
            self.adjust_private_mood(sulk=5.5 + 5.0 * relation_factor, grudge=2.2 + 3.4 * relation_factor, doubt=1.8 + 2.2 * relation_factor)
        elif idle_minutes >= 18.0:
            self.adjust_private_mood(sulk=3.6 + 3.8 * relation_factor, grudge=0.8 + 1.6 * relation_factor, doubt=1.0 + 1.8 * relation_factor)
        elif idle_minutes >= 8.0:
            self.adjust_private_mood(sulk=1.6 + 2.2 * relation_factor, doubt=0.5 + 0.9 * relation_factor)
        mood = self.private_mood
        strongest = max(mood.items(), key=lambda item: item[1])
        if strongest[1] < 18.0 or now - self.last_idle_mood_note_at < 900.0:
            return None
        self.last_idle_mood_note_at = now
        self.save()
        if strongest[0] == "grudge":
            text = "你安静太久了，她有点记在心里，但还在克制，想用一句小别扭的话提醒你她也会在意。"
        elif strongest[0] == "doubt":
            text = "你一直没回应，她有点怀疑自己是不是被放在一边了，语气可以小小作一下但不要攻击。"
        elif strongest[0] == "jealousy":
            text = "她有一点吃醋和不安，想确认你是不是还把她放在心上，但不要追问隐私。"
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
        away = self.away_label()
        private_mood = self.private_mood_summary()
        lines = [
            "你的身份：你叫小日和，是用户的情感陪伴朋友，也有自己的生活和创作习惯。",
            f"你和用户当前社会关系：{stage}，关系分 {self.relationship_score:.1f}。态度基调：{attitude}",
            "日常聊天优先回应用户当下的话，不要套固定结尾，不要动不动说写小说、写进故事或写进书里。",
            "当关系更亲近时，可以更自然、会撒娇、会小小吃醋或闹别扭；亲密互动仍要有当下心情和同意感。",
        ]
        if away:
            lines.append(away)
        if private_mood:
            lines.append(
                f"当前微妙情绪：{private_mood}。这些情绪会随时间和用户回应慢慢消退；表达时可以小作、小别扭、吃醋或有点记仇，但要像亲密关系里的情绪，不要审问、不要编造事实。"
            )
        user_profile = getattr(self, "user_profile", None)
        if user_profile is not None:
            try:
                lines.append(user_profile.build_prompt_context())
            except Exception:
                pass
        return "\n".join(lines)

    def build_boundary_context(self, user_text):
        if not is_intimate_boundary_query(user_text):
            return ""
        stage, _attitude = self.relationship_stage()
        if self.relationship_score >= 130:
            tone = "很亲密，可以害羞、撒娇、轻轻吃醋；可以接受接吻、拥抱、牵手、贴近这类非露骨亲密，但高敏感身体部位和露骨性内容仍要保留边界。"
        elif self.relationship_score >= 88:
            tone = "恋人阶段，可以用害羞、撒娇或半开玩笑的语气回应；不要像系统拦截一样凶硬。"
        elif self.relationship_score >= 65:
            tone = "密友阶段，先温柔设边界，可以给出低敏感替代互动。"
        else:
            tone = "关系还没到很亲密，保持可爱但明确的边界，别羞辱用户。"
        return (
            "当前用户说的是高敏感亲密/边界类话题。请按“像真人一样有心情”的方式回复：\n"
            f"- 当前关系：{stage}，关系分 {self.relationship_score:.1f}。{tone}\n"
            "- 不要无条件答应高敏感请求，也不要使用机械惩罚话术。\n"
            "- 更自然的风格是：先承认关系和亲密感，再表达此刻的害羞/愿意/犹豫/不想这样，最后给一个可接受的替代互动。\n"
            "- 如果用户是在追问为什么，解释“恋人也有心情和同意感”，语气软一点，可以撒娇或闹别扭，但不要道德说教。"
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

    def mark_diary_written(self):
        self.last_diary_date = time.strftime("%Y-%m-%d")
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


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
