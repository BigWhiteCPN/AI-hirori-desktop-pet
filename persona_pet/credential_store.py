"""Optional OS credential-store support for sensitive config values."""

from persona_pet.error_reporter import report_exception

SECRET_CONFIG_KEYS = (
    "api_key",
    "doubao_asr_api_key",
    "doubao_asr_app_key",
    "doubao_asr_access_key",
    "volcengine_tts_api_key",
    "volcengine_tts_token",
)

DEFAULT_CREDENTIAL_SERVICE = "persona_pet"


def _load_keyring(runtime=None, logger=None):
    try:
        import keyring  # type: ignore

        return keyring
    except Exception as exc:
        report_exception(runtime, logger, "credential_store", "load_keyring", exc, level="info")
        return None


def credential_username(profile, key):
    profile = str(profile or "main").strip() or "main"
    key = str(key or "").strip()
    return f"{profile}:{key}"


def _credential_meta(config):
    meta = config.get("credential_store")
    if not isinstance(meta, dict):
        meta = {}
    refs = meta.get("refs")
    if not isinstance(refs, dict):
        refs = {}
    return {
        "enabled": bool(meta.get("enabled", config.get("credential_store_enabled", True))),
        "service": str(meta.get("service") or config.get("credential_store_service") or DEFAULT_CREDENTIAL_SERVICE),
        "refs": dict(refs),
    }


def externalize_config_secrets(config, profile="main", backend=None, runtime=None, logger=None):
    data = dict(config or {})
    meta = _credential_meta(data)
    if not meta["enabled"]:
        data["credential_store"] = meta
        return data
    backend = backend if backend is not None else _load_keyring(runtime=runtime, logger=logger)
    if backend is None:
        data["credential_store"] = meta
        return data

    refs = dict(meta.get("refs") or {})
    for key in SECRET_CONFIG_KEYS:
        secret = str(data.get(key) or "")
        if not secret:
            refs.pop(key, None)
            continue
        username = refs.get(key) or credential_username(profile, key)
        try:
            backend.set_password(meta["service"], username, secret)
        except Exception as exc:
            report_exception(runtime, logger, "credential_store", "set_password", exc, key=key, service=meta["service"])
            continue
        refs[key] = username
        data[key] = ""
    meta["refs"] = refs
    data["credential_store"] = meta
    data["credential_store_enabled"] = True
    data["credential_store_service"] = meta["service"]
    return data


def hydrate_config_secrets(config, profile="main", backend=None, runtime=None, logger=None):
    data = dict(config or {})
    meta = _credential_meta(data)
    if not meta["enabled"]:
        return data
    backend = backend if backend is not None else _load_keyring(runtime=runtime, logger=logger)
    if backend is None:
        return data

    refs = dict(meta.get("refs") or {})
    for key in SECRET_CONFIG_KEYS:
        if data.get(key):
            continue
        username = refs.get(key) or credential_username(profile, key)
        try:
            secret = backend.get_password(meta["service"], username)
        except Exception as exc:
            report_exception(runtime, logger, "credential_store", "get_password", exc, key=key, service=meta["service"])
            secret = ""
        if secret:
            data[key] = secret
            refs[key] = username
    meta["refs"] = refs
    data["credential_store"] = meta
    return data


def profile_from_config_path(path):
    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1]
    if name == "persona_llm_config.json":
        return "main"
    prefix = "persona_llm_config."
    suffix = ".json"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)] or "main"
    return "main"
