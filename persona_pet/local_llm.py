"""Local LLM helpers for Ollama-backed chat."""

import json
import os
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urlparse

from persona_pet.llm_config import (
    DEFAULT_LOCAL_LLM_BASE_URL,
    DEFAULT_LOCAL_LLM_MODEL,
    DEFAULT_LOCAL_LLM_MODELS_DIR,
    normalize_local_llm_model_name,
    resolve_project_path,
)

_OLLAMA_PROCESS = None


def is_local_llm_config(config):
    return str((config or {}).get("provider") or "").strip().lower() == "ollama"


def normalize_local_llm_config(config):
    data = dict(config or {})
    model = normalize_local_llm_model_name(data.get("local_llm_model") or data.get("model"))
    base_url = str(data.get("local_llm_base_url") or DEFAULT_LOCAL_LLM_BASE_URL).strip() or DEFAULT_LOCAL_LLM_BASE_URL
    models_dir = str(data.get("local_llm_models_dir") or DEFAULT_LOCAL_LLM_MODELS_DIR).strip() or DEFAULT_LOCAL_LLM_MODELS_DIR
    data.update(
        {
            "provider": "ollama",
            "model": model,
            "fast_model": model,
            "reasoning_model": model,
            "base_url": base_url,
            "local_llm_provider": "ollama",
            "local_llm_model": model,
            "local_llm_base_url": base_url,
            "local_llm_models_dir": models_dir,
        }
    )
    if "local_llm_auto_pull" not in data:
        data["local_llm_auto_pull"] = True
    if "local_llm_context_tokens" not in data:
        data["local_llm_context_tokens"] = 8192
    return data


def resolve_local_models_dir(base_dir, config):
    raw = str((config or {}).get("local_llm_models_dir") or DEFAULT_LOCAL_LLM_MODELS_DIR).strip()
    return resolve_project_path(base_dir, raw)


def apply_local_llm_environment(base_dir, config):
    if not is_local_llm_config(config):
        return ""
    models_dir = resolve_local_models_dir(base_dir, config)
    if models_dir:
        os.makedirs(models_dir, exist_ok=True)
        os.environ["OLLAMA_MODELS"] = models_dir
    return models_dir


def ollama_host_from_base_url(base_url):
    parsed = urlparse(str(base_url or DEFAULT_LOCAL_LLM_BASE_URL))
    return parsed.netloc or parsed.path or "127.0.0.1:11435"


def ollama_executable():
    return shutil.which("ollama") or shutil.which("ollama.exe")


def ollama_tags(base_url, timeout=2.0):
    url = str(base_url or DEFAULT_LOCAL_LLM_BASE_URL).rstrip("/") + "/api/tags"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def ollama_is_running(base_url):
    try:
        ollama_tags(base_url, timeout=1.5)
        return True
    except Exception:
        return False


def start_ollama_server(base_dir, config):
    global _OLLAMA_PROCESS
    base_url = str((config or {}).get("base_url") or DEFAULT_LOCAL_LLM_BASE_URL).rstrip("/")
    if ollama_is_running(base_url):
        return True
    exe = ollama_executable()
    if not exe:
        return False
    env = os.environ.copy()
    models_dir = apply_local_llm_environment(base_dir, config)
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir
    env["OLLAMA_HOST"] = ollama_host_from_base_url(base_url)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        _OLLAMA_PROCESS = subprocess.Popen(
            [exe, "serve"],
            cwd=base_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:
        return False
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if ollama_is_running(base_url):
            return True
        if _OLLAMA_PROCESS.poll() is not None:
            return False
        time.sleep(0.35)
    return ollama_is_running(base_url)


def ollama_model_installed(base_url, model):
    wanted = str(model or DEFAULT_LOCAL_LLM_MODEL).strip()
    try:
        tags = ollama_tags(base_url, timeout=3.0)
    except Exception:
        return False
    for item in tags.get("models") or []:
        name = str(item.get("name") or item.get("model") or "").strip()
        if name == wanted:
            return True
        if ":" not in wanted and name.split(":", 1)[0] == wanted:
            return True
    return False


def pull_ollama_model(base_dir, config, progress_callback=None):
    model = str((config or {}).get("model") or (config or {}).get("local_llm_model") or DEFAULT_LOCAL_LLM_MODEL).strip() or DEFAULT_LOCAL_LLM_MODEL
    base_url = str((config or {}).get("base_url") or (config or {}).get("local_llm_base_url") or DEFAULT_LOCAL_LLM_BASE_URL).rstrip("/")
    apply_local_llm_environment(base_dir, config)
    payload = json.dumps({"name": model, "stream": True}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_status = ""
    with urllib.request.urlopen(request, timeout=3600) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                item = {"status": line}
            if item.get("error"):
                raise RuntimeError(str(item.get("error")))
            status = str(item.get("status") or "").strip()
            if status:
                last_status = status
            if progress_callback is not None:
                total = item.get("total")
                completed = item.get("completed")
                if total and completed:
                    progress_callback(f"{status} {int(completed)}/{int(total)}")
                else:
                    progress_callback(status)
    if last_status and last_status not in ("success", "verifying sha256 digest", "writing manifest", "removing any unused layers"):
        progress_callback(last_status) if progress_callback is not None else None
    return True
