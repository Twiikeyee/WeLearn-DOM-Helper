# -*- coding: utf-8 -*-
"""
Text-to-speech engine for audio/speaking tasks.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("WeLearnBot")


class TTSEngine:
    """TTS engine supporting edge-tts, Windows SAPI, and macOS say."""

    EDGE_VOICE = "en-US-AriaNeural"
    CACHE_LIMIT = 32

    def __init__(
        self,
        engine: str = "auto",
        voice: str = "",
        proxy: str = "",
        rate: str = "+0%",
    ):
        self.engine = (engine or "auto").strip().lower()
        self.voice = (voice or "").strip()
        self.proxy = (proxy or os.environ.get("WELEARN_TTS_PROXY", "") or "").strip()
        self.rate = rate or "+0%"
        self.last_error = ""
        self._cache: Dict[str, Tuple[str, bytes]] = {}

    @property
    def enabled(self) -> bool:
        return self.engine not in ("off", "none", "disable", "disabled")

    def _engine_order(self) -> List[str]:
        if self.engine in ("edge", "edge-tts"):
            return ["edge"]
        if self.engine == "sapi" and sys.platform.startswith("win"):
            return ["sapi"]
        if self.engine in ("say", "macos") and sys.platform == "darwin":
            return ["macos_say"]

        # auto mode
        order = ["edge"]
        if sys.platform == "darwin":
            order.append("macos_say")
        elif sys.platform.startswith("win"):
            order.append("sapi")
        return order

    def synthesize(self, text: str) -> Tuple[str, bytes]:
        """Synthesize text into audio bytes. Returns (format, bytes)."""
        if not self.enabled:
            self.last_error = "TTS is disabled in config"
            return "", b""

        clean_text = text.strip()
        if not clean_text:
            self.last_error = "Text is empty"
            return "", b""

        key = hashlib.md5(f"{clean_text}|{self.voice}|{self.rate}".encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]

        for engine_name in self._engine_order():
            try:
                if engine_name == "edge":
                    fmt, data = self._synthesize_edge(clean_text)
                elif engine_name == "macos_say":
                    fmt, data = self._synthesize_macos(clean_text)
                elif engine_name == "sapi":
                    fmt, data = self._synthesize_sapi(clean_text)
                else:
                    continue

                if data:
                    if len(self._cache) >= self.CACHE_LIMIT:
                        self._cache.clear()
                    self._cache[key] = (fmt, data)
                    return fmt, data
            except Exception as e:
                self.last_error = f"{engine_name}: {e}"
                logger.debug("TTS engine %s error: %s", engine_name, e)

        return "", b""

    def _synthesize_edge(self, text: str) -> Tuple[str, bytes]:
        import edge_tts

        voice = self.voice or self.EDGE_VOICE

        async def _run():
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=self.rate,
                proxy=self.proxy or None,
            )
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(_run())
            loop.close()
            return "mp3", data
        except Exception as e:
            self.last_error = str(e)
            return "", b""

    def _synthesize_macos(self, text: str) -> Tuple[str, bytes]:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
            temp_path = f.name

        try:
            cmd = ["say", "-o", temp_path, text]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with open(temp_path, "rb") as f:
                data = f.read()
            return "aiff", data
        except Exception as e:
            self.last_error = str(e)
            return "", b""
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _synthesize_sapi(self, text: str) -> Tuple[str, bytes]:
        # Windows SAPI fallback placeholder
        self.last_error = "SAPI not available on current platform"
        return "", b""
