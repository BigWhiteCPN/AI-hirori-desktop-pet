from __future__ import annotations

import math
import time

from live2d.v3.params import StandardParams

from persona_pet.behavior import (
    PARAM_CHEEK,
    PARAM_EYE_L_SMILE,
    PARAM_EYE_R_SMILE,
    PARAM_HAIR_AHOGE,
)
from persona_pet.touch_reaction import touch_zone_family


class TouchVisual:
    def __init__(self):
        self.active = False
        self._blush_only = False
        self.pos = (0.0, 0.0)
        self._norm_pos = (0.5, 0.5)
        self._reaction_name = "calm"
        self._zone = ""
        self._zone_family = ""
        self._reaction_score = 0.0
        self._intensity = 0.45
        self._started_at = 0.0
        self._duration = 0.72

    def _pose_scale(self):
        return min(2.38, 1.16 + self._intensity * 0.84 + max(0.0, self._reaction_score) * 0.07)

    def _detail_scale(self):
        return min(2.0, 1.10 + self._intensity * 0.55 + max(0.0, self._reaction_score) * 0.06)

    def _zone_boost(self):
        if self._zone == "neck":
            return 1.55
        if self._zone == "private":
            return 1.70
        if self._zone == "chest":
            return 1.42
        if self._zone in {"thigh", "calf", "foot"}:
            return 1.30
        if self._zone == "belly":
            return 1.34
        if self._zone in {"arm", "cheek"}:
            return 1.25
        if self._zone in {"hair", "head", "hand"}:
            return 1.08
        return 1.15

    def _duration_for_zone(self):
        if self._zone == "neck":
            return 0.58
        if self._zone == "hair":
            return 0.62
        if self._zone in {"head", "cheek", "hand", "arm"}:
            return 0.66
        if self._zone in {"belly", "calf", "foot"}:
            return 0.72
        if self._zone in {"chest", "thigh", "private"}:
            return 0.78
        return 0.68

    def trigger(self, x, y, reaction_name="calm", zone="", score=0.0, intensity=0.45, norm_pos=None):
        self.active = True
        self._blush_only = False
        self.pos = (float(x), float(y))
        if isinstance(norm_pos, (tuple, list)) and len(norm_pos) >= 2:
            nx = max(0.0, min(1.0, float(norm_pos[0])))
            ny = max(0.0, min(1.0, float(norm_pos[1])))
            self._norm_pos = (nx, ny)
        else:
            self._norm_pos = (0.5, 0.5)
        self._reaction_name = str(reaction_name or "calm")
        self._zone = str(zone or "").lower()
        self._zone_family = touch_zone_family(self._zone)
        self._reaction_score = float(score or 0.0)
        self._intensity = max(0.25, min(1.2, float(intensity or 0.45)))
        self._started_at = time.monotonic()
        self._duration = self._duration_for_zone()

    def trigger_blush(self, zone=""):
        self.active = True
        self._blush_only = True
        self._zone = str(zone or "").lower()
        self._zone_family = touch_zone_family(self._zone)
        self._intensity = 0.8
        self._reaction_score = 0.0
        self._started_at = time.monotonic()
        self._duration = 1.2
        self._norm_pos = (0.5, 0.5)

    def _state(self, now=None):
        now = time.monotonic() if now is None else float(now)
        if not self.active:
            return None
        t = (now - self._started_at) / self._duration
        if t >= 1.0:
            self.active = False
            return None
        fade = max(0.0, 1.0 - t)
        attack = max(0.0, min(1.0, t / 0.12))
        settle = max(0.0, min(1.0, (t - 0.08) / 0.46))
        tail = max(0.0, min(1.0, (t - 0.04) / 0.40))
        recoil = math.sin(attack * math.pi * 0.5) * math.pow(fade, 1.05)
        rebound = math.sin(settle * math.pi) * math.pow(fade, 1.18)
        tremor_gate = math.sin(tail * math.pi * 0.5) * math.pow(fade, 0.72)
        tremor = (
            math.sin((t * 13.2 + 0.13) * math.pi)
            + math.sin((t * 20.5 + 0.57) * math.pi) * 0.36
        ) * 0.46 * tremor_gate
        micro_tremor = (
            math.sin((t * 24.0 + 0.41) * math.pi)
            + math.sin((t * 31.0 + 0.11) * math.pi) * 0.25
        ) * 0.14 * tremor_gate * math.pow(fade, 0.50)
        nx, ny = self._norm_pos
        side = -1.0 if nx < 0.5 else 1.0
        vertical = max(-1.0, min(1.0, (ny - 0.5) * 2.0))
        strength = min(2.35, 1.12 + self._intensity * 0.78 + max(0.0, self._reaction_score) * 0.08)
        shake_x = tremor * 0.50 + micro_tremor * 0.22
        shake_z = -tremor * 0.28 + micro_tremor * 0.36
        influence = min(0.62, 0.16 + abs(recoil) * 0.08 + abs(rebound) * 0.05 + abs(tremor) * 0.12 + abs(micro_tremor) * 0.06)
        return {
            "fade": fade,
            "recoil": recoil,
            "rebound": rebound,
            "tremor": tremor,
            "shake_x": shake_x,
            "shake_z": shake_z,
            "side": side,
            "vertical": vertical,
            "strength": strength,
            "influence": influence,
        }

    def _build_reaction_overlay(self, state):
        fade = state["fade"]
        scale = self._detail_scale() * min(1.45, 0.88 + state["strength"] * 0.28)
        if self._reaction_name == "happy":
            return {
                PARAM_CHEEK: 0.18 * fade * scale,
                PARAM_EYE_L_SMILE: 0.14 * fade * scale,
                PARAM_EYE_R_SMILE: 0.14 * fade * scale,
                StandardParams.ParamMouthForm: 0.12 * fade * scale,
            }
        if self._reaction_name == "annoyed":
            return {
                StandardParams.ParamBrowLForm: 0.22 * fade * scale,
                StandardParams.ParamBrowRForm: 0.22 * fade * scale,
                StandardParams.ParamAngleZ: 0.52 * state["rebound"] * scale,
            }
        if self._reaction_name == "shy":
            return {
                PARAM_CHEEK: 0.22 * fade * scale,
                StandardParams.ParamEyeBallY: -0.12 * fade * scale,
                StandardParams.ParamMouthForm: 0.07 * fade * scale,
            }
        if self._reaction_name == "nervous":
            return {
                StandardParams.ParamEyeLOpen: -0.12 * fade * scale,
                StandardParams.ParamEyeROpen: -0.12 * fade * scale,
                StandardParams.ParamAngleY: 0.48 * state["recoil"] * scale,
            }
        if self._reaction_name == "clingy":
            return {
                PARAM_CHEEK: 0.13 * fade * scale,
                StandardParams.ParamEyeBallX: 0.05 * fade * scale,
            }
        return {}

    def _build_zone_overlay(self, state):
        scale = self._pose_scale() * state["strength"] * self._zone_boost()
        side = state["side"]
        vertical = state["vertical"]
        recoil = state["recoil"] * scale
        rebound = state["rebound"] * scale
        tremor = state["tremor"] * scale
        shake_x = state["shake_x"] * scale * 0.76
        shake_z = state["shake_z"] * scale * 0.78
        overlay = {}
        if self._zone == "hair":
            overlay[PARAM_HAIR_AHOGE] = recoil * 1.35 + abs(shake_z) * 0.72
            overlay[StandardParams.ParamAngleX] = side * shake_x * 0.16
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.10
            overlay[StandardParams.ParamAngleY] = -recoil * 0.10 + rebound * 0.05
        elif self._zone == "head":
            overlay[PARAM_HAIR_AHOGE] = abs(recoil) * 0.35 + abs(shake_z) * 0.20
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.42 - rebound * 0.16) + side * shake_x * 0.10
            overlay[StandardParams.ParamAngleY] = -recoil * 0.12 + rebound * 0.05
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.08
        elif self._zone == "cheek":
            overlay[PARAM_CHEEK] = overlay.get(PARAM_CHEEK, 0.0) + state["fade"] * 0.14 * scale
            overlay[StandardParams.ParamAngleX] = side * shake_x * 0.12
            overlay[StandardParams.ParamAngleZ] = -side * (recoil * 0.58 - rebound * 0.18) + shake_z * 0.12
            overlay[StandardParams.ParamEyeBallX] = -side * recoil * 0.08
            overlay[StandardParams.ParamEyeBallY] = -state["fade"] * 0.07 * scale
        elif self._zone == "neck":
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.82 - rebound * 0.24) + side * shake_x * 0.22
            overlay[StandardParams.ParamAngleY] = recoil * 0.25 + rebound * 0.07
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.24
            overlay[StandardParams.ParamEyeBallX] = -side * recoil * 0.06
            overlay[StandardParams.ParamEyeBallY] = state["fade"] * 0.04 * scale
        elif self._zone == "arm":
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.24 - rebound * 0.10) + side * shake_x * 0.12
        elif self._zone == "hand":
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.12 - rebound * 0.05)
            overlay[StandardParams.ParamEyeBallX] = side * state["fade"] * 0.025 * scale
        elif self._zone == "chest":
            overlay[PARAM_CHEEK] = overlay.get(PARAM_CHEEK, 0.0) + state["fade"] * 0.16 * scale
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.52 - rebound * 0.16) + side * shake_x * 0.12
            overlay[StandardParams.ParamAngleY] = recoil * 0.16 + rebound * 0.05
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.10
            overlay[StandardParams.ParamEyeBallY] = -state["fade"] * 0.05 * scale
        elif self._zone == "belly":
            overlay[PARAM_CHEEK] = overlay.get(PARAM_CHEEK, 0.0) + state["fade"] * 0.10 * scale
            overlay[StandardParams.ParamAngleX] = side * shake_x * 0.05
            overlay[StandardParams.ParamMouthForm] = overlay.get(StandardParams.ParamMouthForm, 0.0) - state["fade"] * 0.025 * scale
        elif self._zone == "private":
            overlay[PARAM_CHEEK] = overlay.get(PARAM_CHEEK, 0.0) + state["fade"] * 0.24 * scale
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.90 - rebound * 0.26) + side * shake_x * 0.24
            overlay[StandardParams.ParamAngleY] = recoil * 0.30 + rebound * 0.08
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.26
            overlay[StandardParams.ParamEyeBallX] = -side * recoil * 0.08
            overlay[StandardParams.ParamEyeBallY] = state["fade"] * 0.05 * scale
            overlay[StandardParams.ParamBrowLForm] = overlay.get(StandardParams.ParamBrowLForm, 0.0) + state["fade"] * 0.08 * scale
            overlay[StandardParams.ParamBrowRForm] = overlay.get(StandardParams.ParamBrowRForm, 0.0) + state["fade"] * 0.08 * scale
        elif self._zone == "thigh":
            overlay[PARAM_CHEEK] = overlay.get(PARAM_CHEEK, 0.0) + state["fade"] * 0.08 * scale
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.34 - rebound * 0.12) + side * shake_x * 0.07
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.06
            overlay[StandardParams.ParamEyeBallY] = (-0.03 + vertical * 0.015) * state["fade"] * scale
        elif self._zone == "calf":
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.14 - rebound * 0.06) + side * shake_x * 0.05
        elif self._zone == "foot":
            overlay[StandardParams.ParamAngleX] = -side * (recoil * 0.16 - rebound * 0.06) + side * shake_x * 0.05
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.06
            overlay[StandardParams.ParamBrowLForm] = overlay.get(StandardParams.ParamBrowLForm, 0.0) + state["fade"] * 0.06 * scale
            overlay[StandardParams.ParamBrowRForm] = overlay.get(StandardParams.ParamBrowRForm, 0.0) + state["fade"] * 0.06 * scale
        elif self._zone_family == "body":
            overlay[StandardParams.ParamAngleX] = side * shake_x * 0.14
            overlay[StandardParams.ParamAngleY] = recoil * 0.16 + rebound * 0.05
            overlay[StandardParams.ParamAngleZ] = shake_z * 0.12
        elif self._zone_family == "leg":
            pass
        return overlay

    def apply_to_params(self, final_params, now=None):
        state = self._state(now=now)
        if not state:
            return final_params
        if getattr(self, "_blush_only", False):
            fade = state["fade"]
            scale = min(2.0, 1.10 + self._intensity * 0.55)
            final_params[PARAM_CHEEK] = final_params.get(PARAM_CHEEK, 0.0) + fade * 0.28 * scale
            return final_params
        overlay = {}
        overlay.update(self._build_reaction_overlay(state))
        for pid, value in self._build_zone_overlay(state).items():
            overlay[pid] = overlay.get(pid, 0.0) + value
        pose_keys = {
            StandardParams.ParamAngleX,
            StandardParams.ParamAngleY,
            StandardParams.ParamAngleZ,
            StandardParams.ParamEyeBallX,
            StandardParams.ParamEyeBallY,
            StandardParams.ParamBrowLForm,
            StandardParams.ParamBrowRForm,
            StandardParams.ParamEyeLOpen,
            StandardParams.ParamEyeROpen,
        }
        influence = state["influence"]
        for pid, value in overlay.items():
            base = final_params.get(pid, 0.0)
            if pid in pose_keys:
                final_params[pid] = base + value * (0.58 + influence * 0.18)
            else:
                final_params[pid] = base + value
        return final_params
