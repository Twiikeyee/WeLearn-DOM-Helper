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
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PlainTextEdit,
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
    "typing_mode": "fast",
    "min_dwell_seconds": 0,
    "enable_llm_subjective": false,
    "subjective_default_text": "From my perspective, this viewpoint is quite reasonable and closely related to our daily study, communication, and practical experiences.",
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "max_tokens": 4096,
    "temperature": 0.3,
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
        self.resize(780, 780)
        self.setMinimumSize(660, 600)
        self.setStyleSheet("background: #17191d; color: #f4f7fb;")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title_lbl = QLabel("WeLearn-DOM-Helper 参数配置编辑器")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #f4f7fb;")
        root.addWidget(title_lbl)

        sub_lbl = QLabel("支持极速模式、零 Token 预设范文模式与真实时长差额补偿，请按需配置。")
        sub_lbl.setStyleSheet("font-size: 12px; color: #8c93a0;")
        root.addWidget(sub_lbl)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 10, 0)
        form_layout.setSpacing(14)

        # Card 1: Efficiency & Typing
        card_eff = CardWidget()
        card_eff_l = QVBoxLayout(card_eff)
        card_eff_l.addWidget(self._section_title("运行模式与答题效率"))
        form_eff = QFormLayout()
        form_eff.setSpacing(10)

        self.combo_typing = ComboBox()
        self.combo_typing.addItem("快速注入 (Fast - 0ms 注入并分发数据绑定事件)")
        self.combo_typing.addItem("模拟按键 (Simulate - 逐字符物理击键，较慢)")
        curr_typing = str(self.cfg.get("typing_mode", "fast")).lower()
        self.combo_typing.setCurrentIndex(1 if curr_typing == "simulate" else 0)
        form_eff.addRow("文本输入方式:", self.combo_typing)

        self.entries["min_dwell_seconds"] = self._line_edit(str(self.cfg.get("min_dwell_seconds", 0)))
        form_eff.addRow("最少停留作答秒数 (填 0 为极速; 如老师要求可填指定秒数):", self.entries["min_dwell_seconds"])

        self.entries["browser"] = self._line_edit(self.cfg.get("browser", "edge"))
        form_eff.addRow("浏览器 (edge / chrome):", self.entries["browser"])

        self.cb_headless = CheckBox("无头模式 (Headless - 后台静默无界面运行)")
        self.cb_headless.setChecked(bool(self.cfg.get("headless", False)))
        form_eff.addRow("后台隐式运行:", self.cb_headless)

        card_eff_l.addLayout(form_eff)
        form_layout.addWidget(card_eff)

        # Card 2: Subjective & LLM
        card_subj = CardWidget()
        card_subj_l = QVBoxLayout(card_subj)
        card_subj_l.addWidget(self._section_title("主观题与大模型设置 (零 Token 模式可关闭)"))
        form_subj = QFormLayout()
        form_subj.setSpacing(10)

        self.cb_enable_llm = CheckBox("启用 LLM 智能生成主观题答案 (不勾选则使用下方预设范句，0 Token 消耗)")
        self.cb_enable_llm.setChecked(bool(self.cfg.get("enable_llm_subjective", False)))
        form_subj.addRow("LLM 开关:", self.cb_enable_llm)

        self.entries["subjective_default_text"] = self._line_edit(
            self.cfg.get(
                "subjective_default_text",
                "From my perspective, this viewpoint is quite reasonable and closely related to our daily study."
            )
        )
        form_subj.addRow("主观题预设通用范文:", self.entries["subjective_default_text"])

        self.entries["api_key"] = self._line_edit(self.cfg.get("api_key", ""), password=True)
        form_subj.addRow("API Key (可选):", self.entries["api_key"])

        self.entries["base_url"] = self._line_edit(self.cfg.get("base_url", ""))
        form_subj.addRow("API Base URL:", self.entries["base_url"])

        self.entries["model"] = self._line_edit(self.cfg.get("model", "gpt-4o-mini"))
        form_subj.addRow("Model 名称:", self.entries["model"])

        card_subj_l.addLayout(form_subj)
        form_layout.addWidget(card_subj)

        # Card 3: Account & URL
        card_acc = CardWidget()
        card_acc_l = QVBoxLayout(card_acc)
        card_acc_l.addWidget(self._section_title("账号与平台地址"))
        form_acc = QFormLayout()
        form_acc.setSpacing(10)

        self.entries["url"] = self._line_edit(self.cfg.get("url", ""))
        form_acc.addRow("主页入口 URL:", self.entries["url"])

        self.entries["username"] = self._line_edit(self.cfg.get("username", ""))
        form_acc.addRow("账号 (可选):", self.entries["username"])

        self.entries["password"] = self._line_edit(self.cfg.get("password", ""), password=True)
        form_acc.addRow("密码 (可选):", self.entries["password"])

        card_acc_l.addLayout(form_acc)
        form_layout.addWidget(card_acc)

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
            dwell_val = int(self.entries["min_dwell_seconds"].text().strip() or "0")
        except ValueError:
            dwell_val = 0

        typing_mode = "simulate" if self.combo_typing.currentIndex() == 1 else "fast"

        data = {
            "username": self.entries["username"].text().strip(),
            "password": self.entries["password"].text().strip(),
            "url": self.entries["url"].text().strip() or DEFAULT_CONFIG["url"],
            "typing_mode": typing_mode,
            "min_dwell_seconds": dwell_val,
            "enable_llm_subjective": self.cb_enable_llm.isChecked(),
            "subjective_default_text": self.entries["subjective_default_text"].text().strip(),
            "api_key": self.entries["api_key"].text().strip(),
            "base_url": self.entries["base_url"].text().strip() or "https://api.openai.com/v1",
            "model": self.entries["model"].text().strip() or "gpt-4o-mini",
            "temperature": float(self.cfg.get("temperature", 0.3)),
            "max_tokens": int(self.cfg.get("max_tokens", 4096)),
            "browser": self.entries["browser"].text().strip().lower() or "edge",
            "headless": self.cb_headless.isChecked(),
            "debug_mode": bool(self.cfg.get("debug_mode", False)),
            "tts_engine": str(self.cfg.get("tts_engine", "auto")),
            "tts_voice": str(self.cfg.get("tts_voice", "")),
            "tts_proxy": str(self.cfg.get("tts_proxy", "")),
        }

        save_config(data)
        InfoBar.success("保存成功", "配置已成功保存至 config.json", duration=1500, parent=self)
        self.accept()


def main():
    app = QApplication(sys.argv)
    dlg = ConfigEditorDialog()
    dlg.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
