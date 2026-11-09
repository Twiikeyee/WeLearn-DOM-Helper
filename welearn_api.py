# -*- coding: utf-8 -*-
"""
WeLearn Platform Catalog and Course API Client.

Derived from Welearn_helper & UnipusAI-Helper (GNU AGPLv3).
Licensed under GNU AGPLv3.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("WeLearnBot")

AJAX_BASE = "https://welearn.sflep.com"


@dataclass
class WeLearnCourse:
    cid: str
    name: str
    progress: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WeLearnUnit:
    unit_idx: int
    name: str
    visible: bool = True
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WeLearnSCO:
    scoid: str
    location: str
    unit_idx: int
    unit_name: str
    iscomplete: bool
    isvisible: bool
    learntime: str
    raw_data: Dict[str, Any] = field(default_factory=dict)


class WeLearnAPI:
    """WeLearn API wrapper executing in browser context or via HTTP session."""

    @staticmethod
    def execute_browser_fetch(driver, url: str, method: str = "GET", body: Optional[dict] = None) -> Any:
        """Execute fetch() inside the Selenium driver context to share active cookies."""
        js_code = """
        var callback = arguments[arguments.length - 1];
        var url = arguments[0];
        var method = arguments[1];
        var bodyData = arguments[2];
        
        var options = {
            method: method,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01'
            },
            credentials: 'same-origin'
        };
        
        if (bodyData && method.toUpperCase() === 'POST') {
            var formBody = [];
            for (var property in bodyData) {
                var encodedKey = encodeURIComponent(property);
                var encodedValue = encodeURIComponent(bodyData[property]);
                formBody.push(encodedKey + "=" + encodedValue);
            }
            options.body = formBody.join("&");
            options.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
        }
        
        fetch(url, options)
            .then(function(res) {
                return res.text();
            })
            .then(function(text) {
                try {
                    callback({success: true, data: JSON.parse(text), raw: text});
                } catch(e) {
                    callback({success: true, data: null, raw: text});
                }
            })
            .catch(function(err) {
                callback({success: false, error: err.toString()});
            });
        """
        try:
            res = driver.execute_async_script(js_code, url, method, body)
            if res and res.get("success"):
                return res.get("data") if res.get("data") is not None else res.get("raw")
            else:
                logger.error("Browser fetch failed: %s", res)
                return None
        except Exception as e:
            logger.error("Exception during browser fetch to %s: %s", url, e)
            return None

    @classmethod
    def get_courses(cls, driver) -> List[WeLearnCourse]:
        """Fetch student course list (/ajax/authCourse.aspx?action=gmc)."""
        url = f"{AJAX_BASE}/ajax/authCourse.aspx?action=gmc"
        res = cls.execute_browser_fetch(driver, url, method="GET")
        courses: List[WeLearnCourse] = []
        if isinstance(res, dict):
            clist = res.get("clist", [])
            for item in clist:
                cid = str(item.get("cid", "") or item.get("id", ""))
                name = str(item.get("name", "") or "未命名课程")
                per = str(item.get("per", "") or item.get("progress", ""))
                courses.append(WeLearnCourse(cid=cid, name=name, progress=per, raw_data=item))
        return courses

    @classmethod
    def get_course_ids(cls, driver, cid: str) -> Tuple[str, str]:
        """Extract (uid, classid) from course_info.aspx or page variables."""
        # Check current page DOM first
        try:
            curr_url = driver.current_url or ""
            if f"cid={cid}" in curr_url:
                page_source = driver.page_source
                uid_match = re.search(r'"uid":\s*"?(\d+)"?', page_source)
                classid_match = re.search(r'"classid":\s*"([^"]+)"', page_source)
                if uid_match and classid_match:
                    return uid_match.group(1), classid_match.group(1)
        except Exception:
            pass

        # Fetch course info page text
        url = f"{AJAX_BASE}/student/course_info.aspx?cid={cid}"
        html = cls.execute_browser_fetch(driver, url, method="GET")
        if isinstance(html, str):
            uid_match = re.search(r'"uid":\s*"?(\d+)"?', html)
            classid_match = re.search(r'"classid":\s*"([^"]+)"', html)
            if uid_match and classid_match:
                return uid_match.group(1), classid_match.group(1)
        return "", ""

    @classmethod
    def get_units(cls, driver, cid: str, uid: str) -> List[WeLearnUnit]:
        """Fetch unit list for given course and student."""
        url = f"{AJAX_BASE}/ajax/StudyStat.aspx?action=courseunits&cid={cid}&uid={uid}"
        res = cls.execute_browser_fetch(driver, url, method="GET")
        units: List[WeLearnUnit] = []
        if isinstance(res, dict):
            info = res.get("info", [])
            for idx, item in enumerate(info):
                name = str(item.get("unitname", "") or item.get("name", "") or f"Unit {idx+1}")
                visible = str(item.get("visible", "true")).lower() != "false"
                units.append(WeLearnUnit(unit_idx=idx, name=name, visible=visible, raw_data=item))
        return units

    @classmethod
    def get_sections(
        cls, driver, cid: str, uid: str, unit_idx: int, classid: str, unit_name: str = ""
    ) -> List[WeLearnSCO]:
        """Fetch sections/SCOs under a specific unit."""
        url = (
            f"{AJAX_BASE}/ajax/StudyStat.aspx?action=scoLeaves"
            f"&cid={cid}&uid={uid}&unitidx={unit_idx}&classid={classid}"
        )
        res = cls.execute_browser_fetch(driver, url, method="GET")
        scos: List[WeLearnSCO] = []
        if isinstance(res, dict):
            info = res.get("info", [])
            for item in info:
                scoid = str(item.get("id", "") or "")
                location = str(item.get("location", "") or scoid)
                is_complete = "已" in str(item.get("iscomplete", "")) or str(item.get("iscomplete", "")).lower() == "completed"
                is_visible = str(item.get("isvisible", "true")).lower() != "false"
                learntime = str(item.get("learntime", "") or "00:00:00")
                scos.append(
                    WeLearnSCO(
                        scoid=scoid,
                        location=location,
                        unit_idx=unit_idx,
                        unit_name=unit_name,
                        iscomplete=is_complete,
                        isvisible=is_visible,
                        learntime=learntime,
                        raw_data=item,
                    )
                )
        return scos
