"""
state.py — 会话共享状态

可变 dataclass，在 AgentMain / TaskRunner / TaskPipeline 间共享，
消除 self._a 反向通道耦合。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SessionState:
    """每轮任务的共享可变状态。

    AgentMain 持有并传递给 TaskRunner / TaskPipeline，
    二者直接修改字段而无须反向引用 AgentMain。
    """
    written_files: List[str] = field(default_factory=list)
    used_tools: List[Dict] = field(default_factory=list)
    used_skills: List[str] = field(default_factory=list)
    token_in: int = 0
    token_out: int = 0
    last_episode: List[Dict] = field(default_factory=list)

    def reset_episode(self) -> None:
        """新任务开始时重置。"""
        self.written_files = []
        self.used_tools = []
        self.used_skills = []
        self.token_in = 0
        self.token_out = 0
        self.last_episode = []
