# -*- coding: utf-8 -*-
"""
WeLearn Configuration Editor GUI.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import json
import os
import sys

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QShortcut,
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
    ScrollArea,
    SpinBox,
    Theme,
    ToolButton,
    setTheme,
)

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "url": "https://welearn.sflep.com/2019/student/index.aspx",
    "typing_mode": "fast",
    "min_dwell_seconds": 0,
    "concurrency_mode": "serial",
    "target_total_seconds": 0,
    "max_concurrent_tabs": 3,
    "enable_llm_subjective": False,
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

CONCURRENCY_MODES = [
    ("serial", "串联顺序模式 (Serial - 单标签页逐个作答与提交，基线模式)"),
    ("decoupled", "答题/挂机解耦并发 (Decoupled - 单路顺序提交答案 + 多标签页纯挂时长，防时间轴检测)"),
    ("pipeline", "错峰流水线并发 (Pipeline - 多标签页并行作答挂机 + 保序错峰提交锁，高效率)"),
]

PALETTE = {
    "bg": "#17191d",
    "panel": "#202328",
    "panel_border": "#2c3138",
    "top": "#202328",
    "input": "#14171b",
    "input_border": "#303640",
    "text": "#f4f7fb",
    "muted": "#a7b0bb",
    "cyan": "#30d9ef",
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


class ConfigEditor(QWidget):
    """Standalone Configuration Editor for WeLearn-DOM-Helper."""

    def __init__(self, parent=None, on_saved=None):
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        setTheme(Theme.DARK)
        super().__init__(parent)
        self.cfg = load_config()
        self.entries = {}
        self.on_saved = on_saved
        self._drag_active = False
        self._drag_position = QPoint()
        self._init_window()
        self._build_ui()
        self._apply_theme()

    def _init_window(self):
        self.setObjectName("windowRoot")
        self.setWindowTitle("WeLearn-DOM-Helper 配置编辑器")
        self.resize(860, 860)
        self.setMinimumSize(720, 680)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        try:
            QShortcut(QKeySequence("Ctrl+M"), self, self.showMinimized)
            QShortcut(QKeySequence("Ctrl+W"), self, self.close)
            QShortcut(QKeySequence("Esc"), self, self.close)
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 24)
        root.setSpacing(14)

        root.addWidget(self._build_top_strip())
        root.addWidget(self._build_form_area(), 1)

    def _build_top_strip(self):
        self.top_strip = QFrame()
        self.top_strip.setObjectName("topStrip")
        self.top_strip.installEventFilter(self)
        layout = QHBoxLayout(self.top_strip)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        self.title_label = QLabel("WeLearn-DOM-Helper 配置编辑器")
        self.title_label.setObjectName("pageTitle")
        self.title_label.installEventFilter(self)
        layout.addWidget(self.title_label)

        sub_tag = QLabel("独立配置控制台")
        sub_tag.setStyleSheet(
            f"color: {PALETTE['cyan']}; font-size: 11px; font-weight: 600; "
            "padding: 2px 8px; border-radius: 4px; background: rgba(48, 217, 239, 0.12);"
        )
        layout.addWidget(sub_tag)

        layout.addStretch(1)

        self.min_btn = ToolButton(FIF.MINIMIZE)
        self.min_btn.setToolTip("最小化")
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(self.min_btn)

        self.close_btn = ToolButton(FIF.CLOSE)
        self.close_btn.setToolTip("关闭")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        return self.top_strip

    def _build_form_area(self):
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setObjectName("contentHost")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)

        # Section 1: 运行模式与答题效率
        card_eff, form_eff = self._create_card("运行模式、并发策略与目标总时长")

        self.combo_concurrency = ComboBox()
        for _, label in CONCURRENCY_MODES:
            self.combo_concurrency.addItem(label)
        curr_conc = str(self.cfg.get("concurrency_mode", "serial")).lower()
        conc_idx = next((i for i, (k, _) in enumerate(CONCURRENCY_MODES) if k == curr_conc), 0)
        self.combo_concurrency.setCurrentIndex(conc_idx)
        form_eff.addRow(self._field_label("并发方式选择"), self.combo_concurrency)

        target_row = QWidget()
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(12)

        self.spin_target_total = SpinBox()
        self.spin_target_total.setRange(0, 360000)
        self.spin_target_total.setSingleStep(60)
        self.spin_target_total.setValue(int(self.cfg.get("target_total_seconds", 0) or 0))
        self.spin_target_total.setToolTip(
            "填 0 表示不启用总时长分摊；填 >0（如测试填 12 秒，正式跑课填 3600 秒=1小时）将自动扣除已学时长并随机分摊至各选中任务"
        )
        target_layout.addWidget(self.spin_target_total)

        self.lbl_target_hint = QLabel("")
        self.lbl_target_hint.setStyleSheet(f"color: {PALETTE['cyan']}; font-size: 12px;")
        target_layout.addWidget(self.lbl_target_hint, 1)
        self.spin_target_total.valueChanged.connect(self._update_target_hint)
        self._update_target_hint(self.spin_target_total.value())
        form_eff.addRow(self._field_label("目标总时长 (秒)"), target_row)

        self.spin_tabs = SpinBox()
        self.spin_tabs.setRange(1, 6)
        self.spin_tabs.setValue(max(1, min(6, int(self.cfg.get("max_concurrent_tabs", 3) or 3))))
        self.spin_tabs.setToolTip("并发模式下同时打开的浏览器标签页数量（推荐 2~4 个，模拟真人多开标签页）")
        form_eff.addRow(self._field_label("并发标签页上限"), self.spin_tabs)

        self.combo_typing = ComboBox()
        self.combo_typing.addItem("快速注入 (Fast - 0ms DOM数据绑定注入，极速免等待)")
        self.combo_typing.addItem("模拟按键 (Simulate - 逐字符物理打字击键，模拟真人输入)")
        curr_typing = str(self.cfg.get("typing_mode", "fast")).lower()
        self.combo_typing.setCurrentIndex(1 if curr_typing == "simulate" else 0)
        form_eff.addRow(self._field_label("填空输入模式"), self.combo_typing)

        self.spin_dwell = SpinBox()
        self.spin_dwell.setRange(0, 7200)
        self.spin_dwell.setValue(int(self.cfg.get("min_dwell_seconds", 0)))
        self.spin_dwell.setToolTip("单小节保底最少停留秒数（填 0 为极速作答；若已设置目标总时长，则优先按目标总时长智能分摊）")
        form_eff.addRow(self._field_label("单小节保底停留 (秒)"), self.spin_dwell)

        self.combo_browser = ComboBox()
        self.combo_browser.addItem("edge")
        self.combo_browser.addItem("chrome")
        curr_browser = str(self.cfg.get("browser", "edge")).lower()
        self.combo_browser.setCurrentText(curr_browser if curr_browser in ("edge", "chrome") else "edge")
        form_eff.addRow(self._field_label("自动化浏览器"), self.combo_browser)

        self.cb_headless = CheckBox("开启无头模式 (Headless - 后台静默无界面运行)")
        self.cb_headless.setChecked(bool(self.cfg.get("headless", False)))
        form_eff.addRow(self._field_label("后台静默运行"), self.cb_headless)
        content_layout.addWidget(card_eff)

        # Section 2: 主观题与大模型设置 (零 Token 模式)
        card_llm, form_llm = self._create_card("主观题与大模型设置 (零 Token 模式可选)")
        self.cb_enable_llm = CheckBox("启用 LLM 辅助主观题作答 (若关闭，则直接填入下方通用学术范句，实现 0 Token 消耗)")
        self.cb_enable_llm.setChecked(bool(self.cfg.get("enable_llm_subjective", False)))
        form_llm.addRow(self._field_label("LLM 智能回答开关"), self.cb_enable_llm)

        self._add_text_row(
            form_llm,
            "subjective_default_text",
            "免 Token 学术通用范文",
            "开放主观题填入的默认范文内容",
            multiline=True,
        )
        self._add_text_row(form_llm, "api_key", "API Key (可选)", "sk-...", password=True)
        self._add_text_row(form_llm, "base_url", "API 地址", "兼容 OpenAI 规范，如 https://api.openai.com/v1")
        self._add_text_row(form_llm, "model", "模型名称", "gpt-4o-mini / qwen-turbo 等")
        self._add_text_row(form_llm, "temperature", "生成温度 (0-2)", "0.3")
        self._add_text_row(form_llm, "max_tokens", "最大 Token 数", "4096")
        content_layout.addWidget(card_llm)

        # Section 3: 账号与平台地址
        card_acc, form_acc = self._create_card("账号凭据与登录地址")
        self._add_text_row(form_acc, "url", "登录地址", "https://welearn.sflep.com/2019/student/index.aspx")
        self._add_text_row(form_acc, "username", "WeLearn 账号 (可选)", "已在 Edge 中登录可留空自动继承会话")
        self._add_text_row(form_acc, "password", "WeLearn 密码 (可选)", "仅在需自动登录时填写", password=True)
        content_layout.addWidget(card_acc)

        # Section 4: 语音合成 (TTS) 与调试
        card_tts, form_tts = self._create_card("语音 (TTS) 与调试模式")
        self._add_text_row(form_tts, "tts_engine", "录音题 TTS 引擎", "auto / edge / mac / sapi / off")
        self._add_text_row(form_tts, "tts_voice", "TTS 音色 (可选)", "如 en-US-AriaNeural")
        self._add_text_row(form_tts, "tts_proxy", "TTS 代理 (可选)", "如 http://127.0.0.1:7890")

        self.cb_debug = CheckBox("开启调试日志输出")
        self.cb_debug.setChecked(bool(self.cfg.get("debug_mode", False)))
        form_tts.addRow(self._field_label("调试模式"), self.cb_debug)
        content_layout.addWidget(card_tts)

        # Bottom Action Bar
        action_row = QHBoxLayout()
        action_row.addStretch(1)

        self.cancel_btn = ToolButton(FIF.CANCEL)
        self.cancel_btn.setText(" 取消")
        self.cancel_btn.clicked.connect(self.close)
        action_row.addWidget(self.cancel_btn)

        self.save_btn = PrimaryPushButton(" 保存配置")
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self.save_btn)

        content_layout.addLayout(action_row)

        scroll.setWidget(content)
        return scroll

    def _create_card(self, title: str):
        card = CardWidget()
        card.setObjectName("panelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QLabel(title)
        header.setStyleSheet(f"color: {PALETTE['cyan']}; font-size: 14px; font-weight: 700; padding-bottom: 4px;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        layout.addLayout(form)
        return card, form

    def _field_label(self, title_text: str) -> QLabel:
        title = QLabel(title_text)
        title.setObjectName("fieldTitle")
        return title

    def _create_input(self, key: str, placeholder: str, multiline: bool = False, password: bool = False):
        if multiline:
            entry = PlainTextEdit()
            entry.setFixedHeight(90)
            entry.setPlaceholderText(placeholder)
            entry.setPlainText(str(self.cfg.get(key, "") or ""))
        else:
            entry = LineEdit()
            entry.setPlaceholderText(placeholder)
            entry.setText(str(self.cfg.get(key, "") or ""))
            entry.setClearButtonEnabled(True)
            if password:
                entry.setEchoMode(LineEdit.Password)
        self.entries[key] = entry
        return entry

    def _add_text_row(self, form: QFormLayout, key: str, title: str, placeholder: str, multiline: bool = False, password: bool = False):
        entry = self._create_input(key, placeholder, multiline=multiline, password=password)
        form.addRow(self._field_label(title), entry)

    def _apply_theme(self):
        self.setStyleSheet(
            f"""
            QWidget#windowRoot {{
                background: {PALETTE['bg']};
            }}
            QFrame#topStrip {{
                background: {PALETTE['top']};
                border: 1px solid {PALETTE['panel_border']};
                border-radius: 8px;
            }}
            QLabel#pageTitle {{
                color: {PALETTE['text']};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#fieldTitle {{
                color: {PALETTE['muted']};
                font-size: 13px;
                font-weight: 600;
            }}
            QWidget#panelCard {{
                background: {PALETTE['panel']};
                border: 1px solid {PALETTE['panel_border']};
                border-radius: 8px;
            }}
            """
        )

    def eventFilter(self, obj, event):
        if obj in (self.top_strip, getattr(self, "title_label", None)):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_active = True
                self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                return True
            elif event.type() == QEvent.MouseMove and self._drag_active:
                self.move(event.globalPos() - self._drag_position)
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._drag_active = False
                return True
        return super().eventFilter(obj, event)

    def _update_target_hint(self, val: int):
        if val <= 0:
            self.lbl_target_hint.setText("未启用总时长分摊（仅按单小节保底停留秒数执行）")
        elif val < 60:
            self.lbl_target_hint.setText(f"自动扣除已学时长后随机分摊至选中任务（共 {val} 秒，适合快速测试）")
        else:
            mins = val / 60.0
            hrs = val / 3600.0
            self.lbl_target_hint.setText(f"自动扣除已学时长后随机分摊（约 {mins:.1f} 分钟 / {hrs:.2f} 小时）")

    def _on_save(self):
        data = {}
        for key, entry in self.entries.items():
            if isinstance(entry, PlainTextEdit):
                data[key] = entry.toPlainText().strip()
            else:
                data[key] = entry.text().strip()

        # Add Combobox and Checkbox items
        conc_idx = self.combo_concurrency.currentIndex()
        if 0 <= conc_idx < len(CONCURRENCY_MODES):
            data["concurrency_mode"] = CONCURRENCY_MODES[conc_idx][0]
        else:
            data["concurrency_mode"] = "serial"

        data["target_total_seconds"] = int(self.spin_target_total.value())
        data["max_concurrent_tabs"] = int(self.spin_tabs.value())
        data["typing_mode"] = "simulate" if self.combo_typing.currentIndex() == 1 else "fast"
        data["min_dwell_seconds"] = int(self.spin_dwell.value())
        data["browser"] = self.combo_browser.currentText().strip().lower() or "edge"
        data["headless"] = self.cb_headless.isChecked()
        data["enable_llm_subjective"] = self.cb_enable_llm.isChecked()
        data["debug_mode"] = self.cb_debug.isChecked()

        try:
            data["max_tokens"] = int(data.get("max_tokens") or 4096)
        except Exception:
            data["max_tokens"] = 4096

        try:
            data["temperature"] = float(data.get("temperature") or 0.3)
        except Exception:
            data["temperature"] = 0.3

        try:
            save_config(data)
            if callable(self.on_saved):
                try:
                    self.on_saved(data)
                except Exception:
                    pass
            InfoBar.success(
                "保存成功",
                "配置已成功保存到 config.json",
                duration=2000,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )
        except Exception as e:
            MessageBox("保存失败", str(e), self).exec()
            InfoBar.error(
                "保存失败",
                str(e),
                duration=2400,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key_S and event.modifiers() & Qt.ControlModifier:
            self._on_save()
            return
        super().keyPressEvent(event)

    def run(self):
        self.show()
        return self._qt_app.exec_()


# Alias for compatibility if imported as Dialog
ConfigEditorDialog = ConfigEditor


def main():
    editor = ConfigEditor()
    editor.run()


if __name__ == "__main__":
    main()
