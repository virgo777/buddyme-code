"""DEPRECATED: 已迁移至 buddyMe.context.prompt_builder。保留此文件用于向后兼容。"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from buddyMe.initspace.utils import _load_md

logger = logging.getLogger(__name__)


def _load_brain_files(brain_dir: str) -> List[str]:
    """向后兼容：加载 brain 文件。"""
    filenames = ["SOUL.md", "IDENTITY.md", "AGENT.md"]
    loaded: List[str] = []
    for name in filenames:
        path = str(Path(brain_dir) / name)
        content = _load_md(path)
        if content:
            loaded.append(content)
    return loaded


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


def _build_tool_section(tool_schemas: List[Dict]) -> str:
    from buddyMe.context.prompt_builder import PromptBuilder
    return PromptBuilder._build_tool_section(tool_schemas)


def build_system_prompt(
    tool_schemas: List[Dict],
    brain_dir: Optional[str] = None,
    soul_path: Optional[str] = None,
    platform: Optional[str] = None,
    skill_metadata: Optional[str] = None,
) -> str:
    """向后兼容：委托给 PromptBuilder。"""
    from buddyMe.context.prompt_builder import PromptBuilder
    builder = PromptBuilder(brain_dir=brain_dir or "", platform=platform)
    return builder.build(
        tool_schemas=tool_schemas,
        skill_metadata=skill_metadata or "",
    )
