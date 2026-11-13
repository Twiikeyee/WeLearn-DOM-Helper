# -*- coding: utf-8 -*-
"""
Fluent UI GUI for WeLearn-DOM-Helper.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import os
import sys
import threading
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QShortcut,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    MSFluentWindow,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SearchLineEdit,
    TextEdit,
    TransparentPushButton,
    TransparentToolButton,
    TreeWidget,
)
from qfluentwidgets.common.font import getFont

from ui_common import GLOBAL_QSS, PALETTE, MacTrafficLightMixin, ensure_qapp, rgba
from version import __version__
from welearn_bot import DurationPlanner

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")

LOG_MAX_BLOCKS = 5000
LOG_MAX_PER_TICK = 400

ROLE_TAB_IDX = Qt.UserRole + 1

_LOG_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("异常", "失败", "错误", "Error", "ERROR", "Traceback"), PALETTE["red"]),
    (("警告", "WARN", "停止", "跳过", "超时", "等待登录"), PALETTE["orange"]),
    (("成功", "完成", "就绪", "已建立"), PALETTE["green"]),
    (("======",), PALETTE["cyan"]),
]


def _log_color(msg: str) -> str:
    for keywords, color in _LOG_RULES:
        if any(k in msg for k in keywords):
            return color
    return PALETTE["text_soft"]


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds / 60:.0f} 分钟"
    return f"{seconds / 3600:.1f} 小时"


class _MainThreadBridge(QObject):
    invoke = pyqtSignal(object)


class FluentModernGUI(MacTrafficLightMixin, MSFluentWindow):
    """Modern Fluent workbench for WeLearn automation."""

    def __init__(self, bot, app_globals: Optional[Dict] = None):
        self._qt_app = ensure_qapp()
        super().__init__()

        self.bot = bot
        self._globals = app_globals or {}
        self.app_version = __version__
        self._closing = False

        self.gui_log_queue = bot.log_queue
        self._bridge = _MainThreadBridge()
        self._bridge.invoke.connect(lambda fn: fn())

        # Data owned by the GUI thread only (bot works on copies).
        self._all_tabs: List[Dict] = []
        self._leaf_items: Dict[int, QTreeWidgetItem] = {}
        self._units: List[Tuple[QTreeWidgetItem, str, List[int]]] = []
        self._selected_idx: Set[int] = set()
        self._sync_pending = False

        # Run state
        self._busy: Optional[str] = None  # None | "scan" | "auto" | "quick"
        self._driver_ready = False
        self._startup_done = False
        self._run_scoid_map: Dict[str, int] = {}
        self._run_total = 0
        self._run_done = 0
        self._config_editor = None

        self._init_window()
        self._build_ui()
        self._apply_theme()
        self._set_busy(None)
        self._set_status("正在启动浏览器...", PALETTE["orange"])
        self._show_empty_hint("正在启动浏览器，就绪后点击【扫描任务列表】。")
        QTimer.singleShot(100, self._poll_logs)

    # ------------------------------------------------------------------ #
    # Window & layout
    # ------------------------------------------------------------------ #
    def _init_window(self):
        self.setWindowTitle("WeLearn-DOM-Helper")
        self.resize(1300, 840)
        self.setMinimumSize(1040, 660)
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor(PALETTE["bg"], PALETTE["bg"])
        self.navigationInterface.hide()
        self.titleBar.setTitle("")
        self.titleBar.titleLabel.hide()

        if sys.platform == "darwin":
            # Native traffic lights live in a 28px system title bar.
            self.setSystemTitleBarButtonVisible(True)
            self.titleBar.setFixedHeight(32)
            self.hBoxLayout.setContentsMargins(0, 32, 0, 0)
        else:
            self.titleBar.setFixedHeight(40)
            self.hBoxLayout.setContentsMargins(0, 44, 0, 0)
        self.titleBar.raise_()

        QShortcut(QKeySequence("Ctrl+M"), self, self.showMinimized)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence.Find, self, lambda: self.search_box.setFocus())

    def _build_ui(self):
        self.workbench = QWidget()
        self.workbench.setObjectName("workbench")
        self.stackedWidget.addWidget(self.workbench)
        self.stackedWidget.setCurrentWidget(self.workbench)

        root = QVBoxLayout(self.workbench)
        root.setContentsMargins(24, 0, 24, 20)
        root.setSpacing(12)

        root.addWidget(self._build_top_strip())
        root.addWidget(self._build_metric_card())

        content_split = QHBoxLayout()
        content_split.setSpacing(14)
        content_split.addWidget(self._build_task_panel(), 6)
        content_split.addWidget(self._build_log_panel(), 4)
        root.addLayout(content_split, 1)

    def _build_top_strip(self) -> QWidget:
        top = QWidget()
        top.setObjectName("topStrip")
        layout = QHBoxLayout(top)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        title_lbl = QLabel("WeLearn-DOM-Helper")
        title_lbl.setObjectName("appTitle")
        layout.addWidget(title_lbl)

        ver_lbl = QLabel(f"v{self.app_version}")
        ver_lbl.setObjectName("versionTag")
        layout.addWidget(ver_lbl)

        author_lbl = QLabel("Based on UnipusAI-Helper by YSJohnson | AGPLv3")
        author_lbl.setObjectName("authorTag")
        layout.addWidget(author_lbl)

        layout.addStretch(1)

        self.btn_config = PushButton("配置设置")
        self.btn_config.setIcon(FIF.SETTING)
        self.btn_config.clicked.connect(self._open_config_editor)
        layout.addWidget(self.btn_config)
        return top

    def _build_metric_card(self) -> QWidget:
        card = CardWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 12, 18, 12)
        outer.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(28)
        self.metric_total = self._metric("总任务数", "0")
        self.metric_selected = self._metric("已勾选", "0")
        self.metric_done = self._metric("已完成", "0")
        self.metric_pending = self._metric("待完成", "0")
        self.metric_eta = self._metric("预计耗时", "—")
        for m in (self.metric_total, self.metric_selected, self.metric_done, self.metric_pending, self.metric_eta):
            row.addWidget(m)
        row.addStretch(1)

        self.status_pill = QLabel("")
        row.addWidget(self.status_pill)
        outer.addLayout(row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        progress_row.addWidget(self.progress_bar, 1)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("hintLabel")
        progress_row.addWidget(self.progress_label)
        self.progress_host = QWidget()
        self.progress_host.setLayout(progress_row)
        self.progress_host.setVisible(False)
        outer.addWidget(self.progress_host)
        return card

    def _build_task_panel(self) -> QWidget:
        card, layout = self._panel_card("任务目录树 (Unit -> Section -> SCO)")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_scan = PrimaryPushButton("扫描任务列表")
        self.btn_scan.setIcon(FIF.SYNC)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        toolbar.addWidget(self.btn_scan)

        self.btn_auto = PrimaryPushButton("处理选中任务 (0)")
        self.btn_auto.setIcon(FIF.PLAY)
        self.btn_auto.clicked.connect(self._on_auto_clicked)
        toolbar.addWidget(self.btn_auto)

        self.btn_quick = PushButton("快速处理当前页")
        self.btn_quick.setIcon(FIF.SEND)
        self.btn_quick.clicked.connect(self._on_quick_clicked)
        toolbar.addWidget(self.btn_quick)

        self.btn_stop = PushButton("停止")
        self.btn_stop.setIcon(FIF.PAUSE)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        toolbar.addWidget(self.btn_stop)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("过滤任务名称、单元或 SCO ID...")
        self.search_box.textChanged.connect(self._filter_tabs)
        filter_row.addWidget(self.search_box, 1)

        self.btn_sel_all = TransparentPushButton("全选")
        self.btn_sel_all.clicked.connect(lambda: self._bulk_check("all"))
        self.btn_sel_invert = TransparentPushButton("反选")
        self.btn_sel_invert.clicked.connect(lambda: self._bulk_check("invert"))
        self.btn_sel_undone = TransparentPushButton("仅未完成")
        self.btn_sel_undone.clicked.connect(lambda: self._bulk_check("undone"))
        for b in (self.btn_sel_all, self.btn_sel_invert, self.btn_sel_undone):
            b.setToolTip("作用于当前过滤结果中可见的任务")
            filter_row.addWidget(b)
        layout.addLayout(filter_row)

        self.tree = TreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["任务", "已学时长", "状态"])
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        layout.addWidget(self.tree, 1)

        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {PALETTE['muted']}; padding: 20px; font-size: 14px;")
        layout.addWidget(self.empty_label)
        return card

    def _build_log_panel(self) -> QWidget:
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch(1)

        btn_clear = TransparentToolButton(FIF.DELETE)
        btn_clear.setToolTip("清空日志")
        btn_clear.clicked.connect(self._clear_log)
        btn_copy = TransparentToolButton(FIF.COPY)
        btn_copy.setToolTip("复制全部日志")
        btn_copy.clicked.connect(self._copy_log)
        btn_folder = TransparentToolButton(FIF.FOLDER)
        btn_folder.setToolTip("打开日志目录")
        btn_folder.clicked.connect(self._open_logs_dir)
        for b in (btn_clear, btn_copy, btn_folder):
            header.addWidget(b)
        layout.addLayout(header)

        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(LOG_MAX_BLOCKS)
        self.log_text.setStyleSheet(
            f"QTextEdit {{ background-color: {PALETTE['log_bg']}; color: {PALETTE['text_soft']}; "
            "font-family: 'JetBrains Mono', 'Menlo', 'Consolas', monospace; font-size: 13px; "
            "border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(self.log_text, 1)
        return card

    def _panel_card(self, title: str):
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        header = QLabel(title)
        header.setObjectName("panelTitle")
        layout.addWidget(header)
        return card, layout

    def _metric(self, title: str, value: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setObjectName("metricValue")
        tit_lbl = QLabel(title)
        tit_lbl.setObjectName("metricTitle")
        layout.addWidget(val_lbl)
        layout.addWidget(tit_lbl)
        box.val_lbl = val_lbl
        return box

    def _apply_theme(self):
        self.setStyleSheet(
            GLOBAL_QSS
            + f"""
            QWidget#workbench {{ background: {PALETTE['bg']}; }}
            CardWidget {{ background: {PALETTE['panel']}; border: 1px solid {PALETTE['panel_border']}; border-radius: 8px; }}
            """
        )

    # ------------------------------------------------------------------ #
    # Status / busy state
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, color: str = PALETTE["cyan"]):
        self.status_pill.setText(text)
        self.status_pill.setStyleSheet(
            f"color: {color}; background: {rgba(color, 0.14)}; padding: 6px 14px; "
            "border-radius: 12px; font-weight: 600;"
        )

    def _set_busy(self, kind: Optional[str]):
        """Single place that decides which buttons are usable."""
        self._busy = kind
        idle = kind is None
        ready = self._driver_ready and self._startup_done

        self.btn_scan.setEnabled(idle and ready)
        self.btn_scan.setText("扫描中..." if kind == "scan" else "扫描任务列表")
        self.btn_quick.setEnabled(idle and ready)
        self.btn_auto.setEnabled(idle and ready and bool(self._selected_idx))
        self.btn_stop.setEnabled(kind == "auto")
        self._update_auto_button_text()

    def _update_auto_button_text(self):
        self.btn_auto.setText(f"处理选中任务 ({len(self._selected_idx)})")

    # Thread-safe notifications from the startup thread --------------------
    def notify_driver_state(self, ok: bool):
        self._bridge.invoke.emit(lambda: self._on_driver_state(ok))

    def notify_login_state(self, logged_in: bool):
        self._bridge.invoke.emit(lambda: self._on_login_state(logged_in))

    def _on_driver_state(self, ok: bool):
        self._driver_ready = ok
        if not ok:
            self._startup_done = True
            self._set_status("浏览器启动失败", PALETTE["red"])
            self._show_empty_hint("浏览器启动失败，请检查配置中的浏览器类型后重启程序。")
        else:
            self._set_status("等待登录...", PALETTE["orange"])
            self._show_empty_hint("浏览器已启动，正在等待登录验证...")
        self._set_busy(self._busy)

    def _on_login_state(self, logged_in: bool):
        self._startup_done = True
        if self._busy is not None:
            return
        if logged_in:
            self._set_status("就绪", PALETTE["green"])
            self._show_empty_hint("登录成功！点击上方【扫描任务列表】加载课程任务。")
        elif self._driver_ready:
            self._set_status("未检测到登录", PALETTE["orange"])
            self._show_empty_hint("未完成自动登录。请在浏览器中登录后，点击【扫描任务列表】。")
        self._set_busy(self._busy)

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    def _poll_logs(self):
        msgs = []
        while len(msgs) < LOG_MAX_PER_TICK and not self.gui_log_queue.empty():
            try:
                msgs.append(str(self.gui_log_queue.get_nowait()))
            except Exception:
                break

        if msgs:
            scrollbar = self.log_text.verticalScrollBar()
            stick_to_bottom = scrollbar.value() >= scrollbar.maximum() - 4
            doc = self.log_text.document()
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.End)
            for msg in msgs:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(_log_color(msg)))
                if not doc.isEmpty():
                    cursor.insertBlock()
                cursor.insertText(msg, fmt)
            if stick_to_bottom:
                scrollbar.setValue(scrollbar.maximum())

        if not self._closing:
            QTimer.singleShot(100, self._poll_logs)

    def _clear_log(self):
        self.log_text.clear()

    def _copy_log(self):
        QApplication.clipboard().setText(self.log_text.toPlainText())
        InfoBar.success("已复制", "日志已复制到剪贴板", duration=1500, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _open_logs_dir(self):
        os.makedirs(LOGS_DIR, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(LOGS_DIR))

    # ------------------------------------------------------------------ #
    # Config editor
    # ------------------------------------------------------------------ #
    def _open_config_editor(self):
        editor = self._config_editor
        try:
            if editor is not None and editor.isVisible():
                editor.showNormal()
                editor.raise_()
                editor.activateWindow()
                return
        except RuntimeError:  # underlying C++ object already deleted
            editor = None

        try:
            from config_editor import ConfigEditor

            if editor is not None:
                editor.deleteLater()

            def _on_cfg_saved(_new_data):
                cfg = self.bot.reload_config()
                self.gui_log_queue.put(
                    f"[配置已热重载] 并发模式: {cfg.concurrency_mode} | "
                    f"目标总时长: {cfg.target_total_seconds}s | "
                    f"并发标签页上限: {cfg.max_concurrent_tabs} | "
                    f"单节保底停留: {cfg.min_dwell_seconds}s"
                )
                self._update_task_stats()

            self._config_editor = ConfigEditor(on_saved=_on_cfg_saved)
            self._config_editor.show()
        except Exception as e:
            self.gui_log_queue.put(f"打开配置编辑器失败: {e}")

    # ------------------------------------------------------------------ #
    # Scan & tree
    # ------------------------------------------------------------------ #
    def _on_scan_clicked(self):
        self._set_busy("scan")
        self._set_status("扫描中...", PALETTE["orange"])
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        tabs: List[Dict] = []
        error: Optional[str] = None
        try:
            tabs = self.bot.scan_catalog() or []
        except Exception as e:
            error = str(e)
            self.gui_log_queue.put(f"扫描异常: {e}")
        self._bridge.invoke.emit(lambda: self._on_scan_completed(tabs, error))

    def _on_scan_completed(self, tabs: List[Dict], error: Optional[str]):
        # GUI keeps its own copies so the worker thread never mutates them.
        self._all_tabs = [dict(t) for t in tabs]
        self.progress_host.setVisible(False)
        self._build_tree()
        self._set_busy(None)

        if error:
            self._set_status("扫描失败", PALETTE["red"])
            InfoBar.error("扫描失败", error, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)
        elif not self._all_tabs:
            self._set_status("未找到任务", PALETTE["orange"])
        else:
            self._set_status("就绪", PALETTE["green"])

    def _show_empty_hint(self, text: str):
        self.empty_label.setText(text)
        self.empty_label.setVisible(True)
        self.tree.setVisible(False)

    def _build_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        self._leaf_items.clear()
        self._units.clear()
        self._selected_idx.clear()

        if not self._all_tabs:
            self.tree.blockSignals(False)
            self._show_empty_hint("未找到任务或尚未扫描。")
            self._update_task_stats()
            return

        self.empty_label.setVisible(False)
        self.tree.setVisible(True)

        unit_groups: Dict[str, List[int]] = {}
        for idx, tab in enumerate(self._all_tabs):
            unit_groups.setdefault(tab.get("unit_label") or "默认单元", []).append(idx)

        bold = getFont(13, QFont.DemiBold)
        for unit_name, indices in unit_groups.items():
            unit_item = QTreeWidgetItem(self.tree, [unit_name, "", ""])
            unit_item.setFlags(unit_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            unit_item.setFont(0, bold)
            for idx in indices:
                tab = self._all_tabs[idx]
                is_done = tab.get("status") == "done"
                title = tab.get("l1_title") or tab.get("scoid", "")
                leaf = QTreeWidgetItem(unit_item, [f"{title}  ({tab.get('scoid', '')})", "", ""])
                leaf.setFlags((leaf.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsAutoTristate)
                leaf.setData(0, ROLE_TAB_IDX, idx)
                leaf.setToolTip(0, f"{unit_name}\n{title}\nSCO: {tab.get('scoid', '')}")
                leaf.setCheckState(0, Qt.Unchecked if is_done else Qt.Checked)
                self._leaf_items[idx] = leaf
                self._apply_leaf_status(idx)
            unit_item.setExpanded(True)
            self._units.append((unit_item, unit_name, indices))

        self.tree.blockSignals(False)
        self._refresh_unit_labels()
        self._filter_tabs(self.search_box.text())
        self._sync_selection()

    def _apply_leaf_status(self, idx: int):
        tab = self._all_tabs[idx]
        leaf = self._leaf_items.get(idx)
        if leaf is None:
            return
        is_done = tab.get("status") == "done"
        leaf.setText(1, f"⏱ {tab.get('learntime') or '00:00:00'}")
        leaf.setText(2, tab.get("status_text") or ("已完成" if is_done else "未完成"))
        leaf.setForeground(1, QBrush(QColor(PALETTE["muted"])))
        leaf.setForeground(2, QBrush(QColor(PALETTE["green"] if is_done else PALETTE["muted"])))

    def _refresh_unit_labels(self):
        for unit_item, _unit_name, indices in self._units:
            done = sum(1 for i in indices if self._all_tabs[i].get("status") == "done")
            total = len(indices)
            unit_item.setText(1, f"{done}/{total}")
            if done == total:
                unit_item.setText(2, "已完成")
                unit_item.setForeground(2, QBrush(QColor(PALETTE["green"])))
            else:
                unit_item.setText(2, f"剩余 {total - done}")
                unit_item.setForeground(2, QBrush(QColor(PALETTE["orange"])))
            unit_item.setForeground(1, QBrush(QColor(PALETTE["muted"])))

    def _on_tree_item_changed(self, _item, column: int):
        if column != 0 or self._sync_pending:
            return
        self._sync_pending = True
        QTimer.singleShot(0, self._sync_selection)

    def _sync_selection(self):
        self._sync_pending = False
        self._selected_idx = {
            idx for idx, leaf in self._leaf_items.items() if leaf.checkState(0) == Qt.Checked
        }
        self._update_task_stats()
        self._set_busy(self._busy)

    def _bulk_check(self, mode: str):
        if not self._leaf_items:
            return
        self.tree.blockSignals(True)
        for idx, leaf in self._leaf_items.items():
            if leaf.isHidden() or (leaf.parent() is not None and leaf.parent().isHidden()):
                continue
            if mode == "all":
                state = Qt.Checked
            elif mode == "invert":
                state = Qt.Unchecked if leaf.checkState(0) == Qt.Checked else Qt.Checked
            else:  # undone
                state = Qt.Unchecked if self._all_tabs[idx].get("status") == "done" else Qt.Checked
            leaf.setCheckState(0, state)
        self.tree.blockSignals(False)
        self.tree.viewport().update()
        self._sync_selection()

    def _filter_tabs(self, text: str):
        query = text.strip().lower()
        for unit_item, unit_name, indices in self._units:
            unit_match = bool(query) and query in unit_name.lower()
            any_visible = False
            for idx in indices:
                tab = self._all_tabs[idx]
                match = (
                    not query
                    or unit_match
                    or query in str(tab.get("scoid", "")).lower()
                    or query in str(tab.get("l1_title") or "").lower()
                )
                self._leaf_items[idx].setHidden(not match)
                any_visible = any_visible or match
            unit_item.setHidden(not any_visible)
            if query and any_visible:
                unit_item.setExpanded(True)

    # ------------------------------------------------------------------ #
    # Stats
    # ------------------------------------------------------------------ #
    def _update_task_stats(self):
        total = len(self._all_tabs)
        done = sum(1 for t in self._all_tabs if t.get("status") == "done")
        self.metric_total.val_lbl.setText(str(total))
        self.metric_selected.val_lbl.setText(str(len(self._selected_idx)))
        self.metric_done.val_lbl.setText(str(done))
        self.metric_pending.val_lbl.setText(str(total - done))

        eta_text, eta_tip = self._estimate_duration()
        self.metric_eta.val_lbl.setText(eta_text)
        self.metric_eta.setToolTip(eta_tip)

    def _estimate_duration(self) -> Tuple[str, str]:
        n = len(self._selected_idx)
        if n == 0:
            return "—", "未勾选任务"
        cfg = self.bot.config
        target = int(getattr(cfg, "target_total_seconds", 0) or 0)
        dwell = int(getattr(cfg, "min_dwell_seconds", 0) or 0)
        mode = str(getattr(cfg, "concurrency_mode", "serial") or "serial")
        tabs = max(1, int(getattr(cfg, "max_concurrent_tabs", 1) or 1))

        if target > 0:
            learned = sum(DurationPlanner.parse_learntime_seconds(t.get("learntime")) for t in self._all_tabs)
            seconds = max(max(0, target - learned), n * dwell)
            tip = "按目标总时长扣除已学时长估算"
        elif dwell > 0:
            seconds = n * dwell
            tip = "按单小节保底停留估算"
        else:
            return "极速", "未设置停留时长，耗时取决于页面加载与作答速度"

        if mode != "serial" and tabs > 1:
            seconds = seconds // tabs
            tip += f"（{tabs} 个标签页并发）"
        return f"≈{_format_duration(seconds)}", tip + "，不含页面加载时间"

    # ------------------------------------------------------------------ #
    # Batch run
    # ------------------------------------------------------------------ #
    def _on_auto_clicked(self):
        if not self._selected_idx or self._busy is not None:
            return

        indices = sorted(self._selected_idx)
        selected_tabs = [dict(self._all_tabs[i]) for i in indices]
        self._run_scoid_map = {str(self._all_tabs[i].get("scoid", "")): i for i in indices}
        self._run_total = len(selected_tabs)
        self._run_done = 0
        self._update_progress()
        self.progress_host.setVisible(True)

        self._set_busy("auto")
        self._set_status("自动化运行中...", PALETTE["orange"])
        threading.Thread(target=self._run_auto_thread, args=(selected_tabs,), daemon=True).start()

    def _run_auto_thread(self, selected_tabs: List[Dict]):
        error: Optional[str] = None
        try:
            self.bot.reload_config()
            self.bot.process_selected_tabs(
                selected_tabs,
                on_task_done=lambda tab: self._bridge.invoke.emit(
                    lambda s=str(tab.get("scoid", "")): self._on_task_completed(s)
                ),
            )
        except Exception as e:
            error = str(e)
            self.gui_log_queue.put(f"自动化异常: {e}")
        stopped = self.bot.stop_requested.is_set()
        self._bridge.invoke.emit(lambda: self._on_auto_finished(stopped, error))

    def _on_task_completed(self, scoid: str):
        idx = self._run_scoid_map.get(scoid)
        if idx is None:
            return
        tab = self._all_tabs[idx]
        tab["status"] = "done"
        tab["status_text"] = "已完成"
        self._apply_leaf_status(idx)
        leaf = self._leaf_items.get(idx)
        if leaf is not None:
            leaf.setCheckState(0, Qt.Unchecked)  # triggers _sync_selection
        self._refresh_unit_labels()
        self._run_done += 1
        self._update_progress()
        self._update_task_stats()

    def _update_progress(self):
        total = max(1, self._run_total)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(self._run_done, total))
        self.progress_label.setText(f"本次进度 {self._run_done} / {self._run_total}")

    def _on_auto_finished(self, stopped: bool, error: Optional[str]):
        self._set_busy(None)
        summary = f"本次完成 {self._run_done} / {self._run_total} 个任务"
        if error:
            self._set_status("运行异常", PALETTE["red"])
            InfoBar.error("运行异常", f"{error}\n{summary}", duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self)
        elif stopped:
            self._set_status("已停止", PALETTE["orange"])
            InfoBar.warning("已停止", summary, duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)
        elif self._run_done < self._run_total:
            self._set_status("部分完成", PALETTE["orange"])
            InfoBar.warning("部分任务未完成", f"{summary}，详情请查看日志", duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)
        else:
            self._set_status("完成", PALETTE["green"])
            InfoBar.success("任务结束", summary, duration=2500, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_stop_clicked(self):
        self.bot.request_stop()
        self.btn_stop.setEnabled(False)
        self._set_status("正在停止...", PALETTE["orange"])
        self.gui_log_queue.put("已发送停止请求，等待当前小节收尾...")

    # ------------------------------------------------------------------ #
    # Quick run
    # ------------------------------------------------------------------ #
    def _on_quick_clicked(self):
        if self._busy is not None:
            return
        self._set_busy("quick")
        self._set_status("快速处理中...", PALETTE["orange"])
        threading.Thread(target=self._run_quick_thread, daemon=True).start()

    def _run_quick_thread(self):
        error: Optional[str] = None
        try:
            self.bot.quick_process_current_page()
        except Exception as e:
            error = str(e)
            self.gui_log_queue.put(f"快速处理异常: {e}")
        self._bridge.invoke.emit(lambda: self._on_quick_finished(error))

    def _on_quick_finished(self, error: Optional[str]):
        self._set_busy(None)
        if error:
            self._set_status("快速处理失败", PALETTE["red"])
        else:
            self._set_status("就绪", PALETTE["green"])

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def mainloop(self):
        self.show()
        return self._qt_app.exec_()

    def closeEvent(self, event):
        try:
            if self._config_editor is not None and self._config_editor.isVisible():
                self._config_editor.close()
                if self._config_editor.isVisible():  # user chose "返回编辑"
                    event.ignore()
                    return
        except RuntimeError:
            pass

        if self._busy in ("auto", "quick"):
            box = MessageBox("任务仍在运行", "关闭窗口将停止当前任务并退出程序，确定要退出吗？", self)
            box.yesButton.setText("停止并退出")
            box.cancelButton.setText("继续运行")
            if not box.exec():
                event.ignore()
                return
            self.bot.request_stop()

        self._closing = True
        super().closeEvent(event)
