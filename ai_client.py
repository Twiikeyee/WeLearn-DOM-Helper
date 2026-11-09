# -*- coding: utf-8 -*-
"""
OpenAI-compatible client for subjective question solving.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
from typing import Dict, List, Optional

from openai import OpenAI
from welearn_config import Config

logger = logging.getLogger("WeLearnBot")


class OpenAICompatibleClient:
    """OpenAI-compatible LLM client for English exercise solving."""

    SYSTEM_PROMPT = """你是一个专业的大学英语学习教学助手，擅长分析并解答中国高校英语教材（特别是外教社 WeLearn 平台）的课后习题。
请根据题目要求（Direction/Stem）和课文/材料背景，给出精准、地道的回答：
- 对于开放简答题或长填空（fillinglong）：直接输出最切合题意的高质量答案，保持语言自然流畅、语法正确。
- 除非题目特别要求解释，否则直接输出答案本身，不要添加多余的礼貌用语或多余标签。
- 答案语言默认使用英文（除非题目明确要求用中文作答）。"""

    def __init__(self, config: Config):
        self.config = config
        self.client: Optional[OpenAI] = None
        if config.api_key:
            try:
                self.client = OpenAI(
                    api_key=config.api_key,
                    base_url=config.base_url or "https://api.openai.com/v1",
                )
            except Exception as e:
                logger.error("Failed to initialize OpenAI client: %s", e)
                self.client = None

        self.current_chapter: str = ""
        self.conversation_history: List[Dict[str, str]] = []

    def start_new_chapter(self, chapter_id: str) -> None:
        """Start a new chapter scope."""
        self.current_chapter = chapter_id
        self.conversation_history.clear()
        logger.info("New chapter started: %s", chapter_id)

    def is_available(self) -> bool:
        """Check if LLM client is configured."""
        return self.client is not None and bool(self.config.api_key)

    def solve_subjective_question(
        self, stem: str, direction: str = "", context: str = ""
    ) -> str:
        """Generate answer for subjective long filling or open questions."""
        if not self.is_available():
            logger.warning("LLM API key is not configured; using placeholder answer.")
            return "Answer is required based on the text."

        prompt_parts = []
        if direction:
            prompt_parts.append(f"【题目要求 / Direction】:\n{direction}")
        if context:
            prompt_parts.append(f"【课文/对话背景 / Context】:\n{context}")
        prompt_parts.append(f"【题目 / Question】:\n{stem}")
        prompt_parts.append(
            "请直接给出最符合要求的作答内容（简明、规范、符合英语习惯）："
        )

        user_content = "\n\n".join(prompt_parts)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            answer = response.choices[0].message.content or ""
            answer = answer.strip()
            # Clean up optional markdown wrapper quotes
            if answer.startswith('"') and answer.endswith('"') and len(answer) > 2:
                answer = answer[1:-1].strip()
            return answer
        except Exception as e:
            logger.error("LLM request failed: %s", e)
            return "According to the reading passage, this is a standard response."
