# -*- coding: utf-8 -*-
"""
WeLearn-DOM-Helper: Browser Automation & LLM Auxiliary Tool for SFLEP WeLearn.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import atexit
import logging
import os
import queue
import sys
import threading
import time

from fluent_ui import FluentModernGUI
from welearn_bot import WeLearnBot
from welearn_config import Config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

gui_log_queue = queue.Queue()


def setup_logging():
    logger = logging.getLogger("WeLearnBot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_file = os.path.join(LOGS_DIR, "welearn_helper.log")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def main():
    logger = setup_logging()
    logger.info("Initializing WeLearn-DOM-Helper...")

    # Load configuration
    config = Config.from_json()

    # Initialize bot
    bot = WeLearnBot(config, gui_log_queue)

    def cleanup():
        if bot.driver:
            try:
                bot.driver.quit()
            except Exception:
                pass

    atexit.register(cleanup)

    # Initialize GUI
    gui = FluentModernGUI(bot)

    def background_startup():
        gui_log_queue.put("正在启动浏览器并连接 WeLearn 平台...")
        try:
            bot.start_driver()
            logged_in = bot.check_or_prompt_login()
            if logged_in:
                gui_log_queue.put("登录就绪！点击【扫描任务列表】即可加载全部单元与小节任务。")
        except Exception as e:
            gui_log_queue.put(f"启动或登录异常: {e}")
            logger.error("Startup error: %s", e, exc_info=True)

    # Launch driver & login watcher in background thread
    startup_thread = threading.Thread(target=background_startup, daemon=True)
    startup_thread.start()

    # Start GUI main loop
    exit_code = gui.mainloop()

    # Ensure cleanup on GUI exit
    bot.request_stop()
    cleanup()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
