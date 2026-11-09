# -*- coding: utf-8 -*-
"""
Local Whisper Audio Transcription Helper.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
import os
import tempfile
import urllib.error
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger("WeLearnBot")


class AudioTranscriber:
    """Audio transcription helper using local OpenAI Whisper."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.local_model = None
        self._transcript_cache: Dict[str, str] = {}
        self._initialized = False

    def _ensure_model(self) -> bool:
        if self._initialized:
            return self.local_model is not None
        self._initialized = True
        try:
            import whisper
            logger.info("Loading Whisper local model (%s)...", self.model_size)
            self.local_model = whisper.load_model(self.model_size)
            logger.info("Whisper model loaded successfully.")
            return True
        except ImportError:
            logger.warning("openai-whisper is not installed. Audio recognition will be unavailable.")
            return False
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e)
            return False

    def transcribe(self, audio_url: str, language: str = "en") -> str:
        """Download audio and transcribe it to text."""
        if audio_url in self._transcript_cache:
            return self._transcript_cache[audio_url]

        if not self._ensure_model():
            return ""

        audio_path = None
        try:
            logger.info("Downloading audio from: %s", audio_url)
            with urllib.request.urlopen(audio_url, timeout=30) as response, \
                    tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(response.read())
                audio_path = f.name

            result = self.local_model.transcribe(
                audio_path,
                language=language,
                fp16=False,
            )
            text = (result.get("text") or "").strip()
            if text:
                self._transcript_cache[audio_url] = text
                logger.info("Transcription succeeded (%d chars)", len(text))
            return text
        except Exception as e:
            logger.error("Audio transcription failed: %s", e)
            return ""
        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass
