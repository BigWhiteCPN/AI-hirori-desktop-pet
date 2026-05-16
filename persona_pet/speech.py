"""Speech input and barge-in monitoring helpers."""

import json
import os
import re
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass, field

from persona_pet.error_reporter import report_exception
from persona_pet.runtime import get_default_runtime

@dataclass
class SpeechInputEvent:
    text: str = ""
    error: str = ""
    wav_path: str = ""
    audio_stats: dict = field(default_factory=dict)

class SpeechInputController:
    def __init__(
        self,
        enabled=True,
        voice_output_dir="",
        helper_path="",
        llm_config_path="",
        base_dir="",
        model_dir="",
        model_size="base",
        record_seconds=0.0,
        min_record_seconds=0.75,
        silence_seconds=1.05,
        silence_rms=0.008,
        start_timeout=8.0,
        chunk_ms=40,
        sample_rate=16000,
        helper_timeout_seconds=0.0,
        logger=None,
        runtime=None,
    ):
        self.enabled = bool(enabled)
        self.voice_output_dir = voice_output_dir
        self.helper_path = helper_path
        self.llm_config_path = llm_config_path
        self.base_dir = base_dir
        self.model_dir = model_dir
        self.model_size = model_size
        self.record_seconds = float(record_seconds)
        self.min_record_seconds = float(min_record_seconds)
        self.silence_seconds = float(silence_seconds)
        self.silence_rms = float(silence_rms)
        self.start_timeout = float(start_timeout)
        self.chunk_ms = int(chunk_ms)
        self.sample_rate = int(sample_rate)
        self.helper_timeout_seconds = float(helper_timeout_seconds)
        self.logger = logger or (lambda *parts: None)
        self.runtime = runtime or get_default_runtime()
        self.lock = threading.Lock()
        self.events = []
        self.busy = False
        self.model = None
        self.current_process = None
        self._persistent_proc = None
        self._persistent_lock = threading.Lock()

    def is_busy(self):
        with self.lock:
            return self.busy

    def load_model(self):
        if self.model is not None:
            return self.model
        with self.lock:
            if self.model is not None:
                return self.model
            os.makedirs(self.model_dir, exist_ok=True)
            from faster_whisper import WhisperModel

            try:
                self.model = WhisperModel(
                    self.model_size,
                    device="cuda",
                    compute_type="int8_float16",
                    download_root=self.model_dir,
                )
            except Exception as exc:
                report_exception(self.runtime, self.logger, "speech", "load_cuda_model", exc, model_size=self.model_size)
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=self.model_dir,
                )
        return self.model

    def _ensure_persistent(self):
        """Start the persistent SenseVoice subprocess if not running."""
        with self._persistent_lock:
            if self._persistent_proc is not None and self._persistent_proc.poll() is None:
                return True
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--speech-helper", "--persistent"]
            else:
                cmd = [sys.executable, "-B", self.helper_path, "--persistent"]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                self._persistent_proc = subprocess.Popen(
                    cmd,
                    cwd=self.base_dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )
                # Skip non-JSON lines (warnings, progress bars) until ready signal
                for _ in range(50):
                    ready_line = self._persistent_proc.stdout.readline()
                    if not ready_line:
                        break
                    ready_line = ready_line.strip()
                    if ready_line.startswith("{"):
                        try:
                            ready = json.loads(ready_line)
                            break
                        except json.JSONDecodeError:
                            continue
                else:
                    ready = {}
                if ready.get("ready"):
                    self.logger("SPEECH_PERSISTENT_READY", {})
                    return True
                else:
                    self.logger("SPEECH_PERSISTENT_NOT_READY", ready)
                    return False
            except Exception as exc:
                self.logger("SPEECH_PERSISTENT_START_ERROR", str(exc)[:200])
                self._persistent_proc = None
                return False

    def _transcribe_persistent(self, wav_path):
        """Send WAV path to persistent process and get transcription."""
        proc = self._persistent_proc
        if proc is None or proc.poll() is not None:
            raise RuntimeError("persistent process not running")
        req = json.dumps({"wav_path": wav_path}) + "\n"
        proc.stdin.write(req)
        proc.stdin.flush()
        # Skip non-JSON lines (progress bars, warnings)
        for _ in range(100):
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("persistent process died")
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        raise RuntimeError("no JSON response from persistent process")

    def stop_persistent(self):
        """Stop the persistent subprocess."""
        with self._persistent_lock:
            if self._persistent_proc is not None:
                try:
                    self._persistent_proc.stdin.write("quit\n")
                    self._persistent_proc.stdin.flush()
                    self._persistent_proc.wait(timeout=3.0)
                except Exception:
                    try:
                        self._persistent_proc.kill()
                    except Exception:
                        pass
                self._persistent_proc = None

    def write_wav(self, path, samples):
        import numpy as np

        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak > 1.0:
            samples = samples / peak
        pcm = np.clip(samples, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        with wave.open(path, "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(self.sample_rate)
            file.writeframes(pcm.tobytes())

    def record_and_transcribe(self):
        os.makedirs(self.voice_output_dir, exist_ok=True)
        wav_path = os.path.join(self.voice_output_dir, "speech_input_last.wav")

        # Step 1: Record audio in subprocess
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--speech-helper"]
        else:
            cmd = [sys.executable, "-B", self.helper_path]
        cmd.extend(
            [
                "--seconds",
                str(self.record_seconds),
                "--adaptive",
                "--min-seconds",
                str(self.min_record_seconds),
                "--silence-seconds",
                str(self.silence_seconds),
                "--silence-rms",
                str(self.silence_rms),
                "--start-timeout",
                str(self.start_timeout),
                "--chunk-ms",
                str(self.chunk_ms),
                "--sample-rate",
                str(self.sample_rate),
                "--model-size",
                self.model_size,
                "--model-dir",
                self.model_dir,
                "--out",
                wav_path,
                "--config",
                self.llm_config_path,
                "--record-only",
            ]
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            cmd,
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        with self.lock:
            self.current_process = process
        helper_timeout = None
        if self.helper_timeout_seconds and self.helper_timeout_seconds > 0:
            helper_timeout = max(30.0, self.helper_timeout_seconds)
        elif self.record_seconds and self.record_seconds > 0:
            helper_timeout = max(90.0, self.record_seconds + 120.0)
        try:
            stdout, stderr = process.communicate(timeout=helper_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            raise RuntimeError("speech helper timed out")
        finally:
            with self.lock:
                if self.current_process is process:
                    self.current_process = None

        stdout = (stdout or "").strip()
        payload = self.parse_helper_payload(stdout)
        if process.returncode != 0 or not payload.get("ok"):
            error = payload.get("error") or stderr or stdout or f"speech helper exited {process.returncode}"
            raise RuntimeError(error)

        recorded_wav = str(payload.get("wav_path") or wav_path)
        stats = payload.get("audio_stats") or {}

        # Step 2: Transcribe via persistent SenseVoice process
        try:
            if not self._ensure_persistent():
                raise RuntimeError("failed to start persistent process")
            result = self._transcribe_persistent(recorded_wav)
            text = str(result.get("text", "")).strip()
            stats.update(result.get("audio_stats") or {})
        except Exception as exc:
            self.logger("SPEECH_PERSISTENT_ERROR", str(exc)[:200])
            # Fallback: run full helper (includes transcription)
            cmd = [c for c in cmd if c != "--record-only"]
            process2 = subprocess.Popen(
                cmd,
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            stdout2, _ = process2.communicate(timeout=helper_timeout)
            payload2 = self.parse_helper_payload((stdout2 or "").strip())
            text = str(payload2.get("text", "")).strip()
            stats = payload2.get("audio_stats") or stats

        return (text, recorded_wav, stats)

    def parse_helper_payload(self, stdout):
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout or "").strip()
        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(cleaned[index:])
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                continue
        return {}

    def stop(self):
        with self.lock:
            process = self.current_process
            self.current_process = None
            self.busy = False
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except Exception as exc:
                self.logger("SPEECH_HELPER_STOP_ERROR", exc)
                report_exception(self.runtime, self.logger, "speech", "stop_helper", exc)
        self.stop_persistent()

    def listen_async(self):
        if not self.enabled:
            return False
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            text = ""
            error = ""
            wav_path = ""
            try:
                with self.runtime.span("speech.listen", kind="audio", payload={"model_size": self.model_size}):
                    text, wav_path, stats = self.record_and_transcribe()
            except Exception as exc:
                error = str(exc)
                self.runtime.emit("speech.error", {"error": error}, level="error")
            with self.lock:
                self.busy = False
                self.runtime.emit(
                    "speech.result",
                    {"has_text": bool(text), "error": bool(error), "wav_path": wav_path},
                    level="error" if error else "info",
                )
                self.events.append(SpeechInputEvent(text=text, error=error, wav_path=wav_path, audio_stats=stats if "stats" in locals() else {}))

        self.runtime.run_background("speech_input", worker, kind="thread")
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

class BargeInController:
    def __init__(
        self,
        enabled=True,
        sample_rate=16000,
        chunk_ms=40,
        min_voiced_seconds=0.32,
        rms=0.14,
        noise_multiplier=7.5,
        runtime=None,
    ):
        self.enabled = bool(enabled)
        self.sample_rate = int(sample_rate)
        self.chunk_ms = int(chunk_ms)
        self.min_voiced_seconds = float(min_voiced_seconds)
        self.rms = float(rms)
        self.noise_multiplier = float(noise_multiplier)
        self.runtime = runtime or get_default_runtime()
        self.lock = threading.Lock()
        self.running = False
        self.active = False
        self.events = []
        self.thread = None
        self.noise_rms = max(0.002, self.rms / self.noise_multiplier)

    def start(self):
        if not self.enabled:
            return False
        with self.lock:
            if self.running:
                return True
            self.running = True

        def worker():
            try:
                self.runtime.emit("barge_in.monitor_start", {})
                self.monitor_loop()
            except Exception as exc:
                with self.lock:
                    self.running = False
                    self.active = False
                    self.events.append({"error": str(exc)})
                self.runtime.emit("barge_in.error", {"error": str(exc)}, level="error")
            finally:
                self.runtime.emit("barge_in.monitor_stop", {})

        task = self.runtime.run_background(
            "barge_in_monitor",
            worker,
            kind="audio",
            resources=("audio_input",),
        )
        self.thread = task.thread
        return True

    def stop(self):
        thread = None
        with self.lock:
            self.running = False
            self.active = False
            thread = self.thread
            self.thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def set_active(self, active):
        if not self.enabled:
            return
        self.start()
        with self.lock:
            self.active = bool(active)

    def monitor_loop(self):
        import numpy as np
        import sounddevice as sd

        blocksize = max(160, int(self.sample_rate * self.chunk_ms / 1000))
        voiced_samples = 0
        needed_samples = max(blocksize, int(self.min_voiced_seconds * self.sample_rate))
        last_trigger_at = 0.0

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                with self.lock:
                    running = self.running
                    active = self.active
                    noise_rms = self.noise_rms
                if not running:
                    return

                data, _overflowed = stream.read(blocksize)
                chunk = np.asarray(data, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0

                if not active:
                    if 0.0005 <= rms <= self.rms:
                        with self.lock:
                            self.noise_rms = self.noise_rms * 0.96 + rms * 0.04
                    voiced_samples = 0
                    continue

                threshold = max(self.rms, noise_rms * self.noise_multiplier)
                if rms >= threshold:
                    voiced_samples += chunk.size
                else:
                    voiced_samples = max(0, voiced_samples - chunk.size)

                now = time.monotonic()
                if voiced_samples >= needed_samples and now - last_trigger_at >= 1.2:
                    last_trigger_at = now
                    voiced_samples = 0
                    with self.lock:
                        self.active = False
                        self.events.append({"rms": round(rms, 6), "threshold": round(threshold, 6)})

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

def normalize_speech_piece(text):
    return re.sub(r"[\s,，。！？!?；;、~～…\.]+", "", text or "")

def clean_speech_input_text(text):
    original = re.sub(r"\s+", "", text or "").strip()
    if not original:
        return ""

    def key_of(value):
        return re.sub(r"[\s,，。！？!?；;、~～….\-]+", "", value or "")

    def repeat_key(value):
        return re.sub(r"[\s,，。！？?！、~～….\-]+", "", value or "")

    for end in range(len(original) - 1, 1, -1):
        prefix = original[:end].strip()
        suffix = original[end:].strip()
        prefix_key = repeat_key(prefix)
        suffix_key = repeat_key(suffix)
        if len(prefix_key) < 3 or not suffix_key:
            continue
        if len(suffix_key) % len(prefix_key) == 0 and suffix_key == prefix_key * (len(suffix_key) // len(prefix_key)):
            return prefix

    raw_parts = []
    current = ""
    for char in original:
        current += char
        if char in "。！？!?；;，,":
            raw_parts.append(current)
            current = ""
    if current:
        raw_parts.append(current)

    parts = []
    keys = []
    for part in raw_parts:
        part = part.strip()
        key = key_of(part)
        if key:
            parts.append(part)
            keys.append(key)

    if parts:
        deduped = []
        deduped_keys = []
        index = 0
        while index < len(parts):
            matched = False
            for group_size in range(min(4, (len(parts) - index) // 2), 0, -1):
                group = keys[index : index + group_size]
                if group == keys[index + group_size : index + group_size * 2]:
                    deduped.extend(parts[index : index + group_size])
                    deduped_keys.extend(group)
                    index += group_size
                    while keys[index : index + group_size] == group:
                        index += group_size
                    matched = True
                    break
            if matched:
                continue
            if keys[index] not in deduped_keys[-3:]:
                deduped.append(parts[index])
                deduped_keys.append(keys[index])
            index += 1
        result = "".join(deduped).strip()
        if result:
            return result

    text = re.sub(r"\s+", "", text or "").strip()
    if not text:
        return ""
    raw_parts = []
    current = ""
    for char in text:
        current += char
        if char in "。！？!?；;":
            raw_parts.append(current)
            current = ""
    if current:
        raw_parts.append(current)

    parts = []
    keys = []
    for part in raw_parts:
        cleaned = re.sub(r"^(你|我|他|她|它)\1+", r"\1", part.strip())
        key = normalize_speech_piece(cleaned)
        if key:
            parts.append(cleaned)
            keys.append(key)

    deduped = []
    deduped_keys = []
    index = 0
    while index < len(parts):
        matched = False
        for group_size in range(min(4, (len(parts) - index) // 2), 0, -1):
            group = keys[index : index + group_size]
            if group == keys[index + group_size : index + group_size * 2]:
                deduped.extend(parts[index : index + group_size])
                deduped_keys.extend(group)
                index += group_size
                while keys[index : index + group_size] == group:
                    index += group_size
                matched = True
                break
        if matched:
            continue
        key = keys[index]
        recent_join = "".join(deduped_keys[-4:])
        if key != recent_join:
            deduped.append(parts[index])
            deduped_keys.append(key)
        index += 1

    result = "".join(deduped).strip()
    return result or text
