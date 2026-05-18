"""
todo_manager.py — 任务计划生成与内部 Todo 跟踪

plan_task()   — 调用 LLM 将用户需求拆解为执行步骤（供 TaskRunner 使用）
TodoManager   — 内存中的任务清单，不持久化，每轮重建
"""

import re
from typing import Dict, List, Optional


async def plan_task(user_input: str, client, skill_metadata: str = "") -> tuple:
    """
    调用 LLM 生成任务计划并标记检查点。
    返回 (steps, checkpoints) — steps 是纯步骤文本列表（已去除 [CP] 标签），
    checkpoints 是需要重新评估后续计划的步骤索引列表。
    """
    skill_section = ""
    if skill_metadata:
        skill_section = f"""
可用技能参考（分解任务时优先对齐已有技能，能匹配到技能的步骤用 [SKILL:技能名] 标注）：
{skill_metadata}
"""

    plan_prompt = f"""分析以下用户需求，按文件操作粒度分解为执行步骤。
{skill_section}
规则：
- 每个步骤必须用标签标注操作类型：
  [SEARCH] 搜索/查找外部信息
  [CREATE] 创建新文件（骨架/初始版本）
  [EDIT] 编辑已有文件（填充内容、添加样式、添加交互）
  [VERIFY] 读取文件并验证完整性、修复问题
  [SKILL:技能名] 该步骤可由指定技能完成
- 最多 7 个步骤，按"骨架→填充→验证"顺序
- 【必须】所有涉及文件创建/编辑的任务，最后一步必须是 [VERIFY] 验证步骤
- 步骤之间不要有内容重叠

【检查点标记】
- 在步骤末尾用 [CP] 标记那些"完成后可能需要调整后续计划"的步骤
- [CP] 标记规则：
  * 搜索步骤：如果搜索结果可能大幅改变方案 → 标记 [CP]
  * 创建步骤：如果骨架结构确定后可能需要调整后续步骤 → 标记 [CP]
  * 编辑步骤：如果填充过程中可能发现需要拆分/合并 → 标记 [CP]
  * 验证步骤：永远不标记 [CP]；最后一步：永远不标记 [CP]
  * 最多标记 3 个 [CP]，均匀分布在前中后阶段
  * 在最终输出前还要特别关注有没有重复子任务或者相似子任务的存在，如果有的话就在后一个子任务加上标记 [CP]
- [CP] 放在步骤末尾，与其他标签用空格分隔

示例：
用户需求：设计一个响应式着陆页
输出：
[SEARCH] 搜索行业着陆页设计趋势和参考案例
[SEARCH] 搜索目标用户偏好和竞品着陆页特点
[CREATE][SKILL:frontend-design] 创建响应式着陆页 HTML 骨架和视觉样式 [CP]
[EDIT][SKILL:frontend-design] 添加英雄区、特性展示、CTA按钮等核心板块
[EDIT] 添加交互动效、滚动动画和响应式适配 [CP]
[VERIFY] 读取最终文件，检查完整性和跨端兼容性

用户需求：帮我写一个 Python 脚本计算斐波那契数列
输出：
[CREATE] 创建斐波那契计算脚本文件，包含函数定义和基本结构
[EDIT] 向脚本中补充用户输入和输出逻辑
[VERIFY] 读取脚本文件，检查语法和逻辑正确性

现在请分解以下用户需求：
{user_input}
"""
    try:
        messages = [
            {"role": "system", "content": "你是一个务实的任务分解助手，擅长识别任务中的关键决策点。"},
            {"role": "user", "content": plan_prompt},
        ]

        response = await client.chat(messages=messages)
        texts = [b["text"] for b in response["content"] if b["type"] == "text"]
        plan_text = "".join(texts).strip()
    except Exception:
        return [user_input], []

    raw_steps = []
    for line in plan_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line[0].isdigit() and len(line) > 2 and line[1] in ".、) ":
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                line = parts[1]
        elif line[0] in "-*•▪▫":
            line = line[1:].strip()
        raw_steps.append(line)

    if not raw_steps:
        return [user_input], []

    # 提取 [CP] 标记，返回纯净步骤文本 + 检查点索引
    steps = []
    checkpoints = []
    last_idx = len(raw_steps) - 1
    for i, step in enumerate(raw_steps):
        has_cp = "[CP]" in step
        clean = step.replace(" [CP]", "").replace("[CP] ", "").replace("[CP]", "").strip()
        steps.append(clean)
        # 程序兜底：即使LLM标记了，前2步和最后1步强制移除检查点
        if has_cp and i > 1 and i < last_idx:
            checkpoints.append(i)

    # 兜底：多步骤计划必须有验证步骤收尾
    if len(steps) >= 2 and "[VERIFY]" not in steps[-1]:
        steps.append("[VERIFY] 读取已生成的文件，检查完整性和正确性，有问题则修复")
    return steps, checkpoints


def identify_checkpoints(plan: list) -> list:
    """识别计划中的非关键检查点（最多3个，均匀分布）。

    跳过前2步（信息收集阶段数据不完整），跳过最后一步和 [VERIFY] 步骤。
    从剩余候选中均匀选取最多3个，确保覆盖执行前中后期。
    """
    # 收集候选步骤索引
    candidates = []
    for i, step in enumerate(plan):
        if i < 2:                 # 跳过前2步
            continue
        if i == len(plan) - 1:    # 跳过最后一步
            continue
        if "[VERIFY]" in step:    # 验证步骤不做检查点
            continue
        candidates.append(i)

    # 均匀选取最多3个（中点采样，覆盖前中后）
    max_cp = 3
    n = len(candidates)
    if n <= max_cp:
        return candidates

    checkpoints = []
    for j in range(max_cp):
        idx = candidates[int((j + 0.5) * n / max_cp)]
        checkpoints.append(idx)
    return checkpoints


async def replan_task(
    user_input: str,
    completed_steps: str,
    remaining_plan: list,
    client,
) -> dict:
    """在检查点重新评估后续计划。

    Returns:
        {
            "changed": bool,
            "reason": str,
            "new_plan": list,       # 继续执行的步骤（含可能新增的）
            "cancelled": list,      # [(step_text, del_reason), ...] 被取消的步骤
            "removed": list,        # 被移除的原始步骤
            "added": list,          # 新增的步骤
        }
    """
    remaining_text = "\n".join(f"- {s}" for s in remaining_plan)
    prompt = f"""你是一个务实的任务规划师。当前正在执行一个多步骤任务，已到达检查点。

【原始用户需求】
{user_input}

【已完成的步骤及结果】
{completed_steps}

【当前剩余的步骤计划】
{remaining_text}

请评估：基于已完成步骤的实际结果，剩余步骤是否需要调整？

不需要调整：回复 NO_CHANGE

需要调整（常见场景）：
- 已完成结果覆盖了后续步骤的目标，后续步骤可以取消
- 搜索结果包含了某步骤所需的全部信息，该步骤不再需要
- 需要增加新步骤或调整步骤顺序
- 某步骤结果需要拆分

如需调整，请按以下格式输出：
[REASON] 简要说明变更原因（一行）
[PLAN]
调整后的步骤列表。需要保留的步骤原样列出。需要取消的步骤用 DEL[原因] 前缀标记。
示例：
[REASON] 天气数据已包含穿衣建议，取消独立的穿衣建议板块
[PLAN]
[CREATE] 创建HTML骨架 [CP]
[EDIT] 填充博物馆信息
DEL[天气数据已包含穿衣建议，无需重复] [EDIT] 添加出行穿衣建议板块
[VERIFY] 最终验证

规则：
- 有 DEL[原因] 前缀的步骤会被跳过，不执行，但留在记录中供追溯
- 只输出剩余步骤，不要包含已完成的
- 总步骤数不超过8个（含已完成的）
- 保持"骨架→填充→验证"顺序
- 最后一步必须是 [VERIFY]"""
    try:
        messages = [
            {"role": "system", "content": "你是一个务实的任务规划师，擅长基于实际情况调整计划。"},
            {"role": "user", "content": prompt},
        ]
        response = await client.chat(messages=messages)
        texts = [b["text"] for b in response["content"] if b["type"] == "text"]
        reply = "".join(texts).strip()
    except Exception:
        return {"changed": False, "reason": "", "new_plan": remaining_plan, "cancelled": [], "removed": [], "added": []}

    if "NO_CHANGE" in reply:
        return {"changed": False, "reason": "", "new_plan": remaining_plan, "cancelled": [], "removed": [], "added": []}

    # 解析变更原因
    reason_match = reply.find("[REASON]")
    plan_match = reply.find("[PLAN]")
    reason = ""
    if reason_match != -1:
        reason_end = plan_match if plan_match != -1 else len(reply)
        reason = reply[reason_match + 8:reason_end].strip()

    # 解析新计划，分离 DEL 步骤
    new_plan = []
    cancelled = []
    if plan_match != -1:
        plan_text = reply[plan_match + 6:].strip()
        for line in plan_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit() and len(line) > 2 and line[1] in ".、) ":
                parts = line.split(maxsplit=1)
                if len(parts) > 1:
                    line = parts[1]
            elif line[0] in "-*•▪▫":
                line = line[1:].strip()
            if not line or line.startswith("[REASON]") or line.startswith("[PLAN]"):
                continue

            # 检测 DEL[原因] 前缀
            del_match = re.match(r"^DEL\[(.+?)\]\s+(.*)", line)
            if del_match:
                del_reason = del_match.group(1)
                step_text = del_match.group(2).strip()
                cancelled.append((step_text, del_reason))
            else:
                new_plan.append(line)

    if not new_plan:
        return {"changed": False, "reason": "", "new_plan": remaining_plan, "cancelled": [], "removed": [], "added": []}

    # 计算变更
    old_set = set(remaining_plan)
    new_set = set(new_plan) | {c[0] for c in cancelled}
    removed = list(old_set - new_set)
    added = list(new_set - old_set)

    return {
        "changed": True,
        "reason": reason,
        "new_plan": new_plan,
        "cancelled": cancelled,
        "removed": removed,
        "added": added,
    }


class TodoManager:
    """智能体内部任务管理器 —— 对大语言模型不可见，不对外暴露为工具"""

    def __init__(self):
        self.items: List[Dict] = []
        self._rounds_since_update: int = 0

    def create_from_plan(self, plan: List[str]) -> str:
        self.items = [
            {"id": i + 1, "text": text, "status": "pending"}
            for i, text in enumerate(plan)
        ]
        if self.items:
            self.items[0]["status"] = "in_progress"
        self._rounds_since_update = 0
        return self.render()

    def mark_current_done(self) -> Optional[Dict]:
        current = self._get_in_progress()
        if current:
            current["status"] = "completed"
        for item in self.items:
            if item["status"] == "pending":
                item["status"] = "in_progress"
                self._rounds_since_update = 0
                return item
        self._rounds_since_update = 0
        return None

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def render(self) -> str:
        if not self.items:
            return ""
        status_map = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}
        lines = ["\n## 当前任务计划"]
        for item in self.items:
            icon = status_map.get(item["status"], "⬜")
            lines.append(f"  {icon} [{item['id']}] {item['text']} ({item['status']})")
        completed = sum(1 for i in self.items if i["status"] == "completed")
        lines.append(f"  进度: {completed}/{len(self.items)}")
        return "\n".join(lines)

    def _get_in_progress(self) -> Optional[Dict]:
        for item in self.items:
            if item["status"] == "in_progress":
                return item
        return None
