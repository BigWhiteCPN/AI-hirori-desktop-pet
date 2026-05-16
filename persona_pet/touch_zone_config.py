from __future__ import annotations

import json
import os


TOUCH_ZONE_ORDER = [
    ("hair", "头发", "#f39ac7"),
    ("cheek", "脸颊", "#ffb0c8"),
    ("neck", "脖子", "#f7c6a3"),
    ("arm", "胳膊", "#f6d27b"),
    ("chest", "胸部", "#e79898"),
    ("belly", "腹部", "#a8d48f"),
    ("private", "隐私部位", "#c87bd6"),
    ("thigh", "大腿", "#72b9f2"),
    ("calf", "小腿", "#71d5cf"),
    ("foot", "脚", "#8aa3f6"),
]

AUTO_TOUCH_ZONE_TEMPLATE_VERSION = 5


def build_default_touch_zone_config():
    return {
        "version": 1,
        "zones": {key: [] for key, _label, _color in TOUCH_ZONE_ORDER},
    }


def ensure_touch_zone_config(config):
    cfg = dict(config or {})
    if not isinstance(cfg.get("zones"), dict):
        cfg = build_default_touch_zone_config()
    cfg.setdefault("version", 1)
    cfg.setdefault("auto_generated", False)
    cfg.setdefault("template_version", 0)
    zones = cfg.setdefault("zones", {})
    for key, _label, _color in TOUCH_ZONE_ORDER:
        if not isinstance(zones.get(key), list):
            zones[key] = []
    return cfg


def load_touch_zone_config(path):
    if not path or not os.path.exists(path):
        return build_default_touch_zone_config()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return build_default_touch_zone_config()
    return ensure_touch_zone_config(data)


def save_touch_zone_config(path, config):
    cfg = ensure_touch_zone_config(config)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, ensure_ascii=False, indent=2)


def has_touch_zone_rects(config):
    cfg = ensure_touch_zone_config(config)
    zones = cfg.get("zones", {})
    for key, _label, _color in TOUCH_ZONE_ORDER:
        rects = zones.get(key, [])
        if isinstance(rects, list) and rects:
            return True
    return False


def build_auto_touch_zone_config():
    cfg = build_default_touch_zone_config()
    cfg["auto_generated"] = True
    cfg["template_version"] = AUTO_TOUCH_ZONE_TEMPLATE_VERSION
    zones = cfg["zones"]
    # Approximate layout generated from model part semantics:
    # face/neck/arms/body/leg are known; chest, belly, private, thigh/calf/foot
    # are inferred by splitting the body silhouette vertically.
    zones["hair"] = [
        {"x1": 0.23, "y1": 0.01, "x2": 0.77, "y2": 0.17},
    ]
    zones["cheek"] = [
        {"x1": 0.35, "y1": 0.16, "x2": 0.44, "y2": 0.27},
        {"x1": 0.56, "y1": 0.16, "x2": 0.65, "y2": 0.27},
    ]
    zones["neck"] = [
        {"x1": 0.41, "y1": 0.25, "x2": 0.59, "y2": 0.33},
    ]
    zones["arm"] = [
        {"x1": 0.23, "y1": 0.26, "x2": 0.33, "y2": 0.59},
        {"x1": 0.67, "y1": 0.26, "x2": 0.77, "y2": 0.59},
    ]
    zones["chest"] = [
        {"x1": 0.32, "y1": 0.31, "x2": 0.68, "y2": 0.42},
    ]
    zones["belly"] = [
        {"x1": 0.34, "y1": 0.41, "x2": 0.66, "y2": 0.52},
    ]
    zones["private"] = [
        {"x1": 0.43, "y1": 0.52, "x2": 0.57, "y2": 0.60},
    ]
    zones["thigh"] = [
        {"x1": 0.34, "y1": 0.57, "x2": 0.48, "y2": 0.72},
        {"x1": 0.52, "y1": 0.57, "x2": 0.66, "y2": 0.72},
    ]
    zones["calf"] = [
        {"x1": 0.36, "y1": 0.72, "x2": 0.47, "y2": 0.86},
        {"x1": 0.53, "y1": 0.72, "x2": 0.64, "y2": 0.86},
    ]
    zones["foot"] = [
        {"x1": 0.30, "y1": 0.85, "x2": 0.47, "y2": 0.93},
        {"x1": 0.53, "y1": 0.85, "x2": 0.70, "y2": 0.93},
    ]
    return cfg


def touch_zone_color(zone_key):
    for key, _label, color in TOUCH_ZONE_ORDER:
        if key == zone_key:
            return color
    return "#ffffff"


def touch_zone_label(zone_key):
    for key, label, _color in TOUCH_ZONE_ORDER:
        if key == zone_key:
            return label
    return zone_key


def normalize_zone_rect(start_pos, end_pos, width, height):
    width = max(1.0, float(width or 1.0))
    height = max(1.0, float(height or 1.0))
    x1 = max(0.0, min(1.0, min(float(start_pos.x()), float(end_pos.x())) / width))
    x2 = max(0.0, min(1.0, max(float(start_pos.x()), float(end_pos.x())) / width))
    y1 = max(0.0, min(1.0, min(float(start_pos.y()), float(end_pos.y())) / height))
    y2 = max(0.0, min(1.0, max(float(start_pos.y()), float(end_pos.y())) / height))
    return {
        "x1": round(x1, 5),
        "y1": round(y1, 5),
        "x2": round(x2, 5),
        "y2": round(y2, 5),
    }


def rect_from_normalized(rect, width, height):
    width = float(width or 0.0)
    height = float(height or 0.0)
    return (
        float(rect.get("x1", 0.0)) * width,
        float(rect.get("y1", 0.0)) * height,
        max(0.0, float(rect.get("x2", 0.0)) - float(rect.get("x1", 0.0))) * width,
        max(0.0, float(rect.get("y2", 0.0)) - float(rect.get("y1", 0.0))) * height,
    )


def point_in_zone_rect(rect, px, py, width, height):
    nx = float(px or 0.0) / max(1.0, float(width or 1.0))
    ny = float(py or 0.0) / max(1.0, float(height or 1.0))
    return (
        float(rect.get("x1", 0.0)) <= nx <= float(rect.get("x2", 0.0))
        and float(rect.get("y1", 0.0)) <= ny <= float(rect.get("y2", 0.0))
    )


def hit_test_touch_zone(config, px, py, width, height):
    cfg = ensure_touch_zone_config(config)
    zones = cfg.get("zones", {})
    for key, _label, _color in TOUCH_ZONE_ORDER:
        for rect in zones.get(key, []):
            if isinstance(rect, dict) and point_in_zone_rect(rect, px, py, width, height):
                return key
    return ""
