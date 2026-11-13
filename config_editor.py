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

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
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
    DoubleSpinBox,
    FluentIcon as FIF,
    FluentWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PasswordLineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SpinBox,
)

from ui_common import GLOBAL_QSS, PALETTE, MacTrafficLightMixin, ensure_qapp

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
    ("decoupled", "答题/挂机解耦并发 (Decoupled - 单路顺序提交答案 + 多标签页挂时长)"),
    ("pipeline", "错峰流水线并发 (Pipeline - 多标签页并行作答 + 保序提交锁，高效率)"),
]

TTS_ENGINES = [
    ("auto", "auto - 自动选择"),
    ("edge", "edge - Edge 在线语音"),
    ("mac", "mac - macOS say"),
    ("sapi", "sapi - Windows SAPI"),
    ("off", "off - 关闭"),
]


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config() -> dict:
    """Load config.json (or the example) merged on top of defaults."""
    merged = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        merged.update(_read_json(CONFIG_PATH))
    elif os.path.exists(EXAMPLE_PATH):
        merged.update(_read_json(EXAMPLE_PATH))
    return merged


def save_config(data: dict) -> bool:
    """Persist config in plain text to config.json, preserving unknown keys."""
    final = _read_json(CONFIG_PATH) if os.path.exists(CONFIG_PATH) else {}
    final.update(data)
    final.pop("secrets_in_keyring", None)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    return True


class ConfigEditor(MacTrafficLightMixin, FluentWidget):
    """Standalone Configuration Editor for WeLearn-DOM-Helper.

    Uses a frameless Fluent window: native traffic lights on macOS,
    Fluent min/max/close buttons on Windows; resizable on every platform.
    """

    def __init__(self, parent=None, on_saved=None):
        self._qt_app = ensure_qapp()
        super().__init__(parent)
        self.cfg = load_config()
        self.entries = {}
        self.on_saved = on_saved
        self._dirty = False
        self._loading = True
        self._init_window()
        self._build_ui()
        self._apply_theme()
        self._update_dependent_states()
        self._loading = False

    # ------------------------------------------------------------------ #
    # Window & layout
    # ------------------------------------------------------------------ #
    def _init_window(self):
        self.setObjectName("windowRoot")
        self.setWindowTitle("WeLearn-DOM-Helper 配置编辑器")
        self.resize(860, 860)
        self.setMinimumSize(720, 600)
        self.setCustomBackgroundColor(PALETTE["bg"], PALETTE["bg"])
        self.titleBar.titleLabel.hide()
        self.titleBar.iconLabel.hide()

        QShortcut(QKeySequence("Ctrl+M"), self, self.showMinimized)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence("Esc"), self, self.close)
        QShortcut(QKeySequence.Save, self, self._on_save)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, self.titleBar.height() + 8, 28, 24)
        root.setSpacing(14)

        root.addWidget(self._build_top_strip())
        root.addWidget(self._build_form_area(), 1)
        root.addLayout(self._build_action_row())
        self.titleBar.raise_()

    def _build_top_strip(self):
        self.top_strip = QFrame()
        self.top_strip.setObjectName("topStrip")
        layout = QHBoxLayout(self.top_strip)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.title_label = QLabel("WeLearn-DOM-Helper 配置编辑器")
        self.title_label.setObjectName("pageTitle")
        layout.addWidget(self.title_label)

        sub_tag = QLabel("独立配置控制台")
        sub_tag.setObjectName("subTag")
        layout.addWidget(sub_tag)

        layout.addStretch(1)

        self.dirty_tag = QLabel("● 未保存")
        self.dirty_tag.setStyleSheet(f"color: {PALETTE['orange']}; font-size: 12px; font-weight: 600;")
        self.dirty_tag.setVisible(False)
        layout.addWidget(self.dirty_tag)
        return self.top_strip

    def _build_form_area(self):
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setObjectName("contentHost")
        content.setStyleSheet("QWidget#contentHost { background: transparent; }")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)

        # Section 1: 答题效率与学时策略
        card_eff, form_eff = self._create_card("答题效率与时长挂机策略")

        # Concurrency controls are kept in memory for backward compatibility
        # but omitted from the UI form to enforce single-tab serial mode cleanly.
        self.combo_concurrency = ComboBox()
        for _, label in CONCURRENCY_MODES:
            self.combo_concurrency.addItem(label)
        self.combo_concurrency.setCurrentIndex(0)
        self.combo_concurrency.currentIndexChanged.connect(self._update_dependent_states)
        # (Omitted from form_eff: form_eff.addRow(..., self.combo_concurrency))

        target_row = QWidget()
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(12)

        self.spin_target_total = SpinBox()
        self.spin_target_total.setRange(0, 360000)
        self.spin_target_total.setSingleStep(60)
        self.spin_target_total.setValue(int(self.cfg.get("target_total_seconds", 0) or 0))
        self.spin_target_total.setToolTip(
            "填 0 表示不启用总时长分摊；填 >0（如 3600 秒=1小时）将自动扣除已学时长并随机分摊至各选中任务"
        )
        target_layout.addWidget(self.spin_target_total)

        self.lbl_target_hint = QLabel("")
        self.lbl_target_hint.setWordWrap(True)
        self.lbl_target_hint.setStyleSheet(f"color: {PALETTE['cyan']}; font-size: 12px;")
        target_layout.addWidget(self.lbl_target_hint, 1)
        self.spin_target_total.valueChanged.connect(self._update_target_hint)
        self._update_target_hint(self.spin_target_total.value())
        form_eff.addRow(self._field_label("目标总时长 (秒)"), target_row)

        self.spin_tabs = SpinBox()
        self.spin_tabs.setRange(1, 6)
        self.spin_tabs.setValue(1)
        # (Omitted from form_eff: form_eff.addRow(..., self.spin_tabs))

        self.combo_typing = ComboBox()
        self.combo_typing.addItem("快速注入 (Fast - DOM 数据绑定注入，免等待)")
        self.combo_typing.addItem("模拟按键 (Simulate - 逐字符击键输入)")
        curr_typing = str(self.cfg.get("typing_mode", "fast")).lower()
        self.combo_typing.setCurrentIndex(1 if curr_typing == "simulate" else 0)
        form_eff.addRow(self._field_label("填空输入模式"), self.combo_typing)

        self.spin_dwell = SpinBox()
        self.spin_dwell.setRange(0, 7200)
        self.spin_dwell.setValue(int(self.cfg.get("min_dwell_seconds", 0) or 0))
        self.spin_dwell.setToolTip("单小节保底最少停留秒数（填 0 为不额外等待；若已设置目标总时长，则优先按目标总时长分摊）")
        form_eff.addRow(self._field_label("单小节保底停留 (秒)"), self.spin_dwell)

        self.combo_browser = ComboBox()
        self.combo_browser.addItems(["edge", "chrome"])
        curr_browser = str(self.cfg.get("browser", "edge")).lower()
        self.combo_browser.setCurrentText(curr_browser if curr_browser in ("edge", "chrome") else "edge")
        form_eff.addRow(self._field_label("自动化浏览器"), self.combo_browser)

        self.cb_headless = CheckBox("开启无头模式 (Headless - 后台无界面运行)")
        self.cb_headless.setChecked(bool(self.cfg.get("headless", False)))
        form_eff.addRow(self._field_label("后台静默运行"), self.cb_headless)
        content_layout.addWidget(card_eff)

        # Section 2: 主观题与大模型设置
        card_llm, form_llm = self._create_card("主观题与大模型设置 (零 Token 模式可选)")
        self.cb_enable_llm = CheckBox("启用 LLM 辅助主观题作答 (关闭时直接填入下方通用范句，0 Token 消耗)")
        self.cb_enable_llm.setChecked(bool(self.cfg.get("enable_llm_subjective", False)))
        self.cb_enable_llm.stateChanged.connect(self._update_dependent_states)
        form_llm.addRow(self._field_label("LLM 智能回答开关"), self.cb_enable_llm)

        self._add_text_row(
            form_llm,
            "subjective_default_text",
            "免 Token 通用范文",
            "开放主观题填入的默认范文内容",
            multiline=True,
        )
        self._add_text_row(form_llm, "api_key", "API Key", "sk-...", password=True)
        self._add_text_row(form_llm, "base_url", "API 地址", "兼容 OpenAI 规范，如 https://api.openai.com/v1")
        self._add_text_row(form_llm, "model", "模型名称", "gpt-4o-mini / qwen-turbo 等")

        self.spin_temperature = DoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.1)
        self.spin_temperature.setDecimals(2)
        self.spin_temperature.setValue(self._safe_float(self.cfg.get("temperature"), 0.3))
        self.lbl_temperature = self._field_label("生成温度 (0-2)")
        form_llm.addRow(self.lbl_temperature, self.spin_temperature)

        self.spin_max_tokens = SpinBox()
        self.spin_max_tokens.setRange(1, 128000)
        self.spin_max_tokens.setSingleStep(256)
        self.spin_max_tokens.setValue(self._safe_int(self.cfg.get("max_tokens"), 4096))
        self.lbl_max_tokens = self._field_label("最大 Token 数")
        form_llm.addRow(self.lbl_max_tokens, self.spin_max_tokens)
        content_layout.addWidget(card_llm)

        # Section 3: 账号与平台地址
        card_acc, form_acc = self._create_card("账号凭据与登录地址")
        self._add_text_row(form_acc, "url", "登录地址", "https://welearn.sflep.com/2019/student/index.aspx")
        self._add_text_row(form_acc, "username", "WeLearn 账号 (可选)", "已在浏览器中登录可留空自动继承会话")
        self._add_text_row(form_acc, "password", "WeLearn 密码 (可选)", "仅在需自动登录时填写", password=True)
        content_layout.addWidget(card_acc)

        # Section 4: 语音合成 (TTS) 与调试
        card_tts, form_tts = self._create_card("语音 (TTS) 与调试模式")
        self.combo_tts = ComboBox()
        for _, label in TTS_ENGINES:
            self.combo_tts.addItem(label)
        curr_tts = str(self.cfg.get("tts_engine", "auto") or "auto").lower()
        self.combo_tts.setCurrentIndex(next((i for i, (k, _) in enumerate(TTS_ENGINES) if k == curr_tts), 0))
        form_tts.addRow(self._field_label("录音题 TTS 引擎"), self.combo_tts)
        self._add_text_row(form_tts, "tts_voice", "TTS 音色 (可选)", "如 en-US-AriaNeural")
        self._add_text_row(form_tts, "tts_proxy", "TTS 代理 (可选)", "如 http://127.0.0.1:7890")

        self.cb_debug = CheckBox("开启调试日志输出")
        self.cb_debug.setChecked(bool(self.cfg.get("debug_mode", False)))
        form_tts.addRow(self._field_label("调试模式"), self.cb_debug)
        content_layout.addWidget(card_tts)
        content_layout.addStretch(1)

        self._connect_dirty_signals()

        scroll.setWidget(content)
        return scroll

    def _build_action_row(self):
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        shortcut_hint = QLabel("⌘S / Ctrl+S 保存 · Esc 关闭" if sys.platform == "darwin" else "Ctrl+S 保存 · Esc 关闭")
        shortcut_hint.setObjectName("hintLabel")
        action_row.addWidget(shortcut_hint)
        action_row.addStretch(1)

        self.cancel_btn = PushButton("取消")
        self.cancel_btn.setIcon(FIF.CANCEL)
        self.cancel_btn.clicked.connect(self.close)
        action_row.addWidget(self.cancel_btn)

        self.save_btn = PushButton("保存")
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self.save_btn)

        self.save_close_btn = PrimaryPushButton("保存并关闭")
        self.save_close_btn.setIcon(FIF.ACCEPT)
        self.save_close_btn.clicked.connect(self._on_save_and_close)
        action_row.addWidget(self.save_close_btn)
        return action_row

    def _create_card(self, title: str):
        card = CardWidget()
        card.setObjectName("panelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QLabel(title)
        header.setObjectName("cardTitle")
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
            entry = PasswordLineEdit() if password else LineEdit()
            entry.setPlaceholderText(placeholder)
            entry.setText(str(self.cfg.get(key, "") or ""))
            if not password:
                entry.setClearButtonEnabled(True)
        self.entries[key] = entry
        return entry

    def _add_text_row(self, form: QFormLayout, key: str, title: str, placeholder: str, multiline: bool = False, password: bool = False):
        entry = self._create_input(key, placeholder, multiline=multiline, password=password)
        label = self._field_label(title)
        entry.setProperty("fieldLabel", label)
        form.addRow(label, entry)

    def _apply_theme(self):
        self.setStyleSheet(
            GLOBAL_QSS
            + f"""
            QFrame#topStrip {{
                background: {PALETTE['panel']};
                border: 1px solid {PALETTE['panel_border']};
                border-radius: 8px;
            }}
            QWidget#panelCard {{
                background: {PALETTE['panel']};
                border: 1px solid {PALETTE['panel_border']};
                border-radius: 8px;
            }}
            QLabel#fieldTitle:disabled {{ color: #5b6270; }}
            """
        )

    # ------------------------------------------------------------------ #
    # State helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _connect_dirty_signals(self):
        for entry in self.entries.values():
            entry.textChanged.connect(self._mark_dirty)
        for combo in (self.combo_concurrency, self.combo_typing, self.combo_browser, self.combo_tts):
            combo.currentIndexChanged.connect(self._mark_dirty)
        for spin in (self.spin_target_total, self.spin_tabs, self.spin_dwell, self.spin_temperature, self.spin_max_tokens):
            spin.valueChanged.connect(self._mark_dirty)
        for cb in (self.cb_headless, self.cb_enable_llm, self.cb_debug):
            cb.stateChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self.dirty_tag.setVisible(dirty)
        base = "WeLearn-DOM-Helper 配置编辑器"
        self.setWindowTitle(f"{base} *" if dirty else base)

    def _update_dependent_states(self, *_):
        is_serial = CONCURRENCY_MODES[self.combo_concurrency.currentIndex()][0] == "serial"
        self.spin_tabs.setEnabled(not is_serial)

        llm_on = self.cb_enable_llm.isChecked()
        for key in ("api_key", "base_url", "model"):
            entry = self.entries.get(key)
            if entry is not None:
                entry.setEnabled(llm_on)
                label = entry.property("fieldLabel")
                if label is not None:
                    label.setEnabled(llm_on)
        for widget in (self.spin_temperature, self.spin_max_tokens, self.lbl_temperature, self.lbl_max_tokens):
            widget.setEnabled(llm_on)

    def _update_target_hint(self, val: int):
        if val <= 0:
            self.lbl_target_hint.setText("未启用总时长分摊（仅按单小节保底停留秒数执行）")
        elif val < 60:
            self.lbl_target_hint.setText(f"自动扣除已学时长后随机分摊至选中任务（共 {val} 秒）")
        else:
            mins = val / 60.0
            hrs = val / 3600.0
            self.lbl_target_hint.setText(f"自动扣除已学时长后随机分摊（约 {mins:.1f} 分钟 / {hrs:.2f} 小时）")

    # ------------------------------------------------------------------ #
    # Save / close
    # ------------------------------------------------------------------ #
    def _collect_data(self) -> dict:
        data = {}
        for key, entry in self.entries.items():
            if isinstance(entry, PlainTextEdit):
                data[key] = entry.toPlainText().strip()
            else:
                data[key] = entry.text().strip()

        # Force serial mode and single tab for release stability
        data["concurrency_mode"] = "serial"
        data["max_concurrent_tabs"] = 1
        data["target_total_seconds"] = int(self.spin_target_total.value())
        data["typing_mode"] = "simulate" if self.combo_typing.currentIndex() == 1 else "fast"
        data["min_dwell_seconds"] = int(self.spin_dwell.value())
        data["browser"] = self.combo_browser.currentText().strip().lower() or "edge"
        data["headless"] = self.cb_headless.isChecked()
        data["enable_llm_subjective"] = self.cb_enable_llm.isChecked()
        data["debug_mode"] = self.cb_debug.isChecked()
        data["temperature"] = round(float(self.spin_temperature.value()), 2)
        data["max_tokens"] = int(self.spin_max_tokens.value())
        tts_idx = self.combo_tts.currentIndex()
        data["tts_engine"] = TTS_ENGINES[tts_idx][0] if 0 <= tts_idx < len(TTS_ENGINES) else "auto"
        return data

    def _on_save(self) -> bool:
        data = self._collect_data()
        try:
            save_config(data)
        except Exception as e:
            MessageBox("保存失败", str(e), self).exec()
            return False

        self.cfg.update(data)
        self._set_dirty(False)
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
        return True

    def _on_save_and_close(self):
        if self._on_save():
            self.close()

    def closeEvent(self, event):
        if self._dirty:
            box = MessageBox("有未保存的修改", "是否在关闭前保存当前配置？", self)
            box.yesButton.setText("保存")
            box.cancelButton.setText("不保存")
            # Esc / reject (0) => keep editing; explicit "不保存" => 3
            box.cancelButton.clicked.disconnect()
            box.cancelButton.clicked.connect(lambda: box.done(3))
            back_btn = PushButton("返回编辑")
            back_btn.clicked.connect(box.reject)
            box.buttonLayout.addWidget(back_btn)
            result = box.exec()
            if result == 0:
                event.ignore()
                return
            if result == 1 and not self._on_save():
                event.ignore()
                return
            self._set_dirty(False)
        super().closeEvent(event)

    def run(self):
        self.show()
        return self._qt_app.exec_()


# Alias for compatibility if imported as Dialog
ConfigEditorDialog = ConfigEditor


def main():
    editor = ConfigEditor()
    sys.exit(editor.run())


if __name__ == "__main__":
    main()
