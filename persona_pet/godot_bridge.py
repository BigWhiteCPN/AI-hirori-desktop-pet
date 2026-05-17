"""Bridge the desktop persona runtime with the external Godot room game."""

import datetime
import json
import os
import subprocess
import time

from PyQt5.QtCore import QTimer

from persona_pet.error_reporter import report_exception
from persona_pet.llm_config import resolve_project_path


DEFAULT_GODOT_PROJECT_DIR = ""
DEFAULT_GODOT_EXE = ""
DEFAULT_HOME_ICON_IDLE_SECONDS = 600.0


class GodotBridgeMixin:
    def setup_godot_bridge(self):
        base_dir = getattr(self, "base_dir", os.getcwd())
        bridge_dir = getattr(self, "godot_bridge_dir", "") or os.path.join(base_dir, "outputs", "godot_bridge")
        os.makedirs(bridge_dir, exist_ok=True)
        self.godot_project_dir = resolve_project_path(base_dir, self.llm_config.get("godot_project_dir") or DEFAULT_GODOT_PROJECT_DIR)
        self.godot_executable = resolve_project_path(base_dir, self.llm_config.get("godot_executable") or DEFAULT_GODOT_EXE)
        self.godot_bridge_path = os.path.join(bridge_dir, "persona_to_game.json")
        self.godot_state_path = os.path.join(bridge_dir, "game_to_persona.json")
        self.godot_process = None
        self.godot_game_active = False
        self.godot_last_write_at = 0.0
        self.godot_last_state_mtime = 0.0
        self.godot_room_state = {}
        self.godot_last_event_id = ""
        self.godot_desired_activity = ""
        self.godot_activity_revision = 0
        self.home_icon_mode = False
        self.home_icon_idle_seconds = float(self.llm_config.get("home_icon_idle_seconds", DEFAULT_HOME_ICON_IDLE_SECONDS) or DEFAULT_HOME_ICON_IDLE_SECONDS)
        self.home_icon_path = str(
            resolve_project_path(base_dir, self.llm_config.get("home_icon_path"))
            or os.path.join(base_dir, "assets", "room_icon", "star_room_icon_256.png")
        )
        self.home_icon_previous_size = None
        self.home_icon_rect = None
        self.godot_bridge_timer = QTimer(self)
        self.godot_bridge_timer.timeout.connect(self.tick_godot_bridge)
        self.godot_bridge_timer.start(250)

    def resolve_godot_executable(self):
        configured = str(getattr(self, "godot_executable", "") or "").strip()
        candidates = [configured, DEFAULT_GODOT_EXE]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                for name in os.listdir(candidate):
                    path = os.path.join(candidate, name)
                    if name.lower().endswith(".exe") and os.path.isfile(path):
                        return path
        return configured

    def toggle_room_mode(self):
        if self.godot_game_active:
            self.stop_godot_room_game(show_main=True)
        elif self.home_icon_mode:
            self.start_godot_room_game()
        else:
            self.enter_home_icon_mode(reason="manual")

    def enter_home_icon_mode(self, reason="idle"):
        if self.home_icon_mode or self.godot_game_active:
            return False
        if self.voice.is_busy_or_playing() or self.behavior.is_speaking() or self.chat.is_busy():
            return False
        self.home_icon_mode = True
        self.room_mode = False
        self.dialogue_active = False
        self.home_icon_previous_size = (self.width(), self.height())
        self.resize(320, 360)
        self.layout_chat_input()
        self.show()
        self.raise_()
        self.show_chat_status("苏念回到自己的小屋了。", seconds=3.0)
        self.write_godot_bridge(force=True)
        print("HOME_ICON_ENTER =", {"reason": reason})
        return True

    def exit_home_icon_mode(self, reason="summon", speak=False):
        was_home = bool(self.home_icon_mode)
        self.home_icon_mode = False
        if self.godot_game_active:
            self.stop_godot_room_game(show_main=False)
        width, height = self.home_icon_previous_size or (getattr(self, "default_window_width", 420), getattr(self, "default_window_height", 700))
        self.resize(width, height)
        self.layout_chat_input()
        self.show()
        self.raise_()
        self.activateWindow()
        self.write_godot_bridge(force=True, mode="closed")
        if was_home:
            print("HOME_ICON_EXIT =", {"reason": reason})
        if speak:
            QTimer.singleShot(250, lambda: self.speak_interaction_feedback("嗯？你叫我呀。怎么啦？", emotion="surprise"))
        return was_home

    def summon_from_home(self, reason="summon", speak=True):
        self.mark_user_active(reason)
        self.exit_home_icon_mode(reason=reason, speak=speak)

    def maybe_auto_enter_home_icon(self, now=None, busy=False):
        if self.home_icon_mode or self.godot_game_active:
            return False
        if busy:
            return False
        if self.chat_input.hasFocus() or self.chat_input.text().strip():
            return False
        now = time.monotonic() if now is None else float(now)
        idle_seconds = now - self.last_user_interaction_at
        if idle_seconds < self.home_icon_idle_seconds:
            return False
        return self.enter_home_icon_mode(reason="idle_timeout")

    def start_godot_room_game(self):
        if self.godot_game_active:
            return True
        project_dir = str(getattr(self, "godot_project_dir", "") or "")
        exe = self.resolve_godot_executable()
        if not os.path.isdir(project_dir):
            self.show_chat_status("Godot 小屋项目目录不存在", seconds=4.0)
            print("GODOT_ROOM_ERROR =", {"missing_project": project_dir})
            return False
        if not os.path.isfile(exe):
            self.show_chat_status("Godot 可执行文件不存在", seconds=4.0)
            print("GODOT_ROOM_ERROR =", {"missing_exe": exe})
            return False

        self.room_mode = False
        if getattr(self, "city_mode", False):
            self.city_mode = False
        self.write_godot_bridge(force=True)
        command = [
            exe,
            "--path",
            project_dir,
            "--scene",
            "res://scenes/Main.tscn",
            "--",
            "--bridge",
            self.godot_bridge_path,
            "--state",
            self.godot_state_path,
        ]
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.godot_process = subprocess.Popen(command, cwd=project_dir, creationflags=creationflags)
            self.godot_game_active = True
            self.show_chat_status("Godot 小屋已打开", seconds=2.0)
            self.hide()
            print("GODOT_ROOM_START =", {"pid": self.godot_process.pid, "project": project_dir})
            return True
        except Exception as exc:
            self.godot_process = None
            self.godot_game_active = False
            self.show_chat_status("Godot 小屋启动失败", seconds=4.0)
            print("GODOT_ROOM_START_ERROR =", {"error": str(exc), "command": command})
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "start_room_game", exc)
            return False

    def stop_godot_room_game(self, show_main=True):
        process = getattr(self, "godot_process", None)
        self.godot_process = None
        self.godot_game_active = False
        self.write_godot_bridge(force=True, mode="closed")
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.5)
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "terminate_process", exc)
                try:
                    process.kill()
                except Exception as kill_exc:
                    report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "kill_process", kill_exc)
        if show_main:
            self.show()
            self.raise_()
            self.activateWindow()
            self.show_chat_status("Godot 小屋已关闭", seconds=2.0)
        print("GODOT_ROOM_STOP")

    def shutdown_godot_bridge(self):
        try:
            self.stop_godot_room_game(show_main=False)
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "shutdown", exc)

    def tick_godot_bridge(self):
        process = getattr(self, "godot_process", None)
        if self.godot_game_active:
            self.read_godot_state()
            if self.handle_godot_room_event():
                return
        if self.godot_game_active and process is not None and process.poll() is not None:
            self.godot_process = None
            self.godot_game_active = False
            self.show()
            self.raise_()
            self.activateWindow()
            self.show_chat_status("Godot 小屋已退出", seconds=2.0)
        if self.godot_game_active:
            self.process_godot_runtime_tick()
            self.write_godot_bridge()
            self.read_godot_state()
            self.handle_godot_room_event()

    def process_godot_runtime_tick(self):
        now = time.monotonic()
        for method_name in (
            "process_voice_events",
            "process_barge_in_events",
            "process_speech_events",
            "process_chat_events",
            "process_chat_advice_events",
            "process_life_writing_events",
            "process_reading_events",
            "maybe_continue_free_talk",
        ):
            method = getattr(self, method_name, None)
            if method is None:
                continue
            try:
                method()
            except Exception as exc:
                print("GODOT_RUNTIME_TICK_ERROR =", {"method": method_name, "error": str(exc)})
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "runtime_tick_method", exc, method=method_name)
        try:
            self.maybe_force_life_writing(now)
        except Exception as exc:
            print("GODOT_LIFE_WRITING_WATCHDOG_ERROR =", {"error": str(exc)})
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "life_writing_watchdog", exc)
        busy = (
            self.speech_input.is_busy()
            or self.chat.is_busy()
            or self.chat_advice.is_busy()
            or self.life_writer.is_busy()
            or self.voice.is_busy_or_playing(now)
            or self.behavior.is_speaking(now)
            or now < float(getattr(self, "ui_interaction_busy_until", 0.0) or 0.0)
        )
        try:
            self.drive.tick(busy=busy)
            self.tick_physiology_module(now=now, busy=busy)
            self.tick_heart_module(now=now, busy=busy)
            if hasattr(self, "body_cycle"):
                self.body_cycle.tick(now=now)
            if hasattr(self, "idle_scheduler"):
                idle_seconds = now - self.last_user_interaction_at
                energy = self.drive.values.get("energy", 50.0)
                self.idle_scheduler.tick(now=now, busy=busy, energy=energy, idle_seconds=idle_seconds)
            self.update_barge_in_monitor()
        except Exception as exc:
            print("GODOT_STATE_TICK_ERROR =", {"error": str(exc)})
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "state_tick", exc)

    def current_godot_desired_activity(self, now=None):
        now = time.monotonic() if now is None else float(now)
        if hasattr(self, "choose_room_activity"):
            return self.choose_room_activity(now)
        if self.chat.is_busy() or self.voice.is_busy_or_playing(now) or self.behavior.is_speaking(now):
            return "chatting"
        return "idle"

    def build_godot_bridge_payload(self, mode="open"):
        now_mono = time.monotonic()
        now = datetime.datetime.now()
        desired = self.current_godot_desired_activity(now_mono)
        if desired != self.godot_desired_activity:
            self.godot_desired_activity = desired
            self.godot_activity_revision += 1

        physiology = {}
        body = {}
        if hasattr(self, "physiology"):
            try:
                physiology = self.physiology.snapshot()
                body = physiology.get("body", {}) or {}
            except Exception as exc:
                report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "physiology_snapshot", exc)
                physiology = {}
                body = {}
        drive_values = dict(getattr(getattr(self, "drive", None), "values", {}) or {})
        energy = float(drive_values.get("energy", 50.0) or 50.0)
        inspiration = max(
            float(drive_values.get("purpose", 0.0) or 0.0),
            float(drive_values.get("novelty", 0.0) or 0.0),
            float(drive_values.get("curiosity", 0.0) or 0.0),
        )
        emotion = "neutral"
        try:
            from persona_pet.behavior import dominant_weight_emotion

            emotion = dominant_weight_emotion(self.current_analysis)
        except Exception as exc:
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "dominant_emotion", exc)
        clock_minutes = now.hour * 60 + now.minute + now.second / 60.0
        values = physiology.get("values", {}) if isinstance(physiology, dict) else {}
        return {
            "version": 1,
            "mode": mode,
            "updated_at": now.isoformat(timespec="seconds"),
            "updated_at_unix": time.time(),
            "clock_minutes": clock_minutes,
            "date": now.strftime("%Y-%m-%d"),
            "time_sync": "realtime",
            "desired_activity": desired,
            "activity_revision": self.godot_activity_revision,
            "dialogue": {
                "chat_busy": bool(self.chat.is_busy()),
                "voice_busy": bool(self.voice.is_busy_or_playing(now_mono)),
                "speaking": bool(self.behavior.is_speaking(now_mono)),
                "free_talk": bool(getattr(self, "free_talk_enabled", False)),
            },
            "emotion": emotion,
            "values": {
                "satiety": float(body.get("satiety", max(0.0, 100.0 - float(values.get("hunger", 28.0) or 28.0)))),
                "hydration": float(body.get("hydration", max(0.0, 100.0 - float(values.get("thirst", 30.0) or 30.0)))),
                "energy": energy,
                "inspiration": inspiration,
                "relationship": float(getattr(getattr(self, "life", None), "relationship_score", 0.0) or 0.0),
                "drive": drive_values,
            },
        }

    def write_godot_bridge(self, force=False, mode="open"):
        now = time.monotonic()
        if not force and now - self.godot_last_write_at < 0.20:
            return
        self.godot_last_write_at = now
        payload = self.build_godot_bridge_payload(mode=mode)
        tmp_path = self.godot_bridge_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.godot_bridge_path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(tmp_path, self.godot_bridge_path)
        except Exception as exc:
            print("GODOT_BRIDGE_WRITE_ERROR =", {"error": str(exc)})
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "write_bridge", exc, path=getattr(self, "godot_bridge_path", ""))

    def read_godot_state(self):
        try:
            mtime = os.path.getmtime(self.godot_state_path)
            if mtime == self.godot_last_state_mtime:
                return
            self.godot_last_state_mtime = mtime
            with open(self.godot_state_path, "r", encoding="utf-8") as file:
                state = json.load(file)
            if isinstance(state, dict):
                self.godot_room_state = state
                if hasattr(self, "chat") and hasattr(self.chat, "client"):
                    self.chat.client._godot_room_state = state
                activity = state.get("activity")
                if activity:
                    self.room_activity = str(activity)
        except FileNotFoundError:
            return
        except Exception as exc:
            print("GODOT_BRIDGE_READ_ERROR =", {"error": str(exc)})
            report_exception(getattr(self, "runtime", None), getattr(self, "runtime_logger", None), "godot_bridge", "read_state", exc, path=getattr(self, "godot_state_path", ""))

    def handle_godot_room_event(self):
        state = getattr(self, "godot_room_state", {}) or {}
        event = state.get("event") if isinstance(state, dict) else None
        if not isinstance(event, dict):
            return False
        event_id = str(event.get("id") or "")
        if not event_id or event_id == self.godot_last_event_id:
            return False
        self.godot_last_event_id = event_id
        if str(event.get("type") or "") == "summon_live2d":
            self.summon_from_home(reason="godot_double_click", speak=True)
            return True
        return False
