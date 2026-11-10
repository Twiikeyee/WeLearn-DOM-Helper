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
import random
import re
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

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


class DurationPlanner:
    """Smart study duration budgeting: deducts existing learned time and distributes net target time randomly."""

    @staticmethod
    def parse_learntime_seconds(learntime_str: Any) -> int:
        """Parse 'HH:MM:SS', 'MM:SS', or numeric seconds string into integer seconds."""
        if learntime_str is None:
            return 0
        if isinstance(learntime_str, (int, float)):
            return max(0, int(learntime_str))

        raw = str(learntime_str).strip()
        if not raw:
            return 0

        if ":" in raw:
            parts = raw.split(":")
            try:
                if len(parts) == 3:
                    return max(0, int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2])))
                elif len(parts) == 2:
                    return max(0, int(parts[0]) * 60 + int(float(parts[1])))
            except Exception:
                return 0

        try:
            return max(0, int(float(raw)))
        except Exception:
            return 0

    @staticmethod
    def format_seconds(seconds: int) -> str:
        """Format integer seconds into HH:MM:SS."""
        sec = max(0, int(seconds))
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @classmethod
    def plan_dwell_allocations(
        cls,
        selected_tabs: List[Dict],
        target_total_seconds: int,
        min_dwell_seconds: int = 0,
        all_course_tabs: Optional[List[Dict]] = None,
    ) -> Tuple[List[int], Dict[str, int]]:
        """
        Calculate per-SCO dwell seconds for selected_tabs.

        - If target_total_seconds <= 0: each task gets min_dwell_seconds.
        - If target_total_seconds > 0:
          1. Sum existing learntime across all_course_tabs (or selected_tabs if not given).
          2. Net deficit = max(0, target_total_seconds - already_learned_seconds).
          3. Randomly distribute net deficit across selected_tabs using weighted jitter (±35%)
             while ensuring exact sum == net deficit and respecting min_dwell_seconds.
        """
        n = len(selected_tabs)
        min_floor = max(0, int(min_dwell_seconds or 0))
        target_total = max(0, int(target_total_seconds or 0))

        reference_tabs = all_course_tabs if all_course_tabs else selected_tabs
        already_learned = sum(cls.parse_learntime_seconds(t.get("learntime", "00:00:00")) for t in reference_tabs)

        if n == 0:
            return [], {
                "target_total_seconds": target_total,
                "already_learned_seconds": already_learned,
                "net_needed_seconds": 0,
                "planned_total_seconds": 0,
            }

        if target_total <= 0:
            allocs = [min_floor for _ in range(n)]
            return allocs, {
                "target_total_seconds": 0,
                "already_learned_seconds": already_learned,
                "net_needed_seconds": sum(allocs),
                "planned_total_seconds": sum(allocs),
            }

        net_needed = max(0, target_total - already_learned)
        if net_needed == 0:
            allocs = [min_floor for _ in range(n)]
            return allocs, {
                "target_total_seconds": target_total,
                "already_learned_seconds": already_learned,
                "net_needed_seconds": 0,
                "planned_total_seconds": sum(allocs),
            }

        if n == 1:
            val = max(min_floor, net_needed)
            return [val], {
                "target_total_seconds": target_total,
                "already_learned_seconds": already_learned,
                "net_needed_seconds": net_needed,
                "planned_total_seconds": val,
            }

        # Generate non-uniform random weights with slight preference for sections with less learned time
        weights = []
        for t in selected_tabs:
            learned_i = cls.parse_learntime_seconds(t.get("learntime", "00:00:00"))
            scarcity_factor = 1.0 / (1.0 + (learned_i / 600.0))
            jitter = random.uniform(0.65, 1.35)
            weights.append(max(0.1, scarcity_factor * jitter))

        weight_sum = sum(weights)
        raw_shares = [(w / weight_sum) * net_needed for w in weights]
        int_shares = [int(s) for s in raw_shares]
        remainder = net_needed - sum(int_shares)

        # Distribute integer remainder to items with largest fractional part
        frac_indices = sorted(range(n), key=lambda i: (raw_shares[i] - int_shares[i]), reverse=True)
        for i in range(remainder):
            int_shares[frac_indices[i % n]] += 1

        # Apply per-task minimum floor if requested
        final_allocs = [max(min_floor, s) for s in int_shares]
        return final_allocs, {
            "target_total_seconds": target_total,
            "already_learned_seconds": already_learned,
            "net_needed_seconds": net_needed,
            "planned_total_seconds": sum(final_allocs),
        }


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
        self.all_tasks_cache: List[Dict] = []

    def reload_config(self, path: str = "config.json") -> Config:
        """Reload runtime configuration from disk and sync with solver."""
        try:
            self.config = Config.from_json(path)
            self.solver.config = self.config
            self.ai_client.config = self.config
        except Exception as e:
            logger.debug("reload_config failed: %s", e)
        return self.config

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
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
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
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
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

        self.all_tasks_cache = tasks
        self._ui_log(f"目录扫描完成，共整理出 {len(tasks)} 个小节任务。")
        return tasks

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep in small increments; return True if interrupted by stop request."""
        end_ts = time.time() + max(0.0, float(seconds))
        while time.time() < end_ts:
            if self._should_stop():
                return True
            time.sleep(min(0.2, max(0.01, end_ts - time.time())))
        return self._should_stop()

    def _mark_tab_done(
        self, tab: Dict, on_task_done: Optional[Callable[[Dict], None]] = None
    ) -> None:
        tab["status"] = "done"
        tab["status_text"] = "已完成"
        if on_task_done:
            try:
                on_task_done(tab)
            except Exception as e:
                logger.debug("on_task_done callback error: %s", e)

    def _acquire_worker_tabs(self, count: int) -> Tuple[str, List[str]]:
        """Ensure `count` browser tab handles are open; returns (primary_handle, all_worker_handles)."""
        base_handle = self.driver.current_window_handle
        worker_handles = [base_handle]
        needed = max(0, count - 1)
        for _ in range(needed):
            try:
                self.driver.switch_to.new_window("tab")
                worker_handles.append(self.driver.current_window_handle)
            except Exception:
                try:
                    before = set(self.driver.window_handles)
                    self.driver.execute_script("window.open('about:blank', '_blank');")
                    after = [h for h in self.driver.window_handles if h not in before]
                    if after:
                        self.driver.switch_to.window(after[0])
                        worker_handles.append(after[0])
                except Exception as e:
                    logger.debug("Failed to open extra worker tab: %s", e)
                    break
        try:
            self.driver.switch_to.window(base_handle)
        except Exception:
            pass
        return base_handle, worker_handles

    def _cleanup_worker_tabs(self, base_handle: str, worker_handles: List[str]) -> None:
        """Close extra worker tabs created for concurrency and restore primary tab."""
        for h in worker_handles:
            if h != base_handle:
                try:
                    self.driver.switch_to.window(h)
                    self.driver.close()
                except Exception:
                    pass
        try:
            self.driver.switch_to.window(base_handle)
        except Exception:
            pass

    def process_selected_tabs(
        self, selected_tabs: List[Dict], on_task_done: Optional[Callable[[Dict], None]] = None
    ) -> None:
        """Batch process user-selected SCO tasks using configured concurrency mode and duration budget."""
        if not self.driver:
            self._ui_log("错误: 浏览器尚未启动！")
            return

        if not selected_tabs:
            self._ui_log("未选中任何任务。")
            return

        self.clear_stop()
        mode = (getattr(self.config, "concurrency_mode", "serial") or "serial").strip().lower()
        target_total = int(getattr(self.config, "target_total_seconds", 0) or 0)
        min_dwell = int(getattr(self.config, "min_dwell_seconds", 0) or 0)
        max_tabs = max(1, int(getattr(self.config, "max_concurrent_tabs", 3) or 3))

        allocations, summary = DurationPlanner.plan_dwell_allocations(
            selected_tabs=selected_tabs,
            target_total_seconds=target_total,
            min_dwell_seconds=min_dwell,
            all_course_tabs=self.all_tasks_cache if self.all_tasks_cache else None,
        )

        mode_names = {
            "serial": "串联顺序模式 (Serial)",
            "decoupled": f"答题/挂机解耦并发模式 (Decoupled, 最大 {max_tabs} 标签页)",
            "pipeline": f"错峰流水线并发模式 (Pipeline, 最大 {max_tabs} 标签页)",
        }
        self._ui_log(f"====== 开始批量处理 {len(selected_tabs)} 个选中任务 ======")
        self._ui_log(f"运行模式: {mode_names.get(mode, mode)}")

        if target_total > 0:
            self._ui_log(
                f"时长预算: 目标总时长 {target_total}s ({DurationPlanner.format_seconds(target_total)}) | "
                f"已学时长 {summary['already_learned_seconds']}s | "
                f"需净增时长 {summary['net_needed_seconds']}s | "
                f"单小节分摊范围 {min(allocations)}s ~ {max(allocations)}s"
            )
        elif min_dwell > 0:
            self._ui_log(f"时长策略: 按单小节保底停留 {min_dwell}s 执行")
        else:
            self._ui_log("时长策略: 极速模式 (0s 额外等待)")

        if mode == "pipeline" and len(selected_tabs) > 1 and max_tabs > 1:
            self._process_tabs_pipeline(selected_tabs, allocations, max_tabs, on_task_done)
        elif mode == "decoupled" and len(selected_tabs) > 1 and max_tabs > 1:
            self._process_tabs_decoupled(selected_tabs, allocations, max_tabs, on_task_done)
        else:
            self._process_tabs_serial(selected_tabs, allocations, on_task_done)

        self._ui_log(
            "\n====== 批量处理结束 ======"
            if not self._should_stop()
            else "\n====== 批量处理已停止 ======"
        )

    def _process_tabs_serial(
        self,
        selected_tabs: List[Dict],
        allocations: List[int],
        on_task_done: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """Serial mode: single tab processes each SCO sequentially."""
        for idx, tab in enumerate(selected_tabs):
            if self._should_stop():
                self._ui_log("收到停止请求，串联处理已中断。")
                break

            scoid = tab.get("scoid", "")
            cid = tab.get("cid") or self.active_cid
            classid = tab.get("classid") or self.active_classid
            direct_url = tab.get("direct_url")
            disp_name = tab.get("l1_title") or scoid
            dwell_sec = allocations[idx] if idx < len(allocations) else self.config.min_dwell_seconds

            self._ui_log(
                f"\n[{idx + 1}/{len(selected_tabs)}] [串联] 正在处理: {disp_name} "
                f"(SCO: {scoid}, 分配时长: {dwell_sec}s)"
            )

            try:
                WeLearnPlayer.navigate_to_sco(
                    self.driver, cid, classid, scoid, direct_url=direct_url
                )

                with WeLearnFrameContext(self.driver, timeout=12.0) as ctx:
                    if not ctx.entered:
                        self._ui_log(f"   警告: 无法切入课件上下文，跳过该小节: {scoid}")
                        continue

                    self.solver.solve_sco(self.driver, scoid, dwell_seconds=dwell_sec)

                WeLearnPlayer.flush_shell_sco(self.driver)
                self._mark_tab_done(tab, on_task_done)

            except Exception as e:
                self._ui_log(f"   处理异常: {e}")
                logger.error("Error processing tab %s: %s", scoid, e, exc_info=True)

            if self._sleep_interruptible(0.8):
                break

    def _process_tabs_pipeline(
        self,
        selected_tabs: List[Dict],
        allocations: List[int],
        max_tabs: int,
        on_task_done: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """
        Staggered Pipeline Mode:
        - Opens up to `max_tabs` browser tabs in parallel.
        - Staggers task launch times and fills DOM answers immediately upon load.
        - Uses an Ordered Submission Gate so tasks submit strictly in catalog order (0 -> 1 -> 2...)
          with an adaptive minimum time gap between consecutive submissions.
        """
        num_workers = min(max_tabs, len(selected_tabs))
        avg_dwell = sum(allocations) / max(1, len(allocations))
        # Adaptive stagger so short tests finish quickly while long sessions space out naturally
        base_ramp_delay = min(15.0, max(0.25, avg_dwell * 0.18))
        base_submit_gap = min(45.0, max(0.35, avg_dwell * 0.22))

        base_handle, worker_handles = self._acquire_worker_tabs(num_workers)
        self._ui_log(
            f"[流水线并发] 已就绪 {len(worker_handles)} 个并发标签页 "
            f"(错峰发车间隔 ~{base_ramp_delay:.1f}s, 保序提交最小间隔 ~{base_submit_gap:.1f}s)"
        )

        # active_slots maps window_handle -> slot metadata dict
        active_slots: Dict[str, Dict[str, Any]] = {}
        skipped_seqs = set()
        next_launch_idx = 0
        next_submit_seq = 0
        last_launch_ts = 0.0
        last_submit_ts = 0.0
        total_tasks = len(selected_tabs)

        try:
            while (next_launch_idx < total_tasks or active_slots) and not self._should_stop():
                now = time.time()

                # 1. Advance next_submit_seq if any sequence index was skipped
                while next_submit_seq in skipped_seqs:
                    next_submit_seq += 1

                # 2. Launch next task into an idle tab if ramp-up stagger allows
                free_handles = [h for h in worker_handles if h not in active_slots]
                if (
                    free_handles
                    and next_launch_idx < total_tasks
                    and (last_launch_ts == 0.0 or (now - last_launch_ts) >= base_ramp_delay)
                ):
                    handle = free_handles[0]
                    seq_idx = next_launch_idx
                    next_launch_idx += 1
                    tab = selected_tabs[seq_idx]
                    scoid = tab.get("scoid", "")
                    cid = tab.get("cid") or self.active_cid
                    classid = tab.get("classid") or self.active_classid
                    direct_url = tab.get("direct_url")
                    disp_name = tab.get("l1_title") or scoid
                    alloc_dwell = float(allocations[seq_idx] if seq_idx < len(allocations) else 0)

                    tab_no = worker_handles.index(handle) + 1
                    self._ui_log(
                        f"\n[流水线发车 #{seq_idx + 1}/{total_tasks} -> Tab {tab_no}] "
                        f"载入并作答: {disp_name} (SCO: {scoid}, 目标停留: {alloc_dwell:.1f}s)"
                    )

                    try:
                        self.driver.switch_to.window(handle)
                        WeLearnPlayer.navigate_to_sco(
                            self.driver, cid, classid, scoid, direct_url=direct_url
                        )
                        WeLearnPlayer.keep_tab_alive(self.driver)

                        with WeLearnFrameContext(self.driver, timeout=12.0) as ctx:
                            if not ctx.entered:
                                self._ui_log(f"   警告: [Tab {tab_no}] 无法切入课件上下文，跳过: {scoid}")
                                skipped_seqs.add(seq_idx)
                                continue

                            stats = self.solver.fill_sco_questions(self.driver, scoid)
                            elapsed = stats.get("elapsed_solving", 0.0)

                        rem_wait = max(0.0, alloc_dwell - elapsed)
                        active_slots[handle] = {
                            "seq_idx": seq_idx,
                            "tab": tab,
                            "scoid": scoid,
                            "disp_name": disp_name,
                            "tab_no": tab_no,
                            "alloc_dwell": alloc_dwell,
                            "ready_at": time.time() + rem_wait,
                        }
                        last_launch_ts = time.time()
                    except Exception as e:
                        self._ui_log(f"   [Tab {tab_no}] 发车异常 ({scoid}): {e}")
                        logger.error("Pipeline launch error on %s: %s", scoid, e, exc_info=True)
                        skipped_seqs.add(seq_idx)
                        continue

                # 3. Ordered Submission Gate: check if the slot with `next_submit_seq` is ready to submit
                target_handle = None
                for h, slot in active_slots.items():
                    if slot["seq_idx"] == next_submit_seq:
                        target_handle = h
                        break

                if target_handle is not None:
                    slot = active_slots[target_handle]
                    now = time.time()
                    submit_gap_ok = (last_submit_ts == 0.0) or ((now - last_submit_ts) >= base_submit_gap)
                    if now >= slot["ready_at"] and submit_gap_ok:
                        tab_no = slot["tab_no"]
                        scoid = slot["scoid"]
                        tab = slot["tab"]
                        self._ui_log(
                            f"[流水线保序提交 #{slot['seq_idx'] + 1}/{total_tasks} <- Tab {tab_no}] "
                            f"挂机已满 ({slot['alloc_dwell']:.1f}s)，正在提交: {slot['disp_name']} ({scoid})"
                        )
                        try:
                            self.driver.switch_to.window(target_handle)
                            with WeLearnFrameContext(self.driver, timeout=8.0) as ctx:
                                if ctx.entered:
                                    self.solver.submit_sco(self.driver, scoid)
                            WeLearnPlayer.flush_shell_sco(self.driver)
                        except Exception as e:
                            self._ui_log(f"   [Tab {tab_no}] 提交异常 ({scoid}): {e}")

                        last_submit_ts = time.time()
                        self._mark_tab_done(tab, on_task_done)
                        del active_slots[target_handle]
                        next_submit_seq += 1
                        continue

                time.sleep(0.15)
        finally:
            self._cleanup_worker_tabs(base_handle, worker_handles)

    def _process_tabs_decoupled(
        self,
        selected_tabs: List[Dict],
        allocations: List[int],
        max_tabs: int,
        on_task_done: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """
        Decoupled Mode:
        - Phase 1: Single primary tab answers and submits all undone SCOs strictly sequentially
          with brief spacing so `submit_time` timeline is 100% single-threaded.
        - Phase 2: Multi-tab worker pool concurrently opens SCOs that still need remaining dwell time
          and keeps them alive until their allocated duration is met (without re-clicking submit).
        """
        total_tasks = len(selected_tabs)
        remaining_dwells: List[Tuple[int, Dict, float]] = []

        self._ui_log(f"\n--- [解耦模式 阶段 1/2] 单标签页顺序快速作答与提交 (共 {total_tasks} 个小节) ---")
        for idx, tab in enumerate(selected_tabs):
            if self._should_stop():
                return

            scoid = tab.get("scoid", "")
            cid = tab.get("cid") or self.active_cid
            classid = tab.get("classid") or self.active_classid
            direct_url = tab.get("direct_url")
            disp_name = tab.get("l1_title") or scoid
            alloc_dwell = float(allocations[idx] if idx < len(allocations) else 0)
            is_already_done = tab.get("status") == "done"

            if is_already_done:
                self._ui_log(
                    f"[{idx + 1}/{total_tasks}] [已完成小节] {disp_name} ({scoid}) 跳过重做，转入阶段 2 补时长 ({alloc_dwell:.1f}s)"
                )
                if alloc_dwell > 0.2:
                    remaining_dwells.append((idx, tab, alloc_dwell))
                else:
                    self._mark_tab_done(tab, on_task_done)
                continue

            # Brief dwell during Phase 1 so sequential submit timestamps are naturally spaced
            phase1_wait = min(alloc_dwell, 1.5)
            t0 = time.time()
            self._ui_log(f"[{idx + 1}/{total_tasks}] [阶段1-顺序作答] {disp_name} (SCO: {scoid})")
            try:
                WeLearnPlayer.navigate_to_sco(
                    self.driver, cid, classid, scoid, direct_url=direct_url
                )
                with WeLearnFrameContext(self.driver, timeout=12.0) as ctx:
                    if not ctx.entered:
                        self._ui_log(f"   警告: 无法切入课件上下文，跳过: {scoid}")
                        continue
                    self.solver.solve_sco(self.driver, scoid, dwell_seconds=phase1_wait)
                WeLearnPlayer.flush_shell_sco(self.driver)
            except Exception as e:
                self._ui_log(f"   阶段1作答异常 ({scoid}): {e}")
                continue

            spent = time.time() - t0
            rem = max(0.0, alloc_dwell - spent)
            if rem > 0.3:
                remaining_dwells.append((idx, tab, rem))
            else:
                self._mark_tab_done(tab, on_task_done)

        if not remaining_dwells or self._should_stop():
            return

        num_workers = min(max_tabs, len(remaining_dwells))
        avg_rem = sum(r for _, _, r in remaining_dwells) / max(1, len(remaining_dwells))
        ramp_delay = min(10.0, max(0.2, avg_rem * 0.15))

        self._ui_log(
            f"\n--- [解耦模式 阶段 2/2] 启动 {num_workers} 个后台标签页并发纯挂时长 "
            f"(共 {len(remaining_dwells)} 个小节待补齐时长，不重复点击提交) ---"
        )

        base_handle, worker_handles = self._acquire_worker_tabs(num_workers)
        active_slots: Dict[str, Dict[str, Any]] = {}
        queue_idx = 0
        last_launch_ts = 0.0

        try:
            while (queue_idx < len(remaining_dwells) or active_slots) and not self._should_stop():
                now = time.time()
                free_handles = [h for h in worker_handles if h not in active_slots]

                if (
                    free_handles
                    and queue_idx < len(remaining_dwells)
                    and (last_launch_ts == 0.0 or (now - last_launch_ts) >= ramp_delay)
                ):
                    handle = free_handles[0]
                    orig_idx, tab, rem_sec = remaining_dwells[queue_idx]
                    queue_idx += 1
                    scoid = tab.get("scoid", "")
                    cid = tab.get("cid") or self.active_cid
                    classid = tab.get("classid") or self.active_classid
                    direct_url = tab.get("direct_url")
                    disp_name = tab.get("l1_title") or scoid
                    tab_no = worker_handles.index(handle) + 1

                    self._ui_log(
                        f"[阶段2-并发挂机 #{orig_idx + 1} -> Tab {tab_no}] "
                        f"打开 {disp_name} ({scoid}) 纯挂机 {rem_sec:.1f}s..."
                    )
                    try:
                        self.driver.switch_to.window(handle)
                        WeLearnPlayer.navigate_to_sco(
                            self.driver, cid, classid, scoid, direct_url=direct_url
                        )
                        WeLearnPlayer.keep_tab_alive(self.driver)
                        active_slots[handle] = {
                            "orig_idx": orig_idx,
                            "tab": tab,
                            "scoid": scoid,
                            "disp_name": disp_name,
                            "tab_no": tab_no,
                            "rem_sec": rem_sec,
                            "ready_at": time.time() + rem_sec,
                        }
                        last_launch_ts = time.time()
                    except Exception as e:
                        self._ui_log(f"   [Tab {tab_no}] 挂机载入异常 ({scoid}): {e}")
                        self._mark_tab_done(tab, on_task_done)
                        continue

                # Check any slot whose dwell timer has completed
                finished_handles = [
                    h for h, slot in active_slots.items() if time.time() >= slot["ready_at"]
                ]
                for h in finished_handles:
                    slot = active_slots.pop(h)
                    tab = slot["tab"]
                    scoid = slot["scoid"]
                    tab_no = slot["tab_no"]
                    try:
                        self.driver.switch_to.window(h)
                        WeLearnPlayer.flush_shell_sco(self.driver)
                    except Exception:
                        pass
                    self._ui_log(
                        f"[阶段2-挂机完成 #{slot['orig_idx'] + 1} <- Tab {tab_no}] "
                        f"{slot['disp_name']} ({scoid}) 已补齐时长 ({slot['rem_sec']:.1f}s)"
                    )
                    self._mark_tab_done(tab, on_task_done)

                time.sleep(0.15)
        finally:
            self._cleanup_worker_tabs(base_handle, worker_handles)

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
