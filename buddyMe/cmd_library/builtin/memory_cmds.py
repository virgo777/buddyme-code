"""
cmd_library/builtin/memory_cmds.py — 记忆管理命令

注册: /memory, /log
使用 ctx.memory_manager 访问记忆系统（解耦自 AgentMain）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from ..base import CommandContext, CommandResult, CommandMeta
from ..registry import CommandRegistry


def register_memory_commands(registry: CommandRegistry) -> None:
    """注册所有记忆管理命令"""
    registry.register_handler("memory", cmd_memory, meta=CommandMeta(
        name="memory", aliases=["mem"],
        description="记忆管理（查看/更新/衰减/整合）",
        usage="/memory [--show | --summary | --update | --decay | --consolidate | --history | --clear]",
        category="memory",
    ))
    registry.register_handler("log", cmd_log, meta=CommandMeta(
        name="log", aliases=["history"],
        description="对话记录管理",
        usage="/log [--today | --date YYYY-MM-DD | --search 关键词 | --clear]",
        category="memory",
    ))


def _get_mgr(ctx: CommandContext):
    """获取 MemoryManager，回退到 agent 属性（向后兼容）。"""
    if ctx.memory_manager is not None:
        return ctx.memory_manager
    return ctx.agent._memory


# ============================================================
# /memory
# ============================================================

def cmd_memory(ctx: CommandContext) -> CommandResult:
    args = ctx.args_text.strip().lstrip("-")

    if not args or args in ("show", "s"):
        return _memory_show(ctx)
    if args == "summary":
        return _memory_summary(ctx)
    if args in ("update", "u"):
        return _memory_update(ctx)
    if args in ("decay", "d"):
        return _memory_decay(ctx)
    if args in ("consolidate", "c"):
        return _memory_consolidate(ctx)
    if args == "history":
        return _memory_history(ctx)
    if args.startswith("clear"):
        return _memory_clear(ctx)

    return CommandResult(
        success=False,
        message=(
            "用法:\n"
            "  /memory              显示当前记忆\n"
            "  /memory --summary    显示对话摘要\n"
            "  /memory --update     手动更新记忆\n"
            "  /memory --decay      执行记忆衰减\n"
            "  /memory --consolidate 执行记忆整合\n"
            "  /memory --history    查看归档历史\n"
            "  /memory --clear      清除所有记忆"
        ),
    )


def _memory_show(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.show())


def _memory_summary(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.summary())


def _memory_update(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    try:
        result = mgr.update_sync()
        if isinstance(result, dict):
            if not result:
                return CommandResult(message="记忆更新完成（无新增内容）")
            lines = ["记忆更新完成，变更的章节:"]
            for section in result:
                lines.append(f"  - {section}")
            return CommandResult(message="\n".join(lines))
        return CommandResult(message=str(result))
    except Exception as e:
        return CommandResult(success=False, message=f"记忆更新失败: {e}")


def _memory_decay(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.do_decay())


def _memory_consolidate(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.do_consolidate())


def _memory_history(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.show_history())


def _memory_clear(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    args = ctx.args_text
    force = "--force" in args or "-f" in args
    return CommandResult(message=mgr.clear(force=force))


# ============================================================
# /log
# ============================================================

def cmd_log(ctx: CommandContext) -> CommandResult:
    args = ctx.args_text.strip().lstrip("-")

    if not args or args in ("recent", "r"):
        return _log_recent(ctx)
    if args in ("today", "t"):
        return _log_date(ctx, datetime.now().strftime("%Y-%m-%d"))
    if args.startswith("date"):
        parts = args.split(None, 1)
        if len(parts) < 2:
            return CommandResult(success=False, message="用法: /log --date YYYY-MM-DD")
        return _log_date(ctx, parts[1].strip())
    if args.startswith("search"):
        parts = args.split(None, 1)
        if len(parts) < 2:
            return CommandResult(success=False, message="用法: /log --search 关键词")
        return _log_search(ctx, parts[1].strip())
    if args.startswith("clear"):
        return _log_clear(ctx)

    return CommandResult(
        success=False,
        message=(
            "用法:\n"
            "  /log                   显示最近对话\n"
            "  /log --today           今天的对话\n"
            "  /log --date YYYY-MM-DD 指定日期对话\n"
            "  /log --search 关键词   搜索对话\n"
            "  /log --clear           清除对话记录"
        ),
    )


def _log_recent(ctx: CommandContext, limit: int = 5) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.log_recent(limit=limit))


def _log_date(ctx: CommandContext, date_str: str) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.log_date(date_str))


def _log_search(ctx: CommandContext, keyword: str) -> CommandResult:
    mgr = _get_mgr(ctx)
    return CommandResult(message=mgr.log_search(keyword))


def _log_clear(ctx: CommandContext) -> CommandResult:
    mgr = _get_mgr(ctx)
    args = ctx.args_text
    force = "--force" in args or "-f" in args
    return CommandResult(message=mgr.log_clear(force=force))
