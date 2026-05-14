"""
subtasks_manager.py — 子任务状态文件管理

封装 subtask_results.json 的读写操作，支持动态计划修订和变更追踪。
"""

import json
import os
from datetime import datetime
from typing import Optional


class SubtasksManager:
    """管理子任务状态 JSON 文件，作为子任务间的数据桥梁。

    支持动态计划修订：在检查点可调整后续子任务，记录变更原因。
    """

    def __init__(self, file_path: str, max_result_len: int = 8192):
        self.file_path = file_path
        self.max_result_len = max_result_len

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------

    def init(self) -> None:
        """删除旧的子任务文件，准备新一轮任务。"""
        if os.path.exists(self.file_path):
            os.remove(self.file_path)

    def create(self, plans: list, checkpoints: list = None) -> None:
        """根据计划列表创建子任务记录（全部为 pending）。

        Args:
            plans: 步骤文本列表
            checkpoints: 检查点索引列表（可选）
        """
        total = len(plans)
        data = {
            "_meta": {
                "version": 1,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_steps": total,
                "completed_count": 0,
                "checkpoints": checkpoints or [],
                "changes": [],
            }
        }
        for idx, text in enumerate(plans):
            is_first = idx == 0
            is_last = idx == total - 1
            tags = []
            if is_first:
                tags.append("start_task")
            if is_last or total == 1:
                tags.append("end_task")
            if checkpoints and idx in checkpoints:
                tags.append("checkpoint")
            data[text] = {"status": "pending", "tags": tags, "result": ""}
        self._write(data)

    def update(self, task_text: str, result: str, is_end_task: bool = False) -> None:
        """更新指定子任务的状态和结果。"""
        if not is_end_task and len(result) > self.max_result_len:
            result = result[:self.max_result_len] + "\n...(结果过长已截断)"

        data = self._read()
        if data is None:
            return

        if task_text in data:
            data[task_text]["status"] = "completed"
            data[task_text]["result"] = result

        # 更新元数据
        meta = data.get("_meta", {})
        completed = sum(1 for k, v in data.items()
                       if not k.startswith("_") and v.get("status") == "completed")
        meta["completed_count"] = completed
        meta["updated_at"] = datetime.now().isoformat()
        data["_meta"] = meta

        self._write(data)

    def read_completed(self) -> str:
        """读取所有已完成的子任务结果（拼接）。"""
        data = self._read()
        if data is None:
            return "暂无已完成的结果"

        parts = []
        for task, info in data.items():
            if task.startswith("_"):
                continue
            if info.get("status") == "completed":
                parts.append(f"【{task}】\n{info.get('result', '无结果')}")
        return "\n\n".join(parts) if parts else "暂无已完成的结果"

    # ------------------------------------------------------------------
    # 动态计划修订
    # ------------------------------------------------------------------

    def get_completed_map(self) -> dict:
        """返回 {task_text: result} 的已完成任务映射。"""
        data = self._read()
        if data is None:
            return {}
        return {
            k: v.get("result", "")
            for k, v in data.items()
            if not k.startswith("_") and v.get("status") == "completed"
        }

    def get_remaining_plan(self) -> list:
        """返回剩余待执行步骤的文本列表。"""
        data = self._read()
        if data is None:
            return []
        return [
            k for k, v in data.items()
            if not k.startswith("_") and v.get("status") == "pending"
        ]

    def get_checkpoints(self) -> list:
        """返回检查点索引列表。"""
        data = self._read()
        if data is None:
            return []
        meta = data.get("_meta", {})
        return meta.get("checkpoints", [])

    def revise_plan(
        self,
        new_remaining_plan: list,
        change_reason: str,
        current_step_index: int,
        cancelled: list = None,
    ) -> None:
        """修订计划：保留已完成步骤，替换剩余步骤，记录变更。

        Args:
            new_remaining_plan: 调整后的剩余步骤列表
            change_reason: 变更原因
            current_step_index: 触发修订时所在的步骤索引（0-based）
            cancelled: [(step_text, del_reason), ...] 被取消的步骤
        """
        data = self._read()
        if data is None:
            return

        # 保留已完成的任务
        completed = {}
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if v.get("status") == "completed":
                completed[k] = v

        # 构建新的 data
        meta = data.get("_meta", {})
        old_remaining = self.get_remaining_plan()

        total_steps = len(completed) + len(new_remaining_plan)
        if cancelled:
            total_steps += len(cancelled)
        meta["version"] = meta.get("version", 1) + 1
        meta["updated_at"] = datetime.now().isoformat()
        meta["total_steps"] = total_steps
        meta["completed_count"] = len(completed)

        # 记录变更
        changes = meta.get("changes", [])
        changes.append({
            "at_step": current_step_index,
            "timestamp": datetime.now().isoformat(),
            "reason": change_reason,
            "old_remaining": old_remaining,
            "new_remaining": new_remaining_plan,
            "cancelled": [{"step": s, "reason": r} for s, r in (cancelled or [])],
        })
        meta["changes"] = changes
        meta["checkpoints"] = []

        new_data = {"_meta": meta}

        for k, v in completed.items():
            new_data[k] = v

        # 写入被取消的步骤（状态 cancelled，保留原因）
        for step_text, del_reason in (cancelled or []):
            new_data[step_text] = {
                "status": "cancelled",
                "tags": ["del"],
                "result": f"[DEL] {del_reason}",
            }

        # 写入新剩余步骤（全部 pending）
        remaining_total = len(new_remaining_plan)
        for idx, text in enumerate(new_remaining_plan):
            is_last = idx == remaining_total - 1
            tags = []
            if is_last:
                tags.append("end_task")
            new_data[text] = {"status": "pending", "tags": tags, "result": ""}

        self._write(new_data)

    def get_full_state(self) -> dict:
        """返回完整的任务状态（供外部检查）。"""
        data = self._read()
        if data is None:
            return {"_meta": {}, "tasks": {}}
        return data

    # ------------------------------------------------------------------
    # 内部 I/O
    # ------------------------------------------------------------------

    def _read(self) -> Optional[dict]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write(self, data: dict) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
