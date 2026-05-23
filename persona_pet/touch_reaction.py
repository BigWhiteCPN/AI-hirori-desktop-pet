from __future__ import annotations


TOUCH_REACTIONS = ("happy", "shy", "annoyed", "clingy", "nervous", "calm")
SENSITIVE_TOUCH_ZONES = {"chest", "private"}
SENSITIVE_TOUCH_ALLOWED_TERMS = (
    "恋人",
    "伴侣",
    "闺蜜",
    "女朋友",
    "男朋友",
    "情侣",
    "对象",
)

ZONE_LABELS = {
    "hair": "头发/头顶",
    "head": "脸",
    "cheek": "脸颊",
    "neck": "脖子",
    "arm": "胳膊",
    "hand": "手/手臂",
    "chest": "胸部",
    "belly": "腹部",
    "body": "身体",
    "private": "隐私部位",
    "thigh": "大腿",
    "calf": "小腿",
    "foot": "脚",
    "leg": "腿部",
}

ZONE_FAMILIES = {
    "hair": "hair",
    "head": "head",
    "cheek": "head",
    "neck": "head",
    "arm": "hand",
    "hand": "hand",
    "chest": "body",
    "belly": "body",
    "body": "body",
    "private": "private",
    "thigh": "leg",
    "calf": "leg",
    "foot": "leg",
    "leg": "leg",
}


def touch_zone_family(zone):
    return ZONE_FAMILIES.get(str(zone or "").strip().lower(), str(zone or "").strip().lower())


def is_sensitive_touch_allowed(stage, relation_score):
    stage_text = str(stage or "")
    if any(term in stage_text for term in SENSITIVE_TOUCH_ALLOWED_TERMS):
        return True
    return float(relation_score or 0.0) >= 130.0


def _pick_top_reaction(scores, allowed=None):
    allowed_names = tuple(allowed or scores.keys())
    best_name = allowed_names[0]
    best_score = float(scores.get(best_name, float("-inf")))
    for name in allowed_names[1:]:
        score = float(scores.get(name, float("-inf")))
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def _resolve_zone_reaction(zone, zone_family, scores, relation_score, trust, fast_poke, intimacy=0.0):
    warm = intimacy >= 0.45
    if zone == "private":
        if warm:
            priority = ("shy", "clingy", "happy", "nervous", "annoyed")
        elif relation_score >= 88 and not fast_poke:
            priority = ("shy", "nervous", "annoyed")
        else:
            priority = ("annoyed", "nervous", "shy")
        return _pick_top_reaction(scores, priority)
    if zone == "neck":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "annoyed"))
        return _pick_top_reaction(scores, ("nervous", "shy", "annoyed", "happy"))
    if zone == "chest":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "calm"))
        return _pick_top_reaction(scores, ("shy", "nervous", "annoyed", "calm"))
    if zone == "belly":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "calm"))
        return _pick_top_reaction(scores, ("shy", "nervous", "happy", "calm", "annoyed"))
    if zone == "thigh":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "annoyed"))
        return _pick_top_reaction(scores, ("shy", "nervous", "annoyed", "happy"))
    if zone in {"calf", "foot"}:
        if warm:
            return _pick_top_reaction(scores, ("shy", "happy", "clingy", "nervous", "calm"))
        return _pick_top_reaction(scores, ("annoyed", "nervous", "shy", "happy", "calm"))
    if zone_family == "body":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "calm"))
        return _pick_top_reaction(scores, ("shy", "nervous", "annoyed", "calm", "happy"))
    if zone_family == "leg":
        if warm:
            return _pick_top_reaction(scores, ("shy", "clingy", "happy", "nervous", "annoyed"))
        return _pick_top_reaction(scores, ("nervous", "annoyed", "shy", "happy", "calm"))
    return max(scores, key=scores.get)


def decide_touch_reaction(emotion_snapshot, drive_snapshot, life_snapshot, personality_snapshot, stimulus, memory_context):
    zone = str(stimulus.meta.get("zone") or stimulus.zone or "head").lower()
    zone_family = touch_zone_family(zone)
    emo = str((emotion_snapshot or {}).get("dominant") or "neutral").lower()
    stage = str((life_snapshot or {}).get("stage") or "朋友")
    relation_score = float((life_snapshot or {}).get("relationship_score", 28.0) or 28.0)
    drive_values = dict((drive_snapshot or {}).get("values") or {})
    affinity = float(drive_values.get("affinity", 42.0) or 42.0)
    attachment = float(drive_values.get("attachment_need", 28.0) or 28.0)
    security = float(drive_values.get("security", 64.0) or 64.0)
    trust = float((personality_snapshot or {}).get("trust", 0.4) or 0.4)
    playfulness = float((personality_snapshot or {}).get("playfulness", 0.6) or 0.6)
    neuroticism = float((personality_snapshot or {}).get("neuroticism", 0.58) or 0.58)
    assertiveness = float((personality_snapshot or {}).get("assertiveness", 0.3) or 0.3)
    recent_count = int(getattr(memory_context, "recent_touch_count", 0) or 0)
    since_last = float(getattr(memory_context, "seconds_since_last_touch", 9999.0) or 9999.0)
    interval = float(stimulus.meta.get("interval", 9.9) or 9.9)
    count = int(stimulus.meta.get("count", 1) or 1)
    fast_poke = count >= 3 and interval < 0.45
    sensitive_blocked = zone in SENSITIVE_TOUCH_ZONES and not is_sensitive_touch_allowed(stage, relation_score)

    scores = {name: 0.0 for name in TOUCH_REACTIONS}

    def add(name, delta):
        scores[name] = scores.get(name, 0.0) + float(delta)

    # --- Continuous intimacy: 0.0 (stranger) → 1.0 (soulmate) ---
    # Computed early so zone scoring can use it.
    r = max(0.0, min(1.0, (relation_score - 30.0) / 220.0))
    t = max(0.0, min(1.0, (trust - 0.25) / 0.55))
    a = max(0.0, min(1.0, (affinity - 30.0) / 70.0))
    at = max(0.0, min(1.0, (attachment - 20.0) / 60.0))
    intimacy = min(1.0, r * 0.45 + t * 0.30 + a * 0.15 + at * 0.10)

    if emo == "joy":
        add("happy", 2.8)
        add("shy", 0.8)
    elif emo == "sadness":
        add("clingy", 2.5)
        add("shy", 0.8)
    elif emo == "anger":
        add("annoyed", 3.0)
    elif emo == "fear":
        add("nervous", 3.0)
    else:
        add("calm", 1.6)

    if stage in ("朋友", "普通朋友"):
        add("nervous", 1.4)
        add("happy", -0.7)
    elif stage in ("亲近朋友", "熟悉朋友", "好朋友"):
        add("calm", 1.0)
        add("shy", 1.0)
    elif stage in ("密友", "深度朋友", "闺蜜"):
        add("happy", 1.5)
        add("shy", 1.0)
    else:
        add("happy", 1.8)
        add("clingy", 1.6)
        add("annoyed", -0.8)

    if attachment > 60:
        add("clingy", 1.8)
    if security < 45:
        add("nervous", 1.5)
    if trust > 0.68:
        add("happy", 1.0)
    if neuroticism > 0.7:
        add("shy", 0.8)
        add("nervous", 0.8)
    if assertiveness > 0.55:
        add("annoyed", 0.8)
    if playfulness > 0.75 and relation_score >= 65:
        add("happy", 0.8)

    if zone_family == "hair":
        add("happy", 1.6)
        add("shy", 0.8)
        if relation_score < 35:
            add("nervous", 1.2)
    elif zone_family == "head":
        add("shy", 0.9)
        if relation_score < 35:
            add("nervous", 1.5)
        if zone == "cheek":
            add("shy", 0.5)
        if zone == "neck":
            add("nervous", 0.5)
            add("annoyed", 0.3)
    elif zone_family == "body":
        zone_dampen = max(0.0, 1.0 - intimacy * 1.2)
        add("nervous", 1.8 * zone_dampen)
        add("annoyed", 1.0 * zone_dampen)
        if relation_score >= 88:
            add("shy", 1.2 + 0.8 * intimacy)
            add("happy", 0.2 + 0.6 * intimacy)
        else:
            add("happy", -0.9 * zone_dampen)
        if zone == "chest":
            add("nervous", 1.0 * zone_dampen)
            add("annoyed", 0.6 * zone_dampen)
            add("shy", 0.6 + 1.0 * intimacy)
            add("happy", -1.3 * zone_dampen)
        if zone == "belly":
            add("shy", 0.9 + 0.6 * intimacy)
            add("happy", -0.4 * zone_dampen)
    elif zone_family == "private":
        zone_dampen = max(0.0, 1.0 - intimacy * 1.3)
        add("nervous", 4.2 * zone_dampen)
        add("annoyed", 3.0 * zone_dampen)
        add("shy", 1.6 + 2.0 * intimacy)
        add("happy", -5.0 * zone_dampen)
        add("clingy", -2.4 * zone_dampen + 2.0 * intimacy)
        add("calm", -1.6 * zone_dampen)
        if relation_score >= 88:
            add("shy", 1.2 * intimacy)
            add("annoyed", -0.5 * intimacy)
    elif zone_family == "leg":
        zone_dampen = max(0.0, 1.0 - intimacy * 1.2)
        add("nervous", 1.6 * zone_dampen)
        add("annoyed", 0.8 * zone_dampen)
        add("shy", 0.6 + 0.6 * intimacy)
        if relation_score >= 88:
            add("shy", 0.8 + 0.5 * intimacy)
            add("happy", 0.1 + 0.4 * intimacy)
        else:
            add("happy", -1.0 * zone_dampen)
        if zone == "foot":
            add("annoyed", 1.0 * zone_dampen)
            add("nervous", 0.4 * zone_dampen)
            add("happy", -0.8 * zone_dampen)
        if zone == "thigh":
            add("nervous", 1.0 * zone_dampen)
            add("shy", 0.8 + 0.8 * intimacy)
            add("happy", -0.8 * zone_dampen)
        if zone == "calf":
            add("annoyed", 0.5 * zone_dampen)
            add("nervous", 0.5 * zone_dampen)
            add("shy", 0.2 + 0.4 * intimacy)
    elif zone_family == "hand":
        add("calm", 1.0)
        add("happy", 0.6)

    if relation_score < 35 and zone_family in {"body", "leg", "private"}:
        add("nervous", 2.0)
        add("annoyed", 1.0)
    if relation_score >= 88 and zone_family == "hair":
        add("happy", 1.8)
        add("clingy", 0.9)

    # Negative emotion suppression: higher intimacy → fear/anger matter less
    if emo == "fear":
        shift = 3.0 * intimacy
        add("nervous", -shift)
        add("clingy", shift * 0.9)
        add("shy", shift * 0.25)
    elif emo == "anger":
        shift = 2.4 * intimacy
        add("annoyed", -shift)
        add("clingy", shift * 0.65)
        add("shy", shift * 0.2)
    elif emo == "sadness":
        add("clingy", 1.6 * intimacy)

    # Frequency penalties: higher intimacy → more tolerant
    if fast_poke:
        penalty_scale = max(0.0, 1.0 - intimacy * 1.2)
        add("annoyed", 3.4 * penalty_scale - 1.6 * intimacy)
        add("happy", -2.0 * penalty_scale + 1.6 * intimacy)
        add("calm", -0.5 * penalty_scale)
        add("clingy", 2.2 * intimacy)
    if recent_count >= 5:
        penalty_scale = max(0.0, 1.0 - intimacy * 1.1)
        add("annoyed", 1.6 * penalty_scale - 0.8 * intimacy)
        add("clingy", 1.6 * intimacy)
        add("happy", 0.6 * intimacy)

    # Touch welcome bonus: scales with intimacy and zone
    zone_bonus = {
        "hair": (1.4, 1.0, 0.4), "head": (1.2, 0.8, 0.4), "hand": (1.0, 0.8, 0.3),
        "body": (0.8, 0.6, 0.4), "leg": (0.6, 0.4, 0.3),
    }
    h_bonus, c_bonus, s_bonus = zone_bonus.get(zone_family, (0.6, 0.4, 0.3))
    if zone_family == "body" and relation_score < 88:
        h_bonus *= 0.3
        c_bonus *= 0.3
    if zone_family == "leg" and relation_score < 88:
        h_bonus *= 0.3
    add("happy", h_bonus * intimacy)
    add("clingy", c_bonus * intimacy)
    add("shy", s_bonus * intimacy)

    if since_last > 3600 and relation_score >= 65:
        add("clingy", 1.5)

    if sensitive_blocked:
        if zone == "private":
            add("annoyed", 6.0)
            add("nervous", 3.6)
            add("happy", -8.0)
            add("clingy", -5.0)
            add("shy", -2.5)
            add("calm", -2.4)
        else:
            add("annoyed", 4.8)
            add("nervous", 3.0)
            add("happy", -5.0)
            add("clingy", -3.5)
            add("shy", -2.0)
            add("calm", -2.0)

    if sensitive_blocked:
        winner = "annoyed"
    else:
        winner = _resolve_zone_reaction(zone, zone_family, scores, relation_score, trust, fast_poke, intimacy=intimacy)
    prompt_directions = {
        "happy": "你现在有点开心，回复自然、轻快，不要太长。",
        "shy": "你现在有点害羞，回复轻一点，可以带点收着的亲近感。",
        "annoyed": "你现在有点不高兴，回复要克制地表达不满，不要太凶。",
        "clingy": "你现在有点黏人，回复里可以带一点想被陪着的感觉。",
        "nervous": "你现在有点紧张，回复要短，带一点不太自在。",
        "calm": "你现在比较平静，随口回应一句就够。",
    }
    emotion_map = {
        "happy": "joy",
        "shy": "joy",
        "annoyed": "anger",
        "clingy": "joy",
        "nervous": "fear",
        "calm": "neutral",
    }
    result = {
        "name": winner,
        "emotion_tag": emotion_map[winner],
        "prompt_direction": prompt_directions[winner],
        "score": round(scores.get(winner, 0.0), 3),
        "scores": {key: round(value, 3) for key, value in scores.items()},
        "sensitive_touch_blocked": bool(sensitive_blocked),
    }
    print("TOUCH_REACTION =", {
        "zone": zone, "emo": emo, "winner": winner,
        "intimacy": round(intimacy, 3),
        "trust": round(trust, 3), "relation": round(relation_score, 1),
        "sensitive_blocked": bool(sensitive_blocked),
        "scores": result["scores"],
    })
    return result
