"""
compressor.py — 上下文压缩器（全新功能）

参考 Hermes paper.md 第4节 ContextCompressor 设计：
  当对话历史超过 token 阈值时，保留首尾关键消息，
  中段调用 LLM 生成结构化摘要，替代原文以减少上下文占用。

压缩策略：
  - 保留前 keep_first 条消息（system prompt + 初始上下文）
  - 压缩中段 → 生成结构化摘要
  - 保留最近 keep_last 条消息（当前工作上下文）
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_COMPRESSION_PROMPT = """Summarize the following conversation segment into a
structured context summary. Follow these rules:

1. Only include information that is still relevant to the ongoing task
2. Use these sections:
   [Key Decisions Made] — decisions the user or assistant made
   [Files Created/Modified] — file paths and what they contain
   [Important Findings] — key information discovered
   [Pending Items] — things not yet completed
3. Be concise. Omit trivial tool output and conversational filler.
4. Output ONLY the structured summary, no preamble.

Conversation segment to compress:
{conversation_segment}

Structured Summary:"""


class ContextCompressor:
    """压缩中间对话消息为结构化 LLM 摘要。

    用法:
        compressor = ContextCompressor(keep_first=2, keep_last=5)
        if compressor.should_compress(messages, max_len=20):
            ctx = await compressor.compress(messages, client)
            messages = compressor.get_compressed_messages(ctx)
    """

    def __init__(self, keep_first: int = 2, keep_last: int = 5,
                 max_summary_chars: int = 3000):
        self.keep_first = keep_first
        self.keep_last = keep_last
        self.max_summary_chars = max_summary_chars
        self._last_summary: str = ""
        self._compression_count: int = 0

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def should_compress(self, messages: List[Dict], max_len: int) -> bool:
        """检查消息是否超过压缩阈值。"""
        return len(messages) > max_len

    async def compress(self, messages: List[Dict], client: Any) -> "CompressedContext":
        """压缩中段消息，返回 CompressedContext。"""
        n = len(messages)

        if n <= self.keep_first + self.keep_last:
            return CompressedContext(
                summary="",
                retained_first=list(messages),
                retained_last=[],
                original_count=n,
                compressed_count=0,
            )

        retained_first = list(messages[:self.keep_first])
        retained_last = list(messages[-self.keep_last:])
        middle = messages[self.keep_first:-self.keep_last]

        if not middle:
            return CompressedContext(
                summary="",
                retained_first=retained_first,
                retained_last=retained_last,
                original_count=n,
                compressed_count=0,
            )

        segment = self._format_for_compression(middle)
        summary = await self._generate_summary(client, segment)

        self._last_summary = summary
        self._compression_count += 1
        logger.info(
            "[Compressor] 压缩 #%d: %d 条消息 → %d 字摘要",
            self._compression_count, len(middle), len(summary),
        )

        return CompressedContext(
            summary=summary,
            retained_first=retained_first,
            retained_last=retained_last,
            original_count=n,
            compressed_count=len(middle),
        )

    def get_compressed_messages(self, ctx: "CompressedContext") -> List[Dict]:
        """从 CompressedContext 重建消息列表。"""
        if not ctx.summary:
            return ctx.retained_first + ctx.retained_last

        summary_msg = {
            "role": "system",
            "content": (
                f"[Context Summary — {ctx.compressed_count} earlier messages compressed]\n\n"
                f"{ctx.summary}"
            ),
        }
        return ctx.retained_first + [summary_msg] + ctx.retained_last

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    def _format_for_compression(self, messages: List[Dict]) -> str:
        """格式化消息为压缩提示的可读文本。"""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "tool":
                name = msg.get("name", "unknown")
                truncated = content[:500] + "..." if len(content) > 500 else content
                parts.append(f"[tool:{name}] {truncated}")
            elif role == "assistant":
                if content is None:
                    tool_calls = msg.get("tool_calls", [])
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    parts.append(f"[assistant] Called tools: {', '.join(names)}")
                else:
                    parts.append(f"[assistant] {content[:1000]}")
            elif role == "user":
                parts.append(f"[user] {content[:1000]}")
            elif role == "system":
                continue

        return "\n\n".join(parts)

    async def _generate_summary(self, client: Any, segment: str) -> str:
        """调用 LLM 生成结构化摘要。"""
        if not segment.strip():
            return ""

        prompt = _COMPRESSION_PROMPT.format(conversation_segment=segment[:8000])

        try:
            messages = [
                {"role": "system", "content": "You are a precise context summarizer. Output structured summaries only."},
                {"role": "user", "content": prompt},
            ]
            response = await client.chat(messages=messages)
            texts = [
                b.get("text", "")
                for b in response.get("content", [])
                if b.get("type") == "text"
            ]
            summary = "\n".join(texts).strip()

            if len(summary) > self.max_summary_chars:
                summary = summary[:self.max_summary_chars] + "\n...(truncated)"

            return summary
        except Exception as e:
            logger.warning("[Compressor] 摘要生成失败: %s", e)
            return f"[Compression failed: {e}]"


class CompressedContext:
    """压缩结果数据类。"""

    __slots__ = ("summary", "retained_first", "retained_last",
                 "original_count", "compressed_count")

    def __init__(self, summary: str, retained_first: List[Dict],
                 retained_last: List[Dict], original_count: int,
                 compressed_count: int):
        self.summary = summary
        self.retained_first = retained_first
        self.retained_last = retained_last
        self.original_count = original_count
        self.compressed_count = compressed_count
