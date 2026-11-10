# -*- coding: utf-8 -*-
"""
Terminal / CLI Controller for WeLearn-DOM-Helper.

Supports full automation, inspection of locked ("未开放") SCOs,
direct bypassing via action=scoAddr, and single/batch testing in real environment.

Licensed under GNU AGPLv3.
"""

import argparse
import glob
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By

import queue
from question_solver import WeLearnQuestionSolver
from welearn_api import WeLearnAPI
from welearn_bot import WeLearnBot
from welearn_config import Config
from welearn_player import WeLearnFrameContext, WeLearnPlayer

logger = logging.getLogger("WeLearnCLI")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def find_active_profile() -> Optional[str]:
    """Search for existing authenticated Edge profile on macOS/Windows."""
    candidates = []
    # Search in macOS temp folders
    for base in [os.environ.get("TMPDIR", ""), "/tmp", "/var/folders"]:
        if base and os.path.exists(base):
            for path in glob.glob(f"{base}/**/welearn_profile_*", recursive=True):
                cookies_db = os.path.join(path, "Default", "Cookies")
                if os.path.exists(cookies_db):
                    candidates.append((os.path.getmtime(cookies_db), path))

    # Also check /tmp/welearn_test_profile
    if os.path.exists("/tmp/welearn_test_profile/Default/Cookies"):
        candidates.append((os.path.getmtime("/tmp/welearn_test_profile/Default/Cookies"), "/tmp/welearn_test_profile"))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


class WeLearnCLI:
    def __init__(self, cid: str = "4395", headless: bool = False, profile_dir: Optional[str] = None):
        self.cid = str(cid)
        self.headless = headless
        self.config = Config.from_json()
        self.profile_dir = profile_dir or find_active_profile()
        self.driver: Optional[webdriver.Edge] = None
        self.uid: str = ""
        self.classid: str = ""
        self.units: List[Dict] = []
        self.scos_cache: Dict[int, List[Dict]] = {}
        self.solver = WeLearnQuestionSolver(config=self.config, log_callback=print)

    def init_driver(self):
        """Initialize Edge with existing authenticated profile copy."""
        if not self.profile_dir or not os.path.exists(self.profile_dir):
            print("未找到现有 Edge 登录 Profile，使用新建临时目录...")
            active_dir = tempfile.mkdtemp(prefix="welearn_cli_profile_")
        else:
            print(f"检测并复用已有 Edge 登录会话 Profile: {self.profile_dir}")
            active_dir = "/tmp/welearn_cli_active_profile"
            if os.path.exists(active_dir):
                try:
                    shutil.rmtree(active_dir)
                except Exception:
                    pass
            try:
                shutil.copytree(self.profile_dir, active_dir)
            except Exception as e:
                print(f"复制 Profile 失败，直接挂载: {e}")
                active_dir = self.profile_dir

        options = EdgeOptions()
        options.add_argument(f"--user-data-dir={active_dir}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        if self.headless:
            options.add_argument("--headless=new")

        print("正在启动 Edge 浏览器...")
        self.driver = webdriver.Edge(options=options)
        self._ensure_session()

    def _ensure_session(self):
        """Navigate to course_info to verify login and retrieve uid/classid."""
        url = f"https://welearn.sflep.com/student/course_info.aspx?cid={self.cid}"
        print(f"正在加载课程主页: {url}")
        self.driver.get(url)
        time.sleep(2)

        import re
        html = self.driver.page_source
        uid_m = re.search(r'"uid":\s*"?(\d+)"?', html)
        classid_m = re.search(r'"classid":\s*"([^"]+)"', html)
        if uid_m and classid_m:
            self.uid = uid_m.group(1)
            self.classid = classid_m.group(1)
            print(f"登录握手成功！用户 UID: {self.uid} | 班级 ClassID: {self.classid}")
        else:
            print("未能自动解析到 UID/ClassID，请确认 Edge 中是否已登录 WeLearn！")

    def fetch_units(self) -> List[Dict]:
        """Fetch all course units via browser session."""
        js = f"""
        var cb = arguments[arguments.length - 1];
        fetch('/ajax/StudyStat.aspx?action=courseunits&cid={self.cid}&uid={self.uid}')
            .then(r => r.json())
            .then(d => cb(d.info || []))
            .catch(e => cb([]));
        """
        self.units = self.driver.execute_async_script(js)
        return self.units

    def fetch_scos(self, unit_idx: int) -> List[Dict]:
        """Fetch all SCOs for given unit (including isvisible=false locked items)."""
        if unit_idx in self.scos_cache:
            return self.scos_cache[unit_idx]

        js = f"""
        var cb = arguments[arguments.length - 1];
        fetch('/ajax/StudyStat.aspx?action=scoLeaves&cid={self.cid}&uid={self.uid}&unitidx={unit_idx}&classid={self.classid}')
            .then(r => r.json())
            .then(d => cb(d.info || []))
            .catch(e => cb([]));
        """
        scos = self.driver.execute_async_script(js)
        self.scos_cache[unit_idx] = scos
        return scos

    def get_courseware_url(self, scoid: str) -> Optional[str]:
        """Bypass locked state by calling POST /Ajax/SCO.aspx?action=scoAddr."""
        js = f"""
        var cb = arguments[arguments.length - 1];
        var scoid = arguments[0];
        fetch('/Ajax/SCO.aspx?uid={self.uid}', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}},
            body: 'action=scoAddr&cid={self.cid}&scoid=' + encodeURIComponent(scoid)
        }})
        .then(r => r.json())
        .then(d => cb(d.addr || ''))
        .catch(e => cb(''));
        """
        addr = self.driver.execute_async_script(js, scoid)
        return WeLearnAPI.normalize_cdn_addr(addr or "")

    def solve_sco(self, scoid: str, location_hint: str = "") -> bool:
        """Execute complete solve workflow for an SCO (even if locked in UI)."""
        print(f"\n{'='*60}")
        print(f">> 开始处理 SCO: [{scoid}] {location_hint}")
        print(f"{'='*60}")

        # Step 1: Ensure we are in StudyCourse shell
        shell_url = f"https://welearn.sflep.com/student/StudyCourse.aspx?cid={self.cid}&classid={self.classid}&sco={scoid}"
        curr_url = self.driver.current_url or ""
        if "studycourse.aspx" not in curr_url.lower():
            self.driver.get(shell_url)
            time.sleep(2)

        # Step 2: Trigger SelectSCO in shell (which bypasses UI lock and sets iframe src)
        self.driver.switch_to.default_content()
        self.driver.execute_script("SelectSCO(arguments[0]);", scoid)
        time.sleep(2.5)

        # Step 3: Enter contentFrame
        try:
            frame = self.driver.find_element(By.ID, "contentFrame")
            self.driver.switch_to.frame(frame)
            time.sleep(1)
        except Exception as e:
            print(f"切入 contentFrame 失败: {e}")
            self.driver.switch_to.default_content()
            return False

        # Step 4: Run question solver inside frame
        try:
            self.solver.solve_sco(self.driver, scoid)
        except Exception as e:
            print(f"答题流程发生异常: {e}")
        finally:
            self.driver.switch_to.default_content()
            try:
                # Trigger native shell LMS save
                res = self.driver.execute_script("""
                if (typeof window.EndSCO === 'function') {
                    return window.EndSCO(false);
                }
                return null;
                """)
                if res:
                    print("   SCORM 外壳已持久化保存 (EndSCO ok)")
            except Exception:
                pass

        return True

    def run_batch_with_bot(
        self,
        scos_list: List[Dict],
        mode: str = "pipeline",
        target_total_seconds: int = 8,
        max_tabs: int = 3,
        use_static_cdn: bool = False,
    ) -> None:
        """Run a batch of SCOs through WeLearnBot using the specified concurrency mode and total duration."""
        log_q: queue.Queue = queue.Queue()
        self.config.concurrency_mode = mode
        self.config.target_total_seconds = target_total_seconds
        self.config.max_concurrent_tabs = max_tabs

        bot = WeLearnBot(self.config, log_q)
        bot.driver = self.driver
        bot.active_cid = self.cid
        bot.active_uid = self.uid
        bot.active_classid = self.classid

        selected_tabs = []
        for idx, s in enumerate(scos_list):
            scoid = s.get("id") or s.get("scoid") or f"m-1-1-{idx+1}"
            direct_url = s.get("direct_url")
            if use_static_cdn and not direct_url and self.uid:
                direct_url = self.get_courseware_url(scoid)
            selected_tabs.append(
                {
                    "scoid": scoid,
                    "l1_title": s.get("location") or scoid,
                    "cid": self.cid,
                    "classid": self.classid,
                    "uid": self.uid,
                    "learntime": s.get("learntime", "00:00:00"),
                    "status": "done" if ("已" in str(s.get("iscomplete", ""))) else "not_started",
                    "direct_url": direct_url,
                }
            )

        def drain_logs():
            while not log_q.empty():
                try:
                    print(log_q.get_nowait())
                except Exception:
                    break

        bot.process_selected_tabs(selected_tabs, on_task_done=lambda _: drain_logs())
        drain_logs()

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="WeLearn-DOM-Helper Terminal CLI Controller")
    parser.add_argument("--cid", default="4395", help="Course ID (default: 4395)")
    parser.add_argument("--sco", default="", help="Single SCO ID to solve (e.g. m-1-1-8)")
    parser.add_argument("--unit", type=int, default=-1, help="Unit index to process (0-based)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of SCOs when processing a unit")
    parser.add_argument("--mode", default="serial", choices=["serial", "decoupled", "pipeline"], help="Concurrency mode")
    parser.add_argument("--total-time", type=int, default=0, help="Target total duration in seconds")
    parser.add_argument("--tabs", type=int, default=3, help="Max concurrent tabs (default: 3)")
    parser.add_argument("--cdn", action="store_true", help="Use static CDN URLs (action=scoAddr) for testing")
    parser.add_argument("--list", action="store_true", help="List all units and SCOs for course")
    parser.add_argument("--head", action="store_true", help="Run in headed mode (display browser)")
    args = parser.parse_args()

    cli = WeLearnCLI(cid=args.cid, headless=not args.head)
    cli.init_driver()

    try:
        units = cli.fetch_units()
        print(f"\n课程 CID {cli.cid} 共包含 {len(units)} 个单元:")
        for idx, u in enumerate(units):
            print(f"  [{idx}] {u.get('unitname')} (visible: {u.get('visible')})")

        if args.list:
            for uidx in range(len(units)):
                scos = cli.fetch_scos(uidx)
                print(f"\n--- Unit {uidx}: {units[uidx].get('unitname')} ({len(scos)} 个小节) ---")
                for s in scos:
                    vis = "开放" if str(s.get("isvisible")).lower() != "false" else "未开放"
                    comp = s.get("iscomplete", "未完成")
                    lt = s.get("learntime", "00:00:00")
                    print(f"  SCO [{s.get('id'):10}] | [{vis}] [{comp:^4}] | ⏱ {lt} | {s.get('location')}")
            return

        if args.sco:
            cli.solve_sco(args.sco)
            return

        if args.unit >= 0:
            scos = cli.fetch_scos(args.unit)
            if args.limit > 0:
                scos = scos[: args.limit]
            print(
                f"\n开始批处理 Unit {args.unit} (共 {len(scos)} 个小节, 模式={args.mode}, "
                f"目标总时长={args.total_time}s, 并发标签页={args.tabs}, CDN直连={args.cdn}):"
            )
            cli.run_batch_with_bot(
                scos,
                mode=args.mode,
                target_total_seconds=args.total_time,
                max_tabs=args.tabs,
                use_static_cdn=args.cdn,
            )
            return

        # Interactive Mode
        print("\n" + "="*50)
        print("WeLearn 终端交互式控制台")
        print("="*50)
        print("1. 查看所有单元与小节详情 (含未开放状态)")
        print("2. 测试单个典型小节 (例如: m-1-1-8 选择题 / m-1-1-6 填空题)")
        print("3. 按单元批处理做题 (自动穿透未开放限制)")
        print("0. 退出")

        choice = input("\n请选择操作 [1/2/3/0]: ").strip()
        if choice == "1":
            for uidx in range(len(units)):
                scos = cli.fetch_scos(uidx)
                print(f"\n--- Unit {uidx}: {units[uidx].get('unitname')} ({len(scos)} 个小节) ---")
                for s in scos:
                    vis = "开放" if str(s.get("isvisible")).lower() != "false" else "未开放"
                    comp = s.get("iscomplete", "未完成")
                    print(f"  SCO [{s.get('id'):10}] | [{vis}] [{comp:^4}] | {s.get('location')}")
        elif choice == "2":
            target_sco = input("请输入要测试的 SCO ID (如 m-1-1-8 或 m-1-1-6): ").strip()
            if target_sco:
                cli.solve_sco(target_sco)
        elif choice == "3":
            unit_in = input(f"请输入要处理的单元编号 [0-{len(units)-1}]: ").strip()
            if unit_in.isdigit():
                uidx = int(unit_in)
                scos = cli.fetch_scos(uidx)
                for s in scos:
                    cli.solve_sco(s.get("id"), location_hint=s.get("location", ""))

    finally:
        cli.close()
        print("\nCLI 运行结束，资源已安全释放。")


if __name__ == "__main__":
    main()
