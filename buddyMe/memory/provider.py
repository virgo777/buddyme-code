"""
provider.py — MemoryProvider Protocol

参考 Hermes paper.md 第6节 MemoryProvider 设计。
定义记忆提供者的生命周期钩子，支持未来扩展外部记忆后端。
"""

from typing import Any, Dict, Protocol


class MemoryProvider(Protocol):
    """记忆提供者接口。

    生命周期：
      prefetch() → 每轮 LLM 调用前，预取相关记忆注入 system prompt
      sync_turn() → 每轮对话后，更新活跃度分数
      on_session_end() → 会话结束时，执行衰减/整合/持久化
    """

    @property
    def data(self) -> Dict[str, Any]:
        """当前所有记忆数据（不可变视图）。"""
        ...

    def prefetch(self, query: str) -> str:
        """每轮 LLM 调用前触发。返回注入 system prompt 的记忆文本。"""
        ...

    def sync_turn(self, query: str, response_summary: str) -> None:
        """每轮对话后触发。更新相关记忆的新鲜度时间戳。"""
        ...

    def on_session_end(self) -> None:
        """会话结束时触发。执行衰减、整合、持久化等清理操作。"""
        ...

    def to_prompt(self, max_sections: int = 5, max_chars: int = 800) -> str:
        """将当前记忆格式化为 system prompt 注入文本。"""
        ...

    async def update(self, days: int = 5) -> Dict[str, Any]:
        """手动触发记忆提取更新。"""
        ...

    def load(self) -> None:
        """从磁盘重新加载记忆。"""
        ...

    def save(self) -> None:
        """将记忆持久化到磁盘。"""
        ...
