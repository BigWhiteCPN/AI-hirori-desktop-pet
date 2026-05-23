"""Diary and novel bookshelf dialog."""

import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


@dataclass
class LibraryEntry:
    kind: str
    title: str
    path: str
    content: str
    modified: float = 0.0

    @property
    def kind_label(self):
        return "日记" if self.kind == "diary" else "小说"

    @property
    def char_count(self):
        return len(re.sub(r"\s+", "", self.content or ""))

    @property
    def modified_label(self):
        if not self.modified:
            return ""
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.modified))


def read_docx_text(path):
    try:
        with zipfile.ZipFile(path, "r") as docx:
            raw = docx.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ET.fromstring(raw)
    except Exception:
        return ""
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        pieces = []
        for text in paragraph.findall(".//w:t", namespace):
            if text.text:
                pieces.append(text.text)
        line = "".join(pieces).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs).strip()


def clean_title_from_filename(path):
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"[_\s]+", " ", name).strip()
    return name or "未命名"


def split_pages(content, max_chars=820):
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", content or "") if part.strip()]
    if not paragraphs:
        return ["还没有内容。"]
    pages = []
    current = ""
    for paragraph in paragraphs:
        addition = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(addition) > max_chars and current:
            pages.append(current)
            current = paragraph
        else:
            current = addition
    if current:
        pages.append(current)
    return pages or ["还没有内容。"]


def load_entries_from_dir(kind, directory):
    if not directory or not os.path.isdir(directory):
        return []
    entries = []
    for name in os.listdir(directory):
        if not name.lower().endswith(".docx"):
            continue
        path = os.path.join(directory, name)
        content = read_docx_text(path)
        if not content:
            continue
        first_line = content.splitlines()[0].strip() if content.splitlines() else ""
        title = first_line or clean_title_from_filename(path)
        entries.append(
            LibraryEntry(
                kind=kind,
                title=title,
                path=path,
                content=content,
                modified=os.path.getmtime(path),
            )
        )
    entries.sort(key=lambda item: item.modified, reverse=True)
    return entries


class LifeLibraryDialog(QDialog):
    FILTERS = (("all", "全部"), ("diary", "日记"), ("novel", "小说"))

    def __init__(self, diary_dir, novel_dir, parent=None):
        super().__init__(parent)
        self.diary_dir = diary_dir
        self.novel_dir = novel_dir
        self.entries = []
        self.filtered_entries = []
        self.current_entry = None
        self.pages = ["还没有内容。"]
        self.page_index = 0
        self.filter_kind = "all"
        self.setWindowTitle("角色的书架")
        self.resize(960, 660)
        self.setMinimumSize(780, 540)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff8fb;
                color: #513246;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#libraryTitle {
                color: #8f2d5a;
                font: 18pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#librarySubtitle, QLabel#libraryStats, QLabel#libraryMeta, QLabel#pageLabel {
                color: #8a6178;
            }
            QFrame#sidebar, QFrame#readerPanel {
                background: rgba(255, 255, 255, 218);
                border: 1px solid rgba(226, 150, 188, 170);
                border-radius: 8px;
            }
            QLineEdit#librarySearch {
                background: rgba(255, 255, 255, 245);
                border: 1px solid rgba(226, 150, 188, 190);
                border-radius: 7px;
                padding: 7px 9px;
                color: #5a3a50;
            }
            QListWidget {
                background: transparent;
                border: none;
                padding: 2px;
                outline: none;
            }
            QListWidget::item {
                padding: 9px 8px;
                border-radius: 7px;
                color: #604056;
            }
            QListWidget::item:selected {
                background: #ffe1ef;
                color: #8f2d5a;
            }
            QListWidget::item:hover {
                background: rgba(255, 229, 242, 175);
            }
            QTextEdit#pageView {
                background: #fffdf8;
                border: 1px solid rgba(214, 165, 124, 165);
                border-radius: 8px;
                padding: 22px 24px;
                color: #49362d;
                font: 11pt "Microsoft YaHei UI";
            }
            QPushButton {
                background: #fff6fb;
                border: 1px solid rgba(226, 150, 188, 220);
                border-radius: 7px;
                padding: 7px 13px;
                color: #743e5c;
            }
            QPushButton:hover {
                background: #ffe5f1;
                border-color: rgba(211, 96, 150, 235);
            }
            QPushButton:checked {
                background: #ffd6e9;
                border-color: rgba(211, 96, 150, 235);
                color: #8f2d5a;
                font-weight: 700;
            }
            QProgressBar {
                background: rgba(255, 241, 248, 230);
                border: 1px solid rgba(226, 150, 188, 150);
                border-radius: 5px;
                height: 9px;
            }
            QProgressBar::chunk {
                background: #e987b9;
                border-radius: 4px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        root.addLayout(header)
        title_block = QVBoxLayout()
        header.addLayout(title_block, 1)
        title = QLabel("角色的书架")
        title.setObjectName("libraryTitle")
        title_block.addWidget(title)
        subtitle = QLabel("翻看她写过的日记和小说。左侧筛选，右侧阅读。方向键也可以翻页。")
        subtitle.setObjectName("librarySubtitle")
        subtitle.setWordWrap(True)
        title_block.addWidget(subtitle)
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("libraryStats")
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.stats_label)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebar")
        sidebar_frame.setFixedWidth(306)
        body.addWidget(sidebar_frame)
        sidebar = QVBoxLayout(sidebar_frame)
        sidebar.setContentsMargins(12, 12, 12, 12)
        sidebar.setSpacing(9)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("librarySearch")
        self.search_input.setPlaceholderText("搜索标题或正文")
        self.search_input.textChanged.connect(self.apply_filters)
        sidebar.addWidget(self.search_input)

        filter_row = QHBoxLayout()
        sidebar.addLayout(filter_row)
        self.filter_buttons = {}
        for key, label in self.FILTERS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=key: self.set_filter(value))
            self.filter_buttons[key] = button
            filter_row.addWidget(button)
        self.filter_buttons["all"].setChecked(True)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_entry_selected)
        sidebar.addWidget(self.list_widget, 1)

        self.refresh_button = QPushButton("刷新书架")
        self.refresh_button.clicked.connect(self.reload_entries)
        sidebar.addWidget(self.refresh_button)

        reader_frame = QFrame()
        reader_frame.setObjectName("readerPanel")
        body.addWidget(reader_frame, 1)
        reader = QVBoxLayout(reader_frame)
        reader.setContentsMargins(14, 12, 14, 14)
        reader.setSpacing(9)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("libraryMeta")
        self.meta_label.setWordWrap(True)
        reader.addWidget(self.meta_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        reader.addWidget(self.progress)

        self.page_view = QTextEdit()
        self.page_view.setObjectName("pageView")
        self.page_view.setReadOnly(True)
        reader.addWidget(self.page_view, 1)

        controls = QHBoxLayout()
        reader.addLayout(controls)
        self.prev_button = QPushButton("上一页")
        self.prev_button.clicked.connect(self.prev_page)
        self.page_label = QLabel("0 / 0")
        self.page_label.setObjectName("pageLabel")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self.next_page)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.page_label, 1)
        controls.addWidget(self.next_button)

        self.reload_entries()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Space):
            self.next_page()
            event.accept()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_PageUp):
            self.prev_page()
            event.accept()
            return
        super().keyPressEvent(event)

    def reload_entries(self):
        self.entries = []
        self.entries.extend(load_entries_from_dir("diary", self.diary_dir))
        self.entries.extend(load_entries_from_dir("novel", self.novel_dir))
        self.apply_filters()

    def set_filter(self, kind):
        self.filter_kind = kind
        for key, button in self.filter_buttons.items():
            button.setChecked(key == kind)
        self.apply_filters()

    def apply_filters(self):
        query = compact_query(self.search_input.text()) if hasattr(self, "search_input") else ""
        self.filtered_entries = []
        for entry in self.entries:
            if self.filter_kind != "all" and entry.kind != self.filter_kind:
                continue
            haystack = compact_query(f"{entry.title}\n{entry.content}")
            if query and query not in haystack:
                continue
            self.filtered_entries.append(entry)
        self.populate_list()

    def populate_list(self):
        current_path = self.current_entry.path if self.current_entry else ""
        self.list_widget.clear()
        diary_count = sum(1 for entry in self.entries if entry.kind == "diary")
        novel_count = sum(1 for entry in self.entries if entry.kind == "novel")
        self.stats_label.setText(f"{diary_count} 篇日记 · {novel_count} 本小说")
        if not self.filtered_entries:
            self.current_entry = None
            self.pages = ["没有匹配的日记或小说。"]
            self.page_index = 0
            self.render_page()
            return
        selected_row = 0
        for index, entry in enumerate(self.filtered_entries):
            item = QListWidgetItem(self.item_text(entry))
            item.setData(Qt.UserRole, entry)
            item.setSizeHint(QSize(0, 74))
            self.list_widget.addItem(item)
            if entry.path == current_path:
                selected_row = index
        self.list_widget.setCurrentRow(selected_row)

    def item_text(self, entry):
        preview = re.sub(r"\s+", " ", entry.content or "").strip()
        if preview.startswith(entry.title):
            preview = preview[len(entry.title) :].strip()
        if len(preview) > 42:
            preview = preview[:42].rstrip() + "..."
        return (
            f"{entry.kind_label}  {entry.title}\n"
            f"{entry.modified_label} · {entry.char_count} 字\n"
            f"{preview or '还没有预览。'}"
        )

    def on_entry_selected(self, current, _previous):
        if current is None:
            return
        self.current_entry = current.data(Qt.UserRole)
        self.pages = split_pages(self.current_entry.content)
        self.page_index = 0
        self.render_page()

    def render_page(self):
        entry = self.current_entry
        if entry is None:
            self.meta_label.setText("书架里暂时没有可显示的内容。")
        else:
            self.meta_label.setText(
                f"{entry.kind_label}：{entry.title}\n"
                f"{entry.modified_label} · {entry.char_count} 字 · {entry.path}"
            )
        self.page_index = max(0, min(self.page_index, len(self.pages) - 1))
        self.page_view.setPlainText(self.pages[self.page_index])
        self.page_label.setText(f"第 {self.page_index + 1} 页 / 共 {len(self.pages)} 页")
        progress = int(round((self.page_index + 1) / max(1, len(self.pages)) * 100))
        self.progress.setValue(progress)
        self.prev_button.setEnabled(self.page_index > 0)
        self.next_button.setEnabled(self.page_index < len(self.pages) - 1)

    def prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self.render_page()

    def next_page(self):
        if self.page_index < len(self.pages) - 1:
            self.page_index += 1
            self.render_page()


def compact_query(text):
    return re.sub(r"\s+", "", str(text or "")).lower()
