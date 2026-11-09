# -*- coding: utf-8 -*-
"""
WeLearn Bot Automation Orchestrator.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
import os
import queue
import re
import sys
import tempfile
import threading
import time
from typing import Callable, Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    SessionNotCreatedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ai_client import OpenAICompatibleClient
from question_solver import WeLearnQuestionSolver
from tts_engine import TTSEngine
from webdriver_helper import WebDriverHelper
from welearn_api import WeLearnAPI, WeLearnCourse, WeLearnSCO, WeLearnUnit
from welearn_config import Config
from welearn_player import WeLearnFrameContext, WeLearnPlayer

logger = logging.getLogger("WeLearnBot")


class WeLearnBot:
    """Manages browser lifecycle, login detection, catalog scanning, and task execution."""

    def __init__(self, config: Config, log_queue: queue.Queue):
        self.config = config
        self.log_queue = log_queue
        self.driver: Optional[webdriver.Remote] = None
        self.stop_requested = threading.Event()

        self.ai_client = OpenAICompatibleClient(self.config)
        self.tts_engine = TTSEngine(
            engine=self.config.tts_engine,
            voice=self.config.tts_voice,
            proxy=self.config.tts_proxy,
        )
        self.solver = WeLearnQuestionSolver(
            config=self.config,
            ai_client=self.ai_client,
            tts_engine=self.tts_engine,
            log_callback=self._ui_log,
        )

        self.active_cid: str = ""
        self.active_uid: str = ""
        self.active_classid: str = ""
        self.courses_cache: List[WeLearnCourse] = []
        self.units_cache: List[WeLearnUnit] = []

    def _ui_log(self, message: str) -> None:
        """Forward log message to GUI log queue."""
        clean_msg = message.strip()
        if clean_msg:
            self.log_queue.put(clean_msg)

    def request_stop(self) -> None:
        self.stop_requested.set()

    def clear_stop(self) -> None:
        self.stop_requested.clear()

    def _should_stop(self) -> bool:
        return self.stop_requested.is_set()

    def start_driver(self) -> webdriver.Remote:
        """Launch Chrome or Edge driver with optimal flags for stability."""
        browser_choice = (self.config.browser or "edge").lower()
        self._ui_log(f"正在启动浏览器 ({browser_choice})...")

        # Create isolated temp profile directory
        profile_dir = tempfile.mkdtemp(prefix="welearn_profile_")

        driver = None
        if browser_choice == "chrome":
            try:
                driver = self._create_chrome_driver(profile_dir)
            except Exception as e:
                self._ui_log(f"Chrome 启动失败 ({e})，尝试回退 Edge...")
                driver = self._create_edge_driver(profile_dir)
        else:
            try:
                driver = self._create_edge_driver(profile_dir)
            except Exception as e:
                self._ui_log(f"Edge 启动失败 ({e})，尝试回退 Chrome...")
                driver = self._create_chrome_driver(profile_dir)

        self.driver = driver
        self.driver.set_page_load_timeout(30)
        self._ui_log("浏览器已成功就绪！")
        return driver

    def _create_edge_driver(self, profile_dir: str):
        options = EdgeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if self.config.headless:
            options.add_argument("--headless=new")
        return webdriver.Edge(options=options)

    def _create_chrome_driver(self, profile_dir: str):
        options = ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if self.config.headless:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    def check_or_prompt_login(self) -> bool:
        """Navigate to WeLearn and ensure user is logged in."""
        if not self.driver:
            return False

        login_url = self.config.url or "https://welearn.sflep.com/2019/student/index.aspx"
        self._ui_log(f"正在打开 WeLearn 学习主页: {login_url}")
        self.driver.get(login_url)

        # Check if login is already valid
        if self._is_logged_in():
            self._ui_log("检测到有效登录状态，会话已建立。")
            return True

        self._ui_log("【等待登录】请在浏览器窗口中完成账号登录与验证...")
        # Poll until user completes login or timeout (10 minutes)
        start_time = time.time()
        while time.time() - start_time < 600:
            if self._should_stop():
                return False
            if self._is_logged_in():
                self._ui_log("登录验证握手成功！")
                return True
            time.sleep(2.0)

        self._ui_log("登录等待超时，请重试。")
        return False

    def _is_logged_in(self) -> bool:
        if not self.driver:
            return False
        try:
            curr_url = self.driver.current_url or ""
            # If on student index or course info page or studycourse
            if any(path in curr_url for path in [
                "/student/index.aspx",
                "/student/course_info.aspx",
                "/student/StudyCourse.aspx",
                "/2019/student/index.aspx"
            ]):
                return True

            # Check if user profile indicator exists
            user_indicators = self.driver.find_elements(
                By.CSS_SELECTOR, ".user-info, .username, #user_name, .loginout, [href*='logout']"
            )
            return len(user_indicators) > 0
        except Exception:
            return False

    def scan_catalog(self, target_cid: Optional[str] = None) -> List[Dict]:
        """Scan WeLearn courses, units, and sections into GUI task tree data."""
        if not self.driver:
            return []

        self._ui_log("正在从 WeLearn 平台拉取课程与目录信息...")
        tasks = []

        # Step 1: Discover courses
        courses = WeLearnAPI.get_courses(self.driver)
        if not courses:
            # Fallback: check current page URL if already on course_info.aspx?cid=XXXX
            curr_url = self.driver.current_url or ""
            if "cid=" in curr_url:
                m = re.search(r'cid=(\d+)', curr_url)
                if m:
                    cid = m.group(1)
                    courses = [WeLearnCourse(cid=cid, name=f"当前课程 (CID: {cid})")]

        if not courses:
            self._ui_log("未找到可用课程，请确保已登录并加入相应课程。")
            return []

        self.courses_cache = courses
        self._ui_log(f"已发现 {len(courses)} 门课程。")

        # Pick specified course or the first course
        chosen_course = None
        if target_cid:
            chosen_course = next((c for c in courses if str(c.cid) == str(target_cid)), None)
        if not chosen_course:
            chosen_course = courses[0]

        self.active_cid = chosen_course.cid
        self._ui_log(f"当前选中课程: {chosen_course.name} (CID: {chosen_course.cid})")

        # Step 2: Extract uid and classid
        uid, classid = WeLearnAPI.get_course_ids(self.driver, chosen_course.cid)
        if not uid or not classid:
            # Try navigating directly to course_info to extract
            self.driver.get(f"https://welearn.sflep.com/student/course_info.aspx?cid={chosen_course.cid}")
            time.sleep(2.0)
            uid, classid = WeLearnAPI.get_course_ids(self.driver, chosen_course.cid)

        if not uid or not classid:
            self._ui_log("未能获取到课程 uid 或 classid，请确认页面是否正常加载。")
            return []

        self.active_uid = uid
        self.active_classid = classid
        self._ui_log(f"用户 ID: {uid}, 班级 ID: {classid}")

        # Step 3: Fetch units
        units = WeLearnAPI.get_units(self.driver, chosen_course.cid, uid)
        self.units_cache = units
        self._ui_log(f"共获取到 {len(units)} 个单元。")

        # Step 4: For each unit, fetch scoLeaves
        for unit in units:
            if not unit.visible:
                continue

            scos = WeLearnAPI.get_sections(
                self.driver,
                chosen_course.cid,
                uid,
                unit.unit_idx,
                classid,
                unit_name=unit.name,
            )

            for sco in scos:
                is_done = sco.iscomplete
                status_key = "done" if is_done else "not_started"
                status_text = "已完成" if is_done else "未完成"

                task_dict = {
                    "l1_idx": len(tasks),
                    "l2_idx": -1,
                    "l1_title": sco.location or sco.scoid,
                    "l2_title": unit.name,
                    "display": f"[{status_text}] {sco.location} ({sco.scoid})",
                    "is_l2": False,
                    "is_compulsory": True,
                    "unit_label": unit.name,
                    "unit_idx": unit.unit_idx,
                    "unit_is_preview": False,
                    "section": sco.location,
                    "status": status_key,
                    "status_text": status_text,
                    "scoid": sco.scoid,
                    "cid": chosen_course.cid,
                    "classid": classid,
                    "uid": uid,
                    "learntime": sco.learntime,
                }
                tasks.append(task_dict)

        self._ui_log(f"目录扫描完成，共整理出 {len(tasks)} 个小节任务。")
        return tasks

    def process_selected_tabs(
        self, selected_tabs: List[Dict], on_task_done: Optional[Callable[[Dict], None]] = None
    ) -> None:
        """Batch process user-selected SCO tasks."""
        if not self.driver:
            self._ui_log("错误: 浏览器尚未启动！")
            return

        self.clear_stop()
        self._ui_log(f"====== 开始批量处理 {len(selected_tabs)} 个选中任务 ======")

        for idx, tab in enumerate(selected_tabs):
            if self._should_stop():
                self._ui_log("收到停止请求，批量处理已中断。")
                break

            scoid = tab.get("scoid", "")
            cid = tab.get("cid") or self.active_cid
            classid = tab.get("classid") or self.active_classid
            disp_name = tab.get("l1_title") or scoid

            self._ui_log(f"\n[{idx + 1}/{len(selected_tabs)}] 正在处理: {disp_name} (SCO: {scoid})")

            try:
                # 1. Switch to the target SCO
                WeLearnPlayer.navigate_to_sco(self.driver, cid, classid, scoid)

                # 2. Enter content frame and solve
                with WeLearnFrameContext(self.driver, timeout=12.0) as ctx:
                    if not ctx.entered:
                        self._ui_log(f"   警告: 无法切入 contentFrame，跳过该小节: {scoid}")
                        continue

                    # Solve questions inside iframe
                    self.solver.solve_sco(self.driver, scoid)

                tab["status"] = "done"
                tab["status_text"] = "已完成"
                if on_task_done:
                    try:
                        on_task_done(tab)
                    except Exception as e:
                        logger.debug("on_task_done callback error: %s", e)

            except Exception as e:
                self._ui_log(f"   处理异常: {e}")
                logger.error("Error processing tab %s: %s", scoid, e, exc_info=True)

            time.sleep(1.0)

        self._ui_log(
            "\n====== 批量处理结束 ======"
            if not self._should_stop()
            else "\n====== 批量处理已停止 ======"
        )

    def quick_process_current_page(self) -> None:
        """Solve whatever SCO is currently active in the browser."""
        if not self.driver:
            self._ui_log("错误: 浏览器尚未启动！")
            return

        self._ui_log("开始快速处理当前页...")
        try:
            curr_scoid = WeLearnPlayer.get_current_scoid(self.driver)
            with WeLearnFrameContext(self.driver, timeout=8.0) as ctx:
                if not ctx.entered:
                    self._ui_log("未能在当前页面找到课件 iframe (contentFrame)！")
                    return
                self.solver.solve_sco(self.driver, curr_scoid or "current")
            self._ui_log("当前页快速处理完成！")
        except Exception as e:
            self._ui_log(f"快速处理当前页失败: {e}")
            logger.error("quick_process_current_page error: %s", e, exc_info=True)
