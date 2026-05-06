import random
import re
import threading
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
    is_intimate_boundary_query,
    memory_now_label,
    normalize_prosody_hint,
    strip_stage_directions,
)
from persona_pet.speech import clean_speech_input_text, normalize_speech_piece
from persona_pet.voicevox import estimate_sentence_seconds

BARGE_IN_AFTER_PLAYBACK_SECONDS = 0.9
FREE_TALK_RELISTEN_DELAY = 0.15
LIFE_WRITING_IDLE_SECONDS = 75.0
LIFE_WRITING_INTERVAL_SECONDS = (150.0, 240.0)
MEMORY_MAX_TEXT_CHARS = 420
MEMORY_MIN_SIGNAL_CHARS = 4
PROACTIVE_ENABLED = True
PROACTIVE_IDLE_SECONDS = 120.0
PROACTIVE_INTERVAL_SECONDS = (180.0, 300.0)
SELF_NOTE_META_KEY = "self_notes"
STRUCTURED_REPLY_MARKERS = ('"zh"', '"emotion"', '"segments"', '"prosody"', '"voice_text"')
VOICE_PLAYBACK_GUARD_SECONDS = 0.25


class PetWorkflowMixin:
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
        self.submit_user_text(text)

    def submit_user_text(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.last_user_interaction_at = time.monotonic()
        self.next_proactive_at = self.last_user_interaction_at + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        self.memory_associate_input(text, source="user_text")
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
        self.physiology_on_user_message(text)
        self.heart_on_user_message(text, emotion=user_emotion)
        self.current_analysis = user_analysis
        self.mixer.set_target(user_analysis.weights)
        self.behavior.set_analysis(
            self.model,
            user_analysis,
            text=text,
            role=DIALOGUE_ROLE_LISTENER,
            force=True,
        )
        self.show_subtitle(f"你：{text}", voice_text="考え中……", duration=2.2)
        self.show_chat_status("思考中……", seconds=30.0)
        print("USER_CHAT =", text)
        if not self.chat.ask_async(text):
            self.show_chat_status("发送失败：上一句还没处理完。", seconds=2.2)

    def interrupt_current_speech(self, reason="user"):
        self.dialogue_active = False
        self.voice.stop_playback()
        self.behavior.stop_speaking()
        self.subtitle_until = min(self.subtitle_until, time.monotonic() + 0.4)
        print("VOICE_INTERRUPTED =", {"reason": reason})

    def start_speech_input(self, auto=False, interrupt=False):
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

        threading.Thread(target=worker, daemon=True).start()

    def maybe_start_self_note(self, idle_seconds):
        if not self.self_notes or self.drive.values.get("energy", 0.0) < 24:
            return False
        note = sorted(self.self_notes, key=lambda item: float(item.get("priority", 1.0)), reverse=True)[0]
        prompt = (
            "你现在不是被动回答用户，而是想主动表达一段自己的深层感受。\n"
            f"用户安静了约{int(idle_seconds)}秒。你的待表达念头：{note.get('text', '')}\n"
            "把它整理成一句更细腻的第一人称关系感受、反思总结或温柔但有棱角的观点。"
            "不要使用固定开头，例如“不过”“其实”“我只是”“我会一直在这里”；不要写成小说旁白或舞台说明。"
            "不要说倒水、喝水、休息、加油、我在这里这类浅层照顾句；不要解释系统。"
            "只输出一句中文，语气自然、亲近但克制，尽量不用问句。"
        )
        if hasattr(self.memory, "associative_trace"):
            self.memory.associative_trace(prompt, source="self_note", role="output_plan")
        self.show_chat_status("她正在整理一段想主动说的深层感受。", seconds=2.2)
        if not self.chat.ask_async(prompt, initiated_by="proactive", memory_user_text="桌宠主动行动：self_expression"):
            return False
        self.self_notes.remove(note)
        self.save_self_notes()
        self.drive.record_intent("self_expression", "主动表达深层感受或关系反思", score=note.get("priority"))
        self.drive.last_action_type = "self_expression"
        self.drive.save()
        self.next_proactive_at = time.monotonic() + random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        print("PROACTIVE_SELF_NOTE =", {"kind": note.get("kind"), "text": note.get("text")})
        return True

    def is_life_writing_due(self, now=None):
        now = time.monotonic() if now is None else now
        idle_seconds = now - self.last_user_interaction_at
        if self.free_talk_enabled and idle_seconds < 300.0 and not self.life.is_user_away(now):
            return False
        if now < self.life.next_writing_at:
            return False
        if self.drive.values.get("energy", 0.0) < 35.0 or now < self.drive.proactive_backoff_until:
            return False
        if idle_seconds < LIFE_WRITING_IDLE_SECONDS and not self.life.is_user_away(now):
            return False
        if self.life.needs_diary():
            return True
        return self.life.should_write_novel()

    def maybe_queue_idle_private_note(self, idle_seconds, now=None):
        if not hasattr(self.life, "observe_idle_private_mood"):
            return
        note = self.life.observe_idle_private_mood(idle_seconds, now=now)
        if not note:
            return
        kind = note.get("kind", "idle_sulk")
        if any(item.get("kind") == kind for item in self.self_notes):
            return
        self.add_self_note(note.get("text", ""), kind=kind, priority=float(note.get("priority", 1.4)))

    def maybe_start_proactive_chat(self):
        if not PROACTIVE_ENABLED:
            return
        now = time.monotonic()
        if now < self.next_proactive_at:
            return
        if now - self.last_user_interaction_at < PROACTIVE_IDLE_SECONDS:
            return
        if self.speech_input.is_busy() or self.chat.is_busy() or self.chat_advice.is_busy() or self.life_writer.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            self.next_proactive_at = now + 30.0
            return
        idle_seconds = now - self.last_user_interaction_at
        if self.is_life_writing_due(now):
            self.next_proactive_at = now + 120.0
            return
        self.maybe_queue_idle_private_note(idle_seconds, now=now)
        if self.maybe_start_self_note(idle_seconds):
            return
        recent_memories = []
        if hasattr(self.memory, "recent_user_memory_snippets"):
            recent_memories = self.memory.recent_user_memory_snippets(limit=3)
        action = self.drive.choose_proactive_action(
            idle_seconds,
            recent_memories=recent_memories,
            writing_due=self.is_life_writing_due(now),
        )
        if not action:
            self.next_proactive_at = now + 45.0
            return
        if action.get("type") == "silent_motion":
            try:
                if self.model is not None:
                    self.model.StartMotion("Idle", random.randrange(max(1, self.motion_groups.get("Idle", 1))), 1)
            except Exception:
                pass
            self.drive.on_silent_motion(action.get("type", "silent_motion"))
            self.show_chat_status("她决定先安静陪着你。", seconds=2.4)
            self.next_proactive_at = now + random.uniform(90.0, 180.0)
            print("PROACTIVE_SILENT =", action)
            return

        prompt = action.get("prompt", "")
        if hasattr(self.memory, "associative_trace"):
            self.memory.associative_trace(prompt or action.get("memory_user_text") or "主动表达", source="proactive", role="output_plan")
        self.show_chat_status("她好像想主动说点什么。", seconds=2.0)
        self.drive.record_intent(action.get("type", "proactive"), "内驱评分触发主动发言", score=action.get("score"))
        self.drive.last_action_type = action.get("type", "proactive")
        self.drive.save()
        self.chat.ask_async(
            prompt,
            initiated_by="proactive",
            memory_user_text=action.get("memory_user_text") or "桌宠主动关心用户",
        )
        interval = random.uniform(*PROACTIVE_INTERVAL_SECONDS)
        if idle_seconds >= 600.0:
            interval += random.uniform(240.0, 420.0)
        self.next_proactive_at = now + interval
        print("PROACTIVE_CHAT =", {"action": action.get("type"), "score": action.get("score"), "prompt": prompt})

    def process_speech_events(self):
        for event in self.speech_input.consume_events():
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
            if raw_text:
                self.memory_associate_input(raw_text, source="speech_raw")
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
            self.memory_associate_output(reply, source=f"assistant_{event.initiated_by}")
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
            self.behavior.set_analysis(
                self.model,
                analysis,
                text=reply,
                role=DIALOGUE_ROLE_SPEAKER,
                force=True,
            )
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
                    "initiated_by": event.initiated_by,
                    "prosody": event.prosody,
                    "segments": event.segments,
                    "singing": singing,
                },
            )

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
            self.memory_associate_output(f"小日和写完了一段{label}：{event.title}", source=f"life_writing_{event.kind}")
            self.show_chat_status(f"小日和写完了一段{label}。", seconds=4.0)
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

    def maybe_start_life_writing(self):
        now = time.monotonic()
        if now < self.life.next_writing_at:
            return
        idle_seconds = now - self.last_user_interaction_at
        if self.free_talk_enabled:
            if idle_seconds < 300.0 and not self.life.is_user_away(now):
                return
            self.free_talk_enabled = False
            self.free_talk_next_at = 0.0
            self.barge_in.stop()
            self.show_chat_status("她先去写点东西。", seconds=3.0)
        if self.drive.values.get("energy", 0.0) < 35.0 or time.monotonic() < self.drive.proactive_backoff_until:
            self.life.next_writing_at = now + 300.0
            return
        if idle_seconds < LIFE_WRITING_IDLE_SECONDS and not self.life.is_user_away(now):
            return
        if (
            self.speech_input.is_busy()
            or self.chat.is_busy()
            or self.chat_advice.is_busy()
            or self.life_writer.is_busy()
            or self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
        ):
            return
        kind = "diary" if self.life.needs_diary() else "novel"
        if kind == "novel" and not self.life.should_write_novel():
            self.life.next_writing_at = now + 1800.0
            return
        if self.life_writer.write_async(kind):
            self.memory_associate_output("小日和正在写日记。" if kind == "diary" else "小日和正在写小说。", source="life_writing_start")
            self.show_chat_status("小日和正在写日记。" if kind == "diary" else "小日和正在写小说。", seconds=18.0)
            self.life.next_writing_at = now + 600.0
            print("LIFE_WRITING_START =", {"kind": kind})

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
        voice_text = strip_stage_directions(voice_text_override or text or "") or "嗯嗯，我在听哦。"
        text = strip_stage_directions(text)
        self.memory_associate_output(text or voice_text, source="voice_output")
        if voice_segments:
            voice_segments = [
                {
                    **segment,
                    "zh": strip_stage_directions(segment.get("zh", "")),
                    "voice_text": strip_stage_directions(segment.get("voice_text") or segment.get("zh", "")),
                    "ja": "",
                }
                for segment in voice_segments
                if isinstance(segment, dict)
            ]
        if singing:
            voice_text = clean_song_text(voice_text) or clean_song_text(text) or voice_text
            voice_segments = None
        self.last_voice_analysis = analysis
        event_id = self.voice.speak_async(
            voice_text,
            emotion=emotion,
            singing=singing,
            source_text=text,
            prosody_hint=prosody_hint,
            segments=voice_segments,
        )
        print(
            "VOLCENGINE_TTS_SING =" if singing else "VOLCENGINE_TTS_SPEAK =",
            {
                "event_id": event_id,
                "emotion": emotion,
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
                if "缺少火山 TTS" in event.error:
                    self.show_chat_status("右键填写火山 TTS API Key", seconds=6.0)
                else:
                    self.show_chat_status(f"TTS 失败：{event.error[:28]}", seconds=6.0)
                print("VOLCENGINE_TTS_ERROR =", {"event_id": event.event_id, "error": event.error})
                continue
            def sync_on_playback_start(duration=event.duration, analysis=self.last_voice_analysis):
                self.voice.mark_playing(duration, guard_seconds=VOICE_PLAYBACK_GUARD_SECONDS)
                self.behavior.sync_speech_to_audio(duration, analysis=analysis)

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
                    "wav": event.wav_path,
                },
            )


