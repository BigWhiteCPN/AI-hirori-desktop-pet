from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time


APP_CATEGORIES = {
    "chrome": "browser",
    "msedge": "browser",
    "firefox": "browser",
    "code": "work",
    "pycharm": "work",
    "idea": "work",
    "devenv": "work",
    "notepad++": "work",
    "wechat": "chat",
    "qq": "chat",
    "telegram": "chat",
    "discord": "chat",
    "steam": "game",
    "epic": "game",
    "unity": "game",
    "unreal": "game",
    "spotify": "music",
    "qqmusic": "music",
    "neteasecloudmusic": "music",
    "bilibili": "video",
    "youtube": "video",
    "explorer": "files",
    "totalcmd": "files",
    "persona_bot_test": "pet",
}


class ActivityMonitor:
    def __init__(self, poll_interval=10.0, logger=None):
        self.poll_interval = max(2.0, float(poll_interval or 10.0))
        self.logger = logger or (lambda *parts: None)
        self._running = False
        self._thread = None
        self._callback = None
        self._current_category = "unknown"
        self._current_app = ""
        self._category_since = time.monotonic()
        self._last_work_overtime_emit = 0.0
        self._last_late_night_emit = 0.0

    def start(self, on_event):
        if self._running:
            return
        self._callback = on_event
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _poll_loop(self):
        while self._running:
            try:
                title, exe_name = self._get_foreground_info()
                category = self._classify(exe_name)
                now = time.monotonic()
                if category != self._current_category:
                    old = self._current_category
                    self._current_category = category
                    self._current_app = exe_name
                    self._category_since = now
                    if self._callback and category != "pet":
                        self._callback({
                            "type": "env_change",
                            "old_category": old,
                            "new_category": category,
                            "app_name": exe_name,
                        })
                duration_minutes = (now - self._category_since) / 60.0
                if (
                    self._callback
                    and category == "work"
                    and duration_minutes >= 120.0
                    and now - self._last_work_overtime_emit >= 1800.0
                ):
                    self._last_work_overtime_emit = now
                    self._callback({
                        "type": "work_overtime",
                        "minutes": round(duration_minutes, 1),
                        "app_name": exe_name,
                    })
                hour = time.localtime().tm_hour
                if (
                    self._callback
                    and category != "pet"
                    and 1 <= hour <= 5
                    and now - self._last_late_night_emit >= 3600.0
                ):
                    self._last_late_night_emit = now
                    self._callback({
                        "type": "late_night",
                        "hour": hour,
                        "app_name": exe_name,
                    })
            except Exception as exc:
                self.logger("ACTIVITY_MONITOR_ERROR", {"error": str(exc)})
            time.sleep(self.poll_interval)

    def _classify(self, exe_name):
        exe = str(exe_name or "").lower()
        for key, category in APP_CATEGORIES.items():
            if key in exe:
                return category
        return "unknown"

    def _get_foreground_info(self):
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return "", ""
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value
        exe_name = ""
        process_handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)
        if process_handle:
            try:
                exe_buffer = ctypes.create_unicode_buffer(260)
                ctypes.windll.psapi.GetModuleBaseNameW(process_handle, None, exe_buffer, 260)
                exe_name = exe_buffer.value
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)
        return title, str(exe_name or "").lower()
