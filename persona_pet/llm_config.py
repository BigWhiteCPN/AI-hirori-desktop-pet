"""LLM and speech service configuration helpers."""

import json
import os

from persona_pet.prompts import PROSODY_PROMPT_CONTRACT


def build_default_llm_config(
    volcengine_tts_url="https://openspeech.bytedance.com/api/v1/tts",
    volcengine_tts_cluster="volcano_icl",
    volcengine_tts_voice_type="S_zEdGPhR02",
    volcengine_tts_format="wav",
    volcengine_tts_rate=24000,
    singing_enabled=True,
    singing_external_command="",
    singing_max_text_chars=72,
):
    return {
        "provider": "openai_compatible",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.75,
        "max_history_turns": 6,
        "speech_provider": "doubao",
        "doubao_asr_api_key": "",
        "doubao_asr_api_key_env": "DOUBAO_ASR_API_KEY",
        "doubao_asr_app_key": "",
        "doubao_asr_access_key": "",
        "doubao_asr_resource_id": "volc.bigasr.auc_turbo",
        "doubao_asr_url": "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
        "tts_provider": "volcengine",
        "volcengine_tts_url": volcengine_tts_url,
        "volcengine_tts_appid": "",
        "volcengine_tts_api_key": "",
        "volcengine_tts_token": "",
        "volcengine_tts_token_env": "VOLCENGINE_TTS_API_KEY",
        "volcengine_tts_cluster": volcengine_tts_cluster,
        "volcengine_tts_voice_type": volcengine_tts_voice_type,
        "volcengine_tts_format": volcengine_tts_format,
        "volcengine_tts_rate": volcengine_tts_rate,
        "volcengine_tts_speed_ratio": 1.0,
        "volcengine_tts_volume_ratio": 1.0,
        "volcengine_tts_pitch_ratio": 1.0,
        "ocr_provider": "tesseract",
        "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        "tesseract_lang": "chi_sim+eng",
        "singing_enabled": singing_enabled,
        "singing_provider": "volcengine_tts",
        "singing_external_command": singing_external_command,
        "singing_max_text_chars": singing_max_text_chars,
        "system_prompt": (
            "你是一个可爱、活泼、亲近用户的二次元桌宠角色。"
            + PROSODY_PROMPT_CONTRACT +
            "不要解释自己是AI，不要写舞台说明。"
            "日常聊天要像真人即时回应，不要形成固定口癖；"
            "除非用户主动问创作或你确实刚完成写作，不要提小说、作家、写进故事、写进书里。"
        ),
    }


def load_llm_config_file(path, defaults):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as file:
            json.dump(defaults, file, ensure_ascii=False, indent=2)
        return dict(defaults)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        config = dict(defaults)
        config.update(data if isinstance(data, dict) else {})
        return config
    except Exception:
        return dict(defaults)


def save_llm_config_file(path, defaults, config):
    data = dict(defaults)
    data.update(config or {})
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(tmp_path, path)
