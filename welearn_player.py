# -*- coding: utf-8 -*-
"""
WeLearn StudyCourse Shell & Content Iframe Context Manager.

Derived from UnipusAI-Helper (PublishPlayer pattern) by YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
import time
from typing import Optional

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("WeLearnBot")


class WeLearnPlayer:
    """WeLearn StudyCourse shell player interactions."""

    SHELL_PATH = "student/StudyCourse.aspx"
    CONTENT_FRAME_ID = "contentFrame"
    CONTENT_FRAME_SELECTORS = (
        'iframe#contentFrame',
        'iframe[name="contentFrame"]',
        'iframe[src*="centercourseware.sflep.com"]',
        'iframe[src*="main"]',
    )

    @classmethod
    def is_shell_page(cls, driver) -> bool:
        """Check if current driver page is the StudyCourse shell."""
        try:
            url = driver.current_url or ""
            return cls.SHELL_PATH.lower() in url.lower()
        except Exception:
            return False

    @classmethod
    def get_current_scoid(cls, driver) -> str:
        """Extract the active scoid from the shell URL or page variable."""
        try:
            url = driver.current_url or ""
            if "sco=" in url:
                return url.split("sco=")[1].split("&")[0]
            val = driver.execute_script("return window.cur_scoid || (window.API_1484_11 && window.API_1484_11.scoid) || '';")
            if val:
                return str(val)
        except Exception:
            pass
        return ""

    @classmethod
    def find_content_frame(cls, driver):
        """Locate contentFrame element in top-level document."""
        driver.switch_to.default_content()
        for sel in cls.CONTENT_FRAME_SELECTORS:
            try:
                frames = driver.find_elements(By.CSS_SELECTOR, sel)
                if frames:
                    return frames[0]
            except Exception:
                continue
        return None

    @classmethod
    def navigate_to_sco(cls, driver, cid: str, classid: str, scoid: str) -> bool:
        """Navigate to or switch active SCO."""
        logger.info("Switching to SCO: %s", scoid)
        
        # If already on the StudyCourse shell for this cid/classid, try JS switch first
        if cls.is_shell_page(driver):
            curr_url = driver.current_url or ""
            if f"cid={cid}" in curr_url and f"classid={classid}" in curr_url:
                try:
                    driver.switch_to.default_content()
                    # Try SelectSCO or SelectSamePageSCO javascript function
                    switched = driver.execute_script(
                        """
                        var targetSco = arguments[0];
                        if (typeof window.SelectSCO === 'function') {
                            window.SelectSCO(targetSco);
                            return true;
                        } else if (typeof window.SelectSamePageSCO === 'function') {
                            window.SelectSamePageSCO(targetSco);
                            return true;
                        }
                        return false;
                        """,
                        scoid,
                    )
                    if switched:
                        time.sleep(1.5)
                        return True
                except Exception as e:
                    logger.debug("JS SelectSCO switch failed, will navigate via URL: %s", e)

                # Try clicking sidebar node
                try:
                    driver.switch_to.default_content()
                    side_li = driver.find_elements(By.CSS_SELECTOR, f"#liSCO_{scoid}, [data-scoid='{scoid}']")
                    if side_li:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", side_li[0])
                        time.sleep(1.5)
                        return True
                except Exception:
                    pass

        # Direct navigation to StudyCourse shell URL
        target_url = f"https://welearn.sflep.com/student/StudyCourse.aspx?cid={cid}&classid={classid}&sco={scoid}"
        driver.get(target_url)
        time.sleep(2.0)
        return True


class WeLearnFrameContext:
    """Context manager for entering the contentFrame and safely exiting to top."""

    def __init__(self, driver, timeout: float = 10.0):
        self.driver = driver
        self.timeout = timeout
        self.entered = False

    def __enter__(self):
        self.entered = self.enter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.driver.switch_to.default_content()
        except Exception:
            pass
        return False

    def enter(self) -> bool:
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                frame_el = WeLearnPlayer.find_content_frame(self.driver)
                if frame_el:
                    self.driver.switch_to.frame(frame_el)
                    self.entered = True
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("Failed to enter contentFrame within %.1f seconds", self.timeout)
        return False
