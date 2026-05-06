"""LLM client, reply parsing, and async chat controller."""

import json
import os
import re
import threading
import time
import urllib.request
from dataclasses import dataclass, field

from persona_pet.lexicon import HARD_BOUNDARY_REPLY_TERMS
from persona_pet.llm_config import build_default_llm_config
from persona_pet.memory import (
    compact_text,
    is_intimate_boundary_query,
    normalize_prosody_hint,
    strip_stage_directions,
)
from persona_pet.prompts import PROSODY_PROMPT_CONTRACT

LLM_EMOTIONS = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
STRUCTURED_REPLY_MARKERS = ('"zh"', '"emotion"', '"segments"', '"prosody"', '"voice_text"')
DEFAULT_LLM_CONFIG = build_default_llm_config()


def default_emotion_from_text(_text):
    return "neutral"


def default_reconcile_emotion(_user_text, _reply_text, emotion):
    emotion = str(emotion or "").strip().lower()
    return (emotion if emotion in LLM_EMOTIONS else "neutral"), "default"


def is_transient_llm_error(error):
    text = str(error or "").lower()
    return any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "temporarily",
            "connection reset",
            "connection aborted",
            "remote end closed",
            "read operation timed out",
            "502",
            "503",
            "504",
            "429",
        )
    )

class LLMClient:
    def __init__(self, config=None, memory_store=None, life_system=None, default_config=None, emotion_from_text=None, reconcile_emotion=None):
        self.default_config = dict(default_config or DEFAULT_LLM_CONFIG)
        self.config = dict(self.default_config)
        self.config.update(config or {})
        self.history = []
        self.memory_store = memory_store
        self.life_system = life_system
        self.emotion_from_text = emotion_from_text or default_emotion_from_text
        self.reconcile_emotion = reconcile_emotion or default_reconcile_emotion

    def trim_history(self):
        max_turns = int(self.config.get("max_history_turns", 6))
        max_messages = max(0, max_turns) * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def chat(self, user_text):
        provider = str(self.config.get("provider", "ollama")).lower()
        if provider in ("openai", "openai_compatible", "compatible"):
            reply = self.chat_openai_compatible(user_text)
        else:
            reply = self.chat_ollama(user_text)
        payload = self.parse_reply_payload(reply)
        payload = self.remove_formulaic_writer_reply(user_text, payload)
        payload = self.soften_boundary_reply(user_text, payload)
        original_emotion = payload.get("emotion", "neutral")
        repaired_emotion, emotion_reason = self.reconcile_emotion(
            user_text,
            payload.get("zh", ""),
            original_emotion,
        )
        if repaired_emotion != original_emotion:
            print(
                "LLM_EMOTION_REPAIR =",
                {
                    "from": original_emotion,
                    "to": repaired_emotion,
                    "reason": emotion_reason,
                    "user": user_text,
                    "reply": payload.get("zh", ""),
                },
            )
            payload["emotion"] = repaired_emotion
            if emotion_reason == "user_request" or not payload.get("segments"):
                for segment in payload.get("segments") or []:
                    segment["emotion"] = repaired_emotion
        if payload.get("segments"):
            repaired_segments = []
            for segment in payload["segments"]:
                segment = dict(segment)
                segment["voice_text"] = self.ensure_voice_text(
                    segment.get("zh", ""),
                    segment.get("voice_text") or segment.get("ja", ""),
                    segment.get("emotion", payload["emotion"]),
                )
                repaired_segments.append(segment)
            payload["segments"] = repaired_segments
            payload["zh"] = payload["zh"] or "".join(segment.get("zh", "") for segment in repaired_segments)
            payload["voice_text"] = payload.get("voice_text") or payload["zh"]
        else:
            payload["voice_text"] = self.ensure_voice_text(payload["zh"], payload.get("voice_text", ""), payload["emotion"])

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": payload["zh"]})
        self.trim_history()
        return payload

    def remove_formulaic_writer_reply(self, user_text, payload):
        if any(token in compact_text(user_text) for token in ("小说", "写作", "稿子", "故事", "日记", "章节")):
            return payload
        payload = dict(payload or {})
        banned = ("写进小说", "写进故事", "写进书里", "写成小说", "写到小说", "写在小说")

        def clean_text(text):
            text = str(text or "")
            if not any(token in text for token in banned):
                return text
            pieces = re.split(r"([。！？!?])", text)
            kept = []
            for index in range(0, len(pieces), 2):
                sentence = pieces[index]
                punct = pieces[index + 1] if index + 1 < len(pieces) else ""
                if any(token in sentence for token in banned):
                    continue
                kept.append(f"{sentence}{punct}")
            return "".join(kept).strip() or "我听见啦。先不把它变成什么台词，我就认真接住你这句话。"

        payload["zh"] = clean_text(payload.get("zh", ""))
        payload["voice_text"] = clean_text(payload.get("voice_text", "")) or payload["zh"]
        cleaned_segments = []
        for segment in payload.get("segments") or []:
            segment = dict(segment)
            segment["zh"] = clean_text(segment.get("zh", ""))
            segment["voice_text"] = clean_text(segment.get("voice_text", "")) or segment["zh"]
            if segment["zh"] or segment["voice_text"]:
                cleaned_segments.append(segment)
        payload["segments"] = cleaned_segments
        return payload

    def soften_boundary_reply(self, user_text, payload):
        if not is_intimate_boundary_query(user_text):
            return payload
        payload = dict(payload or {})
        reply_text = compact_text(payload.get("zh", ""))
        needs_soften = payload.get("emotion") == "anger" or any(term in reply_text for term in HARD_BOUNDARY_REPLY_TERMS)
        if not needs_soften:
            return payload
        score = float(getattr(self.life_system, "relationship_score", 0.0) or 0.0)
        stage = "朋友"
        if self.life_system is not None:
            stage, _attitude = self.life_system.relationship_stage()
        if score >= 130:
            text = (
                "我们当然很亲近呀，所以我才会认真说。"
                "亲密不是按钮开关，也要看我当下的心情嘛。"
                "如果你温柔一点，亲亲、抱一下或者靠近一点都可以；更敏感的事先慢慢来。"
            )
            emotion = "joy"
        elif score >= 88:
            text = (
                "咱们是恋人没错呀，可恋人也不是按钮开关嘛。"
                "我不是讨厌你，只是这种亲密要慢慢来，还要看我当下的心情。"
                "今天先牵手、抱抱或者摸摸头，我会更愿意靠近你一点。"
            )
            emotion = "surprise"
        elif score >= 65:
            text = (
                "我知道你是在确认我们的距离啦。"
                "只是现在还没有到那种亲密程度，我会有点紧张。"
                "可以先摸摸头或者陪我玩一会儿，慢慢让我更安心。"
            )
            emotion = "surprise"
        else:
            text = (
                "这个话题对我来说有点太快啦。"
                "我愿意和你更熟一点，但现在先保持舒服的距离，好不好？"
                "摸头或者一起玩小游戏，我会比较安心。"
            )
            emotion = "surprise"
        payload.update(
            {
                "zh": text,
                "voice_text": text,
                "emotion": emotion,
                "segments": [],
                "prosody": {"pace": "normal", "tone": "soft", "emphasis": [], "pause_after": []},
            }
        )
        print("BOUNDARY_REPLY_SOFTENED =", {"stage": stage, "relationship_score": score})
        return payload

    def build_messages(self, user_text):
        system_prompt = str(self.config.get("system_prompt", self.default_config["system_prompt"]))
        if "VOICEVOX" in system_prompt or "\"ja\"" in system_prompt or "日语配音" in system_prompt:
            system_prompt = self.default_config["system_prompt"]
        if "prosody" not in system_prompt or "segments" not in system_prompt:
            system_prompt = f"{system_prompt}{PROSODY_PROMPT_CONTRACT}"
        style_guard = (
            "风格约束：像真人即时聊天，不要套固定结尾。"
            "除非用户主动问创作、小说、稿子，或者你正在执行写作任务，否则不要提小说、作家、写进故事、写进书里。"
            "不要用括号动作、旁白、心理描写代替正常说话。"
        )
        if style_guard not in system_prompt:
            system_prompt = f"{system_prompt}{style_guard}"
        messages = [{"role": "system", "content": system_prompt}]
        if self.memory_store is not None:
            memory_context = self.memory_store.build_prompt_context(user_text)
            if memory_context:
                messages.append({"role": "system", "content": memory_context})
        if self.life_system is not None:
            life_context = self.life_system.build_prompt_context()
            if life_context:
                messages.append({"role": "system", "content": life_context})
            boundary_context = self.life_system.build_boundary_context(user_text)
            if boundary_context:
                messages.append({"role": "system", "content": boundary_context})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def post_json(self, url, payload, headers=None, timeout=120):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))

    def chat_ollama(self, user_text):
        base_url = str(self.config.get("base_url") or self.default_config["base_url"]).rstrip("/")
        payload = {
            "model": self.config.get("model", self.default_config["model"]),
            "messages": self.build_messages(user_text),
            "stream": False,
            "options": {
                "temperature": float(self.config.get("temperature", 0.75)),
            },
        }
        data = self.post_json(f"{base_url}/api/chat", payload, timeout=180)
        reply = data.get("message", {}).get("content", "")
        return self.clean_reply(reply)

    def chat_openai_compatible(self, user_text):
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"
        headers = {}
        api_key_env = self.config.get("api_key_env") or "OPENAI_API_KEY"
        api_key = self.config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing API key. Set {api_key_env} or fill api_key in persona_llm_config.json.")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.config.get("model", ""),
            "messages": self.build_messages(user_text),
            "temperature": float(self.config.get("temperature", 0.75)),
            "stream": False,
        }
        data = self.post_json(url, payload, headers=headers, timeout=180)
        choices = data.get("choices") or []
        reply = choices[0].get("message", {}).get("content", "") if choices else ""
        return self.clean_reply(reply)

    def clean_reply(self, reply):
        reply = (reply or "").strip()
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
        reply = re.sub(r"\s+", " ", reply)
        return reply or "嗯嗯，我在听哦。"

    def extract_loose_json_string(self, text, key, following_keys=None):
        following_keys = following_keys or ("emotion", "segments", "prosody", "voice_text", "ja", "tts")
        key_pattern = re.escape(str(key))
        for next_key in following_keys:
            pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*,\s*"{re.escape(next_key)}"\s*:'
            match = re.search(pattern, text or "", flags=re.S)
            if match:
                return self.unescape_loose_json_text(match.group(1))
        pattern = rf'"{key_pattern}"\s*:\s*"(.*?)"\s*\}}'
        match = re.search(pattern, text or "", flags=re.S)
        if match:
            return self.unescape_loose_json_text(match.group(1))
        return ""

    def unescape_loose_json_text(self, text):
        text = str(text or "")
        text = text.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
        text = re.sub(r"\s+", " ", text).strip()
        return strip_stage_directions(text)

    def parse_loose_reply_payload(self, candidate):
        candidate = str(candidate or "").strip()
        if not any(marker in candidate for marker in STRUCTURED_REPLY_MARKERS):
            return {}
        zh = self.extract_loose_json_string(candidate, "zh")
        if not zh:
            zh = self.extract_loose_json_string(candidate, "reply")
        if not zh:
            zh = self.extract_loose_json_string(candidate, "reply_zh")
        if not zh:
            return {}
        emotion_match = re.search(r'"emotion"\s*:\s*"([A-Za-z_]+)"', candidate)
        emotion = (emotion_match.group(1).lower() if emotion_match else "").strip()
        if emotion not in LLM_EMOTIONS:
            emotion = self.emotion_from_text(zh)
        voice_text = self.extract_loose_json_string(candidate, "voice_text")
        segment_source = ""
        segment_block = re.search(r'"segments"\s*:\s*\[(.*?)\]\s*,\s*"prosody"', candidate, flags=re.S)
        if segment_block:
            segment_source = segment_block.group(1)
        segment_matches = re.findall(r'\{\s*"zh"\s*:\s*"(.*?)"\s*,\s*"emotion"\s*:\s*"([A-Za-z_]+)"', segment_source, flags=re.S)
        segments = []
        for segment_zh, segment_emotion in segment_matches[:4]:
            segment_zh = self.unescape_loose_json_text(segment_zh)
            segment_emotion = segment_emotion.lower().strip()
            if segment_zh:
                segments.append(
                    {
                        "zh": segment_zh,
                        "voice_text": segment_zh,
                        "ja": "",
                        "emotion": segment_emotion if segment_emotion in LLM_EMOTIONS else emotion,
                    }
                )
        if len(segments) <= 1:
            segments = []
        return {
            "zh": zh,
            "voice_text": voice_text,
            "emotion": emotion,
            "prosody": {},
            "segments": segments,
        }

    def parse_reply_payload(self, reply):
        cleaned = self.clean_reply(reply)
        candidate = cleaned
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.S | re.I)
        if fence:
            candidate = fence.group(1).strip()
        match = re.search(r"\{.*\}", candidate, flags=re.S)
        if match:
            candidate = match.group(0)

        try:
            data = json.loads(candidate)
        except Exception as exc:
            data = self.parse_loose_reply_payload(candidate)
            if data:
                print("LLM_JSON_REPAIRED =", {"error": str(exc)[:120], "zh": data.get("zh", "")[:80]})
        if not isinstance(data, dict):
            data = {}

        zh = strip_stage_directions(data.get("zh") or data.get("reply_zh") or data.get("reply") or cleaned)
        if not data and any(marker in cleaned for marker in STRUCTURED_REPLY_MARKERS):
            zh = re.sub(r'"(?:emotion|segments|prosody|voice_text|ja|tts)"\s*:\s*[^,}]+', "", cleaned)
            zh = re.sub(r'[{}[\]"]+', "", zh)
            zh = re.sub(r"\bzh\s*:\s*", "", zh)
            zh = strip_stage_directions(re.sub(r"\s+", " ", zh).strip(" ,:"))
        emotion = str(data.get("emotion") or "").strip().lower()
        if emotion not in LLM_EMOTIONS:
            emotion = self.emotion_from_text(zh)
        voice_text = strip_stage_directions(data.get("voice_text") or data.get("tts") or data.get("ja") or data.get("voice_ja") or data.get("jp") or "")
        prosody = normalize_prosody_hint(data.get("prosody"))
        segments = self.parse_reply_segments(data, zh, voice_text, emotion)

        return {
            "zh": zh or "嗯嗯，我在听哦。",
            "voice_text": voice_text,
            "ja": "",
            "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
            "prosody": prosody,
            "segments": segments,
            "raw": cleaned,
        }

    def parse_reply_segments(self, data, fallback_zh, fallback_ja, fallback_emotion):
        raw_segments = data.get("segments") if isinstance(data, dict) else None
        if not isinstance(raw_segments, list):
            return []
        segments = []
        for item in raw_segments[:4]:
            if not isinstance(item, dict):
                continue
            zh = strip_stage_directions(item.get("zh") or item.get("text") or "")
            voice_text = strip_stage_directions(item.get("voice_text") or item.get("tts") or item.get("ja") or item.get("voice_ja") or "")
            emotion = str(item.get("emotion") or fallback_emotion or "").strip().lower()
            if emotion not in LLM_EMOTIONS:
                seed = zh or fallback_zh
                emotion = self.emotion_from_text(seed)
            if not zh and not voice_text:
                continue
            segments.append(
                {
                    "zh": zh,
                    "voice_text": voice_text or zh,
                    "ja": "",
                    "emotion": emotion if emotion in LLM_EMOTIONS else "neutral",
                }
            )
        if len(segments) <= 1:
            return []
        if not any(segment.get("voice_text") for segment in segments) and fallback_ja:
            return []
        return segments

    def ensure_voice_text(self, zh, ja, emotion):
        zh = str(zh or "").strip()
        zh = strip_stage_directions(zh)
        voice_text = strip_stage_directions(ja)
        if voice_text and not re.search(r"[\u3040-\u30ff]", voice_text):
            return voice_text
        return zh or voice_text or "嗯嗯，我在听哦。"

    def chat_openai_compatible_messages(self, messages, temperature=0.35, timeout=90):
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
        api_key_env = self.config.get("api_key_env") or "OPENAI_API_KEY"
        api_key = self.config.get("api_key") or os.environ.get(api_key_env, "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing API key. Set {api_key_env} or fill api_key in persona_llm_config.json.")
        payload = {
            "model": self.config.get("model", ""),
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        data = self.post_json(url, payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        choices = data.get("choices") or []
        return self.clean_reply(choices[0].get("message", {}).get("content", "") if choices else "")

    def chat_ollama_messages(self, messages, temperature=0.35, timeout=120):
        base_url = str(self.config.get("base_url") or self.default_config["base_url"]).rstrip("/")
        payload = {
            "model": self.config.get("model", self.default_config["model"]),
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self.post_json(f"{base_url}/api/chat", payload, timeout=timeout)
        return self.clean_reply(data.get("message", {}).get("content", ""))

    def chat_messages(self, messages, temperature=0.35, timeout=120):
        provider = str(self.config.get("provider", "ollama")).lower()
        if provider in ("openai", "openai_compatible", "compatible"):
            return self.chat_openai_compatible_messages(messages, temperature=temperature, timeout=timeout)
        return self.chat_ollama_messages(messages, temperature=temperature, timeout=timeout)

@dataclass
class LLMReplyEvent:
    user_text: str
    reply: str
    voice_text: str = ""
    emotion: str = "neutral"
    prosody: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)
    error: str = ""
    degraded_error: str = ""
    initiated_by: str = "user"
    memory_user_text: str = ""

class LLMChatController:
    def __init__(self, config=None, memory_store=None, life_system=None, default_config=None, emotion_from_text=None, reconcile_emotion=None, retry_seconds=1.2):
        self.client = LLMClient(
            config=config,
            memory_store=memory_store,
            life_system=life_system,
            default_config=default_config,
            emotion_from_text=emotion_from_text,
            reconcile_emotion=reconcile_emotion,
        )
        self.retry_seconds = float(retry_seconds)
        self.lock = threading.Lock()
        self.events = []
        self.busy = False

    def fallback_payload(self, initiated_by, error):
        if initiated_by == "proactive":
            text = "刚才想和你说句话，但是脑袋有点卡住了，我先安静陪你一会儿。"
        elif is_transient_llm_error(error):
            text = "刚才连接有点慢，我先缓一下。你刚才说的我还在听，可以再说一遍吗？"
        else:
            text = "我这边刚才没接好话，但我还在。你再跟我说一次好吗？"
        return {
            "zh": text,
            "voice_text": text,
            "emotion": "neutral",
            "prosody": {"pace": "slow", "tone": "soft", "emphasis": [], "pause_after": []},
            "segments": [],
        }

    def ask_async(self, user_text, initiated_by="user", memory_user_text=""):
        user_text = (user_text or "").strip()
        if not user_text:
            return False
        initiated_by = (initiated_by or "user").strip() or "user"
        memory_user_text = (memory_user_text or "").strip()
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            payload = {"zh": "", "voice_text": "", "emotion": "neutral"}
            error = ""
            degraded_error = ""
            try:
                payload = self.client.chat(user_text)
            except Exception as exc:
                error = str(exc)
                if is_transient_llm_error(error):
                    time.sleep(self.retry_seconds)
                    try:
                        payload = self.client.chat(user_text)
                        print("LLM_RETRY_OK =", {"initiated_by": initiated_by})
                        error = ""
                    except Exception as retry_exc:
                        error = str(retry_exc)
                if error:
                    degraded_error = error
                    payload = self.fallback_payload(initiated_by, error)
                    error = ""
            with self.lock:
                self.busy = False
                self.events.append(
                    LLMReplyEvent(
                        user_text=user_text,
                        reply=payload.get("zh", ""),
                        voice_text=payload.get("voice_text") or payload.get("zh", ""),
                        emotion=payload.get("emotion", "neutral"),
                        prosody=payload.get("prosody") or {},
                        segments=payload.get("segments") or [],
                        error=error,
                        degraded_error=degraded_error,
                        initiated_by=initiated_by,
                        memory_user_text=memory_user_text,
                    )
                )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def is_busy(self):
        with self.lock:
            return self.busy
