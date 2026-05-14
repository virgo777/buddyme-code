"""context — 上下文构建与压缩模块

参考 Hermes paper.md 的分层设计：
  BrainLoader       — 加载 SOUL.md / IDENTITY.md / AGENT.md
  PromptBuilder     — 按固定层次组装 system prompt
  ContextCompressor — 长对话中段压缩（保留首尾，LLM 生成结构化摘要）
"""

from buddyMe.context.brain_loader import BrainLoader
from buddyMe.context.prompt_builder import PromptBuilder
from buddyMe.context.compressor import ContextCompressor

__all__ = [
    "BrainLoader",
    "PromptBuilder",
    "ContextCompressor",
]
