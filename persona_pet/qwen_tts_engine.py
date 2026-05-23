"""Local Qwen3-TTS voice clone engine using FasterQwen3TTS.

Provides a singleton wrapper that loads the model once at startup and keeps the
local voice-clone call path aligned with TTS_qwen_test/realtime_voice_clone.py.
"""

from __future__ import annotations

import os
import random
import threading
import time
import wave

import numpy as np

# Pre-import transformers in the main thread so its _LazyModule is fully
# initialised before any background thread tries to resolve AutoConfig.
# Without this, the first ``from transformers import AutoConfig`` inside a
# background thread can race with the main-thread lazy import machinery and
# produce "cannot import name 'AutoConfig'".
try:
    import transformers  # noqa: F401
    _ = transformers.AutoConfig  # force lazy resolution
except Exception:
    pass

from persona_pet.runtime import get_default_runtime

# Project root: persona_pet/ -> person_test_all/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default paths (relative to project root)
_DEFAULT_MODEL_PATH = os.path.join(_PROJECT_ROOT, "third_party", "qwen_tts_model")
_DEFAULT_REF_DIR = os.path.join(_PROJECT_ROOT, "third_party", "qwen_tts_refs")
_DEFAULT_REF_AUDIO = os.path.join(_DEFAULT_REF_DIR, "reference.wav")
DEFAULT_QWEN_TTS_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
_SINGLE_REF_CANDIDATES = ("reference", "ref", "speaker", "neutral")
_MODEL_WEIGHT_SUFFIXES = (".safetensors", ".bin")

DEFAULT_SAMPLE_RATE = 24000
TARGET_PEAK = 0.86
STREAM_STABILIZE_MIN_RMS = 0.018
STREAM_STABILIZE_REF_CHUNKS = 4
STREAM_STABILIZE_GAIN_MIN = 0.92
STREAM_STABILIZE_GAIN_MAX = 1.12
STREAM_STABILIZE_SMOOTH = 0.22
STREAM_STABILIZE_MAX_STEP = 0.035



def _runtime_log(msg: str) -> None:
    print(f"[QwenTTS] {msg}", flush=True)


def _looks_like_remote_model_id(value: str) -> bool:
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://", "./", ".\\", "../", "..\\", "~")):
        return False
    if os.path.isabs(text) or "\\" in text:
        return False
    normalized = text.replace("\\", "/")
    first = normalized.split("/", 1)[0].strip().lower()
    if first in {"third_party", "assets", "models", "model", "persona_pet", "tools"}:
        return False
    return normalized.count("/") == 1


def qwen_tts_model_ready(model_path: str) -> bool:
    path = str(model_path or "").strip()
    if not path:
        path = _DEFAULT_MODEL_PATH
    if _looks_like_remote_model_id(path):
        return True
    if not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, "config.json")):
        return False
    for name in os.listdir(path):
        if name.lower().endswith(_MODEL_WEIGHT_SUFFIXES):
            return True
    return False


def download_qwen_tts_model(
    model_id: str = DEFAULT_QWEN_TTS_MODEL_ID,
    target_dir: str = "",
    progress_callback=None,
) -> str:
    repo_id = str(model_id or DEFAULT_QWEN_TTS_MODEL_ID).strip() or DEFAULT_QWEN_TTS_MODEL_ID
    local_dir = str(target_dir or _DEFAULT_MODEL_PATH).strip() or _DEFAULT_MODEL_PATH
    os.makedirs(local_dir, exist_ok=True)

    def progress(message: str) -> None:
        _runtime_log(message)
        if progress_callback is not None:
            progress_callback(message)

    progress(f"Downloading model {repo_id} -> {local_dir}")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("缺少 huggingface_hub，无法自动下载本地 TTS 模型。请安装 requirements_local_tts.txt。") from exc

    snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    if not qwen_tts_model_ready(local_dir):
        raise RuntimeError(f"模型下载后仍不完整：{local_dir}")
    progress("Qwen TTS model download complete")
    return local_dir


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def _active_rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-6:
        return 0.0
    threshold = max(0.012, peak * 0.08)
    active = audio[np.abs(audio) >= threshold]
    if active.size < max(64, audio.size // 20):
        return _rms(audio)
    return _rms(active)


def _limit_peak(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > TARGET_PEAK:
        audio = np.tanh(audio / TARGET_PEAK) * TARGET_PEAK
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > TARGET_PEAK:
        audio = audio / peak * TARGET_PEAK
    return audio.astype(np.float32)


def _stabilize_stream_chunk(
    audio: np.ndarray,
    target_rms: float,
    prev_gain: float,
) -> tuple[np.ndarray, float, float]:
    """Apply a very light per-chunk loudness correction for long streaming lines."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return audio, prev_gain, 0.0

    chunk_rms = _active_rms(audio)
    if target_rms <= 1e-6 or chunk_rms < STREAM_STABILIZE_MIN_RMS:
        return audio, prev_gain, chunk_rms

    desired_gain = target_rms / max(chunk_rms, 1e-6)
    desired_gain = max(STREAM_STABILIZE_GAIN_MIN, min(STREAM_STABILIZE_GAIN_MAX, desired_gain))
    smoothed_gain = prev_gain + (desired_gain - prev_gain) * STREAM_STABILIZE_SMOOTH
    gain_delta = smoothed_gain - prev_gain
    gain_delta = max(-STREAM_STABILIZE_MAX_STEP, min(STREAM_STABILIZE_MAX_STEP, gain_delta))
    gain = prev_gain + gain_delta
    if abs(gain - 1.0) < 0.01:
        gain = 1.0

    stabilized = _limit_peak(audio * gain)
    return stabilized, gain, chunk_rms


def write_wav(path: str, audio: np.ndarray, sample_rate: int) -> float:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return len(audio) / max(sample_rate, 1)


class QwenTTSEngine:
    """Singleton local TTS engine backed by FasterQwen3TTS."""

    _instance: QwenTTSEngine | None = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(
        self,
        model_path: str = "",
        ref_dir: str = "",
        ref_audio: str = "",
        ref_text: str = "",
        xvec_only: bool = False,
        do_sample: bool = True,
        seed: int = 24681357,
        temperature: float = 0.9,
        top_p: float = 1.0,
        model_id: str = DEFAULT_QWEN_TTS_MODEL_ID,
        auto_download: bool = True,
        device: str = "cuda",
        runtime=None,
    ):
        if self._initialized:
            if runtime is not None:
                self.runtime = runtime
            return
        self._initialized = True
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.ref_dir = ref_dir or _DEFAULT_REF_DIR
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.xvec_only = bool(xvec_only)
        self.do_sample = bool(do_sample)
        self.seed = int(seed or 0)
        self.temperature = float(temperature or 0.9)
        self.top_p = float(top_p or 1.0)
        self.model_id = str(model_id or DEFAULT_QWEN_TTS_MODEL_ID).strip() or DEFAULT_QWEN_TTS_MODEL_ID
        self.auto_download = bool(auto_download)
        self.device = device
        self.runtime = runtime or get_default_runtime()
        self.model = None
        self._ready = False
        self._loading = False
        self._load_error = ""
        self._ready_event = threading.Event()

    @classmethod
    def get_instance(cls) -> QwenTTSEngine | None:
        return cls._instance

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None

    def update_paths(
        self,
        model_path: str,
        ref_dir: str,
        ref_audio: str = "",
        ref_text: str = "",
        xvec_only: bool | None = None,
        do_sample: bool | None = None,
        seed: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        model_id: str | None = None,
        auto_download: bool | None = None,
    ):
        self.model_path = model_path
        self.ref_dir = ref_dir
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        if xvec_only is not None:
            self.xvec_only = bool(xvec_only)
        if do_sample is not None:
            self.do_sample = bool(do_sample)
        if seed is not None:
            self.seed = int(seed or 0)
        if temperature is not None:
            self.temperature = float(temperature or self.temperature)
        if top_p is not None:
            self.top_p = float(top_p or self.top_p)
        if model_id is not None:
            self.model_id = str(model_id or self.model_id).strip() or self.model_id
        if auto_download is not None:
            self.auto_download = bool(auto_download)

    def is_ready(self) -> bool:
        return self._ready

    def is_loading(self) -> bool:
        return self._loading

    def wait_until_ready(self, timeout: float = 120.0) -> bool:
        return self._ready_event.wait(timeout=timeout)

    def load_model(self):
        """Load the FasterQwen3TTS model. Call once at startup."""
        if self._ready or self._loading:
            return
        self._loading = True
        self._load_error = ""
        try:
            import torch
            from faster_qwen3_tts import FasterQwen3TTS

            if self.auto_download and not qwen_tts_model_ready(self.model_path):
                self.model_path = download_qwen_tts_model(self.model_id, self.model_path)
            _runtime_log(f"Loading model: {self.model_path}")
            t0 = time.perf_counter()
            self.model = FasterQwen3TTS.from_pretrained(
                self.model_path,
                device=self.device,
                dtype=torch.bfloat16 if self.device.startswith("cuda") else torch.float32,
            )
            elapsed = time.perf_counter() - t0
            _runtime_log(f"Model loaded in {elapsed:.1f}s, ready for synthesis")
            self._ready = True
        except ImportError as exc:
            # Retry once after ensuring transformers lazy module is resolved
            _runtime_log(f"Import error (retrying): {exc}")
            try:
                import transformers as _tf  # noqa: F401
                _ = _tf.AutoConfig
                import torch
                from faster_qwen3_tts import FasterQwen3TTS
                if self.auto_download and not qwen_tts_model_ready(self.model_path):
                    self.model_path = download_qwen_tts_model(self.model_id, self.model_path)
                _runtime_log(f"Loading model (retry): {self.model_path}")
                t0 = time.perf_counter()
                self.model = FasterQwen3TTS.from_pretrained(
                    self.model_path,
                    device=self.device,
                    dtype=torch.bfloat16 if self.device.startswith("cuda") else torch.float32,
                )
                elapsed = time.perf_counter() - t0
                _runtime_log(f"Model loaded in {elapsed:.1f}s (retry succeeded)")
                self._ready = True
            except Exception as exc2:
                self._load_error = str(exc2)
                _runtime_log(f"Model load FAILED: {exc2}")
        except Exception as exc:
            self._load_error = str(exc)
            _runtime_log(f"Model load FAILED: {exc}")
        finally:
            self._loading = False
            self._ready_event.set()

    def load_model_async(self):
        """Start model loading in a background thread."""
        self.runtime.run_background(
            "qwen_tts_model_load",
            self.load_model,
            kind="audio",
            resources=("tts_model_load",),
            timeout=900,
        )

    def _resolve_ref(self) -> tuple[str, str]:
        """Return the single reference audio and text used for every emotion."""
        ref_wav = self.ref_audio.strip()
        ref_txt = ""
        if ref_wav and os.path.isdir(ref_wav):
            ref_wav = os.path.join(ref_wav, "neutral.wav")
        if not ref_wav and self.ref_dir and os.path.isfile(self.ref_dir):
            ref_wav = self.ref_dir
        if not ref_wav:
            for name in _SINGLE_REF_CANDIDATES:
                candidate = os.path.join(self.ref_dir, f"{name}.wav")
                if os.path.exists(candidate):
                    ref_wav = candidate
                    break
        if not ref_wav and os.path.isdir(self.ref_dir):
            wavs = sorted(
                os.path.join(self.ref_dir, name)
                for name in os.listdir(self.ref_dir)
                if name.lower().endswith(".wav")
            )
            if wavs:
                ref_wav = wavs[0]
        if not ref_wav:
            ref_wav = _DEFAULT_REF_AUDIO

        explicit_ref_text = self.ref_text.strip()
        if explicit_ref_text and os.path.exists(explicit_ref_text):
            ref_txt = explicit_ref_text
        elif explicit_ref_text:
            return ref_wav, explicit_ref_text
        else:
            ref_txt = os.path.splitext(ref_wav)[0] + ".txt"

        ref_text = ""
        if os.path.exists(ref_txt):
            with open(ref_txt, "r", encoding="utf-8") as f:
                ref_text = f.read().strip()
        return ref_wav, ref_text

    def _seed_generation(self) -> None:
        if self.seed <= 0 or self.do_sample:
            return
        random.seed(self.seed)
        np.random.seed(self.seed % (2**32 - 1))
        try:
            import torch

            torch.manual_seed(self.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.seed)
        except Exception:
            pass

    def _generate_audio_once(
        self,
        text: str,
        emotion: str,
        ref_wav: str,
        ref_text: str,
        segment_index: int = 0,
        prosody_hint: dict | None = None,
    ) -> tuple[np.ndarray, int]:
        _runtime_log(f"Segment {segment_index + 1} [{emotion}]: {text[:40]}...")
        if self.seed > 0 and not self.do_sample:
            self._seed_generation()

        audio_list, sr = self.model.generate_voice_clone(
            text=text,
            language="Chinese",
            ref_audio=ref_wav,
            ref_text=ref_text,
            xvec_only=self.xvec_only,
            do_sample=self.do_sample,
            temperature=self.temperature,
            top_p=self.top_p,
        )

        audio = audio_list[0] if isinstance(audio_list, (list, tuple)) else audio_list
        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        return np.asarray(audio, dtype=np.float32).reshape(-1), sr

    def stream_synthesize_chunks(
        self,
        text: str,
        emotion: str = "neutral",
        prosody_hint: dict | None = None,
        chunk_size: int = 8,
    ):
        if not self._ready:
            if self._loading:
                _runtime_log("Waiting for model to load...")
                self.wait_until_ready()
            if not self._ready:
                raise RuntimeError(f"Qwen TTS model not loaded: {self._load_error}")

        ref_wav, ref_text = self._resolve_ref()
        if not os.path.exists(ref_wav):
            raise FileNotFoundError(f"Reference audio not found: {ref_wav}")

        text = str(text or "").strip()
        if not text:
            raise ValueError("Qwen TTS text is empty")

        if self.seed > 0 and not self.do_sample:
            self._seed_generation()
        chunk_size = int(chunk_size or 8)

        _runtime_log(f"Streaming [{emotion}] with one reference: {text[:50]}...")
        ref_rms_values: list[float] = []
        target_rms = 0.0
        current_gain = 1.0
        for index, (audio_chunk, sr, timing) in enumerate(
            self.model.generate_voice_clone_streaming(
                text=text,
                language="Chinese",
                ref_audio=ref_wav,
                ref_text=ref_text,
                chunk_size=chunk_size,
                xvec_only=self.xvec_only,
                do_sample=self.do_sample,
                temperature=self.temperature,
                top_p=self.top_p,
            )
        ):
            if hasattr(audio_chunk, "cpu"):
                audio_chunk = audio_chunk.cpu().numpy()
            chunk = np.asarray(audio_chunk, dtype=np.float32).reshape(-1)
            if chunk.size == 0:
                continue
            chunk_rms = _active_rms(chunk)
            if chunk_rms >= STREAM_STABILIZE_MIN_RMS and len(ref_rms_values) < STREAM_STABILIZE_REF_CHUNKS:
                ref_rms_values.append(chunk_rms)
                target_rms = float(np.mean(ref_rms_values))
            if target_rms > 1e-6:
                chunk, current_gain, chunk_rms = _stabilize_stream_chunk(chunk, target_rms, current_gain)
            _runtime_log(f"Chunk {index + 1}: {len(chunk) / max(sr, 1):.2f}s")
            yield chunk, sr, timing

    def prepare_segments(self, text: str) -> list[str]:
        cleaned = str(text or "").strip()
        return [cleaned] if cleaned else []

    def synthesize_segment_to_path(
        self,
        text: str,
        emotion: str,
        output_path: str,
        segment_index: int = 0,
        prosody_hint: dict | None = None,
    ) -> tuple[str, float]:
        if not self._ready:
            if self._loading:
                _runtime_log("Waiting for model to load...")
                self.wait_until_ready()
            if not self._ready:
                raise RuntimeError(f"Qwen TTS model not loaded: {self._load_error}")

        ref_wav, ref_text = self._resolve_ref()
        if not os.path.exists(ref_wav):
            raise FileNotFoundError(f"Reference audio not found: {ref_wav}")

        audio, sr = self._generate_audio_once(
            text,
            emotion,
            ref_wav,
            ref_text,
            segment_index=segment_index,
            prosody_hint=prosody_hint,
        )
        duration = write_wav(output_path, audio, sr)
        return output_path, duration

    def synthesize(
        self,
        text: str,
        emotion: str = "neutral",
        output_path: str = "",
        prosody_hint: dict | None = None,
    ) -> tuple[str, float]:
        """Synthesize text to WAV file. Returns (path, duration_seconds).

        Blocks until model is ready. Uses one reference audio and lets the
        instruction carry the requested emotion.
        """
        if not self._ready:
            if self._loading:
                _runtime_log("Waiting for model to load...")
                self.wait_until_ready()
            if not self._ready:
                raise RuntimeError(f"Qwen TTS model not loaded: {self._load_error}")

        ref_wav, ref_text = self._resolve_ref()
        if not os.path.exists(ref_wav):
            raise FileNotFoundError(f"Reference audio not found: {ref_wav}")

        text = str(text or "").strip()
        if not text:
            raise ValueError("Qwen TTS text is empty")

        _runtime_log(f"Synthesizing [{emotion}] with one reference: {text[:50]}...")
        t0 = time.perf_counter()
        audio, sr = self._generate_audio_once(
            text,
            emotion,
            ref_wav,
            ref_text,
            segment_index=0,
            prosody_hint=prosody_hint,
        )

        duration = write_wav(output_path, audio, sr)
        elapsed = time.perf_counter() - t0
        _runtime_log(f"Done in {elapsed:.2f}s, duration={duration:.2f}s -> {output_path}")
        return output_path, duration
