import random
import re
import time
import traceback

from persona_pet.behavior import (
    DIALOGUE_ROLE_LISTENER,
    DIALOGUE_ROLE_SPEAKER,
    LLM_EMOTIONS,
    analyze_text_to_emotion,
    apply_emotion_override,
    clean_song_text,
    dominant_weight_emotion,
    is_singing_request,
    primary_dominant_analysis,
    reply_contains_song,
)
from persona_pet.chat_advice import ChatAdviceDialog
from persona_pet.memory import (
    collapse_repeated_memory_text,
    clean_spoken_reply_text,
    is_intimate_boundary_query,
    memory_now_label,
    normalize_prosody_hint,
    strip_stage_directions,
)
from persona_pet.speech import clean_speech_input_text, normalize_speech_piece
from persona_pet.error_reporter import report_exception
from persona_pet.runtime import get_default_runtime
from persona_pet.stimulus import Stimulus
from persona_pet.touch_reaction import ZONE_LABELS, decide_touch_reaction, touch_zone_family
from persona_pet.voicevox import estimate_sentence_seconds
from persona_pet.voicevox import normalize_tts_emotion

BARGE_IN_AFTER_PLAYBACK_SECONDS = 0.9
FREE_TALK_RELISTEN_DELAY = 0.15
LIFE_WRITING_IDLE_SECONDS = 75.0
LIFE_WRITING_INTERVAL_SECONDS = (150.0, 240.0)
MEMORY_MAX_TEXT_CHARS = 420
MEMORY_MIN_SIGNAL_CHARS = 4
PROACTIVE_ENABLED = True
PROACTIVE_IDLE_SECONDS = 240.0
PROACTIVE_INTERVAL_SECONDS = (300.0, 480.0)
SELF_NOTE_META_KEY = "self_notes"
VOICE_PLAYBACK_GUARD_SECONDS = 0.25


class PetWorkflowMixin:
    def run_runtime_task(self, name, fn, kind="thread", payload=None, resources=(), timeout=None):
        runtime = getattr(self, "runtime", None) or get_default_runtime()
        return runtime.run_background(
            name,
            fn,
            kind=kind,
            payload=payload,
            resources=resources,
            timeout=timeout,
        )

    def mark_user_active(self, source="user"):
        self.last_user_interaction_at = time.monotonic()
        self.next_proactive_at = self.last_user_interaction_at + random.uniform(*PROACTIVE_INTERVAL_SECONDS)

    def memory_associate_input(self, text, source="input"):
        text = (text or "").strip()
        if not text or not hasattr(self, "memory"):
            return
        try:
            if hasattr(self.memory, "associative_trace"):
                self.memory.associative_trace(text, source=source, role="input")
        except Exception as exc:
            self.runtime_logger("MEMORY_INPUT_ASSOC_ERROR", {"source": source, "error": str(exc)})

    def memory_associate_output(self, text, source="output"):
        text = collapse_repeated_memory_text(strip_stage_directions(text or ""))
        if not text or not hasattr(self, "memory"):
            return
        now = time.monotonic()
        last = getattr(self, "_last_memory_output_assoc", None)
        key = (str(source or "output"), text[:160])
        if last and last[0] == key and now - float(last[1]) < 2.0:
            return
        self._last_memory_output_assoc = (key, now)
        try:
            if hasattr(self.memory, "associative_trace"):
                self.memory.associative_trace(text, source=source, role="output")
        except Exception as exc:
            self.runtime_logger("MEMORY_OUTPUT_ASSOC_ERROR", {"source": source, "error": str(exc)})

    def submit_chat_input(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        if getattr(self, "home_icon_mode", False) or getattr(self, "godot_game_active", False):
            self.exit_home_icon_mode(reason="text_call", speak=False)
        self.submit_user_text(text)

    def submit_user_text(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.mark_user_active("submit")
        self.memory_associate_input(text, source="user_text")
        if self.handle_todo_input(text):
            return
        if self.handle_file_agent_input(text):
            return
        if self.handle_browser_agent_input(text):
            return
        if self.chat.is_busy():
            self.show_chat_status("还在思考上一句哦。", seconds=1.8)
            return

        self.chat_input.clear()
        self.dialogue_active = False
        user_analysis = primary_dominant_analysis(analyze_text_to_emotion(text))
        user_emotion = dominant_weight_emotion(user_analysis)
        self.user_profile_on_message(text, emotion=user_emotion)
        self.drive.on_user_message(text, emotion=user_emotion)
        self.life.observe_user_message(text, emotion=user_emotion)
        self.life.attachment_need = self.drive.values.get("attachment_need", 28.0)
        self.physiology_on_user_message(text)
        self.heart_on_user_message(text, emotion=user_emotion)
        if hasattr(self, 'emotion_engine'):
            mood = self.drive.compute_mood() if hasattr(self.drive, 'compute_mood') else "quiet"
            self.emotion_engine.update(
                target_emotion=user_emotion,
                intensity=0.5,
                user_text=text,
                user_emotion=user_emotion,
                mood=mood,
            )
        def _deferred_user_observation():
            try:
                if hasattr(self, 'time_awareness'):
                    self.time_awareness.record_interaction()
                if hasattr(self, 'personality_growth'):
                    self.personality_growth.observe_user_message(text, emotion=user_emotion)
                if hasattr(self, 'body_cycle'):
                    self.body_cycle.on_user_message(text, emotion=user_emotion)
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "deferred_user_observation", exc)
        self.run_runtime_task(
            "user_observation",
            _deferred_user_observation,
            kind="state",
            payload={"chars": len(text), "emotion": user_emotion},
            resources=("profile_write", "life_state"),
            timeout=30,
        )
        self.current_analysis = user_analysis
        self.mixer.set_target(user_analysis.weights)
        self.behavior.set_analysis(
            self.model,
            user_analysis,
            text=text,
            role=DIALOGUE_ROLE_LISTENER,
            force=False,
        )
        self.show_subtitle(f"你：{text}", voice_text="考え中……", duration=2.2)
        self.show_chat_status("思考中……", seconds=30.0)
        print("USER_CHAT =", text)
        if not self.chat.ask_async(text):
            self.show_chat_status("发送失败：上一句还没处理完。", seconds=2.2)

    def on_stimulus(self, stimulus):
        if stimulus is None:
            return False
        if not isinstance(stimulus, Stimulus):
            stimulus = Stimulus(**dict(stimulus))
        stimulus = stimulus.normalized()
        reaction = None
        if self._should_mark_stimulus_active(stimulus):
            self.mark_user_active(stimulus.source or stimulus.type)
        pre_emotion_snapshot = {}
        if hasattr(self, "emotion_engine"):
            pre_emotion_snapshot = self.emotion_engine.state.snapshot()
        if stimulus.type == "touch":
            reaction = self._decide_touch_stimulus_reaction(stimulus, pre_emotion_snapshot)
        try:
            if hasattr(self, "emotion_engine"):
                mood = self.drive.compute_mood() if hasattr(self.drive, "compute_mood") else "quiet"
                target_emotion = reaction["emotion_tag"] if reaction else stimulus.emotion_hint
                self.emotion_engine.update(
                    target_emotion=target_emotion,
                    intensity=max(0.15, float(stimulus.intensity or 0.0)),
                    user_text=stimulus.describe(),
                    user_emotion=stimulus.emotion_hint,
                    mood=mood,
                )
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "stimulus_emotion_update", exc, stimulus_type=stimulus.type)
        try:
            self._apply_stimulus_to_drive_and_life(stimulus, reaction=reaction)
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "apply_stimulus_to_drive_and_life", exc, stimulus_type=stimulus.type)
        self._observe_stimulus_personality(stimulus, reaction=reaction)
        self._observe_stimulus_metacognition(stimulus, reaction=reaction)
        try:
            self._remember_stimulus(stimulus, reaction=reaction)
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "remember_stimulus", exc, stimulus_type=stimulus.type)
        if stimulus.type == "touch" and hasattr(self, "behavior") and hasattr(self, "model") and self.model:
            try:
                zone = str(stimulus.meta.get("zone") or stimulus.zone or "").lower()
                _zone_motion_map = {
                    "private": "m04_wronged_sadness",
                    "thigh": "m04_wronged_sadness",
                    "chest": "m04_wronged_sadness",
                    "head": "m08_joy",
                    "hair": "m08_joy",
                    "cheek": "m08_joy",
                }
                motion_key = _zone_motion_map.get(zone, "m07_surprise")
                # Emotion override: only anger and sadness/fear
                if hasattr(self, "emotion_engine"):
                    emo_snap = self.emotion_engine.state.snapshot()
                    dominant = str(emo_snap.get("dominant") or "neutral").lower()
                    intensity = float(emo_snap.get("intensity") or 0.0)
                    if dominant == "anger" and intensity > 0.25:
                        motion_key = "m09_anger"
                    elif dominant in ("sadness", "fear") and intensity > 0.25:
                        motion_key = "m04_wronged_sadness"
                blush_zones = {"private", "thigh", "chest", "belly", "neck"}
                if zone in blush_zones and hasattr(self, "_touch_visual"):
                    try:
                        self._touch_visual.trigger_blush(zone)
                    except Exception:
                        pass
                from persona_pet.behavior import EmotionAnalysis
                self.behavior.trigger_emotion_motion(
                    self.model,
                    EmotionAnalysis.neutral(),
                    motion_key_override=motion_key,
                    force=True,
                )
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "touch_motion_trigger", exc)
        if stimulus.type != "touch":
            self.current_analysis = self._analysis_from_stimulus(stimulus, reaction=reaction)
            self.mixer.set_target(self.current_analysis.weights)
            if hasattr(self, "behavior"):
                self.behavior.analysis = self.current_analysis
        stimulus_log = {
            "type": stimulus.type,
            "source": stimulus.source,
            "zone": stimulus.zone,
            "should_talk": bool(stimulus.should_talk),
            "reaction": (reaction or {}).get("name", ""),
            "intensity": round(float(stimulus.intensity or 0.0), 3),
        }
        self.runtime_logger("STIMULUS", stimulus_log)
        print("STIMULUS =", stimulus_log)
        if stimulus.should_talk:
            try:
                self._trigger_stimulus_dialogue(stimulus, reaction=reaction)
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "trigger_stimulus_dialogue", exc, stimulus_type=stimulus.type)
        return True

    def _should_mark_stimulus_active(self, stimulus):
        return stimulus.type in {"touch", "stare", "drag_start", "drag_drop"}

    def _is_interaction_dialogue_allowed(self):
        now = time.monotonic()
        return not (
            self.chat.is_busy()
            or self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
            or self.speech_input.is_busy()
            or self.life_writer.is_busy()
            or self.chat_advice.is_busy()
            or now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0)
        )

    def _is_stimulus_dialogue_allowed(self, stimulus, reaction=None):
        now = time.monotonic()
        if self.chat.is_busy():
            return False
        if self.speech_input.is_busy() or self.life_writer.is_busy() or self.chat_advice.is_busy():
            return False
        if now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0):
            return False
        stimulus_type = str(getattr(stimulus, "type", "") or "").strip().lower()
        if stimulus_type == "touch":
            return True
        return not (
            self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
        )

    def _decide_touch_stimulus_reaction(self, stimulus, pre_emotion_snapshot):
        stage, _attitude = self.life.relationship_stage()
        return decide_touch_reaction(
            pre_emotion_snapshot or {},
            self.drive.snapshot() if hasattr(self.drive, "snapshot") else {"values": dict(getattr(self.drive, "values", {}) or {})},
            {"stage": stage, "relationship_score": float(getattr(self.life, "relationship_score", 28.0) or 28.0)},
            self.personality_growth.get_trait_snapshot() if hasattr(self, "personality_growth") else {},
            stimulus,
            self._build_touch_memory_context(),
        )

    def _build_touch_memory_context(self):
        now = time.monotonic()
        history = list(getattr(self, "_touch_history", []) or [])
        recent = [item for item in history if now - float(item) <= 2.0]
        setattr(self, "_touch_history", recent[-12:])
        previous_touch_at = float(getattr(self, "_previous_touch_at", 0.0) or 0.0)

        class Context:
            recent_touch_count = len(recent)
            seconds_since_last_touch = now - previous_touch_at if previous_touch_at > 0 else 9999.0

        return Context()

    def _apply_stimulus_to_drive_and_life(self, stimulus, reaction=None):
        reaction_name = str((reaction or {}).get("name") or "calm").lower()
        zone = str(stimulus.meta.get("zone") or stimulus.zone or "").lower()
        zone_family = touch_zone_family(zone)
        relation_score = float(getattr(self.life, "relationship_score", 28.0) or 28.0)
        if stimulus.type == "touch":
            affinity_delta = 0.45
            security_delta = 0.12
            companionship_delta = 0.10
            attachment_delta = -0.15
            relation_delta = 0.08
            if zone_family == "hair":
                affinity_delta += 0.25
                relation_delta += 0.10
            elif zone_family in {"body", "leg"}:
                security_delta -= 0.25
                relation_delta -= 0.04
            elif zone_family == "private":
                security_delta -= 0.60
                relation_delta -= 0.18
                affinity_delta -= 0.20
            if reaction_name == "happy":
                affinity_delta += 0.35
                security_delta += 0.18
                relation_delta += 0.18
            elif reaction_name == "shy":
                affinity_delta += 0.18
                companionship_delta += 0.15
                relation_delta += 0.10
            elif reaction_name == "clingy":
                companionship_delta += 0.30
                attachment_delta -= 0.30
                relation_delta += 0.08
            elif reaction_name == "nervous":
                security_delta -= 0.30
                companionship_delta -= 0.10
                relation_delta -= 0.05
            elif reaction_name == "annoyed":
                affinity_delta -= 0.35
                security_delta -= 0.50
                companionship_delta -= 0.20
                attachment_delta += 0.15
                relation_delta -= 0.20
            if relation_score < 35.0 and zone_family in {"body", "leg", "private"}:
                security_delta -= 0.35
                relation_delta -= 0.10
            self.drive.adjust(
                affinity=affinity_delta,
                security=security_delta,
                companionship=companionship_delta,
                attachment_need=attachment_delta,
            )
            self.life.relationship_score = max(0.0, self.life.relationship_score + relation_delta)
            self.drive.save()
            self.life.attachment_need = self.drive.values.get("attachment_need", 28.0)
            self.life.save()
            return
        if stimulus.type == "stare":
            self.drive.adjust(curiosity=0.45, novelty=0.35, companionship=0.12)
            self.drive.save()
            return
        if stimulus.type == "drag_start":
            self.drive.adjust(security=-0.50, energy=-0.10)
            self.drive.save()
            return
        if stimulus.type == "drag_drop":
            velocity = float(stimulus.meta.get("velocity", 0.0) or 0.0)
            if velocity > 850:
                self.drive.adjust(security=-0.40, energy=-0.15)
            else:
                self.drive.adjust(security=0.12)
            self.drive.save()
            return
        if stimulus.type == "env_change":
            category = str(stimulus.meta.get("new_category") or "").lower()
            if category == "work":
                self.drive.adjust(companionship=0.25, purpose=0.20)
            elif category == "game":
                self.drive.adjust(curiosity=0.30, novelty=0.25)
            elif category in {"music", "video"}:
                self.drive.adjust(companionship=0.10, security=0.05)
            self.drive.save()
            return
        if stimulus.type == "work_overtime":
            self.drive.adjust(companionship=1.10, attachment_need=0.60, purpose=0.35)
            self.drive.save()
            return
        if stimulus.type == "late_night":
            self.drive.adjust(companionship=0.85, security=-0.30, attachment_need=0.55)
            self.drive.save()

    def _observe_stimulus_personality(self, stimulus, reaction=None):
        if not hasattr(self, "personality_growth"):
            return
        try:
            if hasattr(self.personality_growth, "observe_stimulus"):
                if isinstance(stimulus.meta, dict):
                    stimulus.meta.setdefault("relationship_score", float(getattr(self.life, "relationship_score", 28.0) or 28.0))
                self.personality_growth.observe_stimulus(stimulus, reaction=reaction or {})
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "stimulus_personality", exc, stimulus_type=stimulus.type)

    def _observe_stimulus_metacognition(self, stimulus, reaction=None):
        if not hasattr(self, "metacognition"):
            return
        def worker():
            try:
                if hasattr(self.metacognition, "observe_stimulus"):
                    self.metacognition.observe_stimulus(stimulus, reaction=reaction or {})
                else:
                    self.metacognition.observe_interaction(
                        user_text=stimulus.describe(),
                        assistant_text=str((reaction or {}).get("prompt_direction") or ""),
                        emotion=str((reaction or {}).get("emotion_tag") or stimulus.emotion_hint),
                        user_reaction=str((reaction or {}).get("name") or ""),
                    )
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "stimulus_metacognition", exc, stimulus_type=stimulus.type)
        self.run_runtime_task(
            "stimulus_metacognition",
            worker,
            kind="memory",
            payload={"type": stimulus.type},
            resources=("memory_write", "profile_write"),
            timeout=30,
        )

    def _remember_stimulus(self, stimulus, reaction=None):
        if not stimulus.memory_worthy or not hasattr(self, "memory"):
            return
        reaction_name = str((reaction or {}).get("name") or "").strip()
        event = {
            "time": memory_now_label(),
            "type": stimulus.type,
            "zone": stimulus.zone,
            "source": stimulus.source,
            "reaction": reaction_name,
            "summary": stimulus.describe()[:220],
        }
        try:
            history = self.memory.load_meta_json("stimulus_events", [])
            if not isinstance(history, list):
                history = []
            history.append(event)
            self.memory.save_meta_json("stimulus_events", history[-40:])
            if self._should_associate_stimulus_memory(stimulus, reaction=reaction):
                self.memory_associate_input(event["summary"], source=f"stimulus_{stimulus.type}")
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "remember_stimulus", exc, stimulus_type=stimulus.type)

    def _should_associate_stimulus_memory(self, stimulus, reaction=None):
        if stimulus is None:
            return False
        if str(getattr(stimulus, "type", "") or "").lower() != "touch":
            return True
        reaction_name = str((reaction or {}).get("name") or "").strip().lower()
        zone = str(getattr(stimulus, "zone", "") or stimulus.meta.get("zone", "")).strip().lower()
        zone_family = touch_zone_family(zone)
        count = int(stimulus.meta.get("count", 1) or 1) if isinstance(stimulus.meta, dict) else 1
        interval = float(stimulus.meta.get("interval", 99.0) or 99.0) if isinstance(stimulus.meta, dict) else 99.0
        if zone_family in {"private", "body", "leg"}:
            return True
        if reaction_name in {"nervous", "annoyed"}:
            return True
        return count >= 4 or interval <= 0.35

    def _build_touch_prompt(self, stimulus, reaction):
        stage, attitude = self.life.relationship_stage()
        emotion_snap = self.emotion_engine.state.snapshot() if hasattr(self, "emotion_engine") else {}
        zone = stimulus.zone or stimulus.meta.get("zone", "")
        zone_name = ZONE_LABELS.get(zone, zone or "触碰")
        relation_score = float(getattr(self.life, "relationship_score", 28.0) or 28.0)
        count = int(stimulus.meta.get("count", 1) or 1)
        positive = reaction["name"] in ("happy", "shy", "clingy")

        # Build base prompt
        lines = [
            f"用户刚才碰了你的{zone_name}。",
            f"当前关系阶段：{stage}，关系分 {relation_score:.1f}。",
            f"当前情绪主导：{emotion_snap.get('dominant', 'neutral')}。",
            f"这次触碰后你的即时反应是：{reaction['name']}。",
            f"态度参考：{attitude}",
        ]

        # Repeated positive touch: encourage proactive / initiating speech
        if positive and count >= 3 and relation_score >= 88:
            lines.append(
                f"这已经是连续第{count}次触碰了，你很享受。"
                "你可以说一句主动的话，比如请求继续、撒娇、或者轻哼。"
                "可以比平时更短，甚至只有几个字。"
            )
        elif positive and count >= 2:
            lines.append("连续被碰，你有点上头，可以自然地发出声音或说半句话。")
        else:
            lines.append(reaction["prompt_direction"])

        lines.append("请只回复一句中文短句，不超过20字，口语化，不要旁白，不要括号动作。")
        return "\n".join(lines)

    def _build_stimulus_prompt(self, stimulus, reaction=None):
        stage, _attitude = self.life.relationship_stage()
        emotion_snap = self.emotion_engine.state.snapshot() if hasattr(self, "emotion_engine") else {}
        if stimulus.type == "stare":
            return (
                f"用户刚才盯着你看了大约{float(stimulus.duration or 0.0):.1f}秒。\n"
                f"当前关系阶段：{stage}。\n"
                f"当前情绪主导：{emotion_snap.get('dominant', 'neutral')}。\n"
                "请自然说一句短短的话，像是注意到对方在看你。不要超过20字。"
            )
        if stimulus.type == "work_overtime":
            return (
                "用户已经连续工作很久了。\n"
                f"当前关系阶段：{stage}。\n"
                "请用关心但不过度打扰的语气，说一句提醒或安慰。不要超过20字。"
            )
        if stimulus.type == "late_night":
            return (
                "现在已经很晚了，用户还在用电脑。\n"
                f"当前关系阶段：{stage}。\n"
                "请说一句简短关心的话，不要说教，不超过20字。"
            )
        return (
            f"刚刚发生了一次互动事件：{stimulus.describe()}。\n"
            f"当前关系阶段：{stage}。\n"
            f"当前情绪主导：{emotion_snap.get('dominant', 'neutral')}。\n"
            "请说一句自然的短回应，不超过20字。"
        )

    def _queue_stimulus_dialogue_retry(self, prompt, stimulus, memory_user_text="", emotion_override=""):
        pending = {
            "prompt": prompt,
            "stimulus_type": str(getattr(stimulus, "type", "") or "").strip().lower(),
            "zone": str(getattr(stimulus, "zone", "") or stimulus.meta.get("zone", "")).strip().lower(),
            "memory_user_text": (memory_user_text or "")[:160],
            "emotion_override": str(emotion_override or "").strip().lower(),
            "retry_at": time.monotonic() + 0.22,
            "attempts": 0,
        }
        setattr(self, "_pending_stimulus_dialogue", pending)
        print(
            "STIMULUS_DIALOGUE_DEFERRED =",
            {
                "type": pending["stimulus_type"],
                "zone": pending["zone"],
            },
        )
        return False

    def _flush_pending_stimulus_dialogue(self):
        pending = getattr(self, "_pending_stimulus_dialogue", None)
        if not pending:
            return False
        now = time.monotonic()
        if now < float(pending.get("retry_at", 0.0) or 0.0):
            return False
        if self.speech_input.is_busy() or self.life_writer.is_busy() or self.chat_advice.is_busy():
            pending["retry_at"] = now + 0.28
            return False
        if now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0):
            pending["retry_at"] = now + 0.28
            return False
        if self.chat.is_busy():
            pending["retry_at"] = now + 0.22
            return False
        started = self.chat.ask_async(
            pending.get("prompt", ""),
            initiated_by="stimulus",
            memory_user_text=pending.get("memory_user_text", ""),
            emotion_override=pending.get("emotion_override", ""),
        )
        if started:
            print(
                "STIMULUS_DIALOGUE_RETRY_OK =",
                {
                    "type": pending.get("stimulus_type", ""),
                    "zone": pending.get("zone", ""),
                },
            )
            setattr(self, "_pending_stimulus_dialogue", None)
            return True
        pending["attempts"] = int(pending.get("attempts", 0) or 0) + 1
        if pending["attempts"] >= 8:
            print(
                "STIMULUS_DIALOGUE_DROP =",
                {
                    "type": pending.get("stimulus_type", ""),
                    "zone": pending.get("zone", ""),
                    "attempts": pending["attempts"],
                },
            )
            setattr(self, "_pending_stimulus_dialogue", None)
            return False
        pending["retry_at"] = now + 0.28
        return False

    def _trigger_stimulus_dialogue(self, stimulus, reaction=None):
        if not self._is_interaction_dialogue_allowed():
            print(
                "STIMULUS_DIALOGUE_BLOCKED =",
                {
                    "type": str(getattr(stimulus, "type", "") or ""),
                    "zone": str(getattr(stimulus, "zone", "") or ""),
                },
            )
            return False
        prompt = self._build_touch_prompt(stimulus, reaction) if stimulus.type == "touch" and reaction else self._build_stimulus_prompt(stimulus, reaction=reaction)
        memory_user_text = stimulus.describe()
        if reaction and reaction.get("name"):
            memory_user_text = f"{memory_user_text}，反应={reaction['name']}"
        status = {
            "touch": "她在感受你的触碰……",
            "stare": "她注意到你的视线了……",
            "work_overtime": "她有点担心你……",
            "late_night": "她在悄悄提醒你……",
        }.get(stimulus.type, "她在思考这次互动……")
        self.show_chat_status(status, seconds=2.0)
        emotion_override = ""
        if reaction and reaction.get("emotion_tag") in LLM_EMOTIONS:
            emotion_override = reaction["emotion_tag"]
        elif stimulus.emotion_hint in LLM_EMOTIONS:
            emotion_override = stimulus.emotion_hint
        started = self.chat.ask_async(
            prompt,
            initiated_by="stimulus",
            memory_user_text=memory_user_text[:160],
            emotion_override=emotion_override,
        )
        if started:
            setattr(self, "_pending_stimulus_dialogue", None)
            return True
        return self._queue_stimulus_dialogue_retry(
            prompt,
            stimulus,
            memory_user_text=memory_user_text,
            emotion_override=emotion_override,
        )

    def _analysis_from_stimulus(self, stimulus, reaction=None):
        analysis = primary_dominant_analysis(analyze_text_to_emotion(stimulus.describe()))
        emotion_override = str((reaction or {}).get("emotion_tag") or stimulus.emotion_hint or "neutral")
        return apply_emotion_override(analysis, emotion_override if emotion_override in LLM_EMOTIONS else "neutral")

    def interrupt_current_speech(self, reason="user"):
        self.dialogue_active = False
        self.voice.stop_playback()
        self.behavior.stop_speaking()
        self.subtitle_until = min(self.subtitle_until, time.monotonic() + 0.4)
        print("VOICE_INTERRUPTED =", {"reason": reason})

    def start_speech_input(self, auto=False, interrupt=False):
        if not auto and (getattr(self, "home_icon_mode", False) or getattr(self, "godot_game_active", False)):
            self.exit_home_icon_mode(reason="voice_call", speak=True)
        self.mark_user_active("speech_start")
        if self.chat.is_busy():
            if not auto:
                self.show_chat_status("大模型还在回复上一句。", seconds=1.8)
            return
        if interrupt and (self.voice.is_busy_or_playing() or self.behavior.is_speaking()):
            self.interrupt_current_speech(reason="speech_input")
            time.sleep(0.12)
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking():
            if not auto:
                self.show_chat_status("角色正在说话，等她说完再听。", seconds=1.8)
            return
        if self.speech_input.is_busy():
            if not auto:
                self.show_chat_status("正在听你说话。", seconds=1.4)
            return
        self.barge_in.stop()
        if not auto:
            self.chat_input.setText("正在听你说话……")
            self.show_subtitle("正在听你说话……", voice_text="", duration=4.0)
            self.show_chat_status("我会一直听到你说完。", seconds=4.0)
        print(
            "SPEECH_INPUT_START =",
            {
                "max_seconds": self.speech_input.record_seconds,
                "adaptive": True,
                "silence_seconds": self.speech_input.silence_seconds,
            },
        )
        if not self.speech_input.listen_async() and not auto:
            self.show_chat_status("语音输入启动失败。", seconds=2.0)

    def start_free_talk(self):
        if getattr(self, "home_icon_mode", False) or getattr(self, "godot_game_active", False):
            self.exit_home_icon_mode(reason="voice_call", speak=False)
        self.free_talk_enabled = True
        self.free_talk_next_at = 0.0
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking():
            self.interrupt_current_speech(reason="free_talk_start")
        self.show_chat_status("自由对话已开启。", seconds=2.0)
        print("FREE_TALK =", {"enabled": True})
        self.start_speech_input(auto=True, interrupt=True)

    def stop_free_talk(self):
        self.free_talk_enabled = False
        self.free_talk_next_at = 0.0
        self.barge_in.stop()
        self.speech_input.stop()
        self.speech_input.consume_events()
        self.show_chat_status("自由对话已关闭。", seconds=2.0)
        print("FREE_TALK =", {"enabled": False})

    def update_barge_in_monitor(self):
        if not self.free_talk_enabled or self.speech_input.is_busy() or self.chat.is_busy():
            self.barge_in.set_active(False)
            return
        now = time.monotonic()
        playback_started_at = self.voice.playback_started_at()
        can_interrupt = (
            self.voice.is_busy_or_playing(now)
            and playback_started_at > 0.0
            and now >= playback_started_at + BARGE_IN_AFTER_PLAYBACK_SECONDS
        )
        self.barge_in.set_active(can_interrupt)

    def process_barge_in_events(self):
        for event in self.barge_in.consume_events():
            if event.get("error"):
                print("BARGE_IN_ERROR =", event)
                self.barge_in.set_active(False)
                continue
            print("BARGE_IN_TRIGGER =", event)
            self.interrupt_current_speech(reason="barge_in")
            self.free_talk_next_at = time.monotonic() + max(0.0, self.speech_input.record_seconds) + FREE_TALK_RELISTEN_DELAY
            self.start_speech_input(auto=True, interrupt=True)

    def maybe_continue_free_talk(self):
        if not self.free_talk_enabled:
            return
        now = time.monotonic()
        if now < self.free_talk_next_at:
            return
        if (
            PROACTIVE_ENABLED
            and now >= self.next_proactive_at
            and now - self.last_user_interaction_at >= PROACTIVE_IDLE_SECONDS
        ):
            return
        if self.speech_input.is_busy() or self.chat.is_busy() or self.life_writer.is_busy():
            return
        if self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            return
        self.free_talk_next_at = now + max(0.0, self.speech_input.record_seconds) + FREE_TALK_RELISTEN_DELAY
        self.start_speech_input(auto=True)

    def load_self_notes(self):
        notes = self.memory.load_meta_json(SELF_NOTE_META_KEY, [])
        if not isinstance(notes, list):
            return []
        return [note for note in notes[-8:] if isinstance(note, dict) and note.get("text")]

    def save_self_notes(self):
        self.memory.save_meta_json(SELF_NOTE_META_KEY, self.self_notes[-8:])

    def add_self_note(self, text, kind="self_expression", priority=1.0):
        text = collapse_repeated_memory_text(text)
        if not text:
            return
        self.self_notes.append(
            {
                "time": memory_now_label(),
                "kind": kind,
                "priority": float(priority),
                "text": text[:220],
            }
        )
        self.self_notes = self.self_notes[-8:]
        self.save_self_notes()

    def remember_turn_async(self, user_text, assistant_text, emotion="neutral", prosody=None, segments=None, source="CHAT"):
        def worker():
            try:
                self.memory.add_turn(
                    user_text,
                    assistant_text,
                    emotion=emotion,
                    prosody=prosody or {},
                    segments=segments or [],
                )
            except Exception as exc:
                print(f"{source}_MEMORY_ADD_ERROR =", {"user": str(user_text or '')[:80], "error": str(exc)})
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "memory_add_turn", exc, source=source)

        self.run_runtime_task(
            "memory_add_turn",
            worker,
            kind="memory",
            payload={"source": source, "chars": len(str(user_text or "")) + len(str(assistant_text or ""))},
            resources=("memory_write",),
            timeout=60,
        )

    def process_speech_events(self):
        for event in self.speech_input.consume_events():
            self.mark_user_active("speech_event")
            if event.error:
                self.chat_input.clear()
                self.show_subtitle("语音识别失败，请再试一次。", voice_text="", duration=3.0)
                self.show_chat_status("STT ERROR", seconds=2.5)
                print("SPEECH_INPUT_ERROR =", {"error": event.error})
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 1.5
                continue
            raw_text = event.text.strip()
            text = clean_speech_input_text(raw_text)
            if text:
                self.memory_associate_input(text, source="speech_clean")
            if not self.free_talk_enabled:
                self.chat_input.clear()
            print(
                "SPEECH_INPUT_TEXT =",
                {"text": text, "raw_text": raw_text, "wav": event.wav_path, "audio_stats": event.audio_stats},
            )
            if not text:
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 0.8
                else:
                    self.show_subtitle("我没有听清楚，可以再说一遍吗？", voice_text="", duration=3.0)
                    self.show_chat_status("没有识别到文字。", seconds=2.2)
                return
            try:
                self.submit_user_text(text)
            except Exception as exc:
                self.show_chat_status("语音文本提交失败", seconds=3.0)
                self.runtime_logger("SPEECH_SUBMIT_ERROR", traceback.format_exc())
                print("SPEECH_SUBMIT_ERROR =", {"text": text, "error": str(exc)})
                if self.free_talk_enabled:
                    self.free_talk_next_at = time.monotonic() + 1.5

    def process_chat_events(self):
        for event in self.chat.consume_events():
            if event.error:
                self.drive.on_llm_result(success=False, initiated_by=event.initiated_by, error=event.error)
                message = "大模型连接失败，请检查 persona_llm_config.json 或本地 Ollama。"
                self.show_subtitle(message, voice_text="", duration=4.0)
                self.show_chat_status("LLM ERROR", seconds=3.0)
                print("LLM_ERROR =", {"user": event.user_text, "error": event.error})
                continue

            if event.degraded_error:
                self.drive.on_llm_result(success=False, initiated_by=event.initiated_by, error=event.degraded_error)
                self.show_chat_status("LLM DEGRADED", seconds=2.5)
                print("LLM_DEGRADED =", {"user": event.user_text, "error": event.degraded_error})
            else:
                self.drive.on_llm_result(success=True, initiated_by=event.initiated_by)

            reply = event.reply
            self.last_assistant_activity_at = time.monotonic()
            def _deferred_memory_ops():
                try:
                    self.memory_associate_output(reply, source=f"assistant_{event.initiated_by}")
                    if hasattr(self.memory, "observe_experience"):
                        self.memory.observe_experience(
                            event.memory_user_text or event.user_text,
                            reply,
                            initiated_by=event.initiated_by,
                        )
                except Exception as exc:
                    report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "assistant_memory_ops", exc, initiated_by=event.initiated_by)
            self.run_runtime_task(
                "assistant_memory_ops",
                _deferred_memory_ops,
                kind="memory",
                payload={"initiated_by": event.initiated_by, "reply_chars": len(reply or "")},
                resources=("memory_write",),
                timeout=60,
            )
            self.chat_status_text = ""
            self.test_text = reply
            self.current_test_key = None
            analysis = primary_dominant_analysis(analyze_text_to_emotion(reply))
            analysis = apply_emotion_override(analysis, event.emotion)
            self.current_analysis = analysis
            self.mixer.set_target(analysis.weights)
            singing = (
                self.singing_enabled
                and is_singing_request(event.user_text)
                and reply_contains_song(reply, event.voice_text)
            )
            self.behavior.analysis = analysis
            self.behavior.mouth_enabled = False
            self.start_voice_for_text(
                reply,
                analysis,
                voice_text_override=event.voice_text,
                emotion_override=event.emotion,
                prosody_hint=event.prosody,
                voice_segments=event.segments,
                singing=singing,
            )
            self.drive.on_assistant_reply(reply, initiated_by=event.initiated_by, emotion=event.emotion)
            self.physiology_on_assistant_reply()
            self.heart_on_assistant_reply(reply, emotion=event.emotion, initiated_by=event.initiated_by)
            if hasattr(self, 'emotion_engine'):
                mood = self.drive.compute_mood() if hasattr(self.drive, 'compute_mood') else "quiet"
                self.emotion_engine.update(
                    target_emotion=event.emotion,
                    intensity=0.6,
                    user_text=event.user_text,
                    user_emotion=event.emotion,
                    mood=mood,
                )
            if hasattr(self, 'metacognition'):
                def _deferred_metacognition():
                    try:
                        self.metacognition.observe_interaction(
                            user_text=event.user_text,
                            assistant_text=reply,
                            emotion=event.emotion,
                        )
                    except Exception as exc:
                        report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "pet_workflow", "metacognition_observe", exc)
                self.run_runtime_task(
                    "metacognition_observe",
                    _deferred_metacognition,
                    kind="memory",
                    payload={"emotion": event.emotion, "reply_chars": len(reply or "")},
                    resources=("memory_write", "profile_write"),
                    timeout=60,
                )
            memory_user_text = event.memory_user_text or event.user_text
            if not event.degraded_error:
                self.remember_turn_async(
                    memory_user_text,
                    reply,
                    emotion=event.emotion,
                    prosody=event.prosody,
                    segments=event.segments,
                    source="CHAT",
                )
            print(
                "LLM_REPLY =",
                {
                    "user": event.user_text,
                    "reply": reply,
                    "voice_text": event.voice_text,
                    "emotion": event.emotion,
                    "emotion_source": getattr(event, "emotion_source", ""),
                    "initiated_by": event.initiated_by,
                    "prosody": event.prosody,
                    "segments": event.segments,
                    "singing": singing,
                },
            )
        self._flush_pending_stimulus_dialogue()

    def process_chat_advice_events(self):
        for event in self.chat_advice.consume_events():
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(event)
            self.chat_advice_dialog.show()
            self.chat_advice_dialog.raise_()
            if event.error:
                self.show_chat_status("聊天截图分析失败", seconds=3.0)
                print("CHAT_ADVICE_ERROR =", {"screenshot": event.screenshot_path, "error": event.error})
            else:
                self.drive.record_intent("chat_advice", "根据截图聊天记录给用户出主意")
                self.drive.save()
                self.show_chat_status("聊天建议已生成", seconds=3.0)
                print(
                    "CHAT_ADVICE_DONE =",
                    {
                        "screenshot": event.screenshot_path,
                        "ocr_chars": len(event.ocr_text or ""),
                        "advice_chars": len(event.advice or ""),
                    },
                )

    def process_life_writing_events(self):
        for event in self.life_writer.consume_events():
            if event.error:
                self.memory_associate_output("写作失败，稍后再试。", source=f"life_writing_{event.kind}")
                self.show_chat_status("写作失败，稍后再试。", seconds=3.0)
                print("LIFE_WRITING_ERROR =", {"kind": event.kind, "error": event.error})
                self.life.next_writing_at = time.monotonic() + 120.0
                continue
            label = "日记" if event.kind == "diary" else "小说"
            self.memory_associate_output(f"苏念写完了一段{label}：{event.title}", source=f"life_writing_{event.kind}")
            self.show_chat_status(f"苏念写完了一段{label}。", seconds=4.0)
            self.drive.record_intent(f"write_{event.kind}", f"作为小说作家完成{label}写作")
            self.drive.save()
            self.add_self_note(
                "刚完成一段写作后，她想把这件事沉淀成一句更深的感受：创作让她觉得自己不是只在等待用户，也在慢慢长出自己的内心。",
                kind=f"write_{event.kind}",
                priority=1.2,
            )
            self.life.next_writing_at = time.monotonic() + random.uniform(*LIFE_WRITING_INTERVAL_SECONDS)
            print(
                "LIFE_WRITING_DONE =",
                {"kind": event.kind, "title": event.title, "path": event.path, "chars": len(event.content or "")},
            )
            if event.kind == "novel":
                self.economy_on_novel_complete(word_count=len(event.content or ""))

    def process_reading_events(self):
        for event in self.reader.consume_events():
            if event.error:
                print("READING_ERROR =", {"topic": event.topic, "error": event.error})
                continue
            self.show_chat_status(f"苏念读完了「{event.topic}」相关内容。", seconds=4.0)
            print("READING_DONE =", {"topic": event.topic, "chars": len(event.content or "")})

    def start_voice_for_text(
        self,
        text,
        analysis,
        test_key=None,
        voice_text_override="",
        emotion_override="",
        prosody_hint=None,
        voice_segments=None,
        singing=False,
    ):
        emotion = emotion_override if emotion_override in LLM_EMOTIONS else dominant_weight_emotion(analysis)
        tts_emotion = normalize_tts_emotion(emotion)
        voice_text = clean_spoken_reply_text(voice_text_override or text or "") or "嗯嗯，我在听哦。"
        text = clean_spoken_reply_text(text)
        voice_was_busy = self.voice.is_busy_or_playing() or self.behavior.is_speaking()
        self.memory_associate_output(text or voice_text, source="voice_output")
        voice_segments = None
        if singing:
            voice_text = clean_song_text(voice_text) or clean_song_text(text) or voice_text
            voice_segments = None
        self.last_voice_analysis = analysis
        event_id = self.voice.speak_async(
            voice_text,
            emotion=tts_emotion,
            singing=singing,
            source_text=text,
            prosody_hint=prosody_hint,
            segments=voice_segments,
        )
        display_texts = getattr(self, "_voice_display_texts", None)
        if not isinstance(display_texts, dict):
            display_texts = {}
            self._voice_display_texts = display_texts
        display_texts[int(event_id or 0)] = text or voice_text
        if voice_was_busy:
            self.show_chat_status("她会说完这句再接下一句。", seconds=1.8)
        else:
            self.show_subtitle(text or voice_text, voice_text="", duration=max(2.8, estimate_sentence_seconds(voice_text, role=DIALOGUE_ROLE_SPEAKER)))
        print(
            "VOLCENGINE_TTS_SING =" if singing else "VOLCENGINE_TTS_SPEAK =",
            {
                  "event_id": event_id,
                  "emotion": tts_emotion,
                  "source_emotion": emotion,
                "singing": singing,
                "voice_type": self.voice.tts_voice_type,
                "cluster": self.voice.tts_cluster,
                "rate": self.voice.tts_rate,
                "prosody": normalize_prosody_hint(prosody_hint),
                "segments": voice_segments or [],
                "text": voice_text,
            },
        )

    def process_voice_events(self):
        for event in self.voice.consume_events():
            if event.error:
                if "???? TTS" in event.error:
                    self.show_chat_status("?????? TTS API Key", seconds=6.0)
                else:
                    self.show_chat_status(f"TTS ???{event.error[:28]}", seconds=6.0)
                print("VOLCENGINE_TTS_ERROR =", {"event_id": event.event_id, "error": event.error})
                continue

            is_streaming = bool(getattr(event, "streaming_chunk", False))
            is_stream_first_chunk = is_streaming and getattr(event, "part_index", 0) == 0

            def sync_on_playback_start(duration=event.duration, analysis=self.last_voice_analysis, evt=event):
                self.last_assistant_activity_at = time.monotonic()
                if not getattr(evt, "streaming_chunk", False) or getattr(evt, "part_index", 0) == 0:
                    display_texts = getattr(self, "_voice_display_texts", {})
                    display_text = ""
                    if isinstance(display_texts, dict):
                        display_text = display_texts.pop(int(getattr(evt, "event_id", 0) or 0), "")
                    self.show_subtitle(
                        display_text or evt.text or "",
                        voice_text="",
                        duration=max(2.8, estimate_sentence_seconds(evt.text or "", role=DIALOGUE_ROLE_SPEAKER)),
                    )
                if getattr(evt, "streaming_chunk", False):
                    self.voice.extend_playing(duration)
                    self.behavior.extend_speech_to_audio(duration, analysis=analysis)
                else:
                    self.voice.mark_playing(duration, guard_seconds=VOICE_PLAYBACK_GUARD_SECONDS)
                    self.behavior.sync_speech_to_audio(duration, analysis=analysis)
                if (not getattr(evt, "streaming_chunk", False) or getattr(evt, "part_index", 0) == 0) and hasattr(self, "model") and self.model:
                    print("VOICE_MOTION_CB =", {"dominant": getattr(analysis, "dominant", "?"), "text": (evt.text or "")[:40]})
                    self.behavior.trigger_emotion_motion(
                        self.model,
                        analysis,
                        text=evt.text,
                        role=DIALOGUE_ROLE_SPEAKER,
                        prefer_talk=False,
                        force=False,
                    )

            if is_streaming and not is_stream_first_chunk:
                self.last_assistant_activity_at = time.monotonic()
                self.voice.extend_playing(event.duration)
                self.behavior.extend_speech_to_audio(event.duration, analysis=self.last_voice_analysis)

            if is_streaming:
                self.voice.play_stream_chunk(event.audio_chunk, event.sample_rate, on_start=sync_on_playback_start)
            else:
                self.voice.play_wav_async(event.wav_path, on_start=sync_on_playback_start)
            if self.free_talk_enabled:
                self.free_talk_next_at = (
                    time.monotonic()
                    + max(0.0, event.duration)
                    + VOICE_PLAYBACK_GUARD_SECONDS
                    + FREE_TALK_RELISTEN_DELAY
                )
            print(
                "VOLCENGINE_TTS_PLAY =",
                {
                    "event_id": event.event_id,
                    "emotion": event.emotion,
                    "voice_type": event.speaker,
                    "duration": round(event.duration, 3),
                    "guard": VOICE_PLAYBACK_GUARD_SECONDS,
                    "part": (
                        f"{getattr(event, 'part_index', 0) + 1}/{getattr(event, 'part_count', 1)}"
                        if getattr(event, "part_count", 1) > 0
                        else f"chunk-{getattr(event, 'part_index', 0) + 1}"
                    ),
                    "wav": event.wav_path,
                },
            )
