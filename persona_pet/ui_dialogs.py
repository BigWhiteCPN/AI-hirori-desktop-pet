"""Low-coupling PyQt dialogs used by the desktop pet."""

import random

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
            QLineEdit {
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
        self.add_field(llm_form, "Provider", "provider", placeholder="openai_compatible")
        self.add_field(llm_form, "模型", "model", placeholder="deepseek-chat")
        self.add_field(llm_form, "接口地址", "base_url", placeholder="https://api.deepseek.com")
        self.add_field(llm_form, "API Key", "api_key", password=True)
        self.add_field(llm_form, "环境变量", "api_key_env", placeholder="DEEPSEEK_API_KEY")

        asr_form = self.add_section(panel_layout, "语音识别")
        self.add_field(asr_form, "豆包 API Key", "doubao_asr_api_key", password=True)
        self.add_field(asr_form, "识别接口", "doubao_asr_url", placeholder="https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash")
        self.add_field(asr_form, "Resource ID", "doubao_asr_resource_id", placeholder="volc.bigasr.auc_turbo")

        ocr_form = self.add_section(panel_layout, "聊天截图 OCR")
        self.add_field(ocr_form, "OCR Provider", "ocr_provider", placeholder="tesseract")
        self.add_field(ocr_form, "Tesseract 路径", "tesseract_cmd", placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.add_field(ocr_form, "识别语言", "tesseract_lang", placeholder="chi_sim+eng")

        tts_form = self.add_section(panel_layout, "中文配音")
        self.add_field(tts_form, "AppID", "volcengine_tts_appid", placeholder="可选，X-Api-Key 模式可留空")
        self.add_field(tts_form, "API Key", "volcengine_tts_api_key", password=True)
        self.add_field(tts_form, "Key 环境变量", "volcengine_tts_token_env", placeholder="VOLCENGINE_TTS_API_KEY")
        self.add_field(tts_form, "配音接口", "volcengine_tts_url", placeholder=self.tts_defaults.get("url", ""))
        self.add_field(tts_form, "Cluster", "volcengine_tts_cluster", placeholder="volcano_icl")
        self.add_field(tts_form, "音色 ID", "volcengine_tts_voice_type", placeholder="S_zEdGPhR02")
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

    def add_field(self, form, label, key, password=False, placeholder=""):
        field = QLineEdit(str(self.config.get(key, self.default_config.get(key, "")) or ""))
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
        form.addRow(label, field)
        self.fields[key] = field

    def values(self):
        data = dict(self.config)
        for key, field in self.fields.items():
            data[key] = field.text().strip()
        data["tts_provider"] = "volcengine"
        data["volcengine_tts_voice_type"] = data.get("volcengine_tts_voice_type") or self.tts_defaults.get("voice_type", "")
        data["volcengine_tts_cluster"] = data.get("volcengine_tts_cluster") or self.tts_defaults.get("cluster", "")
        data["volcengine_tts_url"] = data.get("volcengine_tts_url") or self.tts_defaults.get("url", "")
        data["volcengine_tts_token_env"] = data.get("volcengine_tts_token_env") or "VOLCENGINE_TTS_API_KEY"
        data["volcengine_tts_token"] = data.get("volcengine_tts_api_key", "")
        data["speech_provider"] = "doubao"
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
        self.setWindowTitle("和小日和玩一会儿")
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
        self.log.setPlainText("小日和：要玩哪个？我会认真陪你玩的。")
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
            self.append_log("小日和：要输入 1 到 20 的数字哦。")
            self.pet.speak_interaction_feedback("要输入 1 到 20 的数字哦，不然我没法判断你有没有猜中。", emotion="joy")
            return
        if value < 1 or value > 20:
            self.append_log(f"小日和：{value} 超出范围啦，数字只能在 1 到 20 之间。")
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
                f"小日和：猜中了，是 {secret}！居然第 {attempts} 次就抓到我的想法了。下一轮我已经换了新数字。",
                voice_text=f"猜中了，是 {secret}。第 {attempts} 次就抓到我的数字了，厉害。下一轮我已经偷偷换了一个新数字。",
            )
        elif value < self.secret_number:
            self.reward(
                "participate",
                f"小日和：你猜 {value}，小啦，我的数字比它大。",
                voice_text=f"你猜 {value}，小啦。我的数字比 {value} 大，再往上试试。",
            )
        else:
            self.reward(
                "participate",
                f"小日和：你猜 {value}，大啦，我的数字比它小。",
                voice_text=f"你猜 {value}，大啦。我的数字比 {value} 小一点，稍微收回来。",
            )

    def play_rps(self, user_choice):
        choices = ("石头", "剪刀", "布")
        pet_choice = random.choice(choices)
        beats = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
        if user_choice == pet_choice:
            result = "draw"
            message = f"小日和：我也是{pet_choice}，平局。默契还不错嘛。"
            voice_text = f"你出{user_choice}，我也出{pet_choice}，平局。我们这一下还挺同步的。"
        elif beats[user_choice] == pet_choice:
            result = "win"
            message = f"小日和：我出{pet_choice}，你赢啦。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这局你赢啦。我记住了，你这手有点准。"
        else:
            result = "lose"
            message = f"小日和：我出{pet_choice}，这次是我赢。"
            voice_text = f"你出{user_choice}，我出{pet_choice}，这次是我赢。不要不服气，下一把再来。"
        self.reward(result, message, voice_text=voice_text)

    def play_sync(self, option):
        preferred = self.sync_question[1][1]
        question = self.sync_question[0]
        if option == preferred:
            self.reward(
                "win",
                f"小日和：对，就是「{option}」。你还挺懂我的。",
                voice_text=f"刚才这题是，{question}。你选的是{option}，我心里想的也是{preferred}。被你猜中我会有点开心。",
            )
        else:
            self.reward(
                "draw",
                f"小日和：你选「{option}」也说得通，不过我刚才想的是「{preferred}」。",
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
