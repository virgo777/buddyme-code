"""
manager.py — 记忆管理器外观

组合 MemoryStore + ConversationLogger，统一调度记忆生命周期。
为命令处理器提供简洁的操作接口。
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MemoryManager:
    """记忆管理器 — 统一调度记忆的完整生命周期。

    组合 MemoryStore（USER.md 记忆）和 ConversationLogger（对话日志），
    对外提供 prefetch / sync_turn / on_session_end 生命周期钩子，
    以及 show / update / decay / consolidate / history / clear 等命令接口。
    """

    def __init__(self, store, conv_logger):
        """
        Args:
            store: MemoryStore 实例
            conv_logger: ConversationLogger 实例
        """
        self.store = store
        self.conv_logger = conv_logger
        self._last_prefetch_query: str = ""

    # ------------------------------------------------------------------
    # 生命周期钩子
    # ------------------------------------------------------------------

    def prefetch(self, query: str = "") -> str:
        """每轮 LLM 调用前：预制相关记忆，返回注入 system prompt 的文本。"""
        self._last_prefetch_query = query
        return self.store.prefetch(query)

    def sync_turn(self, query: str, response_summary: str) -> None:
        """每轮对话后：同步记忆活跃度。"""
        self.store.sync_turn(query, response_summary)

    def on_session_end(self) -> None:
        """会话结束时：执行衰减并持久化。"""
        self.store.on_session_end()

    # ------------------------------------------------------------------
    # 命令接口：记忆管理
    # ------------------------------------------------------------------

    def show(self) -> str:
        """显示当前用户记忆。"""
        if not self.store.data:
            self.store.load()
        if not self.store.data:
            return "记忆为空"

        lines = []
        for section, content in self.store.data.items():
            if not content:
                continue
            lines.append(f"## {section}")
            if isinstance(content, list):
                for item in content:
                    lines.append(f"  - {item}")
            else:
                for line in str(content).splitlines():
                    lines.append(f"  {line}")
            lines.append("")
        return "当前用户记忆:\n" + "\n".join(lines)

    def summary(self) -> str:
        """显示近期对话摘要。"""
        return "（对话摘要功能，待实现 memory_summary.md 写入路径）"

    async def do_update(self) -> str:
        """手动触发记忆提取更新。"""
        try:
            result = await self.store.update()
            if not result:
                return "记忆更新完成（无新增内容）"
            lines = ["记忆更新完成，变更的章节:"]
            for section in result:
                lines.append(f"  - {section}")
            return "\n".join(lines)
        except Exception as e:
            return f"记忆更新失败: {e}"

    def update_sync(self) -> str:
        """同步版本的 update，供命令处理器调用。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, self.store.update()).result()
            else:
                return asyncio.run(self.store.update())
        except RuntimeError:
            return asyncio.run(self.store.update())

    def do_decay(self) -> str:
        """执行记忆衰减。"""
        try:
            before = len(self.store.data)
            self.store.run_memory_decay()
            after = len(self.store.data)
            return f"记忆衰减完成: {before} -> {after} 章节（移除 {before - after} 个低分记忆）"
        except Exception as e:
            return f"记忆衰减失败: {e}"

    def do_consolidate(self) -> str:
        """执行记忆整合。"""
        try:
            before = len(self.store.data)
            self.store.run_memory_consolidation()
            after = len(self.store.data)
            return f"记忆整合完成: {before} -> {after} 章节（合并 {before - after} 个碎片）"
        except Exception as e:
            return f"记忆整合失败: {e}"

    def show_history(self) -> str:
        """查看记忆归档历史。"""
        history = self.store._load_history()
        archive = history.get("archive", {})
        last_active = history.get("last_active", {})
        importance = history.get("importance", {})

        if not archive and not last_active:
            return "暂无记忆历史"

        lines = []
        if last_active:
            lines.append("=== 活跃记忆 ===")
            for section, timestamp in sorted(last_active.items(), key=lambda x: x[1], reverse=True):
                score = importance.get(section, "N/A")
                if isinstance(score, float):
                    score = f"{score:.2f}"
                ts = timestamp[:19] if len(timestamp) > 19 else timestamp
                lines.append(f"  [{score}] {section} (最后活跃: {ts})")

        if archive:
            lines.append("\n=== 归档记忆 ===")
            for section, entries in archive.items():
                lines.append(f"  {section} ({len(entries)} 条归档)")

        return "\n".join(lines)

    def clear(self, force: bool = False) -> str:
        """清除所有用户记忆。"""
        if not force:
            return "确认清除所有记忆？请使用 --force 参数"
        try:
            self.store.data = {}
            self.store.save()
            history_path = self.store.history_path
            if os.path.exists(history_path):
                os.remove(history_path)
            return "所有用户记忆已清除"
        except Exception as e:
            return f"清除记忆失败: {e}"

    # ------------------------------------------------------------------
    # 命令接口：对话日志
    # ------------------------------------------------------------------

    @property
    def conv_log_path(self) -> str:
        return str(self.conv_logger.log_path)

    def log_recent(self, limit: int = 5) -> str:
        data = self._read_log()
        if data is None:
            return "暂无对话记录"

        all_dates = sorted(data.keys(), reverse=True)
        entries = []
        count = 0
        for date in all_dates:
            for record in reversed(data[date]):
                if count >= limit:
                    break
                time_str = record.get("time", "?")
                query = record.get("query", "")
                model = record.get("model", "")
                entries.append(f"[{date} {time_str}] ({model}) {query}")
                count += 1
            if count >= limit:
                break

        if not entries:
            return "暂无对话记录"
        total = sum(len(v) for v in data.values())
        return f"最近 {len(entries)} 条对话（共 {total} 条）:\n" + "\n".join(entries)

    def log_date(self, date_str: str) -> str:
        data = self._read_log()
        if data is None:
            return "暂无对话记录"

        records = data.get(date_str, [])
        if not records:
            return f"{date_str} 无对话记录"

        lines = [f"=== {date_str} ({len(records)} 条对话) ==="]
        for record in records:
            time_str = record.get("time", "?")
            query = record.get("query", "")
            model = record.get("model", "")
            response = record.get("response_summary", record.get("response", ""))
            if len(response) > 100:
                response = response[:100] + "..."
            lines.append(f"[{time_str}] ({model}) Q: {query}")
            lines.append(f"  A: {response}")
        return "\n".join(lines)

    def log_search(self, keyword: str) -> str:
        data = self._read_log()
        if data is None:
            return "暂无对话记录"

        keyword_lower = keyword.lower()
        results = []
        for date in sorted(data.keys(), reverse=True):
            for record in data[date]:
                query = record.get("query", "")
                response = record.get("response_summary", record.get("response", ""))
                if keyword_lower in query.lower() or keyword_lower in response.lower():
                    time_str = record.get("time", "?")
                    model = record.get("model", "")
                    results.append(f"[{date} {time_str}] ({model}) {query}")
                    if len(results) >= 20:
                        break
            if len(results) >= 20:
                break

        if not results:
            return f"未找到包含 '{keyword}' 的对话"
        return f"搜索 '{keyword}' 找到 {len(results)} 条:\n" + "\n".join(results)

    def log_clear(self, force: bool = False) -> str:
        if not force:
            return "确认清除所有对话记录？请使用 --force 参数"
        try:
            if os.path.exists(self.conv_logger.log_path):
                os.remove(self.conv_logger.log_path)
            return "对话记录已清除"
        except Exception as e:
            return f"清除失败: {e}"

    def _read_log(self) -> Optional[Dict]:
        log_path = self.conv_logger.log_path
        if not os.path.exists(log_path):
            return None
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
