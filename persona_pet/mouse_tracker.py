from __future__ import annotations

import math
import time


class MouseTracker:
    def __init__(self, gaze_radius_px=500, stare_threshold_sec=3.0, movement_threshold_px=5.0):
        self.gaze_radius_px = float(gaze_radius_px)
        self.stare_threshold_sec = float(stare_threshold_sec)
        self.movement_threshold_px = float(movement_threshold_px)
        self.range_feather_px = max(48.0, min(160.0, self.gaze_radius_px * 0.26))
        self.deadzone = 0.035
        self._cursor_abs = None
        self._relative = (0.0, 0.0)
        self._smoothed = (0.0, 0.0)
        self._in_range = False
        self._stare_start = 0.0
        self._stare_notified = False
        self._last_update_at = 0.0
        self._focus_strength = 0.0
        self._entry_warmup = 0.0  # 0-1 ramp for first-time entry into gaze range

    def update(self, cursor_global_x, cursor_global_y, window_x, window_y, window_w, window_h):
        prev = self._cursor_abs
        new_pos = (float(cursor_global_x), float(cursor_global_y))
        cx = float(window_x) + float(window_w) / 2.0
        cy = float(window_y) + float(window_h) / 2.0
        dx = new_pos[0] - cx
        dy = new_pos[1] - cy
        dist = math.hypot(dx, dy)
        rx = max(-1.0, min(1.0, dx / max(1.0, self.gaze_radius_px)))
        ry = max(-1.0, min(1.0, dy / max(1.0, self.gaze_radius_px)))
        now = time.monotonic()
        dt = 1.0 / 60.0 if self._last_update_at <= 0.0 else max(1.0 / 240.0, min(0.15, now - self._last_update_at))
        self._last_update_at = now
        self._relative = (self._apply_deadzone(rx), self._apply_deadzone(ry))
        target_focus = self._distance_focus(dist)
        focus_active = target_focus > 0.02
        self._in_range = target_focus >= 0.28

        # Entry warmup: when focus was near-zero and target is now active,
        # ramp up a warmup gate over ~0.35s so the eyes glide in instead of snapping.
        was_idle = self._focus_strength < 0.05
        if focus_active and was_idle and self._entry_warmup < 1.0:
            self._entry_warmup = min(1.0, self._entry_warmup + dt * 2.8)
        elif not focus_active:
            self._entry_warmup = 0.0
        else:
            self._entry_warmup = min(1.0, self._entry_warmup + dt * 5.0)

        # Use the slower of the natural focus ramp and the entry warmup gate
        effective_focus = target_focus * self._entry_warmup

        focus_alpha = min(1.0, dt * (5.0 if target_focus > self._focus_strength else 4.8))
        self._focus_strength += (effective_focus - self._focus_strength) * focus_alpha

        # Position smoothing: slow down during entry warmup to let focus build first
        entry_slow = 1.0 if self._entry_warmup >= 0.9 else self._entry_warmup
        smooth_alpha = min(1.0, dt * (8.5 if target_focus > self._focus_strength else 5.8) * entry_slow)
        sx, sy = self._smoothed
        tx, ty = self._relative
        tx *= effective_focus
        ty *= effective_focus
        self._smoothed = (
            sx + (tx - sx) * smooth_alpha,
            sy + (ty - sy) * smooth_alpha,
        )

        move_dist = 9999.0
        if prev is not None:
            move_dist = math.hypot(new_pos[0] - prev[0], new_pos[1] - prev[1])
        self._cursor_abs = new_pos

        if not focus_active:
            self._stare_start = 0.0
            self._stare_notified = False
            return
        if move_dist > self.movement_threshold_px:
            self._stare_start = now
            self._stare_notified = False
            return
        if self._stare_start <= 0.0:
            self._stare_start = now

    def consume_stare_event(self):
        if not self._in_range or self._stare_notified or self._stare_start <= 0.0:
            return None
        duration = time.monotonic() - self._stare_start
        if duration < self.stare_threshold_sec:
            return None
        self._stare_notified = True
        return duration

    @property
    def relative_x(self):
        return float(self._relative[0])

    @property
    def relative_y(self):
        return float(self._relative[1])

    @property
    def smoothed_x(self):
        return float(self._smoothed[0])

    @property
    def smoothed_y(self):
        return float(self._smoothed[1])

    @property
    def in_range(self):
        return bool(self._in_range)

    @property
    def focus_strength(self):
        return float(max(0.0, min(1.0, self._focus_strength)))

    def get_gaze_blend(self, emotion_eye_x, emotion_eye_y, blend=0.7):
        if self._focus_strength <= 0.001:
            return emotion_eye_x, emotion_eye_y
        blend = max(0.0, min(1.0, float(blend)))
        mx, my = self._smoothed
        blend *= self.focus_strength
        return (
            emotion_eye_x * (1.0 - blend) + mx * blend,
            emotion_eye_y * (1.0 - blend) + (-my) * blend,
        )

    def _apply_deadzone(self, value):
        sign = -1.0 if value < 0.0 else 1.0
        magnitude = abs(float(value))
        if magnitude <= self.deadzone:
            return 0.0
        remapped = (magnitude - self.deadzone) / max(0.001, 1.0 - self.deadzone)
        remapped = min(1.0, max(0.0, remapped))
        remapped = remapped * remapped * (3.0 - 2.0 * remapped)
        remapped = math.pow(remapped, 0.82)
        return sign * remapped

    def _distance_focus(self, dist):
        dist = max(0.0, float(dist))
        outer = self.gaze_radius_px + self.range_feather_px
        inner = max(1.0, self.gaze_radius_px - self.range_feather_px * 0.45)
        if dist <= inner:
            return 1.0
        if dist >= outer:
            return 0.0
        t = (outer - dist) / max(1.0, outer - inner)
        t = min(1.0, max(0.0, t))
        return t * t * (3.0 - 2.0 * t)
