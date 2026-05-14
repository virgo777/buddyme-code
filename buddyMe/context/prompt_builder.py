"""
prompt_builder.py — System Prompt 构建器

从 initspace/contextbuild.py 重构，封装为 PromptBuilder 类。
按固定层次组装：SOUL → Memory → Skills → Tools → Platform Hints。
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from buddyMe.context.brain_loader import BrainLoader

logger = logging.getLogger(__name__)


class PromptBuilder:
    """动态构建完整的 system prompt。

    组装顺序（参考 paper.md 5 节）：
      1. 环境信息（平台）
      2. Brain 文件（SOUL.md → IDENTITY.md → AGENT.md）
      3. 记忆（MemoryStore.to_prompt()）
      4. Skill 元数据
      5. 工具能力指南
    """

    def __init__(self, brain_dir: str, platform: Optional[str] = None):
        self.brain_loader = BrainLoader(brain_dir)
        self.platform = platform

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def build(
        self,
        tool_schemas: List[Dict],
        skill_metadata: str = "",
        memory_prompt: str = "",
    ) -> str:
        """构建完整的 system prompt。"""
        sections: List[str] = []

        # 1. 环境信息
        if self.platform:
            sections.append(f"【环境信息】\n系统平台: {self.platform}")

        # 2. Brain 文件（SOUL → IDENTITY → AGENT）
        brain_contents = self.brain_loader.load()
        sections.extend(brain_contents)

        # 3. 记忆（在 Skill 之前注入）
        if memory_prompt:
            sections.append(memory_prompt)

        # 4. Skill 元数据（在工具之前注入，优先引导 LLM 使用技能）
        if skill_metadata:
            sections.append(skill_metadata)

        # 5. 工具能力与调用指南
        tool_section = self._build_tool_section(tool_schemas)
        if tool_section:
            sections.append(tool_section)

        return "\n\n".join(sections)

    def load_sub_agent_prompt(self, max_steps: int = 11, max_output: int = 8192) -> str:
        """加载子代理提示，支持格式化变量替换。"""
        content = self.brain_loader.load_sub_agent_prompt()
        if not content:
            return ""
        return content.format(max_steps=max_steps, max_output=max_output)

    # ------------------------------------------------------------------
    # 工具段落生成
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tool_section(tool_schemas: List[Dict]) -> str:
        if not tool_schemas:
            return ""

        lines = [
            "【工具能力与调用指南】",
            "以下是你可以使用的工具。根据用户需求选择合适的工具，先获取数据再回答，禁止凭空编造。",
            "",
        ]

        for schema in tool_schemas:
            func = schema.get("function", schema)
            name = func.get("name", "unknown")
            description = func.get("description", "")
            parameters = func.get("parameters", {})
            properties = parameters.get("properties", {})
            required = parameters.get("required", [])

            desc_sections = PromptBuilder._parse_tool_description(description)
            summary = description.strip().split("\n")[0].strip()
            lines.append(f"▶ {name} — {summary}")

            scenarios = desc_sections.get("适用场景", "")
            if scenarios:
                lines.append("  适用场景：")
                for s in scenarios.split("\n"):
                    s = s.strip()
                    if s:
                        lines.append(f"    {s}")

            if properties:
                lines.append("  调用参数：")
                lines.append(PromptBuilder._format_params(properties, required))

            output = desc_sections.get("输出", "")
            if output:
                lines.append(f"  输出：{output}")

            for extra_key in ("安全限制", "注意", "限制"):
                extra = desc_sections.get(extra_key, "")
                if extra:
                    lines.append(f"  {extra_key}：{extra}")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _parse_tool_description(description: str) -> Dict[str, str]:
        sections: Dict[str, str] = {}
        current_key = ""
        current_lines: List[str] = []

        for line in description.split("\n"):
            match = re.match(r"^【(.+?)】", line.strip())
            if match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = match.group(1)
                current_lines = []
            elif current_key:
                current_lines.append(line)

        if current_key:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections

    @staticmethod
    def _format_params(properties: Dict, required: List[str]) -> str:
        parts = []
        for pname, pinfo in properties.items():
            ptype = pinfo.get("type", "any")
            pdesc = pinfo.get("description", "")
            req = "必需" if pname in required else "可选"
            default = pinfo.get("default")
            suffix = f"，默认{default}" if default is not None else ""
            parts.append(f"  - {pname} ({ptype}, {req}): {pdesc}{suffix}")
        return "\n".join(parts)
