import re
import threading
from dataclasses import dataclass

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QRubberBand, QTextEdit, QVBoxLayout, QWidget

from persona_pet.llm_client import LLMClient
from persona_pet.memory import compact_text


@dataclass
class ChatAdviceEvent:
    screenshot_path: str = ""
    ocr_text: str = ""
    advice: str = ""
    copy_reply: str = ""
    error: str = ""


class ChatAdviceController:
    def __init__(self, config=None, memory_store=None, client_kwargs=None, default_config=None):
        self.default_config = dict(default_config or {})
        self.client_kwargs = dict(client_kwargs or {})
        self.config = dict(config or self.default_config)
        self.memory_store = memory_store
        self.client = LLMClient(config=self.config, memory_store=memory_store, **self.client_kwargs)
        self.lock = threading.Lock()
        self.busy = False
        self.events = []

    def update_config(self, config):
        self.config = dict(config or self.default_config)
        self.client = LLMClient(config=self.config, memory_store=self.memory_store, **self.client_kwargs)

    def is_busy(self):
        with self.lock:
            return self.busy

    def analyze_async(self, screenshot_path):
        with self.lock:
            if self.busy:
                return False
            self.busy = True

        def worker():
            event = ChatAdviceEvent(screenshot_path=screenshot_path)
            try:
                event.ocr_text = self.ocr_image(screenshot_path)
                if len(compact_text(event.ocr_text)) < 8:
                    raise RuntimeError("OCR 没有识别到足够的聊天文字。请把聊天窗口放大一点，或确认截图里有文字。")
                event.advice = self.ask_advice(event.ocr_text)
                event.copy_reply = self.extract_copy_reply(event.advice)
            except Exception as exc:
                event.error = str(exc)
            with self.lock:
                self.busy = False
                self.events.append(event)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def consume_events(self):
        with self.lock:
            events = self.events
            self.events = []
        return events

    def ocr_image(self, image_path):
        provider = str(self.config.get("ocr_provider") or "tesseract").lower()
        if provider != "tesseract":
            raise RuntimeError(f"暂不支持 OCR Provider: {provider}")
        try:
            from PIL import Image, ImageOps
            import pytesseract
        except Exception as exc:
            raise RuntimeError(f"缺少 OCR 依赖：{exc}") from exc

        tesseract_cmd = str(self.config.get("tesseract_cmd") or "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        lang = str(self.config.get("tesseract_lang") or "chi_sim+eng").strip() or "chi_sim+eng"
        image = Image.open(image_path)
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        if max(image.size) < 2200:
            image = image.resize((int(image.width * 1.45), int(image.height * 1.45)))
        try:
            text = pytesseract.image_to_string(image, lang=lang, config="--psm 6")
        except Exception:
            text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        text = re.sub(r"[ \t]+", " ", text or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    def ask_advice(self, ocr_text):
        memory_context = ""
        if self.memory_store is not None:
            memory_context = self.memory_store.build_prompt_context(ocr_text)
        system = (
            "你是桌宠的聊天记录顾问。用户给你一张聊天记录 OCR 文本，"
            "你要像亲近用户但有边界感的朋友一样分析。"
            "只根据 OCR 和记忆上下文判断，不要编造事实；不要替用户操控别人；"
            "涉及感情、人际冲突时，要具体、温柔、可执行。"
        )
        user = (
            f"{memory_context}\n\n"
            "【截图 OCR 文本】\n"
            f"{ocr_text[:6000]}\n\n"
            "请输出：\n"
            "1. 我看到的关键信息\n"
            "2. 可能的关系/情绪模式\n"
            "3. 给用户的建议\n"
            "4. 【可复制回复】给出 1-3 条用户可以直接复制发送的短回复，每条自然一点。"
        )
        return self.client.chat_messages(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.45,
            timeout=180,
        )

    def extract_copy_reply(self, advice):
        text = advice or ""
        match = re.search(r"【可复制回复】([\s\S]+)$", text)
        if match:
            block = match.group(1).strip()
        else:
            block = text.strip()
        lines = [re.sub(r"^\s*[-*0-9.、）)]+", "", line).strip() for line in block.splitlines()]
        lines = [line.strip("“”\" ") for line in lines if len(line.strip()) >= 2]
        return "\n".join(lines[:3]) or text[:500]


class ChatAdviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.copy_reply = ""
        self.setWindowTitle("聊天截图顾问")
        self.resize(720, 620)
        self.setMinimumSize(620, 520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff2f8;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#statusLabel {
                color: #8a6178;
            }
            QTextEdit {
                background: rgba(255, 255, 255, 236);
                border: 1px solid rgba(235, 144, 188, 196);
                border-radius: 8px;
                padding: 10px;
                color: #513247;
            }
            QPushButton {
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #ffe8f3;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("聊天截图顾问")
        title.setObjectName("titleLabel")
        root.addWidget(title)
        self.status_label = QLabel("准备截图 OCR...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.advice_text = QTextEdit()
        self.advice_text.setReadOnly(True)
        self.advice_text.setPlaceholderText("建议会显示在这里。")
        root.addWidget(self.advice_text, 2)

        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText("OCR 识别文本会显示在这里。")
        self.ocr_text.setMaximumHeight(150)
        root.addWidget(self.ocr_text, 1)

        buttons = QHBoxLayout()
        self.copy_reply_button = QPushButton("复制回复模板")
        self.copy_all_button = QPushButton("复制完整建议")
        self.close_button = QPushButton("关闭")
        self.copy_reply_button.clicked.connect(self.copy_reply_to_clipboard)
        self.copy_all_button.clicked.connect(self.copy_all_to_clipboard)
        self.close_button.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_reply_button)
        buttons.addWidget(self.copy_all_button)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)
        self.set_busy("正在截图，稍等一下...")

    def set_busy(self, text):
        self.status_label.setText(text)
        self.copy_reply_button.setEnabled(False)
        self.copy_all_button.setEnabled(False)

    def set_result(self, event):
        self.ocr_text.setPlainText(event.ocr_text or "")
        if event.error:
            self.status_label.setText(f"失败：{event.error}")
            self.advice_text.setPlainText("")
            self.copy_reply = ""
            self.copy_reply_button.setEnabled(False)
            self.copy_all_button.setEnabled(False)
            return
        self.status_label.setText(f"分析完成。截图：{event.screenshot_path}")
        self.advice_text.setPlainText(event.advice or "")
        self.copy_reply = event.copy_reply or ""
        self.copy_reply_button.setEnabled(bool(self.copy_reply))
        self.copy_all_button.setEnabled(bool(event.advice))

    def copy_reply_to_clipboard(self):
        QApplication.clipboard().setText(self.copy_reply or self.advice_text.toPlainText())
        self.status_label.setText("已复制回复模板。")

    def copy_all_to_clipboard(self):
        QApplication.clipboard().setText(self.advice_text.toPlainText())
        self.status_label.setText("已复制完整建议。")


class ChatScreenshotSelector(QWidget):
    def __init__(self, screen_geometry, on_selected, on_cancelled, parent=None):
        super().__init__(parent)
        self.on_selected = on_selected
        self.on_cancelled = on_cancelled
        self.origin = QPoint()
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: rgba(60, 35, 55, 72);")

        self.hint = QLabel("拖拽框选聊天记录区域，松开后开始 OCR；按 ESC 取消", self)
        self.hint.setStyleSheet(
            "QLabel {"
            "background: rgba(255, 246, 251, 236);"
            "border: 1px solid rgba(235, 144, 188, 220);"
            "border-radius: 8px;"
            "padding: 9px 14px;"
            "color: #6a3f57;"
            "font: 10pt 'Microsoft YaHei UI';"
            "}"
        )
        self.hint.adjustSize()
        self.hint.move(24, 24)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.origin = event.pos()
        self.rubber_band.setGeometry(QRect(self.origin, self.origin))
        self.rubber_band.show()
        event.accept()

    def mouseMoveEvent(self, event):
        if self.rubber_band.isVisible():
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        rect = self.rubber_band.geometry().normalized()
        self.rubber_band.hide()
        self.close()
        if rect.width() < 40 or rect.height() < 40:
            self.on_cancelled("框选区域太小，已取消。")
        else:
            self.on_selected(rect)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.rubber_band.hide()
            self.close()
            self.on_cancelled("已取消聊天截图。")
            return
        super().keyPressEvent(event)
