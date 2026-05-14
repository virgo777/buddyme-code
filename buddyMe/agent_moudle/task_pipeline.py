"""
task_pipeline.py — 任务拆解与子任务执行

负责:
    - 简单任务判定 + 快速执行（单轮 LLM + 工具调用）
    - 子任务 Prompt 构建（system / user / skill / 工具选择）
    - 子任务执行（LLM + 工具调用循环、搜索限制、上下文压缩、结果清洗）
    - 工具函数（token 追踪、结果压缩、乱码清理）

依赖通过构造函数注入，不再通过 self._a 反向通道访问 AgentMain。
"""

import json
import logging
import os
import re
from typing import List

logger = logging.getLogger(__name__)

_GARBLED_CHAR_RE = re.compile('[぀-ゟ゠-ヿÀ-ÿ�]')

_SIMPLE_TASK_KEYWORDS = [
    "生成", "创建", "写", "制作", "开发", "设计", "实现", "构建",
    "html", "css", "js", "javascript", "python", "vue", "react",
    "页面", "脚本", "程序", "项目", "系统", "前端", "后端",
    "重构", "方案", "架构", "并", "且", "然后",
]

_VERIFY_KEYWORDS = ["验证", "检查", "测试", "修复", "确认", "[VERIFY]"]
_BUILD_KEYWORDS = [
    "生成", "编写", "创建", "写", "制作", "实现", "开发", "构建",
    "html", "css", "js", "javascript", "python",
    "页面", "脚本", "程序", "文件", "代码", "样式", "交互",
    "添加", "注入", "补充", "填充", "整合",
    "[CREATE]", "[EDIT]",
]


class TaskPipeline:
    """任务拆解 + 子任务执行引擎。

    依赖通过构造函数注入：
      - client / sub_client: LLM 客户端
      - executor: 工具执行器
      - skill_loader: Skill 加载器
      - memory_store: 用户记忆
      - workspace_dir / output_dir: 路径配置
      - prompt_builder: System prompt 构建器
      - compressor: 上下文压缩器（可选）
      - state: 共享 SessionState
    """

    def __init__(
        self,
        client,
        sub_client,
        executor,
        skill_loader,
        memory_store,
        workspace_dir,
        output_dir,
        prompt_builder,
        state,
        system_prompt: str = "",
        max_steps: int = 11,
        max_messages_length: int = 20,
        max_search_calls: int = 5,
        max_tools_compress_len: int = 5120,
        max_subtask_result_len: int = 8192,
        agent_max_token: int = 131072,
        sub_agent_max_token: int = 32768,
        compressor=None,
    ):
        self._client = client
        self._sub_client = sub_client
        self._executor = executor
        self._skill_loader = skill_loader
        self._memory_store = memory_store
        self._workspace_dir = workspace_dir
        self._output_dir = output_dir
        self._prompt_builder = prompt_builder
        self._state = state
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._max_messages_length = max_messages_length
        self._max_search_calls = max_search_calls
        self._max_tools_compress_len = max_tools_compress_len
        self._max_subtask_result_len = max_subtask_result_len
        self._agent_max_token = agent_max_token
        self._sub_agent_max_token = sub_agent_max_token
        self._compressor = compressor

    # ==================================================================
    # 任务分类
    # ==================================================================

    @staticmethod
    def is_simple_task(text: str) -> bool:
        t = text.strip().lower()
        if any(kw in t for kw in _SIMPLE_TASK_KEYWORDS):
            return False
        if len(t) < 40:
            return True
        return len(t) <= 100

    @staticmethod
    def classify_subtask(text: str) -> str:
        t = text.lower()
        if any(kw in t for kw in _VERIFY_KEYWORDS):
            return "verify"
        if any(kw in t for kw in _BUILD_KEYWORDS):
            return "build"
        return "research"

    # ==================================================================
    # 简单任务执行
    # ==================================================================

    async def run_simple(self, user_input: str, conv_ctx: str) -> str:
        memory = self._memory_store.to_prompt()
        full_system = self._system_prompt + "\n\n" + memory
        path_hint = (
            f"\n\n【环境信息】\n"
            f"项目工作空间: {self._workspace_dir}\n"
            f"默认输出目录: {self._output_dir}\n\n"
            f"【文件输出规则】\n"
            f"当用户没有明确指定文件保存路径时，所有生成的文件必须保存到默认输出目录: {self._output_dir}"
        )
        enriched = user_input
        if conv_ctx:
            enriched = f"{conv_ctx}\n\n{'=' * 40}\n\n当前用户需求:\n{user_input}"
        messages = [
            {"role": "system", "content": full_system + path_hint},
            {"role": "user", "content": enriched},
        ]
        tools = self._executor.get_all_schemas()
        full_text = ""
        for step in range(1, 6):
            try:
                resp = await self._client.chat(messages=messages, tools=tools)
                self._track_usage(resp)
            except Exception as e:
                logger.error("[短路 Step %d] LLM 调用失败: %s", step, e)
                return full_text or f"[执行失败: {e}]"
            blocks = resp.get("content", [])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
            if texts:
                full_text = "\n".join(texts)
            if not tool_calls:
                return full_text or "[任务完成]"
            messages.append(self._format_tool_calls(tool_calls))
            for tc in tool_calls:
                name = tc["name"]
                inp = tc.get("input", {})
                # ---------- 展示工具/Skill 调用 ----------
                if name == "invoke_skill":
                    print(f"  🎯 [Skill] {inp.get('skill_name', '未知')}")
                else:
                    args_summary = ", ".join(f"{k}={str(v)[:40]}" for k, v in inp.items())
                    print(f"  🔧 [{name}] {args_summary}")
                self._state.used_tools.append({"tool_name": name, "args": inp})
                result_text = await self._executor.execute(name, inp)
                if not result_text:
                    result_text = "[工具无输出]"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": result_text})
                limit = min(self._agent_max_token // 4, 8000)
                if len(result_text) <= limit:
                    full_text = result_text
                else:
                    full_text = result_text[:limit * 2 // 3] + "\n...(中间已省略)...\n" + result_text[-(limit // 3):]
        return full_text or "[任务完成]"

    # ==================================================================
    # 子任务执行（LLM + 工具调用循环）
    # ==================================================================

    async def run_sub_task(self, task_messages: list, task_text: str, tool_schemas: list) -> str:
        full_text = ""
        collected = []
        search_count = 0

        for step in range(1, self._max_steps + 1):
            try:
                resp = await self._client.chat(messages=task_messages, tools=tool_schemas)
                self._track_usage(resp)
            except Exception as e:
                logger.error("[子任务 Step %d] LLM 调用失败: %s", step, e)
                if len(task_messages) > 3:
                    summary = self._compress_tool_results(task_messages, self._max_tools_compress_len)
                    task_messages = [
                        task_messages[0],
                        {"role": "user", "content": f"以下是已获取的信息:\n\n{summary}\n\n请直接基于以上信息完成任务。"},
                    ]
                    try:
                        resp = await self._sub_client.chat(messages=task_messages, tools=tool_schemas)
                        self._track_usage(resp)
                    except Exception as e2:
                        logger.error("[子任务 Step %d] 重试也失败: %s", step, e2)
                        return full_text or "[子任务执行失败]"
                else:
                    return full_text or "[子任务执行失败]"

            blocks = resp.get("content", [])
            tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
            self._state.used_tools.extend([{"tool_name": tc["name"], "args": tc.get("input", {})} for tc in tool_calls])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            step_text = "\n".join(texts)
            if step_text:
                full_text += step_text + "\n"

            if not tool_calls:
                return full_text or "[子任务完成]"

            search_tools = [tc for tc in tool_calls if tc["name"] == "baidu_search"]
            other_tools = [tc for tc in tool_calls if tc["name"] != "baidu_search"]
            if search_count + len(search_tools) > self._max_search_calls:
                remaining = self._max_search_calls - search_count
                if remaining <= 0:
                    if other_tools:
                        tool_calls = other_tools
                    else:
                        return full_text.strip() or "[子任务完成]"
                else:
                    tool_calls = search_tools[:remaining] + other_tools
            search_count += sum(1 for tc in tool_calls if tc["name"] == "baidu_search")

            task_messages.append(self._format_tool_calls(tool_calls))
            for tc in tool_calls:
                name = tc["name"]
                inp = tc.get("input", {})
                # ---------- 展示工具/Skill 调用 ----------
                if name == "invoke_skill":
                    skill_name = inp.get("skill_name", "未知")
                    print(f"  🎯 [Skill] {skill_name}")
                else:
                    args_summary = ", ".join(f"{k}={str(v)[:40]}" for k, v in inp.items())
                    print(f"  🔧 [{name}] {args_summary}")
                if not inp:
                    result_content = f"错误：工具 '{name}' 的参数为空。"
                else:
                    try:
                        result = await self._executor.execute(name, inp)
                        result_content = result or "(无输出)"
                    except Exception as e:
                        result_content = f"执行失败: {type(e).__name__}"
                if name == "write_file" and "成功" in result_content:
                    result_content += "\n\n[系统] 文件已成功写入，当前子任务已完成。"
                if name == "invoke_skill":
                    self._state.used_skills.append(inp.get("skill_name", "未知"))
                collected.append(f"[{name}] {result_content}")
                task_messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": result_content})

            if len(task_messages) > self._max_messages_length:
                if self._compressor:
                    try:
                        compressed_ctx = await self._compressor.compress(task_messages, self._sub_client)
                        task_messages = self._compressor.get_compressed_messages(compressed_ctx)
                    except Exception:
                        summary = self._compress_tool_results(task_messages, self._max_tools_compress_len)
                        task_messages = [
                            task_messages[0],
                            {"role": "user", "content": f"【当前子任务目标】{task_text}\n\n以下是已获取的信息:\n\n{summary}\n\n请直接基于以上信息完成当前子任务。"},
                        ]
                else:
                    summary = self._compress_tool_results(task_messages, self._max_tools_compress_len)
                    task_messages = [
                        task_messages[0],
                        {"role": "user", "content": f"【当前子任务目标】{task_text}\n\n以下是已获取的信息:\n\n{summary}\n\n请直接基于以上信息完成当前子任务。"},
                    ]

            if search_count >= self._max_search_calls:
                summary = self._compress_tool_results(task_messages, self._max_tools_compress_len)
                task_messages = [
                    {"role": "system", "content": f"你是助手，当前子任务: {task_text}"},
                    {"role": "user", "content": f"【当前子任务目标】{task_text}\n\n以下是已获取的信息:\n\n{summary}\n\n请直接基于以上信息给出最终结果。"},
                ]
                try:
                    resp = await self._client.chat(messages=task_messages)
                    self._track_usage(resp)
                    final = "\n".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
                    return (full_text + "\n" + final).strip() if full_text else final.strip()
                except Exception as e:
                    logger.error("[子任务] 强制总结失败: %s", e)
                    return full_text.strip() or "[子任务完成]"

        if full_text.strip():
            return full_text.strip()
        if collected:
            return "[已收集的信息]\n" + "\n\n".join(collected)
        return "[达到最大步数限制]"

    # ==================================================================
    # Subtask Prompt 构建
    # ==================================================================

    def build_subtask_system(self, task_text: str, idx: int, total: int, is_end_task: bool, task_type: str,
                             written_files: list, subtask_mgr) -> str:
        sub_rules = self._load_sub_agent_prompt()
        skill_meta = self._skill_loader.get_metadata_prompt()
        readonly = (
            f"\n\n【环境信息】\n"
            f"项目工作空间: {self._workspace_dir}\n"
            f"默认输出目录: {self._output_dir}\n"
            f"使用 grep/glob/read_file 等工具时，path 参数应基于项目工作空间。\n\n"
            f"【文件输出规则】\n"
            f"当用户没有明确指定文件保存路径时，所有生成的文件必须保存到默认输出目录: {self._output_dir}\n"
            f"write_file 的 path 参数必须以该目录为基础路径。\n\n"
            "【禁止事项】\n"
            "严禁使用 write_file 或 edit_file 修改 initspace/memorys/subtask_results.json，"
            "该文件由系统自动管理，你只能通过 read_file 读取它。"
        )
        if skill_meta:
            readonly += f"\n\n{skill_meta}"
        if is_end_task and idx > 0:
            files = "\n".join(f"  - {f}" for f in written_files) or "  (暂无)"
            return (
                f"当前子任务: 最终验证与修复\n\n"
                f"【已生成的文件】\n{files}\n\n"
                f"【验证任务】\n"
                f"1. 用 read_file 读取已生成的文件\n2. 检查结构完整性\n"
                f"3. 发现问题用 edit_file 修复\n4. 无问题则输出文件路径和功能说明\n"
                f"5. 禁止重新搜索\n" + readonly + "\n\n" + sub_rules
            )
        if total == 1:
            return (
                f"当前子任务: {task_text}\n\n"
                f"【文件构建策略】\n"
                f"1. 先用 write_file 创建文件骨架\n2. 再用 edit_file 逐步填充\n"
                f"3. 每次写入控制在合理长度内\n4. 写入后不要读回验证\n"
                + readonly + "\n\n" + sub_rules
            )
        if task_type == "build":
            prev = subtask_mgr.read_completed() if idx > 0 else ""
            files = "\n".join(f"  - {f}" for f in written_files) or "  (暂无)"
            prev_ctx = ""
            if prev and prev != "暂无已完成的结果":
                prev_ctx = f"\n\n【前置子任务结果】\n{prev[:self._max_tools_compress_len]}"
            return (
                f"当前子任务: {task_text}\n\n"
                f"【文件构建策略】\n"
                f"1. 先用 write_file 创建文件骨架\n2. 再用 edit_file 逐步填充\n"
                f"3. 每次写入控制在合理长度内\n4. 写入后不要读回验证\n"
                f"5. 优先使用前置子任务的已有结果\n\n"
                f"【已生成的文件】\n{files}" + prev_ctx + readonly + "\n\n" + sub_rules
            )
        prev = subtask_mgr.read_completed() if idx > 0 else ""
        if prev and prev != "暂无已完成的结果":
            return (
                f"当前子任务: {task_text}\n\n"
                f"【严格规则】\n"
                f"1. 下方已提供前置子任务的结果\n2. 禁止重新搜索已有信息\n"
                f"3. 只有全新信息才搜索\n4. 只输出结果，不要创建文件\n"
                + readonly + "\n\n" + sub_rules
            )
        return (
            f"当前子任务: {task_text}\n"
            f"只完成这一个子任务。只输出搜索/整理结果，不要创建文件。"
            + readonly + "\n\n" + sub_rules
        )

    def build_subtask_user(self, user_input: str, task_text: str, idx: int, total: int,
                           is_end_task: bool, task_type: str, conversation_context: str,
                           written_files: list, subtask_mgr) -> str:
        cp = f"{conversation_context}\n\n{'=' * 40}\n\n" if conversation_context else ""
        if is_end_task and idx > 0:
            files = "\n".join(f"  - {f}" for f in written_files) or "  (暂无)"
            return f"{cp}请验证并修复以下已生成的文件:\n{files}\n\n原始需求: {user_input}"
        if task_type == "build" and idx > 0:
            prev = subtask_mgr.read_completed()
            ps = ""
            if prev and prev != "暂无已完成的结果":
                ps = f"\n\n{'=' * 40}\n前置子任务已完成的结果:\n\n{prev[:self._max_tools_compress_len]}\n\n{'=' * 40}\n请基于以上已有信息完成任务。"
            return f"{cp}请完成以下任务: {task_text}\n\n背景信息: {user_input}{ps}"
        if not is_end_task and idx > 0:
            prev = subtask_mgr.read_completed()
            if prev and prev != "暂无已完成的结果":
                return (
                    f"{cp}请完成以下任务: {task_text}\n\n背景信息: {user_input}\n\n"
                    f"{'=' * 40}\n前置子任务已完成的结果:\n\n{prev}\n\n{'=' * 40}\n"
                    f"请基于以上已有信息完成任务。"
                )
            return f"{cp}请完成以下任务: {task_text}\n\n背景信息: {user_input}"
        return f"{cp}请完成以下任务: {task_text}\n\n背景信息: {user_input}"

    def build_skill_prefix(self, task_text: str) -> str:
        matched = self._skill_loader.get_matched_instructions(task_text, max_skills=1)
        if matched:
            return matched + "\n\n---\n【技能已预加载】请严格按照指令执行。"
        meta = self._skill_loader.get_metadata_prompt()
        if meta:
            return (
                "【技能优先规则】\n1. 先检查技能列表匹配\n2. 匹配则调用 invoke_skill\n"
                "3. 无匹配才自行完成\n\n" + meta + "\n\n---\n"
            )
        return ""

    def pick_tools(self, is_end_task: bool, task_type: str, total: int) -> list:
        all_schemas = self._executor.get_all_schemas()
        if is_end_task and total > 1:
            allowed = {"read_file", "edit_file", "write_file", "invoke_skill"}
        elif task_type == "build":
            allowed = {"read_file", "write_file", "edit_file", "grep", "glob", "baidu_search", "invoke_skill"}
        else:
            return all_schemas
        return [s for s in all_schemas if s.get("function", {}).get("name") in allowed]

    # ==================================================================
    # 工具函数
    # ==================================================================

    def _track_usage(self, response: dict):
        usage = response.get("usage", {})
        self._state.token_in += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        self._state.token_out += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)

    @staticmethod
    def _format_tool_calls(tool_calls: list) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tc["id"], "type": "function",
                "function": {"name": tc["name"], "arguments": json.dumps(tc.get("input", {}), ensure_ascii=False)},
            } for tc in tool_calls],
        }

    @staticmethod
    def _compress_tool_results(messages: list, max_chars: int) -> str:
        items = [(m.get("name", "unknown"), m.get("content", "")) for m in messages if m.get("role") == "tool"]
        if not items:
            return "暂无"
        if max_chars < 100:
            return "暂无(压缩空间不足)"
        n = len(items)
        budget = max_chars // max(n, 1)
        formatted = []
        for tool_name, content in items:
            label = f"[{tool_name}] "
            avail = budget - len(label)
            if avail < 50:
                formatted.append(label + "(结果已省略)")
            elif len(content) <= avail:
                formatted.append(label + content)
            else:
                formatted.append(label + content[:avail * 2 // 3] + "\n...(中间已省略)...\n" + content[-(avail // 3):])
        combined = "\n\n".join(formatted)
        if len(combined) <= max_chars:
            return combined
        selected = []
        remaining = max_chars
        skipped = 0
        for item in reversed(formatted):
            needed = len(item) + (2 if selected else 0)
            if needed <= remaining:
                selected.insert(0, item)
                remaining -= needed
            else:
                skipped += 1
        if not selected and formatted:
            last = formatted[-1]
            selected.append(last[:max_chars - 3] + "..." if len(last) > max_chars else last)
            skipped = n - 1
        if skipped > 0:
            selected.insert(0, f"...(已省略前 {skipped} 条早期工具结果)...")
        return "\n\n".join(selected) if selected else "暂无"

    @staticmethod
    def compress_tool_results(messages: list, max_chars: int) -> str:
        """公开静态方法，向后兼容。"""
        return TaskPipeline._compress_tool_results(messages, max_chars)

    def sanitize_result(self, text: str, max_length: int = 0) -> str:
        if not text:
            return text
        lines = [l for l in text.split("\n") if not self._is_garbled_line(l)]
        result = "\n".join(lines)
        if max_length > 0 and len(result) > max_length:
            result = result[:max_length] + "\n...(结果过长已截断)"
        return result

    @staticmethod
    def _is_garbled_line(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if '�' in s:
            return True
        count = len(_GARBLED_CHAR_RE.findall(s))
        return len(s) > 5 and count / len(s) > 0.2

    def _load_sub_agent_prompt(self) -> str:
        return self._prompt_builder.load_sub_agent_prompt(
            max_steps=self._max_steps,
            max_output=self._sub_agent_max_token,
        )
