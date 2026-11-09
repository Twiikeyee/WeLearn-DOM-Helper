# -*- coding: utf-8 -*-
"""
Fluent UI GUI for WeLearn-DOM-Helper.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import re
import sys
import threading
import time
import webbrowser
from typing import Dict, List, Optional, Set

from PyQt5.QtCore import QObject, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QShortcut,
)
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    MSFluentWindow,
    PrimaryPushButton,
    ProgressRing,
    PushButton,
    ScrollArea,
    SearchLineEdit,
    TextEdit,
    Theme,
    ToolButton,
    setTheme,
)
from qfluentwidgets.common.font import getFont, setFont as setWidgetFont


class _MainThreadBridge(QObject):
    invoke = pyqtSignal(object)


class _ClickableRow(QWidget):
    """Clickable row container to toggle collapse/expand state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_click = None
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and callable(self.on_click):
            self.on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class FluentModernGUI(MSFluentWindow):
    """Modern Fluent workbench for WeLearn automation."""

    def __init__(self, bot, app_globals: Optional[Dict] = None):
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        setTheme(Theme.DARK)
        super().__init__()

        self.bot = bot
        self._globals = app_globals or {}
        self.app_version = "1.0.0"
        self._closing = False

        self.gui_log_queue = bot.log_queue
        self._bridge = _MainThreadBridge()
        self._bridge.invoke.connect(lambda fn: fn())

        self._all_tabs: List[Dict] = []
        self._tab_widget_items: List[Dict] = []
        self._section_items: List[Dict] = []
        self._selected_tab_keys: Set[str] = set()
        self._auto_running = False
        self._quick_running = False
        self._labels = []
        self._panel_cards = []
        self._metric_boxes = []
        self.font_scale = 1.05

        self._init_window()
        self._build_ui()
        self._apply_theme()
        self.after(100, self._poll_logs)

    def systemTitleBarRect(self, size: QSize) -> QRect:
        if sys.platform == "darwin":
            # macOS traffic light position
            return QRect(10, 15, 75, 28)
        return super().systemTitleBarRect(size)

    def _init_window(self):
        self.setWindowTitle("WeLearn-DOM-Helper")
        self.resize(1300, 840)
        self.setMinimumSize(1040, 660)
        self.setMicaEffectEnabled(False)
        if sys.platform == "darwin":
            self.setSystemTitleBarButtonVisible(True)
        else:
            self.setSystemTitleBarButtonVisible(False)
        self.navigationInterface.hide()
        self.titleBar.raise_()
        self.titleBar.setTitle("")
        self.titleBar.titleLabel.hide()
        self.titleBar.setFixedHeight(40)

        try:
            QShortcut(QKeySequence("Ctrl+M"), self, self.showMinimized)
            QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        except Exception:
            pass

    def _build_ui(self):
        self.workbench = QWidget()
        self.workbench.setObjectName("workbench")
        self.stackedWidget.addWidget(self.workbench)
        self.stackedWidget.setCurrentWidget(self.workbench)

        root = QVBoxLayout(self.workbench)
        root.setContentsMargins(24, 0, 24, 20)
        root.setSpacing(12)

        # Top Strip
        top = QWidget()
        top.setObjectName("topStrip")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 6, 12, 6)
        top_layout.setSpacing(12)

        title_lbl = self._label("WeLearn-DOM-Helper", 24, "#f5f7fb", 800)
        top_layout.addWidget(title_lbl)

        ver_lbl = self._label(f"v{self.app_version}", 12, "#30d9ef", 700)
        ver_lbl.setStyleSheet("padding: 4px 8px; border-radius: 4px; background: rgba(48, 217, 239, 0.12);")
        top_layout.addWidget(ver_lbl)

        author_lbl = self._label("Based on UnipusAI-Helper by YSJohnson | AGPLv3", 12, "#c9d2dd", 500)
        author_lbl.setStyleSheet("padding: 4px 10px; border-radius: 4px; background: rgba(255, 255, 255, 0.05);")
        top_layout.addWidget(author_lbl)

        top_layout.addStretch(1)

        self.btn_config = PushButton("配置设置")
        self.btn_config.setIcon(FIF.SETTING)
        self.btn_config.clicked.connect(self._open_config_editor)
        top_layout.addWidget(self.btn_config)

        root.addWidget(top)

        # Status & Metric Cards
        metric_card = CardWidget()
        metric_layout = QHBoxLayout(metric_card)
        metric_layout.setContentsMargins(18, 12, 18, 12)
        metric_layout.setSpacing(20)

        self.metric_total = self._metric("总任务数", "0")
        self.metric_selected = self._metric("已勾选", "0")
        self.metric_done = self._metric("已完成", "0")
        self.metric_pending = self._metric("待完成", "0")

        metric_layout.addWidget(self.metric_total)
        metric_layout.addWidget(self.metric_selected)
        metric_layout.addWidget(self.metric_done)
        metric_layout.addWidget(self.metric_pending)
        metric_layout.addStretch(1)

        self.status_pill = self._status_pill("就绪", "#30d9ef")
        metric_layout.addWidget(self.status_pill)

        root.addWidget(metric_card)

        # Main Split Content: Left Task Tree, Right Log Terminal
        content_split = QHBoxLayout()
        content_split.setSpacing(14)

        # Left: Task Panel
        left_card = self._panel_card("任务目录树 (Unit -> Section -> SCO)")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_scan = PrimaryPushButton("扫描任务列表")
        self.btn_scan.setIcon(FIF.SYNC)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        toolbar.addWidget(self.btn_scan)

        self.btn_auto = PrimaryPushButton("处理选中任务 (0)")
        self.btn_auto.setIcon(FIF.PLAY)
        self.btn_auto.clicked.connect(self._on_auto_clicked)
        self.btn_auto.setEnabled(False)
        toolbar.addWidget(self.btn_auto)

        self.btn_quick = PushButton("快速处理当前页")
        self.btn_quick.setIcon(FIF.SEND)
        self.btn_quick.clicked.connect(self._on_quick_clicked)
        toolbar.addWidget(self.btn_quick)

        self.btn_stop = PushButton("停止")
        self.btn_stop.setIcon(FIF.PAUSE)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_stop.setEnabled(False)
        toolbar.addWidget(self.btn_stop)

        left_layout.addLayout(toolbar)

        # Search Bar
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("过滤任务名称、单元或 SCO ID...")
        self.search_box.textChanged.connect(self._filter_tabs)
        left_layout.addWidget(self.search_box)

        # Scrollable Task Tree Area
        self.task_scroll = ScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setStyleSheet("background: transparent; border: none;")

        self.task_list_container = QWidget()
        self._tab_list_layout = QVBoxLayout(self.task_list_container)
        self._tab_list_layout.setContentsMargins(0, 0, 0, 0)
        self._tab_list_layout.setSpacing(4)
        self._tab_list_layout.setAlignment(Qt.AlignTop)

        self.task_scroll.setWidget(self.task_list_container)
        left_layout.addWidget(self.task_scroll, 1)

        content_split.addWidget(left_card, 6)

        # Right: Log Terminal
        right_card = self._panel_card("运行日志")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(8)

        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #1a1c23; color: #d8dee9; font-family: 'JetBrains Mono', 'Menlo', 'Consolas', monospace; font-size: 13px; border-radius: 6px; padding: 8px; }"
        )
        right_layout.addWidget(self.log_text, 1)

        content_split.addWidget(right_card, 4)

        root.addLayout(content_split, 1)

    def _label(self, text, size=13, color="#f4f7fb", weight=400):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: {int(size * self.font_scale)}px; font-weight: {weight};")
        self._labels.append((lbl, size, weight))
        return lbl

    def _panel_card(self, title: str):
        card = CardWidget()
        header = QLabel(title)
        header.setStyleSheet("color: #aab2c0; font-size: 13px; font-weight: 600; padding: 6px 12px 0 12px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(header)
        return card

    def _metric(self, title: str, value: str):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("color: #30d9ef; font-size: 20px; font-weight: 700;")
        tit_lbl = QLabel(title)
        tit_lbl.setStyleSheet("color: #8c93a0; font-size: 12px;")
        layout.addWidget(val_lbl)
        layout.addWidget(tit_lbl)
        box.val_lbl = val_lbl
        return box

    def _status_pill(self, text: str, color: str):
        pill = QLabel(text)
        pill.setStyleSheet(
            f"color: {color}; background: rgba(48, 217, 239, 0.12); padding: 6px 14px; border-radius: 12px; font-weight: 600;"
        )
        return pill

    def _set_status(self, text: str, color: str = "#30d9ef"):
        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(
            f"color: {color}; background: rgba(48, 217, 239, 0.12); padding: 6px 14px; border-radius: 12px; font-weight: 600;"
        )

    def _apply_theme(self):
        self.setStyleSheet("""
            #workbench { background: #121318; }
            CardWidget { background: #1b1c24; border: 1px solid #282a36; border-radius: 8px; }
        """)

    def after(self, ms: int, callback):
        QTimer.singleShot(ms, callback)

    def mainloop(self):
        self.show()
        return self._qt_app.exec_()

    def _poll_logs(self):
        updated = False
        while not self.gui_log_queue.empty():
            try:
                msg = self.gui_log_queue.get_nowait()
                self.log_text.append(msg)
                updated = True
            except Exception:
                break
        if updated:
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        if not self._closing:
            self.after(100, self._poll_logs)

    def _open_config_editor(self):
        try:
            from config_editor import ConfigEditorDialog
            dlg = ConfigEditorDialog(self)
            dlg.exec_()
        except Exception as e:
            self.gui_log_queue.put(f"打开配置编辑器失败: {e}")

    def _on_scan_clicked(self):
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("扫描中...")
        self._set_status("扫描中...", "#ffb25f")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            tabs = self.bot.scan_catalog()
            self._bridge.invoke.emit(lambda: self._on_scan_completed(tabs))
        except Exception as e:
            self.gui_log_queue.put(f"扫描异常: {e}")
            self._bridge.invoke.emit(lambda: self._on_scan_completed([]))

    def _on_scan_completed(self, tabs: List[Dict]):
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("扫描任务列表")
        self._all_tabs = tabs
        self._build_tree_ui()

    def _build_tree_ui(self):
        # Clear existing
        while self._tab_list_layout.count():
            item = self._tab_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._tab_widget_items = []
        self._section_items = []
        self._selected_tab_keys.clear()

        if not self._all_tabs:
            empty_lbl = QLabel("未找到任务或尚未扫描。")
            empty_lbl.setStyleSheet("color: #7b8390; padding: 20px; font-size: 14px;")
            self._tab_list_layout.addWidget(empty_lbl)
            self._update_task_stats()
            return

        # Group by unit
        unit_groups: Dict[str, List[int]] = {}
        for idx, tab in enumerate(self._all_tabs):
            unit_name = tab.get("unit_label") or "默认单元"
            unit_groups.setdefault(unit_name, []).append(idx)

            # Pre-select undone tasks by default
            if tab.get("status") != "done":
                self._selected_tab_keys.add(self._tab_key(idx, tab))

        for unit_name, indices in unit_groups.items():
            self._tab_list_layout.addWidget(self._build_unit_widget(unit_name, indices))

        self._tab_list_layout.addStretch(1)
        self._update_task_stats()
        self.btn_auto.setEnabled(len(self._selected_tab_keys) > 0)
        self.btn_auto.setText(f"处理选中任务 ({len(self._selected_tab_keys)})")
        self._set_status("就绪", "#37d987")

    def _tab_key(self, idx: int, tab: Dict) -> str:
        return f"{idx}_{tab.get('scoid', '')}"

    def _build_unit_widget(self, unit_name: str, indices: List[int]) -> QWidget:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 2, 0, 2)
        container_layout.setSpacing(2)

        # Header row
        header = _ClickableRow()
        header.setStyleSheet("background: #20222c; border-radius: 6px; padding: 6px 10px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        arrow_lbl = QLabel("▾")
        arrow_lbl.setStyleSheet("color: #8c93a0; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(arrow_lbl)

        title_lbl = QLabel(unit_name)
        title_lbl.setStyleSheet("color: #f0f3f8; font-size: 14px; font-weight: 700;")
        header_layout.addWidget(title_lbl)

        count_done = sum(1 for i in indices if self._all_tabs[i].get("status") == "done")
        info_lbl = QLabel(f"共 {len(indices)} 个小节 · 已完成 {count_done}")
        info_lbl.setStyleSheet("color: #8c93a0; font-size: 12px;")
        header_layout.addWidget(info_lbl)
        header_layout.addStretch(1)

        container_layout.addWidget(header)

        # Body items
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 2, 0, 4)
        body_layout.setSpacing(2)

        for idx in indices:
            row_w = self._build_task_row(idx)
            body_layout.addWidget(row_w)

        container_layout.addWidget(body)

        def toggle():
            is_visible = body.isVisible()
            body.setVisible(not is_visible)
            arrow_lbl.setText("▸" if is_visible else "▾")

        header.on_click = toggle
        return container

    def _build_task_row(self, idx: int) -> QWidget:
        tab = self._all_tabs[idx]
        key = self._tab_key(idx, tab)

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 8, 2)
        row_layout.setSpacing(8)

        # Checkbox
        cb = CheckBox()
        cb.setChecked(key in self._selected_tab_keys)
        cb.stateChanged.connect(lambda state, k=key: self._on_checkbox_changed(k, state))
        row_layout.addWidget(cb)

        # Badge
        badge = QLabel("SCO")
        badge.setStyleSheet("color: #ffb25f; background: rgba(255, 178, 95, 0.15); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;")
        row_layout.addWidget(badge)

        # Task Name
        title = tab.get("l1_title") or tab.get("scoid", "")
        title_lbl = QLabel(f"{title} ({tab.get('scoid', '')})")
        title_lbl.setStyleSheet("color: #d8dee9; font-size: 13px;")
        row_layout.addWidget(title_lbl, 1)

        # Status Pill
        is_done = tab.get("status") == "done"
        st_lbl = QLabel(tab.get("status_text") or ("已完成" if is_done else "未完成"))
        st_color = "#37d987" if is_done else "#8c93a0"
        st_lbl.setStyleSheet(f"color: {st_color}; font-size: 11px; font-weight: 600; padding: 2px 8px;")
        row_layout.addWidget(st_lbl)

        item_meta = {
            "key": key,
            "idx": idx,
            "widget": row,
            "checkbox": cb,
            "status_label": st_lbl,
            "tab": tab,
        }
        self._tab_widget_items.append(item_meta)
        return row

    def _on_checkbox_changed(self, key: str, state: int):
        if state == Qt.Checked:
            self._selected_tab_keys.add(key)
        else:
            self._selected_tab_keys.discard(key)

        self._update_task_stats()
        self.btn_auto.setEnabled(len(self._selected_tab_keys) > 0)
        self.btn_auto.setText(f"处理选中任务 ({len(self._selected_tab_keys)})")

    def _update_task_stats(self):
        total = len(self._all_tabs)
        done = sum(1 for t in self._all_tabs if t.get("status") == "done")
        selected = len(self._selected_tab_keys)
        pending = total - done

        self.metric_total.val_lbl.setText(str(total))
        self.metric_selected.val_lbl.setText(str(selected))
        self.metric_done.val_lbl.setText(str(done))
        self.metric_pending.val_lbl.setText(str(pending))

    def _filter_tabs(self, text: str):
        query = text.strip().lower()
        for item in self._tab_widget_items:
            tab = item["tab"]
            scoid = tab.get("scoid", "").lower()
            title = (tab.get("l1_title") or "").lower()
            unit = (tab.get("unit_label") or "").lower()
            match = (not query) or (query in scoid) or (query in title) or (query in unit)
            item["widget"].setVisible(match)

    def _on_auto_clicked(self):
        if not self._selected_tab_keys:
            return

        selected_tabs = []
        for item in self._tab_widget_items:
            if item["key"] in self._selected_tab_keys:
                selected_tabs.append(item["tab"])

        if not selected_tabs:
            return

        self._auto_running = True
        self.btn_auto.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.btn_quick.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_status("自动化运行中...", "#ffb25f")

        threading.Thread(target=self._run_auto_thread, args=(selected_tabs,), daemon=True).start()

    def _run_auto_thread(self, selected_tabs: List[Dict]):
        try:
            self.bot.process_selected_tabs(
                selected_tabs,
                on_task_done=lambda tab: self._bridge.invoke.emit(lambda t=tab: self._on_task_completed(t))
            )
        except Exception as e:
            self.gui_log_queue.put(f"自动化异常: {e}")
        finally:
            self._bridge.invoke.emit(self._on_auto_finished)

    def _on_task_completed(self, tab: Dict):
        scoid = tab.get("scoid")
        for item in self._tab_widget_items:
            if item["tab"].get("scoid") == scoid:
                item["checkbox"].setChecked(False)
                item["status_label"].setText("已完成")
                item["status_label"].setStyleSheet("color: #37d987; font-size: 11px; font-weight: 600; padding: 2px 8px;")
                self._selected_tab_keys.discard(item["key"])
                break
        self._update_task_stats()
        self.btn_auto.setText(f"处理选中任务 ({len(self._selected_tab_keys)})")

    def _on_auto_finished(self):
        self._auto_running = False
        self.btn_auto.setEnabled(len(self._selected_tab_keys) > 0)
        self.btn_auto.setText(f"处理选中任务 ({len(self._selected_tab_keys)})")
        self.btn_scan.setEnabled(True)
        self.btn_quick.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("完成", "#37d987")
        InfoBar.success("任务结束", "选中的任务已处理完毕。", duration=2000, parent=self)

    def _on_quick_clicked(self):
        self.btn_quick.setEnabled(False)
        self._set_status("快速处理中...", "#ffb25f")
        threading.Thread(target=self._run_quick_thread, daemon=True).start()

    def _run_quick_thread(self):
        try:
            self.bot.quick_process_current_page()
        except Exception as e:
            self.gui_log_queue.put(f"快速处理异常: {e}")
        finally:
            self._bridge.invoke.emit(self._on_quick_finished)

    def _on_quick_finished(self):
        self.btn_quick.setEnabled(True)
        self._set_status("就绪", "#37d987")

    def _on_stop_clicked(self):
        self.bot.request_stop()
        self.btn_stop.setEnabled(False)
        self.gui_log_queue.put("已发送停止请求，等待当前小节收尾...")
