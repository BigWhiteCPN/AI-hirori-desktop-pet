import argparse
import base64
import json
import math
import os
import re
import sys
import time
import uuid
import urllib.request
import warnings
import wave
from pathlib import Path

# Suppress torchaudio/ffmpeg warnings
warnings.filterwarnings("ignore", message=".*ffmpeg.*")
os.environ.setdefault("TORCHAUDIO_USE_SOX", "0")
os.environ.setdefault("TORCHAUDIO_USE_BACKEND_DISPATCHER", "1")

import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "outputs" / "voice" / "speech_input_last.wav"
DEFAULT_MODEL_DIR = BASE_DIR / "third_party" / "faster_whisper"
DEFAULT_CONFIG_PATH = BASE_DIR / "persona_llm_config.json"
DOUBAO_ASR_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
DOUBAO_RESOURCE_ID = "volc.bigasr.auc_turbo"


def load_runtime_config(config_path=DEFAULT_CONFIG_PATH):
    try:
        with Path(config_path).open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def audio_stats(samples):
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return {"samples": 0, "rms": 0.0, "peak": 0.0, "dbfs": -120.0}
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    dbfs = 20.0 * math.log10(max(rms, 1e-6))
    return {
        "samples": int(samples.size),
        "rms": round(rms, 6),
        "peak": round(peak, 6),
        "dbfs": round(dbfs, 2),
    }


def write_wav(path, samples, sample_rate):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1.0:
        samples = samples / peak
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(pcm.tobytes())


def record(seconds, sample_rate, output_path):
    import sounddevice as sd

    frames = int(seconds * sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    write_wav(output_path, audio, sample_rate)
    return output_path, audio_stats(audio)


def record_adaptive(
    max_seconds,
    sample_rate,
    output_path,
    min_seconds,
    silence_seconds,
    silence_rms,
    start_timeout,
    chunk_ms=40,
):
    import sounddevice as sd

    blocksize = max(160, int(sample_rate * chunk_ms / 1000))
    max_samples = max(blocksize, int(max_seconds * sample_rate)) if max_seconds and max_seconds > 0 else 10**12
    min_samples = max(blocksize, int(min_seconds * sample_rate))
    silence_samples_needed = max(blocksize, int(silence_seconds * sample_rate))
    start_timeout_samples = max(blocksize, int(start_timeout * sample_rate))

    chunks = []
    total_samples = 0
    silent_samples = 0
    voiced_samples = 0
    warmup_rms = []
    dynamic_threshold = float(silence_rms)
    speech_started = False
    started_at = time.monotonic()

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", blocksize=blocksize) as stream:
        while total_samples < max_samples:
            data, _overflowed = stream.read(blocksize)
            chunk = np.asarray(data, dtype=np.float32).reshape(-1).copy()
            chunks.append(chunk)
            total_samples += chunk.size

            rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0
            if not speech_started:
                warmup_rms.append(rms)
                if len(warmup_rms) > 25:
                    warmup_rms = warmup_rms[-25:]
                noise_floor = float(np.percentile(warmup_rms, 70)) if warmup_rms else 0.0
                dynamic_threshold = max(float(silence_rms), noise_floor * 2.8)

            if rms >= dynamic_threshold:
                speech_started = True
                silent_samples = 0
                voiced_samples += chunk.size
            else:
                silent_samples += chunk.size

            if not speech_started and total_samples >= start_timeout_samples:
                break
            if speech_started and voiced_samples >= min_samples and silent_samples >= silence_samples_needed:
                break

    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    stats = audio_stats(audio)
    stats.update(
        {
            "record_seconds": round(total_samples / max(sample_rate, 1), 2),
            "adaptive": True,
            "speech_started": speech_started,
            "vad_threshold": round(dynamic_threshold, 6),
            "voiced_seconds": round(voiced_samples / max(sample_rate, 1), 2),
            "elapsed": round(time.monotonic() - started_at, 2),
        }
    )
    write_wav(output_path, audio, sample_rate)
    return output_path, stats


_sensevoice_model = None


def _get_sensevoice_model():
    global _sensevoice_model
    if _sensevoice_model is not None:
        return _sensevoice_model
    import torch
    from funasr import AutoModel
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    _sensevoice_model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="fsmn-vad",
        punc_model="ct-punc",
        device=device,
        disable_update=True,
    )
    return _sensevoice_model


def transcribe(wav_path, model_size, model_dir):
    model = _get_sensevoice_model()
    result = model.generate(
        input=str(wav_path),
        cache={},
        language="auto",
        use_itn=True,
        batch_size_s=60,
    )
    if not result:
        return ""
    # result is a list of dicts with 'text' key
    texts = []
    for item in result:
        text = str(item.get("text", "")).strip()
        if text:
            # SenseVoice prepends tags like <|zh|><|NEUTRAL|><|Speech|><|withtn|>
            text = re.sub(r"<\s*\|[^|]*\|\s*>", "", text).strip()
            texts.append(text)
    return "".join(texts)


def extract_text_from_doubao_payload(payload):
    if not isinstance(payload, (dict, list)):
        return ""
    candidates = []

    def text_key(value):
        return re.sub(r"[\s,，。！？?！、~～….\-]+", "", value or "")

    def walk(value, key=""):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                walk(child_value, str(child_key).lower())
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str):
            text = value.strip()
            if text and key in {"text", "utterance", "sentence", "transcript"}:
                candidates.append(text)

    walk(payload)
    unique = []
    seen = set()
    for text in candidates:
        key = text_key(text)
        if key and key not in seen:
            unique.append(text)
            seen.add(key)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0].strip()

    keyed = [(text, text_key(text)) for text in unique]
    full_text, full_key = max(keyed, key=lambda item: len(item[1]))
    if full_key and all(key in full_key for _text, key in keyed if key != full_key):
        return full_text.strip()

    parts = []
    joined_key = ""
    for text, key in keyed:
        if not key or key in joined_key:
            continue
        parts.append(text)
        joined_key += key
    return "".join(parts).strip()


def transcribe_doubao(wav_path, config):
    api_key_env = config.get("doubao_asr_api_key_env") or "DOUBAO_ASR_API_KEY"
    api_key = config.get("doubao_asr_api_key") or os.environ.get(api_key_env, "")
    app_key = config.get("doubao_asr_app_key") or os.environ.get("DOUBAO_ASR_APP_KEY", "")
    access_key = config.get("doubao_asr_access_key") or os.environ.get("DOUBAO_ASR_ACCESS_KEY", "")
    if not api_key and not (app_key and access_key):
        raise RuntimeError("Doubao ASR API key is empty.")

    url = config.get("doubao_asr_url") or DOUBAO_ASR_URL
    resource_id = config.get("doubao_asr_resource_id") or DOUBAO_RESOURCE_ID
    with Path(wav_path).open("rb") as file:
        audio_base64 = base64.b64encode(file.read()).decode("ascii")

    payload = {
        "user": {"uid": "persona_test_all"},
        "audio": {
            "format": "wav",
            "data": audio_base64,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_punc": True,
            "enable_itn": True,
            "enable_ddc": True,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    else:
        headers["X-Api-App-Key"] = app_key
        headers["X-Api-Access-Key"] = access_key

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        status_code = response.headers.get("X-Api-Status-Code", "")
        status_message = response.headers.get("X-Api-Message", "")
    data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    if status_code and status_code not in {"20000000", "0"}:
        raise RuntimeError(f"Doubao ASR failed: {status_code} {status_message}".strip())
    text = extract_text_from_doubao_payload(data)
    if not text:
        raise RuntimeError(f"Doubao ASR returned no text: {data}")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--model-size", default="base")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--asr-provider", default="auto", choices=["auto", "local", "doubao"])
    parser.add_argument("--no-local-fallback", action="store_true")
    parser.add_argument("--adaptive", action="store_true")
    parser.add_argument("--min-seconds", type=float, default=0.55)
    parser.add_argument("--silence-seconds", type=float, default=0.38)
    parser.add_argument("--silence-rms", type=float, default=0.008)
    parser.add_argument("--start-timeout", type=float, default=2.5)
    parser.add_argument("--chunk-ms", type=int, default=40)
    parser.add_argument("--record-only", action="store_true", help="Only record audio, skip transcription")
    args = parser.parse_args()

    try:
        config = load_runtime_config(args.config)
        if args.adaptive:
            wav_path, stats = record_adaptive(
                args.seconds,
                args.sample_rate,
                Path(args.out),
                args.min_seconds,
                args.silence_seconds,
                args.silence_rms,
                args.start_timeout,
                args.chunk_ms,
            )
        else:
            wav_path, stats = record(args.seconds, args.sample_rate, Path(args.out))

        if args.record_only:
            payload = {"ok": True, "text": "", "wav_path": str(wav_path), "audio_stats": stats, "record_only": True}
        else:
            provider = args.asr_provider
            if provider == "auto":
                provider = str(config.get("speech_provider") or "local").lower()
            if provider in ("volcengine", "bytedance"):
                provider = "doubao"

            asr_error = ""
            try:
                if provider == "doubao":
                    text = transcribe_doubao(wav_path, config)
                    used_provider = "doubao"
                else:
                    text = transcribe(wav_path, args.model_size, Path(args.model_dir))
                    used_provider = "local"
            except Exception as exc:
                if provider == "doubao" and not args.no_local_fallback:
                    asr_error = str(exc)
                    text = transcribe(wav_path, args.model_size, Path(args.model_dir))
                    used_provider = "local_fallback"
                else:
                    raise

            stats["asr_provider"] = used_provider
            if asr_error:
                stats["asr_fallback_reason"] = asr_error[:240]
            payload = {"ok": True, "text": text, "wav_path": str(wav_path), "audio_stats": stats}
    except Exception as exc:
        payload = {"ok": False, "text": "", "wav_path": args.out, "error": str(exc)}

    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.flush()
    return 0 if payload.get("ok") else 1


def persistent_mode():
    """Long-running mode: keep model loaded, accept WAV paths via stdin."""
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    model = _get_sensevoice_model()
    # Signal ready
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line or line == "quit":
            break
        try:
            req = json.loads(line)
            wav_path = req.get("wav_path", "")
            if not wav_path:
                raise ValueError("missing wav_path")
            t0 = time.perf_counter()
            result = model.generate(input=wav_path, cache={}, language="auto", use_itn=True, batch_size_s=60)
            elapsed = time.perf_counter() - t0
            texts = []
            for item in result:
                text = str(item.get("text", "")).strip()
                text = re.sub(r"<\s*\|[^|]*\|\s*>", "", text).strip()
                if text:
                    texts.append(text)
            payload = {"ok": True, "text": "".join(texts), "wav_path": wav_path, "audio_stats": {"asr_provider": "sensevoice", "elapsed": round(elapsed, 3)}}
        except Exception as exc:
            payload = {"ok": False, "text": "", "error": str(exc)}
        sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    if "--persistent" in sys.argv:
        persistent_mode()
    else:
        raise SystemExit(main())
