"""
task_runner.py — 任务执行管线编排

三阶段管线：上下文 → 规划 → 分步执行 → 合并
支持动态任务规划：在非关键检查点重新评估后续计划。

依赖通过构造函数注入：
  - pipeline: TaskPipeline（已注入所有子依赖）
  - subtask_mgr: SubtasksManager
  - state: SessionState
  - conv_logger: ConversationLogger
"""

import logging
import os
import re
from datetime import datetime

from buddyMe.agent_moudle import todo_manager

logger = logging.getLogger(__name__)


class TaskRunner:
    """任务执行管线编排。

    依赖通过构造函数注入，不再通过 self._a 反向通道访问 AgentMain。
    """

    def __init__(
        self,
        pipeline,
        subtask_mgr,
        state,
        conv_logger,
        skill_loader,
        client,
        project_root: str = "",
        context_summary_max_chars: int = 6000,
        agent_max_token: int = 131072,
    ):
        self._pipeline = pipeline
        self._subtask_mgr = subtask_mgr
        self._state = state
        self._conv_logger = conv_logger
        self._skill_loader = skill_loader
        self._client = client
        self._project_root = project_root
        self._context_summary_max_chars = context_summary_max_chars
        self._agent_max_token = agent_max_token

    # ==================================================================
    # 三阶段执行管线
    # ==================================================================

    async def run(self, user_input: str) -> str:
        p = self._pipeline

        conversation_context = self._build_conversation_context()

        if p.is_simple_task(user_input):
            print(f"\n📌 简单任务，直接执行")
            return await p.run_simple(user_input, conversation_context)

        enriched = user_input
        if conversation_context:
            enriched = (
                f"{conversation_context}\n\n{'=' * 40}\n\n当前用户需求:\n{user_input}"
            )
        plans, checkpoints = await todo_manager.plan_task(
            enriched, client=self._client,
            skill_metadata=self._skill_loader.get_metadata_prompt(),
        )

        p._max_subtask_result_len = self._agent_max_token // max(len(plans), 1)
        p._max_tools_compress_len = int(p._max_subtask_result_len * 0.67)

        # 如果 LLM 未标记检查点，机械规则兜底
        if not checkpoints:
            checkpoints = todo_manager.identify_checkpoints(plans)
        cp_labels = {cp: "🔵检查点" for cp in checkpoints}

        # ---------- 展示任务计划 ----------
        total = len(plans)
        print(f"\n{'─' * 50}")
        print(f"📋 任务已分解为 {total} 个步骤:")
        for i, t in enumerate(plans):
            tag = p.classify_subtask(t)
            cp_mark = f" {cp_labels.get(i, '')}" if i in checkpoints else ""
            print(f"  {i+1}. [{tag}] {t[:75]}{'...' if len(t) > 75 else ''}{cp_mark}")
        if checkpoints:
            print(f"  ⚡ 共 {len(checkpoints)} 个检查点，到达时将重新评估后续计划")
        print(f"{'─' * 50}")

        sub_results = []
        if total > 0:
            self._subtask_mgr.init()
            self._subtask_mgr.create(plans, checkpoints)

        # ---------- 当前执行循环的指针 ----------
        i = 0
        while i < len(plans):
            task_text = plans[i]
            is_last = i == len(plans) - 1
            is_end_task = is_last or len(plans) == 1
            task_type = p.classify_subtask(task_text)

            # ---------- 检查点：CP步骤开始前重新评估包括自己在内的所有剩余步骤 ----------
            if i in checkpoints and i < len(plans) - 1:
                print(f"\n{'▸' * 25}")
                print(f"🔵 到达检查点 (Step {i+1}/{total})，重新评估剩余计划（含当前步骤）...")
                completed_map = self._subtask_mgr.get_completed_map()
                remaining = plans[i:]  # 包含当前CP步骤在内的所有剩余

                completed_text_parts = []
                for ct, cr in completed_map.items():
                    completed_text_parts.append(f"【已完成】{ct}\n结果: {cr[:300]}")
                completed_text = "\n\n".join(completed_text_parts) if completed_text_parts else "（无）"

                replan_result = await todo_manager.replan_task(
                    user_input=user_input,
                    completed_steps=completed_text,
                    remaining_plan=remaining,
                    client=self._client,
                )

                if replan_result["changed"]:
                    reason = replan_result["reason"]
                    new_remaining = replan_result["new_plan"]
                    cancelled = replan_result.get("cancelled", [])

                    print(f"  ⚠️  计划需要调整！")
                    print(f"  变更原因: {reason}")
                    if cancelled:
                        print(f"  🗑️  取消步骤:")
                        for cs, cr in cancelled:
                            print(f"      DEL[{cr}] {cs[:60]}")
                    if replan_result["removed"]:
                        print(f"  移除: {replan_result['removed']}")
                    if replan_result["added"]:
                        print(f"  新增: {replan_result['added']}")
                    print(f"  新剩余计划 ({len(new_remaining)}步):")
                    for j, t in enumerate(new_remaining):
                        print(f"    {i+1+j}. {t[:70]}{'...' if len(t) > 70 else ''}")

                    self._subtask_mgr.revise_plan(
                        new_remaining_plan=new_remaining,
                        change_reason=reason,
                        current_step_index=i,
                        cancelled=cancelled,
                    )
                    # 重建 plans：已完成 + 新计划
                    plans = list(completed_map.keys()) + new_remaining
                    new_checkpoints = todo_manager.identify_checkpoints(new_remaining)
                    checkpoints = {i + cp for cp in new_checkpoints}
                    total = len(plans)
                    print(f"  📋 更新后共计 {total} 个步骤（已完成 {len(completed_map)} 个）")
                    # 重新获取当前步骤（可能已被替换）
                    if i < len(plans):
                        task_text = plans[i]
                        is_last = i == len(plans) - 1
                        is_end_task = is_last or len(plans) == 1
                        task_type = p.classify_subtask(task_text)
                else:
                    print(f"  ✅ 计划无需调整，继续执行")
                print(f"{'▸' * 25}")

            # ---------- 当前步骤：执行 ----------
            emoji = {"build": "🔨", "verify": "✅", "research": "🔍"}.get(task_type, "📌")
            print(
                f"\n{emoji} Step {i+1}/{total} [{task_type}] "
                f"{task_text[:70]}{'...' if len(task_text) > 70 else ''}"
            )

            system_content = p.build_subtask_system(
                task_text, i, total, is_end_task, task_type,
                self._state.written_files, self._subtask_mgr,
            )
            user_content = p.build_subtask_user(
                user_input, task_text, i, total, is_end_task, task_type,
                conversation_context or "", self._state.written_files, self._subtask_mgr,
            )
            skill_prefix = p.build_skill_prefix(task_text)
            if skill_prefix:
                system_content = skill_prefix + "\n\n" + system_content

            task_messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]
            tool_schemas = p.pick_tools(is_end_task, task_type, total)

            result = await p.run_sub_task(task_messages, task_text, tool_schemas)
            result = p.sanitize_result(result)
            sub_results.append({"task": task_text, "result": result})

            # ---------- 步骤完成 ----------
            ok = not result.startswith("[子任务执行失败]")
            status = "✅" if ok else "❌"
            preview = result[:120].replace('\n', ' ') + ('...' if len(result) > 120 else '')
            print(f"  {status} 完成 ({len(result)}字): {preview}")

            if not (is_end_task and i > 0):
                self._subtask_mgr.update(task_text, result, is_end_task=is_end_task)

            self._state.last_episode.append({
                "task": task_text,
                "success": ok,
                "result_preview": result[:200],
            })

            i += 1

        return self._merge_results(sub_results, total)

    # ==================================================================
    # 上下文构建（每次 run 前注入历史摘要）
    # ==================================================================

    def _build_conversation_context(self) -> str:
        parts = []
        summary_path = os.path.join(
            self._project_root, "initspace", "memorys", "memory_summary.md"
        )
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                sections = re.split(r"^## ", raw, flags=re.MULTILINE)
                if len(sections) >= 2:
                    today = datetime.now().strftime("%Y-%m-%d")
                    summary_parts = []
                    total = 0
                    for sec in sections[1:]:
                        s = sec.strip()
                        if not s:
                            continue
                        if s.startswith(today):
                            continue
                        if total + len(s) > self._context_summary_max_chars:
                            break
                        summary_parts.append(f"## {s}")
                        total += len(s)
                    if summary_parts:
                        parts.append("[近期摘要]\n" + "\n".join(summary_parts))
            except Exception as e:
                logger.warning("[上下文] 读取 memory_summary.md 失败: %s", e)
        return "\n\n".join(parts) if parts else ""

    # ==================================================================
    # 子任务文件管理（委托给 SubtasksManager）
    # ==================================================================

    def _subtask_init(self):
        self._subtask_mgr.init()

    def _subtask_create(self, plans: list):
        self._subtask_mgr.create(plans)

    def _subtask_update(self, task_text: str, result: str, is_end_task: bool = False):
        self._subtask_mgr.update(task_text, result, is_end_task)

    def read_completed(self) -> str:
        return self._subtask_mgr.read_completed()

    # ==================================================================
    # 结果合并
    # ==================================================================

    @staticmethod
    def _merge_results(sub_results: list, total: int) -> str:
        if total >= 1 and sub_results:
            last = sub_results[-1]["result"]
            if last and len(last) > 50:
                summary = "\n".join(f"- {r['task']}: 已完成" for r in sub_results[:-1])
                final = last
                if summary:
                    final += f"\n\n---\n已完成所有子任务：\n{summary}"
                return final
        return "\n\n".join(f"**{r['task']}**\n{r['result']}" for r in sub_results)
