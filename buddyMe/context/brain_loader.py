"""
brain_loader.py — Brain 文件加载器

按层级顺序加载 SOUL.md → IDENTITY.md → AGENT.md，
从 initspace/contextbuild.py 的 _load_brain_files() 抽离。
"""

import logging
from pathlib import Path
from typing import List

from buddyMe.initspace.utils import _load_md

logger = logging.getLogger(__name__)


class BrainLoader:
    """按固定层级加载 brain 目录下的 Agent 人格文件。

    加载顺序决定 system prompt 中的层级排列：
      1. SOUL.md     — 人格内核（L0，最稳定）
      2. IDENTITY.md — 角色身份（L1，切换角色时替换）
      3. AGENT.md    — 执行规范（能力边界）
    """

    def __init__(self, brain_dir: str):
        self.brain_dir = brain_dir
        self._filenames = ["SOUL.md", "IDENTITY.md", "AGENT.md"]

    def load(self) -> List[str]:
        """加载所有非空的 brain 文件，按层级顺序返回。"""
        loaded: List[str] = []
        for name in self._filenames:
            path = str(Path(self.brain_dir) / name)
            content = _load_md(path)
            if content:
                loaded.append(content)
        return loaded

    def load_sub_agent_prompt(self) -> str:
        """加载 SUB_AGENT.md（子代理执行规范）。"""
        path = str(Path(self.brain_dir) / "SUB_AGENT.md")
        return _load_md(path)
