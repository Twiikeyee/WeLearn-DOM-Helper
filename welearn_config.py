# -*- coding: utf-8 -*-
"""
Configuration management for WeLearn-DOM-Helper.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_WELEARN_URL = "https://welearn.sflep.com/2019/student/index.aspx"
DEFAULT_SUBJECTIVE_TEXT = (
    "From my perspective, this viewpoint is quite reasonable and closely "
    "related to our daily study, communication, and practical experiences."
)


@dataclass
class Config:
    """WeLearn-DOM-Helper runtime configuration."""
    username: str = ""
    password: str = ""
    url: str = DEFAULT_WELEARN_URL
    
    # Typing & Speed
    typing_mode: str = "fast"  # "fast" (instant JS injection) or "simulate" (human keystrokes)
    min_dwell_seconds: int = 0  # 0 for max speed, or set > 0 if teacher requires minimum study time
    
    # LLM Settings
    enable_llm_subjective: bool = False  # False for 0-token free mode with default template
    subjective_default_text: str = DEFAULT_SUBJECTIVE_TEXT
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 4096
    
    # Browser & Runtime
    browser: str = "edge"
    headless: bool = False
    debug_mode: bool = False
    
    # TTS
    tts_engine: str = "auto"
    tts_voice: str = ""
    tts_proxy: str = ""

    @classmethod
    def from_json(cls, path: str = "config.json") -> "Config":
        if not os.path.exists(path):
            example_path = "config.example.json"
            if os.path.exists(example_path):
                try:
                    with open(example_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
                except Exception:
                    pass
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            username=str(data.get("username", "") or "").strip(),
            password=str(data.get("password", "") or "").strip(),
            url=str(data.get("url", "") or DEFAULT_WELEARN_URL).strip(),
            typing_mode=str(data.get("typing_mode", "fast") or "fast").strip().lower(),
            min_dwell_seconds=int(data.get("min_dwell_seconds", 0)),
            enable_llm_subjective=bool(data.get("enable_llm_subjective", False)),
            subjective_default_text=str(
                data.get("subjective_default_text", DEFAULT_SUBJECTIVE_TEXT) or DEFAULT_SUBJECTIVE_TEXT
            ).strip(),
            api_key=str(data.get("api_key", "") or "").strip(),
            base_url=str(data.get("base_url", "https://api.openai.com/v1") or "").strip(),
            model=str(data.get("model", "gpt-4o-mini") or "").strip(),
            temperature=float(data.get("temperature", 0.3)),
            max_tokens=int(data.get("max_tokens", 4096)),
            browser=str(data.get("browser", "edge") or "edge").strip().lower(),
            headless=bool(data.get("headless", False)),
            debug_mode=bool(data.get("debug_mode", False)),
            tts_engine=str(data.get("tts_engine", "auto") or "auto").strip().lower(),
            tts_voice=str(data.get("tts_voice", "") or "").strip(),
            tts_proxy=str(data.get("tts_proxy", "") or "").strip(),
        )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "typing_mode": self.typing_mode,
            "min_dwell_seconds": self.min_dwell_seconds,
            "enable_llm_subjective": self.enable_llm_subjective,
            "subjective_default_text": self.subjective_default_text,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "browser": self.browser,
            "headless": self.headless,
            "debug_mode": self.debug_mode,
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_proxy": self.tts_proxy,
        }

    def save_json(self, path: str = "config.json") -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
