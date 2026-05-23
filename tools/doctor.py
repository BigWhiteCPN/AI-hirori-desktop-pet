"""Preflight checks for first-run setup and cross-machine portability."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persona_pet.llm_config import (  # noqa: E402
    build_default_llm_config,
    load_llm_config_file,
    looks_like_remote_model_id,
    resolve_project_path,
    resolve_tesseract_cmd,
)


REQUIRED_FILES = (
    ROOT / "persona_bot_test.py",
    ROOT / "persona_pet",
    ROOT / "hiyori_pro_zh" / "hiyori_pro_zh" / "runtime" / "hiyori_pro_t11.model3.json",
    ROOT / "assets" / "room" / "background.png",
    ROOT / "assets" / "city_map" / "background.png",
    ROOT / "persona_llm_config.release.json",
)

CORE_MODULES = (
    ("PyQt5", "GUI runtime"),
    ("live2d", "Live2D runtime"),
    ("numpy", "numeric runtime"),
    ("sounddevice", "microphone/audio I/O"),
)

OPTIONAL_MODULES = (
    ("playwright", "browser agent"),
    ("PIL", "OCR image preprocessing"),
    ("pytesseract", "OCR bridge"),
    ("keyring", "credential store"),
    ("sentence_transformers", "dense memory retrieval"),
)

LOCAL_TTS_MODULES = (
    ("torch", "PyTorch for local TTS"),
    ("transformers", "transformers for local TTS"),
    ("huggingface_hub", "model download helper for local TTS"),
    ("faster_qwen3_tts", "faster-qwen3-tts runtime"),
)

LOCAL_ASR_MODULES = (
    ("torch", "PyTorch for local ASR"),
    ("funasr", "FunASR runtime"),
)

OPTIONAL_HINTS = {
    "playwright": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_browser_agent.txt, then run: .\\.venv\\Scripts\\python.exe -m playwright install chromium",
    "PIL": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_ocr.txt",
    "pytesseract": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_ocr.txt",
    "keyring": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_desktop_optional.txt",
    "sentence_transformers": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_memory.txt",
    "huggingface_hub": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_local_tts.txt",
    "faster_qwen3_tts": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_local_tts.txt",
    "funasr": "Install with: .\\.venv\\Scripts\\python.exe -m pip install -r .\\requirements_local_asr.txt",
}


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def print_result(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def collect_config():
    defaults = build_default_llm_config()
    config_path = ROOT / "persona_llm_config.json"
    template_path = ROOT / "persona_llm_config.release.json"
    if config_path.exists():
        config = load_llm_config_file(str(config_path), defaults)
        return config_path, config
    config = load_llm_config_file(str(template_path), defaults)
    return config_path, config


def check_required_files(failures: list[str]) -> None:
    for path in REQUIRED_FILES:
        if path.exists():
            print_result("OK", f"Found {path.relative_to(ROOT)}")
        else:
            failures.append(f"Missing required file: {path.relative_to(ROOT)}")
            print_result("FAIL", f"Missing required file: {path.relative_to(ROOT)}")


def check_python(failures: list[str]) -> None:
    version = sys.version_info
    if version >= (3, 10):
        print_result("OK", f"Python {version.major}.{version.minor}.{version.micro}")
    else:
        failures.append("Python 3.10+ is required")
        print_result("FAIL", f"Python {version.major}.{version.minor}.{version.micro} is too old; need 3.10+")


def check_modules(items, failures: list[str] | None = None, warnings: list[str] | None = None, required: bool = False) -> None:
    for module_name, description in items:
        if module_available(module_name):
            print_result("OK", f"{module_name} available ({description})")
        else:
            message = f"{module_name} missing ({description})"
            hint = OPTIONAL_HINTS.get(module_name, "")
            if required:
                if failures is not None:
                    failures.append(message)
                print_result("FAIL", message)
            else:
                if warnings is not None:
                    warnings.append(message)
                print_result("WARN", message)
                if hint:
                    print_result("INFO", hint)


def describe_path_setting(config: dict, key: str) -> None:
    raw_value = str(config.get(key) or "").strip()
    if not raw_value:
        return
    if key == "qwen_tts_model_path" and looks_like_remote_model_id(raw_value):
        print_result("INFO", f"{key} uses remote model id: {raw_value}")
        return
    resolved = resolve_project_path(str(ROOT), raw_value)
    if os.path.isabs(raw_value):
        try:
            inside_project = os.path.commonpath([str(ROOT), os.path.abspath(resolved)]) == str(ROOT)
        except ValueError:
            inside_project = False
        if inside_project:
            print_result("INFO", f"{key} points inside project: {resolved}")
        else:
            print_result("WARN", f"{key} uses machine-specific absolute path: {resolved}")
    elif resolved != raw_value:
        print_result("INFO", f"{key} resolves relative to project root: {raw_value} -> {resolved}")
    else:
        print_result("INFO", f"{key} kept as-is: {raw_value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether person_test_all is ready to run on this machine.")
    parser.add_argument("--quick", action="store_true", help="Only run core setup checks.")
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    print_result("INFO", f"Project root: {ROOT}")
    check_python(failures)
    check_required_files(failures)

    config_path, config = collect_config()
    if config_path.exists():
        print_result("OK", f"Runtime config found: {config_path.name}")
    else:
        print_result("WARN", "Runtime config not found; setup script can create persona_llm_config.json from the release template")
        warnings.append("Runtime config missing")

    print_result("INFO", "Core dependencies")
    check_modules(CORE_MODULES, failures=failures, required=True)

    tesseract_cmd = resolve_tesseract_cmd(str(ROOT), config.get("tesseract_cmd"))
    if tesseract_cmd and os.path.exists(tesseract_cmd):
        print_result("OK", f"Tesseract detected: {tesseract_cmd}")
    else:
        print_result("WARN", "Tesseract not detected; OCR/chat screenshot advice will stay unavailable until installed")
        warnings.append("Tesseract not detected")

    for key in (
        "qwen_tts_model_path",
        "qwen_tts_ref_dir",
        "qwen_tts_ref_audio",
        "qwen_tts_ref_text",
        "local_llm_models_dir",
        "godot_project_dir",
        "godot_executable",
        "tesseract_cmd",
    ):
        describe_path_setting(config, key)

    if str(config.get("provider") or "").strip().lower() == "ollama":
        print_result("INFO", "Local LLM is enabled in config")
        if shutil.which("ollama") or shutil.which("ollama.exe"):
            print_result("OK", "Ollama executable detected")
        else:
            print_result("WARN", "Ollama executable not detected; install Ollama before using local qwen3:4b-instruct")
            warnings.append("Ollama executable not detected")
    else:
        print_result("INFO", "Local LLM is not enabled in config")

    if not args.quick:
        print_result("INFO", "Optional dependencies")
        check_modules(OPTIONAL_MODULES, warnings=warnings)

        if str(config.get("tts_provider") or "").strip().lower() == "local":
            print_result("INFO", "Local TTS is enabled in config")
            check_modules(LOCAL_TTS_MODULES, warnings=warnings)
        else:
            print_result("INFO", "Local TTS is not enabled in config")

        if str(config.get("speech_provider") or "").strip().lower() == "local":
            print_result("INFO", "Local ASR is enabled in config")
            check_modules(LOCAL_ASR_MODULES, warnings=warnings)
        else:
            print_result("INFO", "Local ASR is not enabled in config")

    if failures:
        print_result("FAIL", f"{len(failures)} blocking issue(s) found")
        return 1

    if warnings:
        print_result("WARN", f"{len(warnings)} non-blocking warning(s) found")
    else:
        print_result("OK", "No warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
