# -*- coding: utf-8 -*-
"""
WebDriver Helper utilities for browser automation.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
import random
import time
from typing import Any, List, Optional, Union

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("WeLearnBot")


class WebDriverHelper:
    """WebDriver interaction helper methods."""

    @staticmethod
    def human_like_delay(base_delay: float = 0.2) -> None:
        """Introduce a slight randomized delay mimicking human interaction."""
        delay = max(0.05, base_delay * (0.8 + random.random() * 0.4))
        time.sleep(delay)

    @staticmethod
    def safe_find_element(
        driver, selectors: Union[str, List[str]], parent=None, timeout: float = 5.0
    ) -> Optional[Any]:
        """Safely locate a single element by trying one or more CSS selectors."""
        search_context = parent if parent is not None else driver
        if isinstance(selectors, str):
            selectors = [selectors]

        wait = WebDriverWait(search_context, timeout)
        for selector in selectors:
            try:
                element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element and element.is_displayed():
                    return element
            except (TimeoutException, NoSuchElementException):
                continue
            except Exception as e:
                logger.debug("safe_find_element error with selector %s: %s", selector, e)
                continue
        return None

    @staticmethod
    def safe_find_elements(
        driver, selectors: Union[str, List[str]], parent=None
    ) -> List[Any]:
        """Safely locate multiple visible elements by one or more CSS selectors."""
        search_context = parent if parent is not None else driver
        if isinstance(selectors, str):
            selectors = [selectors]

        for selector in selectors:
            try:
                elements = search_context.find_elements(By.CSS_SELECTOR, selector)
                visible = [e for e in elements if e.is_displayed()]
                if visible:
                    return visible
                elif elements:
                    return elements
            except Exception as e:
                logger.debug("safe_find_elements error with selector %s: %s", selector, e)
                continue
        return []

    @staticmethod
    def safe_click(driver, element, retries: int = 3) -> bool:
        """Safely click an element with scroll-into-view and JS fallback."""
        if element is None:
            return False

        for i in range(retries):
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                    element,
                )
                time.sleep(0.2)

                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                return True
            except StaleElementReferenceException:
                if i < retries - 1:
                    time.sleep(0.5)
                    continue
            except Exception as e:
                if i < retries - 1:
                    time.sleep(0.5)
                    continue
                logger.debug("safe_click failed: %s", e)
        return False

    @staticmethod
    def simulate_typing(driver, element, text: str) -> None:
        """Simulate human typing with keystroke delays and event dispatches."""
        if element is None or text is None:
            return

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                element,
            )
        except Exception:
            pass

        try:
            actions = ActionChains(driver)
            actions.move_to_element(element).click().perform()
        except Exception:
            try:
                element.click()
            except Exception:
                pass

        WebDriverHelper.human_like_delay(0.1)

        try:
            element.clear()
        except Exception:
            pass

        WebDriverHelper.human_like_delay(0.1)

        for char in str(text):
            try:
                element.send_keys(char)
            except Exception:
                # If send_keys fails (e.g. non-BMP chars), set value directly
                driver.execute_script(
                    "arguments[0].value = (arguments[0].value || '') + arguments[1];",
                    element,
                    char,
                )
            time.sleep(random.uniform(0.015, 0.05))

        # Dispatch standard input/change/blur events to notify page scripts
        try:
            driver.execute_script(
                """
                var el = arguments[0];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
                """,
                element,
            )
        except Exception:
            pass

        WebDriverHelper.human_like_delay(0.1)
