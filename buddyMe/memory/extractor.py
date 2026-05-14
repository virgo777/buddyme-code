"""
extractor.py — 记忆提取器

根据 MD 文件标题结构，从 conversation_log.json 当日对话中批量提取信息的子 Agent。
从 initspace/memory_extractor.py 迁移。
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from buddyMe.initspace.utils import _PROJECT_ROOT, _extract_json, _load_md

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """记忆提取器 — 根据 MD 文件标题结构，从 conversation_log.json 当日对话中批量提取信息。"""

    _SKIP_SECTIONS = frozenset({"说明"})

    def __init__(self, model_name: str = "glm", md_path: str = "",
                 conversation_log_path: str = "",
                 client: Optional[Any] = None):
        self.model_name: str = model_name
        self.md_path: str = md_path
        self.sections: List[str] = self._parse_sections(md_path)
        self.conversation_log_path: str = conversation_log_path

        if client is not None:
            self.client = client
        else:
            from buddyMe.llm_moudle import basic_llm
            self.client = basic_llm.create_client(model_name)

    def _parse_sections(self, md_path: str) -> List[str]:
        raw = _load_md(md_path)
        if not raw:
            return []
        return [
            s for s in re.findall(r"^#{2,3}\s+(.+)$", raw, re.MULTILINE)
            if s.strip() not in self._SKIP_SECTIONS
        ]

    def _get_recent_conversations(self, days: int = 5) -> str:
        if not self.conversation_log_path:
            return ""

        abs_path = Path(self.conversation_log_path).resolve()
        if not abs_path.exists():
            abs_path = Path(_PROJECT_ROOT) / self.conversation_log_path
        if not abs_path.exists():
            return ""

        data = json.loads(abs_path.read_text(encoding="utf-8"))

        today = datetime.now()
        date_keys = [
            (today - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(days)
        ]

        parts = []
        for date_key in date_keys:
            conversations = data.get(date_key, [])
            if not conversations:
                continue
            for conv in conversations:
                query = conv.get("query", "")
                response = conv.get("response", "")
                parts.append(
                    "[" + date_key + "] 用户: " + query + "\n助手: " + response
                )

        return "\n\n".join(parts)

    async def extract(self, days: int = 5) -> Dict[str, Any]:
        text = self._get_recent_conversations(days)
        if not text.strip() or not self.sections:
            return {}
        sections_str = ", ".join(self.sections)
        prompt = (
            "从以下近" + str(days) + "日对话记录中提取信息。只提取这些字段：" + sections_str + "\n"
            "规则：只提取明确提到的，不推测。没有新发现就输出空 JSON: {}\n"
            "输出纯 JSON：{\"字段名\": \"值或列表\", ...}"
        )
        try:
            response = await self.client.chat(messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ])
            raw = "".join(
                b.get("text", "") for b in response.get("content", [])
                if b.get("type") == "text"
            )
            return _extract_json(raw)
        except Exception as e:
            logger.warning(f"[MemoryExtractor] 提取失败: {e}")
            return {}
