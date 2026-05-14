"""memory — 记忆管理模块

Hermes 风格的三层记忆系统：
  MemoryProvider Protocol  — 定义生命周期钩子（prefetch / sync_turn / on_session_end）
  MemoryStore               — 文件系统实现（评分、衰减、整合）
  MemoryManager             — 统一调度外观
"""

from buddyMe.memory.provider import MemoryProvider
from buddyMe.memory.store import MemoryStore
from buddyMe.memory.extractor import MemoryExtractor
from buddyMe.memory.manager import MemoryManager

__all__ = [
    "MemoryProvider",
    "MemoryStore",
    "MemoryExtractor",
    "MemoryManager",
]
