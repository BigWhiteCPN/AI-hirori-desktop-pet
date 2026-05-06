import os
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from persona_pet.chat_advice import ChatAdviceDialog, ChatAdviceEvent, ChatScreenshotSelector


class ChatAdviceCaptureMixin:
    def start_chat_advice_capture(self):
        if self.chat_advice.is_busy():
            self.show_chat_status("聊天截图正在分析中。", seconds=2.0)
            return
        if self.chat_advice_dialog is not None:
            self.chat_advice_dialog.hide()
        self.show_chat_status("请框选聊天记录区域。", seconds=2.0)
        self.hide()
        QTimer.singleShot(260, self.capture_chat_advice_screen)

    def capture_chat_advice_screen(self):
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                raise RuntimeError("没有找到可截图的屏幕。")
            self.chat_advice_full_pixmap = screen.grabWindow(0)
            self.chat_advice_selector = ChatScreenshotSelector(
                screen.geometry(),
                self.finish_chat_advice_selection,
                self.cancel_chat_advice_selection,
            )
            self.chat_advice_selector.show()
            self.chat_advice_selector.raise_()
            self.chat_advice_selector.activateWindow()
        except Exception as exc:
            self.show()
            self.raise_()
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(ChatAdviceEvent(error=str(exc)))
            self.chat_advice_dialog.show()
            self.show_chat_status("聊天截图失败", seconds=3.0)
            print("CHAT_ADVICE_CAPTURE_ERROR =", {"error": str(exc)})

    def finish_chat_advice_selection(self, rect):
        screenshot_path = ""
        try:
            screenshot_dir = getattr(self, "chat_advice_screenshot_dir", "")
            os.makedirs(screenshot_dir, exist_ok=True)
            if self.chat_advice_full_pixmap is None:
                raise RuntimeError("没有可用的屏幕截图。")
            selected = self.chat_advice_full_pixmap.copy(rect)
            screenshot_path = os.path.join(
                screenshot_dir,
                time.strftime("chat_%Y%m%d_%H%M%S.png"),
            )
            if not selected.save(screenshot_path, "PNG"):
                raise RuntimeError("截图保存失败。")
            self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_busy("已框选聊天区域，正在 OCR 识别和分析...")
            self.chat_advice_dialog.show()
            self.chat_advice_dialog.raise_()
            self.show()
            self.raise_()
            if not self.chat_advice.analyze_async(screenshot_path):
                raise RuntimeError("上一张聊天截图还在分析中。")
            print(
                "CHAT_ADVICE_CAPTURE =",
                {"screenshot": screenshot_path, "rect": [rect.x(), rect.y(), rect.width(), rect.height()]},
            )
        except Exception as exc:
            self.show()
            self.raise_()
            if self.chat_advice_dialog is None:
                self.chat_advice_dialog = ChatAdviceDialog(self)
            self.chat_advice_dialog.set_result(ChatAdviceEvent(screenshot_path=screenshot_path, error=str(exc)))
            self.chat_advice_dialog.show()
            self.show_chat_status("聊天截图失败", seconds=3.0)
            print("CHAT_ADVICE_CAPTURE_ERROR =", {"error": str(exc)})
        finally:
            self.chat_advice_full_pixmap = None

    def cancel_chat_advice_selection(self, reason):
        self.chat_advice_full_pixmap = None
        self.show()
        self.raise_()
        self.show_chat_status(reason, seconds=2.0)
        print("CHAT_ADVICE_CANCEL =", {"reason": reason})


