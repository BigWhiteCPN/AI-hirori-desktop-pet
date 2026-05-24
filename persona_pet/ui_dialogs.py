"""Low-coupling PyQt dialogs used by the desktop pet."""

import random

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from persona_pet.local_llm import normalize_local_llm_config

class FirstRunDialog(QDialog):
    def __init__(self, config, parent=None, default_config=None, tts_defaults=None):
        super().__init__(parent)
        self.config = dict(config or {})
        self.default_config = dict(default_config or {})
        self.tts_defaults = dict(tts_defaults or {})
        self.setWindowTitle("第一次连接")
        self.setModal(True)
        self.resize(1240, 720)
        self.setMinimumWidth(1160)
        self.fields = {}
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#hintLabel {
                color: #8a6178;
                line-height: 140%;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 218);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 10px;
                margin-top: 10px;
                padding: 12px 14px 10px 14px;
                font-weight: 700;
                color: #8f2d5a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #fff6fb;
            }
            QLineEdit, QComboBox, QTextEdit {
                min-height: 30px;
                padding: 5px 9px;
                border: 1px solid rgba(225, 135, 180, 210);
                border-radius: 8px;
                background: rgba(255, 255, 255, 245);
                color: #513247;
            }
            QDialogButtonBox QPushButton {
                min-width: 88px;
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QDialogButtonBox QPushButton:default {
                background: #e866a3;
                color: white;
                border-color: #d94e91;
            }
            QScrollArea#firstRunScroll {
                border: none;
                background: transparent;
            }
            QScrollArea#firstRunScroll > QWidget {
                background: transparent;
            }
            QWidget#firstRunPanel {
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 14, 22, 18)
        layout.setSpacing(4)

        title = QLabel("第一次连接")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        intro = QLabel("这里会保存初始身份和服务配置。下次启动会直接进入桌宠，不再显示这个界面。")
        intro.setObjectName("hintLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea(self)
        scroll.setObjectName("firstRunScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        panel = QWidget()
        panel.setObjectName("firstRunPanel")
        panel.setAutoFillBackground(False)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)

        profile_form = self.add_section(panel_layout, "用户身份")
        self.gender_box = QComboBox()
        self.gender_box.addItems(["男", "女", "不透露"])
        current_gender = str(self.config.get("user_gender") or "不透露")
        idx = self.gender_box.findText(current_gender)
        self.gender_box.setCurrentIndex(idx if idx >= 0 else 2)
        profile_form.addRow("性别", self.gender_box)

        persona_form = self.add_section(panel_layout, "人物背景经历")
        background_hint = QLabel("留空会使用默认苏念背景；填写后会作为她的稳定背景经历参与对话。")
        background_hint.setObjectName("hintLabel")
        background_hint.setWordWrap(True)
        persona_form.addRow("", background_hint)
        self.add_text_area(
            persona_form,
            "背景经历",
            "persona_background",
            placeholder="例如：她来自哪里、成长经历、重要关系、职业、价值观、来到用户电脑前发生了什么。",
            height=92,
        )

        api_form = self.add_section(panel_layout, "连接配置")
        # LLM mode selection
        llm_mode_label = QLabel("大模型模式")
        llm_mode_label.setStyleSheet("font-weight: 700; color: #8f2d5a; margin-top: 8px;")
        api_form.addRow(llm_mode_label)
        self.llm_mode_group = QButtonGroup(self)
        self.llm_cloud_radio = QRadioButton("DeepSeek 云端")
        self.llm_local_radio = QRadioButton("本地 Qwen3 4B")
        current_provider = str(self.config.get("provider") or "openai_compatible").strip().lower()
        self.llm_local_radio.setChecked(current_provider == "ollama")
        self.llm_cloud_radio.setChecked(current_provider != "ollama")
        self.llm_mode_group.addButton(self.llm_cloud_radio, 0)
        self.llm_mode_group.addButton(self.llm_local_radio, 1)
        llm_choice_layout = QVBoxLayout()
        llm_choice_layout.setContentsMargins(0, 0, 0, 0)
        llm_choice_layout.setSpacing(4)
        llm_choice_layout.addWidget(self.llm_cloud_radio)
        cloud_hint = QLabel("需要 API Key，默认使用 DeepSeek 云端接口。")
        cloud_hint.setObjectName("hintLabel")
        cloud_hint.setWordWrap(True)
        cloud_hint.setContentsMargins(24, 0, 0, 4)
        llm_choice_layout.addWidget(cloud_hint)
        llm_choice_layout.addWidget(self.llm_local_radio)
        local_model_hint = QLabel("通过 Ollama 使用 qwen3:4b-instruct，免 API Key，可离线；首次需要下载模型。")
        local_model_hint.setObjectName("hintLabel")
        local_model_hint.setWordWrap(True)
        local_model_hint.setContentsMargins(24, 0, 0, 0)
        llm_choice_layout.addWidget(local_model_hint)
        api_form.addRow("", llm_choice_layout)

        self.llm_cloud_fields_widget = QWidget()
        llm_cloud_form = QFormLayout(self.llm_cloud_fields_widget)
        llm_cloud_form.setContentsMargins(0, 0, 0, 0)
        self.add_field(llm_cloud_form, "DeepSeek API Key", "api_key", password=True)
        api_form.addRow("", self.llm_cloud_fields_widget)

        self.llm_local_fields_widget = QWidget()
        llm_local_layout = QVBoxLayout(self.llm_local_fields_widget)
        llm_local_layout.setContentsMargins(0, 0, 0, 0)
        llm_local_form = QFormLayout()
        llm_local_form.setContentsMargins(0, 0, 0, 0)
        self.add_field(llm_local_form, "Ollama 模型", "local_llm_model", placeholder="qwen3:4b-instruct")
        self.add_field(llm_local_form, "模型目录", "local_llm_models_dir", placeholder="third_party/ollama_models")
        llm_local_layout.addLayout(llm_local_form)
        self.local_llm_auto_pull_check = QCheckBox("缺失时自动下载模型")
        self.local_llm_auto_pull_check.setChecked(bool(self.config.get("local_llm_auto_pull", True)))
        llm_local_layout.addWidget(self.local_llm_auto_pull_check)
        llm_local_hint = QLabel("模型会通过 Ollama 使用；默认缓存到项目内 third_party/ollama_models。首次下载体积较大，下载完成后可离线使用。")
        llm_local_hint.setObjectName("hintLabel")
        llm_local_hint.setWordWrap(True)
        llm_local_layout.addWidget(llm_local_hint)
        api_form.addRow("", self.llm_local_fields_widget)

        # TTS mode selection
        tts_mode_label = QLabel("语音合成模式")
        tts_mode_label.setStyleSheet("font-weight: 700; color: #8f2d5a; margin-top: 8px;")
        api_form.addRow(tts_mode_label)
        self.tts_mode_group = QButtonGroup(self)
        self.tts_volcengine_radio = QRadioButton("火山云服务（需要 API Key）")
        self.tts_local_radio = QRadioButton("本地模型（免 API Key，需 GPU）")
        current_tts = str(self.config.get("tts_provider") or "volcengine")
        self.tts_volcengine_radio.setChecked(current_tts != "local")
        self.tts_local_radio.setChecked(current_tts == "local")
        self.tts_mode_group.addButton(self.tts_volcengine_radio, 0)
        self.tts_mode_group.addButton(self.tts_local_radio, 1)
        api_form.addRow("", self.tts_volcengine_radio)
        api_form.addRow("", self.tts_local_radio)

        # Volcengine fields container
        self.volcengine_fields_widget = QWidget()
        self.volcengine_fields_layout = QFormLayout(self.volcengine_fields_widget)
        self.volcengine_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.add_field(self.volcengine_fields_layout, "火山 TTS AppID", "volcengine_tts_appid", placeholder="user")
        appid_hint = QLabel("AppID 只是火山语音请求标识；没有服务商指定时，填 user 或你自己的通用标识即可。")
        appid_hint.setObjectName("hintLabel")
        appid_hint.setWordWrap(True)
        self.volcengine_fields_layout.addRow("", appid_hint)
        self.add_field(self.volcengine_fields_layout, "豆包/火山 API Key", "voice_api_key", password=True)
        self.add_field(self.volcengine_fields_layout, "音色 ID", "volcengine_tts_voice_type", placeholder=self.tts_defaults.get("voice_type", ""))
        api_form.addRow("", self.volcengine_fields_widget)

        # Local TTS info
        self.local_fields_widget = QWidget()
        local_layout = QVBoxLayout(self.local_fields_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_hint = QLabel("使用本地 Qwen3-TTS 模型，无需 API Key。\n首次启用会自动下载模型；参考音频仍需提前准备。")
        local_hint.setObjectName("hintLabel")
        local_hint.setWordWrap(True)
        local_layout.addWidget(local_hint)
        api_form.addRow("", self.local_fields_widget)

        # ASR mode selection
        asr_mode_label = QLabel("语音识别模式")
        asr_mode_label.setStyleSheet("font-weight: 700; color: #8f2d5a; margin-top: 8px;")
        api_form.addRow(asr_mode_label)
        self.asr_mode_group = QButtonGroup(self)
        self.asr_volcengine_radio = QRadioButton("火山云服务（需要 API Key）")
        self.asr_local_radio = QRadioButton("本地模型（免 API Key）")
        current_asr = str(self.config.get("speech_provider") or "doubao")
        self.asr_volcengine_radio.setChecked(current_asr != "local")
        self.asr_local_radio.setChecked(current_asr == "local")
        self.asr_mode_group.addButton(self.asr_volcengine_radio, 0)
        self.asr_mode_group.addButton(self.asr_local_radio, 1)
        api_form.addRow("", self.asr_volcengine_radio)
        api_form.addRow("", self.asr_local_radio)

        asr_local_widget = QWidget()
        asr_local_layout = QVBoxLayout(asr_local_widget)
        asr_local_layout.setContentsMargins(0, 0, 0, 0)
        asr_local_hint = QLabel("使用本地 SenseVoiceSmall 模型，无需 API Key。首次启用时会自动下载并缓存识别模型。")
        asr_local_hint.setObjectName("hintLabel")
        asr_local_hint.setWordWrap(True)
        asr_local_layout.addWidget(asr_local_hint)
        api_form.addRow("", asr_local_widget)
        self.asr_local_info_widget = asr_local_widget

        self.tts_volcengine_radio.toggled.connect(self._update_tts_fields_visibility)
        self.asr_volcengine_radio.toggled.connect(self._update_asr_fields_visibility)
        self.llm_cloud_radio.toggled.connect(self._update_llm_fields_visibility)
        self.llm_local_radio.toggled.connect(self._update_llm_fields_visibility)
        self._update_llm_fields_visibility()
        self._update_tts_fields_visibility()
        self._update_asr_fields_visibility()

        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if save_button:
            save_button.setText("开始")
            save_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_section(self, layout, title):
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        group_layout.addLayout(form)
        layout.addWidget(group)
        return form

    def _update_tts_fields_visibility(self):
        is_volcengine = self.tts_volcengine_radio.isChecked()
        self.volcengine_fields_widget.setVisible(is_volcengine)
        self.local_fields_widget.setVisible(not is_volcengine)

    def _update_llm_fields_visibility(self):
        is_local = self.llm_local_radio.isChecked()
        self.llm_cloud_fields_widget.setVisible(not is_local)
        self.llm_local_fields_widget.setVisible(is_local)

    def _update_asr_fields_visibility(self):
        is_volcengine = self.asr_volcengine_radio.isChecked()
        self.asr_local_info_widget.setVisible(not is_volcengine)

    def add_field(self, form, label, key, password=False, placeholder=""):
        initial = ""
        if key == "voice_api_key":
            initial = self.config.get("doubao_asr_api_key") or self.config.get("volcengine_tts_api_key") or ""
        elif key == "volcengine_tts_appid":
            initial = self.config.get(key) or self.default_config.get(key) or "user"
        else:
            initial = self.config.get(key, self.default_config.get(key, "")) or ""
        field = QLineEdit(str(initial))
        field.setClearButtonEnabled(True)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        if password:
            field.setEchoMode(QLineEdit.Password)
        form.addRow(label, field)
        self.fields[key] = field

    def add_text_area(self, form, label, key, placeholder="", height=100):
        initial = self.config.get(key, self.default_config.get(key, "")) or ""
        field = QTextEdit(str(initial))
        field.setAcceptRichText(False)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        field.setMinimumHeight(int(height))
        form.addRow(label, field)
        self.fields[key] = field

    def add_browse_field(self, form, label, key, placeholder=""):
        initial = self.config.get(key, self.default_config.get(key, "")) or ""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        field = QLineEdit(str(initial))
        field.setClearButtonEnabled(True)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        h.addWidget(field)
        browse_btn = QPushButton("浏览")
        browse_btn.setFixedWidth(60)
        def do_browse():
            d = QFileDialog.getExistingDirectory(self, "选择目录", field.text() or "")
            if d:
                field.setText(d)
        browse_btn.clicked.connect(do_browse)
        h.addWidget(browse_btn)
        form.addRow(label, container)
        self.fields[key] = field

    def values(self):
        data = dict(self.config)
        data["user_gender"] = self.gender_box.currentText()
        data["onboarding_complete"] = True
        data["onboarding_first_greeting_pending"] = True
        data["persona_background"] = self.fields["persona_background"].toPlainText().strip()
        api_key = self.fields["api_key"].text().strip()
        if self.llm_local_radio.isChecked():
            data["local_llm_model"] = self.fields["local_llm_model"].text().strip() or "qwen3:4b-instruct"
            data["local_llm_models_dir"] = self.fields["local_llm_models_dir"].text().strip() or "third_party/ollama_models"
            data["local_llm_auto_pull"] = self.local_llm_auto_pull_check.isChecked()
            data = normalize_local_llm_config(data)
        else:
            data["provider"] = "openai_compatible"
            data["model"] = self.default_config.get("model") or "deepseek-v4-pro"
            data["fast_model"] = self.default_config.get("fast_model") or "deepseek-v4-flash"
            data["reasoning_model"] = self.default_config.get("reasoning_model") or "deepseek-v4-pro"
            data["base_url"] = self.default_config.get("base_url") or "https://api.deepseek.com"
        if api_key:
            data["api_key"] = api_key
        # TTS provider
        if self.tts_local_radio.isChecked():
            data["tts_provider"] = "local"
        else:
            appid = self.fields["volcengine_tts_appid"].text().strip() or "user"
            voice_key = self.fields["voice_api_key"].text().strip()
            voice_type = self.fields["volcengine_tts_voice_type"].text().strip() or self.tts_defaults.get("voice_type", "")
            if voice_key:
                data["doubao_asr_api_key"] = voice_key
                data["volcengine_tts_api_key"] = voice_key
                data["volcengine_tts_token"] = voice_key
            data["volcengine_tts_appid"] = appid
            data["volcengine_tts_voice_type"] = voice_type
            data["tts_provider"] = "volcengine"
            data["volcengine_tts_cluster"] = data.get("volcengine_tts_cluster") or self.tts_defaults.get("cluster", "")
            data["volcengine_tts_url"] = data.get("volcengine_tts_url") or self.tts_defaults.get("url", "")
        # ASR provider
        data["speech_provider"] = "local" if self.asr_local_radio.isChecked() else "doubao"
        return data

class ApiSettingsDialog(QDialog):
    def __init__(self, config, parent=None, default_config=None, tts_defaults=None):
        super().__init__(parent)
        self.setWindowTitle("桌宠 API 设置")
        self.setModal(True)
        self.config = dict(config or {})
        self.default_config = dict(default_config or {})
        self.tts_defaults = dict(tts_defaults or {})
        self.fields = {}
        self.resize(560, 620)
        self.setMinimumWidth(520)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#hintLabel {
                color: #8a6178;
                line-height: 140%;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 210);
                border: 1px solid rgba(235, 144, 188, 210);
                border-radius: 10px;
                margin-top: 16px;
                padding: 16px 14px 12px 14px;
                font-weight: 700;
                color: #8f2d5a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #fff6fb;
            }
            QLabel {
                color: #6b4058;
            }
            QLineEdit, QTextEdit {
                min-height: 30px;
                padding: 5px 9px;
                border: 1px solid rgba(225, 135, 180, 210);
                border-radius: 8px;
                background: rgba(255, 255, 255, 245);
                color: #513247;
                selection-background-color: #f4a6c7;
            }
            QLineEdit:focus {
                border: 1px solid #d85f9b;
                background: #ffffff;
            }
            QLineEdit[secret="true"] {
                background: #fffafd;
            }
            QDialogButtonBox QPushButton {
                min-width: 88px;
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QDialogButtonBox QPushButton:hover {
                background: #ffe8f3;
            }
            QDialogButtonBox QPushButton:default {
                background: #e866a3;
                color: white;
                border-color: #d94e91;
            }
            QDialogButtonBox QPushButton:default:hover {
                background: #df4f94;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("API 设置")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        intro = QLabel("保存后会写入 persona_llm_config.json，并立即应用到桌宠。敏感字段会隐藏显示；留空的可选项会使用默认值。")
        intro.setObjectName("hintLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        llm_form = self.add_section(panel_layout, "大模型")
        self.llm_provider_combo = QComboBox()
        self.llm_provider_combo.addItem("DeepSeek 云端模型", "deepseek")
        self.llm_provider_combo.addItem("本地 Qwen3 4B Instruct（Ollama）", "local")
        self.llm_provider_combo.addItem("自定义/高级", "custom")
        current_provider = str(self.config.get("provider") or "openai_compatible").strip().lower()
        current_model = str(self.config.get("model") or "").strip()
        if current_provider == "ollama":
            mode_idx = 1
        elif current_provider in ("openai", "openai_compatible", "compatible") and (not current_model or "deepseek" in current_model.lower()):
            mode_idx = 0
        else:
            mode_idx = 2
        self.llm_provider_combo.setCurrentIndex(mode_idx)
        llm_form.addRow("连接模式", self.llm_provider_combo)
        self.add_field(llm_form, "Provider", "provider", placeholder="openai_compatible")
        self.add_field(llm_form, "模型", "model", placeholder="deepseek-chat")
        self.add_field(llm_form, "接口地址", "base_url", placeholder="https://api.deepseek.com")
        self.add_field(llm_form, "API Key", "api_key", password=True)
        self.add_field(llm_form, "环境变量", "api_key_env", placeholder="DEEPSEEK_API_KEY")
        self.local_llm_fields_widget = QWidget()
        local_llm_layout = QVBoxLayout(self.local_llm_fields_widget)
        local_llm_layout.setContentsMargins(0, 0, 0, 0)
        local_llm_form = QFormLayout()
        local_llm_form.setContentsMargins(0, 0, 0, 0)
        self.add_field(local_llm_form, "Ollama 模型", "local_llm_model", placeholder="qwen3:4b-instruct")
        self.add_field(local_llm_form, "模型目录", "local_llm_models_dir", placeholder="third_party/ollama_models")
        local_llm_layout.addLayout(local_llm_form)
        self.local_llm_auto_pull_check = QCheckBox("缺失时自动下载模型")
        self.local_llm_auto_pull_check.setChecked(bool(self.config.get("local_llm_auto_pull", True)))
        local_llm_layout.addWidget(self.local_llm_auto_pull_check)
        local_llm_hint = QLabel("保存为本地模式后会使用 Ollama 的 qwen3:4b-instruct；模型目录默认在项目内 third_party/ollama_models。")
        local_llm_hint.setObjectName("hintLabel")
        local_llm_hint.setWordWrap(True)
        local_llm_layout.addWidget(local_llm_hint)
        llm_form.addRow("", self.local_llm_fields_widget)
        self.llm_provider_combo.currentIndexChanged.connect(self._update_llm_fields_visibility)
        self._update_llm_fields_visibility()

        persona_form = self.add_section(panel_layout, "人物背景经历")
        persona_hint = QLabel("留空会使用默认苏念背景；填写后会作为她的稳定背景经历参与对话。")
        persona_hint.setObjectName("hintLabel")
        persona_hint.setWordWrap(True)
        persona_form.addRow("", persona_hint)
        self.add_text_area(
            persona_form,
            "背景经历",
            "persona_background",
            placeholder="例如：她来自哪里、成长经历、重要关系、职业、价值观、来到用户电脑前发生了什么。",
            height=130,
        )

        asr_form = self.add_section(panel_layout, "语音识别")
        # ASR provider selector
        self.asr_provider_combo = QComboBox()
        self.asr_provider_combo.addItem("火山云服务", "doubao")
        self.asr_provider_combo.addItem("本地模型（免 API Key）", "local")
        current_asr = str(self.config.get("speech_provider") or "doubao")
        asr_idx = 1 if current_asr == "local" else 0
        self.asr_provider_combo.setCurrentIndex(asr_idx)
        asr_form.addRow("识别模式", self.asr_provider_combo)

        # Volcengine ASR fields
        self.asr_volcengine_widget = QWidget()
        asr_ve_form = QFormLayout(self.asr_volcengine_widget)
        asr_ve_form.setContentsMargins(0, 0, 0, 0)
        self.add_field(asr_ve_form, "豆包 API Key", "doubao_asr_api_key", password=True)
        self.add_field(asr_ve_form, "识别接口", "doubao_asr_url", placeholder="https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash")
        self.add_field(asr_ve_form, "Resource ID", "doubao_asr_resource_id", placeholder="volc.bigasr.auc_turbo")
        asr_form.addRow("", self.asr_volcengine_widget)

        # Local ASR info
        self.asr_local_widget = QWidget()
        asr_local_layout = QVBoxLayout(self.asr_local_widget)
        asr_local_layout.setContentsMargins(0, 0, 0, 0)
        asr_local_hint = QLabel("使用本地 SenseVoiceSmall 模型，无需 API Key。首次启用时会自动下载并缓存识别模型；识别速度和准确率通常低于云端。")
        asr_local_hint.setObjectName("hintLabel")
        asr_local_hint.setWordWrap(True)
        asr_local_layout.addWidget(asr_local_hint)
        asr_form.addRow("", self.asr_local_widget)

        self.asr_provider_combo.currentIndexChanged.connect(self._update_asr_fields_visibility)
        self._update_asr_fields_visibility()

        ocr_form = self.add_section(panel_layout, "聊天截图 OCR")
        self.add_field(ocr_form, "OCR Provider", "ocr_provider", placeholder="tesseract")
        self.add_field(ocr_form, "Tesseract 路径", "tesseract_cmd", placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.add_field(ocr_form, "识别语言", "tesseract_lang", placeholder="chi_sim+eng")

        tts_form = self.add_section(panel_layout, "中文配音")
        # TTS provider selector
        self.tts_provider_combo = QComboBox()
        self.tts_provider_combo.addItem("火山云服务", "volcengine")
        self.tts_provider_combo.addItem("本地模型（免 API Key）", "local")
        current_tts = str(self.config.get("tts_provider") or "volcengine")
        idx = 1 if current_tts == "local" else 0
        self.tts_provider_combo.setCurrentIndex(idx)
        tts_form.addRow("语音合成模式", self.tts_provider_combo)

        # Volcengine fields container
        self.volcengine_fields_widget = QWidget()
        ve_form = QFormLayout(self.volcengine_fields_widget)
        ve_form.setContentsMargins(0, 0, 0, 0)
        self.add_field(ve_form, "AppID", "volcengine_tts_appid", placeholder="默认 user；没有服务商要求时可自定义")
        self.add_field(ve_form, "API Key", "volcengine_tts_api_key", password=True)
        self.add_field(ve_form, "Key 环境变量", "volcengine_tts_token_env", placeholder="VOLCENGINE_TTS_API_KEY")
        self.add_field(ve_form, "配音接口", "volcengine_tts_url", placeholder=self.tts_defaults.get("url", ""))
        self.add_field(ve_form, "Cluster", "volcengine_tts_cluster", placeholder="volcano_icl")
        self.add_field(ve_form, "音色 ID", "volcengine_tts_voice_type", placeholder="")
        tts_form.addRow("", self.volcengine_fields_widget)

        # Local TTS info
        self.local_fields_widget = QWidget()
        local_layout = QVBoxLayout(self.local_fields_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_hint = QLabel("使用本地 Qwen3-TTS 模型，无需 API Key。\n首次启用会自动下载模型；参考音频仍需提前准备。")
        local_hint.setObjectName("hintLabel")
        local_hint.setWordWrap(True)
        local_layout.addWidget(local_hint)
        tts_form.addRow("", self.local_fields_widget)

        self.tts_provider_combo.currentIndexChanged.connect(self._update_tts_fields_visibility)
        self._update_tts_fields_visibility()

        panel_layout.addStretch(1)
        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if save_button:
            save_button.setText("保存")
            save_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_section(self, layout, title):
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 10, 12, 10)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        group_layout.addLayout(form)
        layout.addWidget(group)
        return form

    def _update_tts_fields_visibility(self):
        is_volcengine = self.tts_provider_combo.currentData() == "volcengine"
        self.volcengine_fields_widget.setVisible(is_volcengine)
        self.local_fields_widget.setVisible(not is_volcengine)

    def _update_llm_fields_visibility(self):
        self.local_llm_fields_widget.setVisible(self.llm_provider_combo.currentData() == "local")

    def _update_asr_fields_visibility(self):
        is_volcengine = self.asr_provider_combo.currentData() == "doubao"
        self.asr_volcengine_widget.setVisible(is_volcengine)
        self.asr_local_widget.setVisible(not is_volcengine)

    def add_field(self, form, label, key, password=False, placeholder=""):
        initial = self.config.get(key, self.default_config.get(key, "")) or ""
        if key == "volcengine_tts_appid":
            initial = initial or "user"
        field = QLineEdit(str(initial))
        field.setClearButtonEnabled(True)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        if password:
            field.setEchoMode(QLineEdit.Password)
            field.setProperty("secret", "true")
        if key == "volcengine_tts_voice_type":
            field.setPlaceholderText(self.tts_defaults.get("voice_type", ""))
        elif key == "volcengine_tts_cluster":
            field.setPlaceholderText(self.tts_defaults.get("cluster", ""))
        elif key == "volcengine_tts_url":
            field.setPlaceholderText(self.tts_defaults.get("url", ""))
        elif key == "volcengine_tts_token_env":
            field.setPlaceholderText("VOLCENGINE_TTS_API_KEY")
        elif key == "volcengine_tts_appid":
            field.setPlaceholderText("默认 user；没有服务商要求时可自定义")
        form.addRow(label, field)
        self.fields[key] = field

    def add_text_area(self, form, label, key, placeholder="", height=120):
        initial = self.config.get(key, self.default_config.get(key, "")) or ""
        field = QTextEdit(str(initial))
        field.setAcceptRichText(False)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        field.setMinimumHeight(int(height))
        form.addRow(label, field)
        self.fields[key] = field

    def add_browse_field(self, form, label, key, placeholder=""):
        initial = self.config.get(key, self.default_config.get(key, "")) or ""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        field = QLineEdit(str(initial))
        field.setClearButtonEnabled(True)
        field.setPlaceholderText(str(placeholder or self.default_config.get(key, "")))
        h.addWidget(field)
        browse_btn = QPushButton("浏览")
        browse_btn.setFixedWidth(60)
        def do_browse():
            d = QFileDialog.getExistingDirectory(self, "选择目录", field.text() or "")
            if d:
                field.setText(d)
        browse_btn.clicked.connect(do_browse)
        h.addWidget(browse_btn)
        form.addRow(label, container)
        self.fields[key] = field

    def values(self):
        data = dict(self.config)
        for key, field in self.fields.items():
            if isinstance(field, QTextEdit):
                data[key] = field.toPlainText().strip()
            else:
                data[key] = field.text().strip()
        llm_mode = self.llm_provider_combo.currentData()
        if llm_mode == "local":
            data["local_llm_auto_pull"] = self.local_llm_auto_pull_check.isChecked()
            data = normalize_local_llm_config(data)
        elif llm_mode == "deepseek":
            data["provider"] = "openai_compatible"
            data["model"] = self.default_config.get("model") or "deepseek-v4-pro"
            data["fast_model"] = self.default_config.get("fast_model") or "deepseek-v4-flash"
            data["reasoning_model"] = self.default_config.get("reasoning_model") or "deepseek-v4-pro"
            data["base_url"] = self.default_config.get("base_url") or "https://api.deepseek.com"
        provider = self.tts_provider_combo.currentData()
        data["tts_provider"] = provider
        if provider != "local":
            data["volcengine_tts_appid"] = data.get("volcengine_tts_appid") or "user"
            data["volcengine_tts_voice_type"] = data.get("volcengine_tts_voice_type") or self.tts_defaults.get("voice_type", "")
            data["volcengine_tts_cluster"] = data.get("volcengine_tts_cluster") or self.tts_defaults.get("cluster", "")
            data["volcengine_tts_url"] = data.get("volcengine_tts_url") or self.tts_defaults.get("url", "")
            data["volcengine_tts_token_env"] = data.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY"
            data["volcengine_tts_token"] = data.get("volcengine_tts_api_key", "")
        data["speech_provider"] = self.asr_provider_combo.currentData()
        return data


class LocalTTSSettingsDialog(QDialog):
    def __init__(self, config, parent=None, default_config=None):
        super().__init__(parent)
        self.config = dict(config or {})
        self.default_config = dict(default_config or {})
        self.setWindowTitle("本地 TTS 调参")
        self.setModal(True)
        self.resize(420, 260)
        self.setMinimumWidth(380)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#titleLabel {
                color: #8f2d5a;
                font: 15pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#hintLabel {
                color: #8a6178;
                line-height: 140%;
            }
            QDoubleSpinBox, QSpinBox {
                min-height: 30px;
                padding: 3px 8px;
                border: 1px solid rgba(225, 135, 180, 210);
                border-radius: 8px;
                background: rgba(255, 255, 255, 245);
                color: #513247;
            }
            QDialogButtonBox QPushButton, QPushButton {
                min-width: 88px;
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 220);
                padding: 4px 14px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QDialogButtonBox QPushButton:default {
                background: #e866a3;
                color: white;
                border-color: #d94e91;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("本地 TTS 调参")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        hint = QLabel("保存后立即写入当前配置；下一句本地流式语音会使用新参数。默认值：temperature 1.0，top_p 0.9，chunk 16。")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.05, 1.20)
        self.temperature_spin.setSingleStep(0.05)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setValue(self._float_value("qwen_tts_temperature", 1.0))
        form.addRow("temperature", self.temperature_spin)

        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.10, 1.00)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(2)
        self.top_p_spin.setValue(self._float_value("qwen_tts_top_p", 0.9))
        form.addRow("top_p", self.top_p_spin)

        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(8, 32)
        self.chunk_size_spin.setSingleStep(2)
        self.chunk_size_spin.setValue(self._int_value("qwen_tts_stream_chunk_size", 16))
        form.addRow("stream chunk", self.chunk_size_spin)

        layout.addLayout(form)

        reset_button = QPushButton("恢复默认")
        reset_button.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_button, alignment=Qt.AlignLeft)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if save_button:
            save_button.setText("保存")
            save_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _float_value(self, key, fallback):
        try:
            return float(self.config.get(key, self.default_config.get(key, fallback)) or fallback)
        except Exception:
            return float(fallback)

    def _int_value(self, key, fallback):
        try:
            return int(self.config.get(key, self.default_config.get(key, fallback)) or fallback)
        except Exception:
            return int(fallback)

    def _reset_defaults(self):
        self.temperature_spin.setValue(1.0)
        self.top_p_spin.setValue(0.9)
        self.chunk_size_spin.setValue(16)

    def values(self):
        data = dict(self.config)
        data["qwen_tts_temperature"] = round(float(self.temperature_spin.value()), 2)
        data["qwen_tts_top_p"] = round(float(self.top_p_spin.value()), 2)
        data["qwen_tts_stream_chunk_size"] = int(self.chunk_size_spin.value())
        return data


class MiniGameDialog(QDialog):
    def __init__(self, parent_pet):
        super().__init__(parent_pet if isinstance(parent_pet, QWidget) else None)
        self.pet = parent_pet
        self.secret_number = random.randint(1, 20)
        self.guess_attempts = 0
        self.sync_question = random.choice(
            [
                ("如果我今天写小说卡住了，你觉得我会先做什么？", ["喝点水", "找你撒娇", "继续硬写"]),
                ("如果你很久没理我，我最可能是什么反应？", ["安静等你", "有点闹别扭", "马上生气"]),
                ("我作为小说家，最容易注意到什么？", ["细节", "数字", "天气预报"]),
            ]
        )
        self.setWindowTitle("和角色玩一会儿")
        self.resize(520, 460)
        self.setMinimumSize(460, 420)
        self.setStyleSheet(
            """
            QDialog {
                background: #fff3fa;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#gameTitle {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#gameHint {
                color: #8a6178;
            }
            QGroupBox {
                background: rgba(255, 255, 255, 220);
                border: 1px solid rgba(235, 144, 188, 205);
                border-radius: 8px;
                margin-top: 14px;
                padding: 12px;
                color: #8f2d5a;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background: #fff3fa;
            }
            QPushButton {
                min-height: 28px;
                border-radius: 8px;
                border: 1px solid rgba(210, 98, 152, 210);
                padding: 4px 12px;
                background: #ffffff;
                color: #8f2d5a;
                font-weight: 600;
            }
            QPushButton:hover { background: #ffe6f2; }
            QLineEdit {
                min-height: 28px;
                border-radius: 8px;
                border: 1px solid rgba(225, 135, 180, 210);
                padding: 4px 8px;
                background: white;
                color: #513247;
            }
            QTextEdit {
                background: rgba(255,255,255,230);
                border: 1px solid rgba(235,144,188,185);
                border-radius: 8px;
                padding: 8px;
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("小游戏时间")
        title.setObjectName("gameTitle")
        root.addWidget(title)
        hint = QLabel("小游戏会增加亲密值；同一天重复游玩收益会递减，第二天刷新。")
        hint.setObjectName("gameHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        guess_group = QGroupBox("猜数字")
        guess_layout = QHBoxLayout(guess_group)
        self.guess_input = QLineEdit()
        self.guess_input.setPlaceholderText("1-20")
        guess_button = QPushButton("猜")
        guess_button.clicked.connect(self.play_guess_number)
        guess_layout.addWidget(QLabel("我心里有个 1-20 的数字："))
        guess_layout.addWidget(self.guess_input)
        guess_layout.addWidget(guess_button)
        root.addWidget(guess_group)

        rps_group = QGroupBox("石头剪刀布")
        rps_layout = QHBoxLayout(rps_group)
        for choice in ("石头", "剪刀", "布"):
            button = QPushButton(choice)
            button.clicked.connect(lambda _checked=False, c=choice: self.play_rps(c))
            rps_layout.addWidget(button)
        root.addWidget(rps_group)

        sync_group = QGroupBox("默契问答")
        sync_layout = QVBoxLayout(sync_group)
        self.sync_question_label = QLabel(self.sync_question[0])
        self.sync_question_label.setWordWrap(True)
        sync_layout.addWidget(self.sync_question_label)
        sync_buttons = QHBoxLayout()
        self.sync_option_buttons = []
        for option in self.sync_question[1]:
            button = QPushButton(option)
            button.clicked.connect(lambda _checked=False, o=option: self.play_sync(o))
            self.sync_option_buttons.append(button)
            sync_buttons.addWidget(button)
        sync_layout.addLayout(sync_buttons)
        root.addWidget(sync_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlainText("角色：要玩哪个？我会认真陪你玩的。")
        root.addWidget(self.log, 1)

    def append_log(self, text):
        self.log.append(text)

    def reward(self, result, message, voice_text=""):
        reward = self.pet.reward_minigame(result, voice_text=voice_text or message)
        self.append_log(f"{message}\n亲密值 +{reward['relation_gain']:.1f}（今日第 {reward['count']} 次小游戏）")

    def play_guess_number(self):
        try:
            value = int(self.guess_input.text().strip())
        except Exception:
            self.append_log("角色：要输入 1 到 20 的数字哦。")
            self.pet.speak_interaction_feedback("要输入 1 到 20 的数字哦，不然我没法判断你有没有猜中。", emotion="joy")
            return
        if value < 1 or value > 20:
            self.append_log(f"角色：{value} 超出范围啦，数字只能在 1 到 20 之间。")
            self.pet.speak_interaction_feedback(f"{value} 超出范围啦，我心里的数字只在 1 到 20 之间。", emotion="joy")
            return
        self.guess_attempts += 1
        if value == self.secret_number:
            attempts = self.guess_attempts
            secret = self.secret_number
            self.secret_number = random.randint(1, 20)
            self.guess_attempts = 0
            self.reward(
                "win",
                f"角色：猜中了，是 {secret}！居然第 {attempts} 次就抓到我的想法了。下一轮我已经换了新数字。",
                voice_text=f"猜中了，是 {secret}。第 {attempts} 次就抓到我的数字了，厉害。下一轮我已经偷偷换了一个新数字。",
            )
        elif value < self.secret_number:
            self.reward(
                "participate",
                f"角色：你猜 {value}，小啦，我的数字比它大。",
                voice_text=f"你猜 {value}，小啦。我的数字比 {value} 大，再往上试试。",
            )
        else:
            self.reward(
                "participate",
                f"角色：你猜 {value}，大啦，我的数字比它小。",
                voice_text=f"你猜 {value}，大啦。我的数字比 {value} 小一点，稍微收回来。",
            )

    def play_rps(self, user_choice):
        choices = ("石头", "剪刀", "布")
        pet_choice = random.choice(choices)
        beats = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
        if user_choice == pet_choice:
            result = "draw"
            message = f"角色：我也是{pet_choice}，平局。默契还不错嘛。"
            voice_text = f"你出{user_choice}，我也出{pet_choice}，平局。我们这一下还挺同步的。"
        elif beats[user_choice] == pet_choice:
            result = "win"
            message = f"角色：我出{pet_choice}，你赢啦。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这局你赢啦。我记住了，你这手有点准。"
        else:
            result = "lose"
            message = f"角色：我出{pet_choice}，这次是我赢。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这次是我赢。下一把再来。"
        self.reward(result, message, voice_text=voice_text)

    def play_sync(self, option):
        preferred = self.sync_question[1][1]
        question = self.sync_question[0]
        if option == preferred:
            self.reward(
                "win",
                f"角色：对，就是「{option}」。你还挺懂我的。",
                voice_text=f"刚才这题是，{question}。你选的是{option}，我心里想的也是{preferred}。被你猜中我会有点开心。",
            )
        else:
            self.reward(
                "draw",
                f"角色：你选「{option}」也说得通，不过我刚才想的是「{preferred}」。",
                voice_text=f"刚才这题是，{question}。你选的是{option}，也说得通，不过我心里想的是{preferred}。",
            )
        self.sync_question = random.choice(
            [
                ("如果我今天写小说卡住了，你觉得我会先做什么？", ["喝点水", "找你撒娇", "继续硬写"]),
                ("如果你很久没理我，我最可能是什么反应？", ["安静等你", "有点闹别扭", "马上生气"]),
                ("我作为小说家，最容易注意到什么？", ["细节", "数字", "天气预报"]),
            ]
        )
        self.refresh_sync_question()

    def refresh_sync_question(self):
        self.sync_question_label.setText(self.sync_question[0])
        for button, option in zip(self.sync_option_buttons, self.sync_question[1]):
            button.setText(option)
            try:
                button.clicked.disconnect()
            except Exception:
                pass
            button.clicked.connect(lambda _checked=False, o=option: self.play_sync(o))


class ScheduleDialog(QDialog):
    """7-day timetable grid populated with real-time data from all systems."""

    MOOD_EMOJI = {
        "tired": "😪", "lonely": "🥺", "worried": "😟",
        "curious": "✨", "attached": "💕", "relaxed": "😊",
        "playful": "😄", "quiet": "😶",
    }
    MOOD_CN = {
        "tired": "疲惫", "lonely": "想你", "worried": "不安",
        "curious": "好奇", "attached": "依恋", "relaxed": "放松",
        "playful": "开心", "quiet": "安静",
    }

    # Time slots: (start_hour, end_hour, label, default_category)
    TIME_SLOTS = [
        (7,  8,  "早晨",   "morning"),
        (8,  9,  "早餐",   "meal"),
        (9,  12, "创作",   "writing"),
        (12, 13, "午休",   "rest"),
        (13, 14, "午餐",   "meal"),
        (14, 18, "自由",   "social"),
        (18, 19, "傍晚",   "social"),
        (19, 20, "晚餐",   "meal"),
        (20, 22, "晚间",   "reading"),
        (22, 24, "就寝",   "sleep"),
    ]

    # category -> (bg, fg)
    CAT_COLORS = {
        "morning":  ("#c8edca", "#2d6a3f"),
        "meal":     ("#fde8b0", "#8a6b00"),
        "writing":  ("#e8d5f5", "#6b3fa0"),
        "rest":     ("#c8edca", "#2d6a3f"),
        "social":   ("#b8dff5", "#1a5f8a"),
        "reading":  ("#f0d5c0", "#8a5a2d"),
        "sleep":    ("#c5b8e8", "#3d2d6b"),
    }
    CAT_CN = {
        "morning": "晨间", "meal": "餐饮", "writing": "创作",
        "rest": "休息", "social": "社交", "reading": "学习", "sleep": "睡眠",
    }
    # Map conversation categories -> cell category
    CHAT_CAT_MAP = {
        "creative": "writing", "social": "social", "emotion": "social",
        "daily": "social", "care": "social", "humor": "social",
        "philosophy": "reading", "memory": "reading", "question": "social",
    }
    # Map intent types -> cell category
    INTENT_CAT_MAP = {
        "write_novel": "writing", "write_diary": "reading",
        "proactive": "social", "self_expression": "social",
        "curious_question": "social", "memory_recall": "reading",
        "care_checkin": "social", "emotional_need": "social",
        "silent_motion": "rest",
    }

    def __init__(self, parent=None, life_system=None, drive_system=None,
                 memory=None, episodic_memory=None, heart=None,
                 physiology=None, time_awareness=None, body_cycle=None):
        super().__init__(parent)
        self.life = life_system
        self.drive = drive_system
        self.memory = memory
        self.episodic = episodic_memory
        self.heart = heart
        self.physio = physiology
        self.time_aware = time_awareness
        self.cycle = body_cycle

        self.setWindowTitle("苏念的一周作息表")
        self.setModal(False)
        self.resize(740, 620)
        self.setMinimumWidth(660)
        self.setStyleSheet("""
            QDialog {
                background: #fff6fb;
                color: #543247;
                font: 10pt "Microsoft YaHei UI";
            }
            QLabel#title {
                color: #8f2d5a;
                font: 16pt "Microsoft YaHei UI";
                font-weight: 700;
            }
            QLabel#dim { color: #a08090; font-size: 8pt; }
            QScrollArea { border: none; background: transparent; }
            QWidget#scrollContent { background: transparent; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("scrollContent")
        main = QVBoxLayout(content)
        main.setContentsMargins(18, 12, 18, 12)
        main.setSpacing(8)

        self._build_header(main)
        self._build_grid(main)
        self._build_status(main)

        main.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------------------------------------------------------ helpers
    def _card_frame(self):
        f = QFrame()
        f.setStyleSheet(
            "QFrame { background: white; border-radius: 10px;"
            " border: 1px solid #f0dce6; }"
        )
        return f

    def _bar(self, value, max_v=100, color="#d4a5e5", w=120):
        outer = QFrame()
        outer.setFixedSize(w, 8)
        outer.setStyleSheet("QFrame { background: #f0e0ea; border-radius: 4px; }")
        inner = QFrame(outer)
        inner_w = max(0, min(int(w * value / max_v), w))
        inner.setFixedSize(inner_w, 8)
        inner.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 4px; }}")
        return outer

    def _parse_ts(self, ts_str):
        """Return (date_str 'YYYY-MM-DD', hour int) or (None, None)."""
        if not ts_str:
            return None, None
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(ts_str)[:19])
            return dt.strftime("%Y-%m-%d"), dt.hour
        except Exception:
            return None, None

    # ------------------------------------------------------------------ data
    def _get_past_days_data(self):
        """Build {date_str: {hour_slot_idx: [activity_labels]}} from memory."""
        result = {}
        if not self.memory:
            return result

        # From conversation turns
        try:
            if hasattr(self.memory, '_load_db_recent_turns'):
                turns = self.memory._load_db_recent_turns(limit=80)
                for turn in turns:
                    ts = turn.get("created_at", "")
                    day, hour = self._parse_ts(ts)
                    if not day or hour is None:
                        continue
                    slot_idx = self._hour_to_slot(hour)
                    if slot_idx is None:
                        continue
                    cats = turn.get("categories", "")
                    cat = "social"
                    if cats:
                        for c in cats.split(","):
                            c = c.strip()
                            if c in self.CHAT_CAT_MAP:
                                cat = self.CHAT_CAT_MAP[c]
                                break
                    result.setdefault(day, {}).setdefault(slot_idx, []).append(cat)
        except Exception:
            pass

        # From intent history
        if self.drive and hasattr(self.drive, 'intent_history'):
            for item in self.drive.intent_history:
                ts = item.get("time", "")
                day, hour = self._parse_ts(ts)
                if not day or hour is None:
                    continue
                slot_idx = self._hour_to_slot(hour)
                if slot_idx is None:
                    continue
                itype = item.get("type", "")
                cat = self.INTENT_CAT_MAP.get(itype, "social")
                result.setdefault(day, {}).setdefault(slot_idx, []).append(cat)

        return result

    def _hour_to_slot(self, hour):
        for i, (start, end, _, _) in enumerate(self.TIME_SLOTS):
            if start <= hour < end:
                return i
        return None

    def _get_today_cell(self, slot_idx):
        """Return (text, category) for today's cell at given slot."""
        now_hour = __import__("datetime").datetime.now().hour
        slot_start, slot_end, slot_label, slot_cat = self.TIME_SLOTS[slot_idx]

        # Past or current slot: check what actually happened
        if now_hour >= slot_end:
            # This slot is over - check intent history for this time range
            if self.drive and hasattr(self.drive, 'intent_history'):
                for item in reversed(self.drive.intent_history):
                    ts = item.get("time", "")
                    _, hour = self._parse_ts(ts)
                    if hour is not None and slot_start <= hour < slot_end:
                        itype = item.get("type", "")
                        cat = self.INTENT_CAT_MAP.get(itype, slot_cat)
                        label = {
                            "write_novel": "写小说", "write_diary": "写日记",
                            "proactive": "聊天", "self_expression": "表达心声",
                            "curious_question": "提问", "memory_recall": "回忆",
                            "care_checkin": "关心你", "emotional_need": "情感需求",
                            "silent_motion": "发呆",
                        }.get(itype, slot_label)
                        return label, cat
            return self._default_today_text(slot_idx), slot_cat

        # Current slot
        if now_hour >= slot_start:
            return self._live_today_text(slot_idx)

        # Future slot - show plan
        return self._future_today_text(slot_idx)

    def _default_today_text(self, slot_idx):
        """Fill past slots with task-aware defaults."""
        _, _, label, _ = self.TIME_SLOTS[slot_idx]
        if slot_idx == 2:  # writing block
            if self.life:
                words = getattr(self.life, 'novel_words_today', 0)
                if words > 0:
                    return f"写小说\n{words}字"
                if hasattr(self.life, 'needs_diary') and not self.life.needs_diary():
                    return "写日记"
            return "写小说"
        if slot_idx in (5, 6):  # social/free block
            if self.life and (getattr(self.life, 'pat_count', 0) > 0 or
                              getattr(self.life, 'feed_count', 0) > 0):
                return "和你互动"
            return "自由活动"
        if slot_idx == 8:  # reading block
            if self.life and hasattr(self.life, 'needs_reading'):
                if not self.life.needs_reading():
                    return "阅读 ✓"
            return "阅读"
        return label

    def _live_today_text(self, slot_idx):
        """Current slot with real-time drive/physio data."""
        _, _, label, cat = self.TIME_SLOTS[slot_idx]
        if slot_idx == 2:  # writing
            if self.life:
                words = getattr(self.life, 'novel_words_today', 0)
                novel = getattr(self.life, 'novel', {})
                title = novel.get('title', '小说') if novel else '小说'
                if words > 0:
                    return f"写《{title}》\n{words}字", "writing"
                if hasattr(self.life, 'should_write_novel') and self.life.should_write_novel():
                    return f"准备写\n《{title}》", "writing"
            return "创作中", "writing"
        if slot_idx in (5, 6):  # social
            if self.drive:
                mood = self.drive.compute_mood()
                if mood in ("lonely", "attached"):
                    return "想你了", "social"
                if mood == "playful":
                    return "想找你玩", "social"
            return "自由活动", "social"
        if slot_idx == 8:  # reading
            if self.life and hasattr(self.life, 'needs_diary') and self.life.needs_diary():
                return "写日记", "reading"
            return "阅读", "reading"
        return label, cat

    def _future_today_text(self, slot_idx):
        _, _, label, cat = self.TIME_SLOTS[slot_idx]
        if slot_idx == 8:
            if self.life and hasattr(self.life, 'needs_diary') and self.life.needs_diary():
                return "写日记", "reading"
        return label, cat

    def _majority_cat(self, cat_list):
        """Return the most common category from a list."""
        if not cat_list:
            return "social"
        from collections import Counter
        return Counter(cat_list).most_common(1)[0][0]

    # ------------------------------------------------------------------ build
    def _build_header(self, layout):
        mood_label = "relaxed"
        emoji = "😊"
        cn = "放松"
        energy = 72.0
        time_ctx = {}

        if self.drive:
            mood_label = self.drive.compute_mood()
            emoji = self.MOOD_EMOJI.get(mood_label, "😶")
            cn = self.MOOD_CN.get(mood_label, "平静")
            energy = self.drive.values.get("energy", 72.0)
        if self.time_aware:
            time_ctx = self.time_aware.get_current_context()

        # Title row
        top = QHBoxLayout()
        title = QLabel(f"苏念的一周  {emoji}")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch()

        # Energy bar in header
        e_lbl = QLabel(f"精力 {energy:.0f}")
        e_lbl.setStyleSheet("font-size:9pt; color:#6b3fa0;")
        top.addWidget(e_lbl)
        top.addWidget(self._bar(energy, 100, "#d4a5e5"))
        layout.addLayout(top)

        # Sub info
        parts = [f"心情{cn}"]
        if time_ctx:
            if time_ctx.get("is_weekend"):
                parts.append("周末")
            d = time_ctx.get("days_together")
            if d:
                parts.append(f"第{d}天")
        if self.drive:
            dv = self.drive.values
            if dv.get("attachment_need", 0) > 50:
                parts.append("有点粘人")
            if dv.get("curiosity", 0) > 65:
                parts.append("好奇心强")
        sub = QLabel(" · ".join(parts))
        sub.setObjectName("dim")
        layout.addWidget(sub)

    def _build_grid(self, layout):
        from datetime import datetime, timedelta

        today_str = datetime.now().strftime("%Y-%m-%d")
        weekday_cn = ["一", "二", "三", "四", "五", "六", "日"]

        # Compute the 7 days (today + 6 previous)
        days = []
        for i in range(6, -1, -1):
            d = datetime.now() - timedelta(days=i)
            days.append(d.strftime("%Y-%m-%d"))

        past_data = self._get_past_days_data()

        # Card frame
        frame = self._card_frame()
        grid = QGridLayout(frame)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setSpacing(3)

        # Column headers
        grid.addWidget(QWidget(), 0, 0)
        for col, day_str in enumerate(days, 1):
            try:
                dt = datetime.fromisoformat(day_str)
                wd = weekday_cn[dt.weekday()]
                hdr_text = f"{day_str[5:]}\n{wd}"
            except Exception:
                hdr_text = day_str[5:]
            hdr = QLabel(hdr_text)
            hdr.setAlignment(Qt.AlignCenter)
            is_today = (day_str == today_str)
            hdr.setStyleSheet(
                f"font-size:8pt; font-weight:700;"
                f"color:{'#8f2d5a' if is_today else '#a08090'};"
            )
            grid.addWidget(hdr, 0, col)

        # Time rows
        for row, (slot_start, slot_end, slot_label, slot_cat) in enumerate(self.TIME_SLOTS, 1):
            # Time label
            t_lbl = QLabel(f"{slot_start:02d}:00")
            t_lbl.setStyleSheet("font-size:8pt; color:#8f2d5a; font-weight:700;")
            grid.addWidget(t_lbl, row, 0)

            # 7 day cells
            for col, day_str in enumerate(days, 1):
                is_today = (day_str == today_str)

                if is_today:
                    text, cat = self._get_today_cell(row - 1)
                else:
                    # Past day: use majority category from memory data
                    day_slots = past_data.get(day_str, {})
                    cat_list = day_slots.get(row - 1, [])
                    if cat_list:
                        cat = self._majority_cat(cat_list)
                        count = len(cat_list)
                        text = f"{self.CAT_CN.get(cat, cat)}"
                        if count > 1:
                            text += f"\n×{count}"
                    else:
                        # No data for this slot on this day
                        cat = slot_cat
                        text = ""

                bg, fg = self.CAT_COLORS.get(cat, ("#f5f0f5", "#543247"))

                cell = QFrame()
                if is_today:
                    cell.setStyleSheet(
                        f"QFrame {{ background:{bg}; border-radius:6px;"
                        f" border: 2px solid {fg}; }}"
                    )
                else:
                    cell.setStyleSheet(
                        f"QFrame {{ background:{bg}; border-radius:6px; }}"
                    )
                cell.setFixedSize(78, 42)

                if text:
                    lbl = QLabel(text)
                    lbl.setStyleSheet(f"color:{fg}; font-size:8pt;")
                    lbl.setAlignment(Qt.AlignCenter)
                    lbl.setWordWrap(True)
                    cb = QVBoxLayout(cell)
                    cb.setContentsMargins(2, 1, 2, 1)
                    cb.addWidget(lbl)

                grid.addWidget(cell, row, col)

        layout.addWidget(frame)

    def _build_status(self, layout):
        parts = []
        # Tasks
        if self.life:
            novel = getattr(self.life, 'novel', {})
            if novel and not novel.get('complete'):
                words = getattr(self.life, 'novel_words_today', 0)
                ch = novel.get('chapter', 0)
                can = self.life.should_write_novel() if hasattr(self.life, 'should_write_novel') else True
                if can:
                    parts.append(f"《{novel.get('title','小说')}》第{ch}章 待续（{words}字）")
                else:
                    parts.append(f"今日写作完成（{words}字）")

            if hasattr(self.life, 'needs_diary'):
                parts.append("日记：" + ("待写" if self.life.needs_diary() else "✓"))
            if hasattr(self.life, 'needs_reading'):
                parts.append("阅读：" + ("待做" if self.life.needs_reading() else "✓"))

        if self.physio:
            pv = self.physio.values if hasattr(self.physio, 'values') else {}
            pp = []
            if pv.get("hunger", 0) > 50:
                pp.append("饿了")
            if pv.get("thirst", 0) > 45:
                pp.append("渴了")
            if pv.get("fatigue", 0) > 55:
                pp.append("疲劳")
            if pp:
                parts.append("身体：" + "、".join(pp))

        if parts:
            bar = QLabel("  |  ".join(parts))
            bar.setStyleSheet("font-size:9pt; color:#8a6178;")
            bar.setWordWrap(True)
            layout.addWidget(bar)
