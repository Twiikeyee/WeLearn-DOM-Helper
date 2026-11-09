# -*- coding: utf-8 -*-
"""
Configuration Editor GUI for WeLearn-DOM-Helper.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import json
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SpinBox,
    Theme,
    ToolButton,
    setTheme,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "url": "https://welearn.sflep.com/2019/student/index.aspx",
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "max_tokens": 4096,
    "temperature": 0.3,
    "min_dwell_seconds": 5,
    "browser": "edge",
    "headless": False,
    "debug_mode": False,
    "tts_engine": "auto",
    "tts_voice": "",
    "tts_proxy": "",
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(cfg)
            return merged
        except Exception:
            pass
    elif os.path.exists(EXAMPLE_PATH):
        try:
            with open(EXAMPLE_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(cfg)
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(data: dict) -> bool:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


class ConfigEditorDialog(QDialog):
    """Configuration Editor Dialog usable both standalone and inside main GUI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        setTheme(Theme.DARK)
        self.cfg = load_config()
        self.entries = {}
        self._init_window()
        self._build_ui()

    def _init_window(self):
        self.setWindowTitle("WeLearn-DOM-Helper 配置编辑器")
        self.resize(760, 720)
        self.setMinimumSize(640, 560)
        self.setStyleSheet("background: #17191d; color: #f4f7fb;")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Header Title
        title_lbl = QLabel("WeLearn-DOM-Helper 配置参数编辑器")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #f4f7fb;")
        root.addWidget(title_lbl)

        sub_lbl = QLabel("修改后点击下方保存配置即可生效，请勿将含密钥的 config.json 提交至公共仓库。")
        sub_lbl.setStyleSheet("font-size: 12px; color: #8c93a0;")
        root.addWidget(sub_lbl)

        # Scroll Area for Form
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 10, 0)
        form_layout.setSpacing(14)

        # Card 1: Account
        card1 = CardWidget()
        card1_l = QVBoxLayout(card1)
        card1_l.addWidget(self._section_title("平台与账号设置"))
        form1 = QFormLayout()
        form1.setSpacing(10)

        self.entries["url"] = self._line_edit(self.cfg.get("url", ""))
        form1.addRow("主页入口 URL:", self.entries["url"])

        self.entries["username"] = self._line_edit(self.cfg.get("username", ""))
        form1.addRow("账号 (可选):", self.entries["username"])

        self.entries["password"] = self._line_edit(self.cfg.get("password", ""), password=True)
        form1.addRow("密码 (可选):", self.entries["password"])

        card1_l.addLayout(form1)
        form_layout.addWidget(card1)

        # Card 2: LLM Settings
        card2 = CardWidget()
        card2_l = QVBoxLayout(card2)
        card2_l.addWidget(self._section_title("OpenAI 兼容 API 设置 (主观题兜底)"))
        form2 = QFormLayout()
        form2.setSpacing(10)

        self.entries["api_key"] = self._line_edit(self.cfg.get("api_key", ""), password=True)
        form2.addRow("API Key:", self.entries["api_key"])

        self.entries["base_url"] = self._line_edit(self.cfg.get("base_url", ""))
        form2.addRow("Base URL:", self.entries["base_url"])

        self.entries["model"] = self._line_edit(self.cfg.get("model", ""))
        form2.addRow("Model 名称:", self.entries["model"])

        self.entries["temperature"] = self._line_edit(str(self.cfg.get("temperature", 0.3)))
        form2.addRow("Temperature:", self.entries["temperature"])

        self.entries["max_tokens"] = self._line_edit(str(self.cfg.get("max_tokens", 4096)))
        form2.addRow("Max Tokens:", self.entries["max_tokens"])

        card2_l.addLayout(form2)
        form_layout.addWidget(card2)

        # Card 3: Automation Behavior
        card3 = CardWidget()
        card3_l = QVBoxLayout(card3)
        card3_l.addWidget(self._section_title("运行与防封对账设置"))
        form3 = QFormLayout()
        form3.setSpacing(10)

        self.entries["min_dwell_seconds"] = self._line_edit(str(self.cfg.get("min_dwell_seconds", 5)))
        form3.addRow("最少停留作答时间(秒):", self.entries["min_dwell_seconds"])

        self.entries["browser"] = self._line_edit(self.cfg.get("browser", "edge"))
        form3.addRow("浏览器 (edge / chrome):", self.entries["browser"])

        self.cb_headless = CheckBox("无头运行 (Headless)")
        self.cb_headless.setChecked(bool(self.cfg.get("headless", False)))
        form3.addRow("后台隐式运行:", self.cb_headless)

        self.cb_debug = CheckBox("调试模式 (Debug Mode)")
        self.cb_debug.setChecked(bool(self.cfg.get("debug_mode", False)))
        form3.addRow("详细调试输出:", self.cb_debug)

        card3_l.addLayout(form3)
        form_layout.addWidget(card3)

        # Card 4: TTS Settings
        card4 = CardWidget()
        card4_l = QVBoxLayout(card4)
        card4_l.addWidget(self._section_title("语音合成 (TTS)"))
        form4 = QFormLayout()
        form4.setSpacing(10)

        self.entries["tts_engine"] = self._line_edit(self.cfg.get("tts_engine", "auto"))
        form4.addRow("TTS 引擎 (auto/edge/say/off):", self.entries["tts_engine"])

        self.entries["tts_voice"] = self._line_edit(self.cfg.get("tts_voice", ""))
        form4.addRow("音色 Voice (留空默认):", self.entries["tts_voice"])

        self.entries["tts_proxy"] = self._line_edit(self.cfg.get("tts_proxy", ""))
        form4.addRow("TTS 代理 URL (可选):", self.entries["tts_proxy"])

        card4_l.addLayout(form4)
        form_layout.addWidget(card4)

        scroll.setWidget(form_widget)
        root.addWidget(scroll, 1)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)
        btn_box.addStretch(1)

        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = PrimaryPushButton("保存配置")
        save_btn.setIcon(FIF.SAVE)
        save_btn.clicked.connect(self._save_and_close)
        btn_box.addWidget(save_btn)

        root.addLayout(btn_box)

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #30d9ef; font-size: 14px; font-weight: 700; padding: 4px 0 8px 0;")
        return lbl

    def _line_edit(self, text: str, password: bool = False) -> LineEdit:
        le = LineEdit()
        le.setText(str(text))
        if password:
            le.setEchoMode(LineEdit.Password)
        return le

    def _save_and_close(self):
        try:
            temp_val = float(self.entries["temperature"].text().strip() or "0.3")
        except ValueError:
            temp_val = 0.3

        try:
            tokens_val = int(self.entries["max_tokens"].text().strip() or "4096")
        except ValueError:
            tokens_val = 4096

        try:
            dwell_val = int(self.entries["min_dwell_seconds"].text().strip() or "5")
        except ValueError:
            dwell_val = 5

        data = {
            "username": self.entries["username"].text().strip(),
            "password": self.entries["password"].text().strip(),
            "url": self.entries["url"].text().strip() or DEFAULT_CONFIG["url"],
            "api_key": self.entries["api_key"].text().strip(),
            "base_url": self.entries["base_url"].text().strip() or "https://api.openai.com/v1",
            "model": self.entries["model"].text().strip() or "gpt-4o-mini",
            "temperature": temp_val,
            "max_tokens": tokens_val,
            "min_dwell_seconds": dwell_val,
            "browser": self.entries["browser"].text().strip().lower() or "edge",
            "headless": self.cb_headless.isChecked(),
            "debug_mode": self.cb_debug.isChecked(),
            "tts_engine": self.entries["tts_engine"].text().strip().lower() or "auto",
            "tts_voice": self.entries["tts_voice"].text().strip(),
            "tts_proxy": self.entries["tts_proxy"].text().strip(),
        }

        save_config(data)
        InfoBar.success("保存成功", "配置已保存至 config.json", duration=1500, parent=self)
        self.accept()


def main():
    app = QApplication(sys.argv)
    dlg = ConfigEditorDialog()
    dlg.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
