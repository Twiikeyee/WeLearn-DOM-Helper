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
    def is_direct_courseware_page(cls, driver) -> bool:
        """Check if current top-level page is already a direct courseware/static CDN DOM."""
        try:
            url = (driver.current_url or "").lower()
            if "centercourseware.sflep.com" in url:
                return True
            els = driver.find_elements(
                By.CSS_SELECTOR,
                'li[data-scoid], [data-controltype="choice"], [data-controltype="filling"], [data-controltype="submit"]',
            )
            return len(els) > 0
        except Exception:
            return False

    @classmethod
    def activate_direct_sco_page(cls, driver, scoid: str) -> None:
        """Activate a specific li[data-scoid] when running directly on a static CDN courseware page."""
        if not scoid:
            return
        try:
            driver.execute_script(
                """
                var targetSco = arguments[0];
                if (typeof window.SelectSamePageSCO === 'function') {
                    try { window.SelectSamePageSCO(targetSco); } catch(e) {}
                }
                var allPages = document.querySelectorAll('li[data-scoid][data-controltype="page"], li[data-scoid]');
                if (allPages.length > 0) {
                    for (var i = 0; i < allPages.length; i++) {
                        var el = allPages[i];
                        if (el.getAttribute('data-scoid') === targetSco) {
                            el.style.display = 'block';
                            el.setAttribute(' data-active', 'true');
                        } else if (el.getAttribute('data-controltype') === 'page') {
                            el.style.display = 'none';
                        }
                    }
                }
                window.cur_scoid = targetSco;
                """,
                scoid,
            )
        except Exception:
            pass

    @classmethod
    def install_shell_patches(cls, driver) -> None:
        """
        Patch StudyCourse.aspx front-end JS to prevent multi-tab studyTicket self-kickout,
        blocking alerts, and 30-minute idle ReturnMain redirects.
        """
        try:
            driver.execute_script(
                """
                try {
                    Object.defineProperty(document, 'hidden', {value: false, configurable: true});
                    Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true});
                } catch(e) {}

                window.ReturnMain = function() {
                    console.log('[WeLearnBot] Blocked ReturnMain redirect');
                };
                window.alert = function(msg) {
                    console.log('[WeLearnBot] Auto-dismissed alert:', msg);
                };
                if (typeof window.actTimerID !== 'undefined') {
                    try { clearInterval(window.actTimerID); } catch(e) {}
                }
                if (typeof window.MoveMouse === 'function') {
                    try { window.MoveMouse(); } catch(e) {}
                }
                if (window.jQuery && !window.__welearn_ticket_patched) {
                    window.__welearn_ticket_patched = true;
                    window.jQuery.ajaxPrefilter(function(options) {
                        var origSuccess = options.success;
                        if (origSuccess) {
                            options.success = function(reData) {
                                try {
                                    if (reData && reData.ticket) {
                                        window.studyTicket = decodeURIComponent(reData.ticket);
                                    }
                                } catch(e) {}
                                return origSuccess.apply(this, arguments);
                            };
                        }
                    });
                }
                """
            )
        except Exception:
            pass

    @classmethod
    def _wait_for_shell_sco_ready(cls, driver, scoid: str, prev_src: str = "", timeout: float = 8.0) -> None:
        """Wait for SelectSCO animation (400ms) + AJAX loadSco + contentFrame ready."""
        deadline = time.time() + timeout
        # Wait at least 0.6s for the 400ms jQuery sidebar slide animation to trigger SelectSCOAfter
        time.sleep(0.65)
        while time.time() < deadline:
            try:
                state = driver.execute_script(
                    """
                    var f = document.getElementById('contentFrame');
                    var src = f ? (f.src || '') : '';
                    return {
                        curSco: window.scoid || '',
                        src: src,
                        hasApi: typeof window.API_1484_11 !== 'undefined'
                    };
                    """
                )
                if state and state.get("src") and "about:blank" not in state.get("src"):
                    curr_src = state.get("src", "")
                    if not prev_src or curr_src != prev_src or scoid in curr_src:
                        break
            except Exception:
                pass
            time.sleep(0.25)
        time.sleep(0.6)

    @classmethod
    def navigate_to_sco(
        cls,
        driver,
        cid: str,
        classid: str,
        scoid: str,
        direct_url: Optional[str] = None,
    ) -> bool:
        """Navigate to or switch active SCO (supports both StudyCourse shell and static CDN direct URL)."""
        logger.info("Switching to SCO: %s", scoid)

        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass

        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        # Static CDN or direct courseware URL mode
        if direct_url:
            curr_url = (driver.current_url or "").split("#")[0]
            target_base = direct_url.split("#")[0]
            if curr_url != target_base:
                driver.get(direct_url)
                time.sleep(0.8)
            cls.activate_direct_sco_page(driver, scoid)
            return True

        # If already on a direct courseware page (e.g. static CDN test page)
        if not cls.is_shell_page(driver) and cls.is_direct_courseware_page(driver):
            cls.activate_direct_sco_page(driver, scoid)
            return True

        # If already on the StudyCourse shell for this cid/classid, switch via JS
        if cls.is_shell_page(driver):
            curr_url = driver.current_url or ""
            if f"cid={cid}" in curr_url and f"classid={classid}" in curr_url:
                cls.install_shell_patches(driver)
                try:
                    prev_info = driver.execute_script(
                        """
                        var f = document.getElementById('contentFrame');
                        return {curSco: window.scoid || '', src: f ? (f.src || '') : ''};
                        """
                    ) or {}
                    prev_src = prev_info.get("src", "")
                    # If already on the exact scoid and startsco needs to be refreshed
                    switched = driver.execute_script(
                        """
                        var targetSco = arguments[0];
                        sessionStorage.setItem('lastscoid', targetSco);
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
                        cls._wait_for_shell_sco_ready(driver, scoid, prev_src=prev_src)
                        cls.install_shell_patches(driver)
                        return True
                except Exception as e:
                    logger.debug("JS SelectSCO switch failed, will navigate via URL: %s", e)

        # Direct navigation to StudyCourse shell URL (e.g. first load or new worker tab)
        target_url = f"https://welearn.sflep.com/student/StudyCourse.aspx?cid={cid}&classid={classid}&sco={scoid}"
        driver.get(target_url)
        time.sleep(1.5)
        cls.install_shell_patches(driver)
        try:
            prev_src = driver.execute_script(
                "var f = document.getElementById('contentFrame'); return f ? (f.src || '') : '';"
            ) or ""
            driver.execute_script(
                """
                var targetSco = arguments[0];
                sessionStorage.setItem('lastscoid', targetSco);
                if (typeof window.SelectSCO === 'function') {
                    window.SelectSCO(targetSco);
                }
                """,
                scoid,
            )
            cls._wait_for_shell_sco_ready(driver, scoid, prev_src=prev_src)
            cls.install_shell_patches(driver)
        except Exception:
            pass
        return True

    @classmethod
    def keep_tab_alive(cls, driver) -> None:
        """Install anti-kickout patches, spoof visibility state, and keep timer active in background tabs."""
        cls.install_shell_patches(driver)

    @classmethod
    def flush_shell_sco(cls, driver) -> None:
        """
        Explicitly trigger KeepLearnTimeAndCheckToken() + EndSCO(false) at the end of a SCO dwell
        so sub-60s and remainder study seconds are immediately credited by the server.
        """
        try:
            driver.switch_to.default_content()
            cls.install_shell_patches(driver)
            driver.execute_script(
                """
                if (typeof window.KeepLearnTimeAndCheckToken === 'function') {
                    try { window.KeepLearnTimeAndCheckToken(); } catch(e) {}
                }
                if (typeof window.EndSCO === 'function') {
                    try { window.EndSCO(false); } catch(e) {}
                }
                """
            )
        except Exception:
            pass


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
                if WeLearnPlayer.is_direct_courseware_page(self.driver):
                    self.entered = True
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("Failed to enter contentFrame within %.1f seconds", self.timeout)
        return False
