"""
message_history.py — 对话消息历史管理

从 AgentMain 抽离的消息列表管理，支持自动截断和压缩预留。
"""

from typing import Any, Dict, List


class MessageHistory:
    """管理对话消息列表，提供添加、重置、截断能力。"""

    def __init__(self, max_messages_length: int = 20):
        self._messages: List[Dict[str, Any]] = []
        self.max_messages_length = max_messages_length

    def add(self, role: str, content: str) -> None:
        """追加一条消息，超出上限时保留首条 + 截断尾部。"""
        if len(self._messages) >= self.max_messages_length:
            self._messages = [self._messages[0]] + self._messages[-(self.max_messages_length - 1):]
        self._messages.append({"role": role, "content": content})

    def reset(self) -> None:
        """清空所有消息。"""
        self._messages = []

    def get_messages(self) -> List[Dict[str, Any]]:
        """返回消息列表引用（可变，供外部直接修改）。"""
        return self._messages

    def replace_all(self, messages: List[Dict[str, Any]]) -> None:
        """整体替换消息列表（供 ContextCompressor 使用）。"""
        self._messages = list(messages)

    def trim(self, keep_first: int, keep_last: int) -> List[Dict[str, Any]]:
        """截取消息列表的首尾部分，返回被裁掉的中间消息。"""
        n = len(self._messages)
        if n <= keep_first + keep_last:
            return []
        middle = self._messages[keep_first:-keep_last]
        return list(middle)

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return f"<MessageHistory count={len(self._messages)} max={self.max_messages_length}>"
