"""Runtime profile selection and path helpers."""

import os
import re


PROFILE_ENV_KEYS = ("PERSONA_RUN_PROFILE", "PERSONA_PROFILE")
RESET_ENV_KEYS = ("PERSONA_RESET_PROFILE", "PERSONA_RESET_PROFILE_ON_START")
PROFILE_FLAGS = ("--profile", "--run-profile", "--persona-profile")
RESET_FLAGS = ("--reset-profile", "--reset-profile-on-start")
NO_RESET_FLAGS = ("--no-reset-profile", "--no-reset-profile-on-start")


def env_truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def sanitize_profile_name(profile, default="main"):
    value = str(profile or default or "main").strip()
    if not value:
        value = str(default or "main").strip() or "main"
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip(" ._")
    if not value or value in (".", ".."):
        value = "main"
    if value.lower() == "main":
        return "main"
    return value[:48]


def select_runtime_profile(default_profile="main", default_reset=False, argv=None, env=None):
    env = os.environ if env is None else env
    args = list(argv or [])
    profile = default_profile
    reset = bool(default_reset)
    source = "default"

    for key in PROFILE_ENV_KEYS:
        if env.get(key):
            profile = env.get(key)
            source = f"env:{key}"
            break
    for key in RESET_ENV_KEYS:
        if env.get(key):
            reset = env_truthy(env.get(key))

    remaining = []
    index = 0
    while index < len(args):
        arg = str(args[index])
        matched = False
        for flag in PROFILE_FLAGS:
            if arg == flag:
                if index + 1 < len(args):
                    profile = args[index + 1]
                    source = f"cli:{flag}"
                    index += 2
                    matched = True
                break
            if arg.startswith(flag + "="):
                profile = arg.split("=", 1)[1]
                source = f"cli:{flag}"
                index += 1
                matched = True
                break
        if matched:
            continue
        if arg in RESET_FLAGS:
            reset = True
            index += 1
            continue
        if arg in NO_RESET_FLAGS:
            reset = False
            index += 1
            continue
        remaining.append(arg)
        index += 1

    profile = sanitize_profile_name(profile, default=default_profile)
    if profile == "main":
        reset = False
    return {
        "profile": profile,
        "reset": reset,
        "source": source,
        "argv": remaining,
    }


def apply_runtime_profile(default_profile="main", default_reset=False, argv=None, env=None):
    selection = select_runtime_profile(default_profile=default_profile, default_reset=default_reset, argv=argv, env=env)
    if argv is not None:
        argv[:] = selection["argv"]
    return selection


def profile_output_dir(base_dir, profile, *parts):
    profile = sanitize_profile_name(profile)
    if profile == "main":
        return os.path.join(base_dir, "outputs", *parts)
    return os.path.join(base_dir, "outputs", "profiles", profile, *parts)


def profile_config_path(base_dir, profile):
    profile = sanitize_profile_name(profile)
    if profile == "main":
        return os.path.join(base_dir, "persona_llm_config.json")
    return os.path.join(base_dir, f"persona_llm_config.{profile}.json")

