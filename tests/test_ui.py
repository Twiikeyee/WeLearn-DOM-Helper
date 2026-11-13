# -*- coding: utf-8 -*-
"""Unit tests for UI components, helpers, and config editor."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import config_editor
import fluent_ui
import ui_common
from version import __version__
from welearn_config import Config


class TestVersion(unittest.TestCase):
    def test_version_string(self):
        self.assertTrue(isinstance(__version__, str) and len(__version__) > 0)


class TestUICommon(unittest.TestCase):
    def test_palette_contains_required_keys(self):
        required = ["bg", "panel", "panel_border", "text", "muted", "cyan", "green", "orange", "red"]
        for key in required:
            self.assertIn(key, ui_common.PALETTE)
            self.assertTrue(ui_common.PALETTE[key].startswith("#"))

    def test_rgba_conversion(self):
        self.assertEqual(ui_common.rgba("#ff0000", 0.5), "rgba(255, 0, 0, 0.5)")
        self.assertEqual(ui_common.rgba("#00ff00", 1.0), "rgba(0, 255, 0, 1.0)")
        self.assertEqual(ui_common.rgba("#0000ff", 0.0), "rgba(0, 0, 255, 0.0)")

    def test_ensure_qapp(self):
        app = ui_common.ensure_qapp()
        self.assertIsNotNone(app)


class TestConfigPersistence(unittest.TestCase):
    def test_save_config_preserves_unknown_keys_and_writes_plaintext_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "custom_user_key": "custom_val",
                        "typing_mode": "fast",
                        "secrets_in_keyring": True,
                    },
                    f,
                )

            with patch.object(config_editor, "CONFIG_PATH", cfg_path):
                config_editor.save_config(
                    {
                        "typing_mode": "simulate",
                        "password": "plain_password",
                        "api_key": "sk-plain",
                    }
                )

                with open(cfg_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["custom_user_key"], "custom_val")
                self.assertEqual(saved["typing_mode"], "simulate")
                self.assertEqual(saved["password"], "plain_password")
                self.assertEqual(saved["api_key"], "sk-plain")
                self.assertNotIn("secrets_in_keyring", saved)

    def test_welearn_config_from_json_plaintext(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"username": "user1", "password": "plain_password", "api_key": "sk-plain"}, f)

            cfg = Config.from_json(cfg_path)
            self.assertEqual(cfg.username, "user1")
            self.assertEqual(cfg.password, "plain_password")
            self.assertEqual(cfg.api_key, "sk-plain")


class TestUIHelpers(unittest.TestCase):
    def test_log_color_rules(self):
        self.assertEqual(fluent_ui._log_color("任务运行异常: 出错啦"), ui_common.PALETTE["red"])
        self.assertEqual(fluent_ui._log_color("警告: 耗时较长"), ui_common.PALETTE["orange"])
        self.assertEqual(fluent_ui._log_color("登录验证握手成功！"), ui_common.PALETTE["green"])
        self.assertEqual(fluent_ui._log_color("普通日志输出"), ui_common.PALETTE["text_soft"])

    def test_format_duration(self):
        self.assertEqual(fluent_ui._format_duration(30), "30 秒")
        self.assertEqual(fluent_ui._format_duration(120), "2 分钟")
        self.assertEqual(fluent_ui._format_duration(7200), "2.0 小时")


class TestConfigEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui_common.ensure_qapp()

    def setUp(self):
        self.editor = config_editor.ConfigEditor()
        self.app.processEvents()

    def tearDown(self):
        self.editor._dirty = False
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def test_collect_data_keys(self):
        data = self.editor._collect_data()
        for key in config_editor.DEFAULT_CONFIG:
            self.assertIn(key, data)

    def test_dirty_flag_on_edit(self):
        self.assertFalse(self.editor._dirty)
        self.editor.spin_dwell.setValue(self.editor.spin_dwell.value() + 5)
        self.app.processEvents()
        self.assertTrue(self.editor._dirty)
        self.assertIn("*", self.editor.windowTitle())

    def test_concurrency_mode_linkage(self):
        # Index 0 is serial
        self.editor.combo_concurrency.setCurrentIndex(0)
        self.app.processEvents()
        self.assertFalse(self.editor.spin_tabs.isEnabled())

        # Index 2 is pipeline
        self.editor.combo_concurrency.setCurrentIndex(2)
        self.app.processEvents()
        self.assertTrue(self.editor.spin_tabs.isEnabled())

    def test_llm_toggle_linkage(self):
        self.editor.cb_enable_llm.setChecked(False)
        self.app.processEvents()
        self.assertFalse(self.editor.entries["api_key"].isEnabled())
        self.assertFalse(self.editor.spin_temperature.isEnabled())
        self.assertFalse(self.editor.spin_max_tokens.isEnabled())

        self.editor.cb_enable_llm.setChecked(True)
        self.app.processEvents()
        self.assertTrue(self.editor.entries["api_key"].isEnabled())
        self.assertTrue(self.editor.spin_temperature.isEnabled())
        self.assertTrue(self.editor.spin_max_tokens.isEnabled())


class TestFluentModernGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui_common.ensure_qapp()

    def setUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.log_queue = MagicMock()
        self.mock_bot.log_queue.empty.return_value = True
        self.mock_bot.config = Config()
        self.gui = fluent_ui.FluentModernGUI(self.mock_bot)
        self.app.processEvents()

    def tearDown(self):
        self.gui._busy = None
        self.gui._closing = True
        self.gui.close()
        self.gui.deleteLater()
        self.app.processEvents()

    def test_startup_button_enablement(self):
        # Initially buttons are disabled
        self.assertFalse(self.gui.btn_scan.isEnabled())
        self.assertFalse(self.gui.btn_quick.isEnabled())

        # Driver ready, but login check still running
        self.gui.notify_driver_state(True)
        self.app.processEvents()
        self.assertFalse(self.gui.btn_scan.isEnabled())

        # Login finished
        self.gui.notify_login_state(True)
        self.app.processEvents()
        self.assertTrue(self.gui.btn_scan.isEnabled())
        self.assertTrue(self.gui.btn_quick.isEnabled())

    def test_tree_construction_and_bulk_selection(self):
        tabs = [
            {"unit_label": "Unit 1", "scoid": "101", "l1_title": "Task A", "learntime": "00:05:00", "status": "undone"},
            {"unit_label": "Unit 1", "scoid": "102", "l1_title": "Task B", "learntime": "00:10:00", "status": "done"},
            {"unit_label": "Unit 2", "scoid": "201", "l1_title": "Task C", "learntime": "00:00:00", "status": "undone"},
        ]
        self.gui._on_scan_completed(tabs, None)
        self.app.processEvents()

        self.assertEqual(self.gui.metric_total.val_lbl.text(), "3")
        self.assertEqual(self.gui.metric_done.val_lbl.text(), "1")
        self.assertEqual(self.gui.metric_pending.val_lbl.text(), "2")

        # By default, undone tasks are checked (Task A and Task C = 2)
        self.assertEqual(self.gui.metric_selected.val_lbl.text(), "2")

        # Bulk select all
        self.gui._bulk_check("all")
        self.app.processEvents()
        self.assertEqual(self.gui.metric_selected.val_lbl.text(), "3")

        # Bulk select undone
        self.gui._bulk_check("undone")
        self.app.processEvents()
        self.assertEqual(self.gui.metric_selected.val_lbl.text(), "2")

        # Invert
        self.gui._bulk_check("invert")
        self.app.processEvents()
        self.assertEqual(self.gui.metric_selected.val_lbl.text(), "1")

    def test_search_filter(self):
        tabs = [
            {"unit_label": "Unit 1", "scoid": "101", "l1_title": "Listening", "learntime": "00:00:00", "status": "undone"},
            {"unit_label": "Unit 2", "scoid": "201", "l1_title": "Reading", "learntime": "00:00:00", "status": "undone"},
        ]
        self.gui._on_scan_completed(tabs, None)
        self.app.processEvents()

        self.gui._filter_tabs("Reading")
        self.app.processEvents()
        self.assertTrue(self.gui._units[0][0].isHidden())   # Unit 1 hidden
        self.assertFalse(self.gui._units[1][0].isHidden())  # Unit 2 visible

        self.gui._filter_tabs("")
        self.app.processEvents()
        self.assertFalse(self.gui._units[0][0].isHidden())
        self.assertFalse(self.gui._units[1][0].isHidden())

    def test_task_completion_lifecycle(self):
        tabs = [
            {"unit_label": "Unit 1", "scoid": "101", "l1_title": "Task A", "learntime": "00:00:00", "status": "undone"},
        ]
        self.gui._on_scan_completed(tabs, None)
        self.app.processEvents()

        self.gui._on_auto_clicked()
        self.assertEqual(self.gui._busy, "auto")

        self.gui._on_task_completed("101")
        self.app.processEvents()
        self.assertEqual(self.gui.metric_done.val_lbl.text(), "1")

        self.gui._on_auto_finished(stopped=False, error=None)
        self.app.processEvents()
        self.assertIsNone(self.gui._busy)
        self.assertEqual(self.gui.status_pill.text(), "完成")
