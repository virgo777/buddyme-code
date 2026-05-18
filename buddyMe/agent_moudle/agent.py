"""
agent.py — 多模型智能体（状态管理 + 生命周期）

职责:
    - 模型客户端管理（创建、切换、关闭）
    - 工具注册与注销、Skill 加载
    - 用户记忆与对话持久化
    - System Prompt 构建、工作空间初始化
    - 命令系统拦截

任务执行管线已提取到 task_runner.py。
"""

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from buddyMe.agent_moudle.task_runner import TaskRunner
from buddyMe.initspace.skill_loader import SkillLoader
from buddyMe.llm_moudle import basic_llm, model_config
from buddyMe.session.conversation_logger import ConversationLogger
from buddyMe.session.message_history import MessageHistory
from buddyMe.session.subtasks_manager import SubtasksManager
from buddyMe.utils.paths import get_package_dir, get_user_data_dir, get_workspace_dir, resolve_data_dir

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AgentMain:
    """统一多模型 Agent"""

    @classmethod
    def supported_models(cls) -> list:
        return basic_llm.list_models()

    @classmethod
    def _create_client(cls, model_name: str):
        return basic_llm.create_client(model_name)

    def __init__(
        self,
        model_name: str = "glm",
        system_prompt: Optional[str] = None,
        data_dir: Optional[str] = None,
        workspace_dir: Optional[str] = None,
    ):
        self.model_name = model_name
        _args = model_config.ModelConfig.get_args()

        self.max_steps = 11
        self.max_messages_length = 20
        self._context_summary_max_chars = 6000

        # 消息历史（抽离到 MessageHistory）
        self._message_history = MessageHistory(max_messages_length=self.max_messages_length)

        # LLM 客户端
        self._client = self._create_client(model_name)
        self._sub_client = basic_llm.create_client("sub_agent_code_plan")
        self._agent_max_token = self._client.max_tokens
        self._sub_agent_max_token = self._agent_max_token // 4

        # 目录系统
        self._PACKAGE_DIR = get_package_dir()
        self._USER_DATA_DIR = get_user_data_dir()
        if data_dir:
            self._DATA_DIR = resolve_data_dir(data_dir)
        else:
            self._init_user_workspace()
            self._DATA_DIR = self._USER_DATA_DIR
        self._PROJECT_ROOT = self._DATA_DIR

        # 工作空间
        if workspace_dir:
            self._WORKSPACE_DIR = Path(workspace_dir).resolve()
        else:
            self._WORKSPACE_DIR = get_workspace_dir()
        self._WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self._DEFAULT_OUTPUT_DIR = self._WORKSPACE_DIR

        # 工具执行器
        from buddyMe.anthropic_standard import basic_anthropic_tool
        self._executor = basic_anthropic_tool.ToolExecutor()
        self._register_tools()

        # Skill
        user_skills = self._DATA_DIR / "skill_library" / "skills"
        pkg_skills = self._PACKAGE_DIR / "skill_library" / "skills"
        self._skill_loader = SkillLoader(skill_dirs=[str(user_skills), str(pkg_skills)])

        from buddyMe.tool_moudle.invoke_skill_tool import InvokeSkillTool
        invoke_skill = InvokeSkillTool(self._skill_loader)
        invoke_skill.set_model_name(self.model_name)
        self._executor.register(invoke_skill)

        # 对话持久化（必须先于 _memory，因为 MemoryManager 依赖它）
        self.conv_logger = ConversationLogger(
            os.path.join(self._PROJECT_ROOT, "initspace", "memorys", "conversation_log.json")
        )

        # 用户记忆（必须先于 _rebuild_system_prompt，因为 system prompt 注入记忆文本）
        from buddyMe.memory.manager import MemoryManager
        from buddyMe.memory.store import MemoryStore
        _brain_path = os.path.join(self._PROJECT_ROOT, "initspace", "brain", "USER.md")
        _conv_log_path = os.path.join(self._PROJECT_ROOT, "initspace", "memorys", "conversation_log.json")
        self._memory_store = MemoryStore(
            _brain_path, conversation_log_path=_conv_log_path, client=self._sub_client
        )
        self._memory = MemoryManager(store=self._memory_store, conv_logger=self.conv_logger)

        # System Prompt（依赖 _executor + _skill_loader + _memory）
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self._rebuild_system_prompt()

        # 子任务文件管理（抽离到 SubtasksManager）
        self._subtask_mgr = SubtasksManager(
            file_path=str(self._PROJECT_ROOT / "initspace" / "memorys" / "subtask_results.json"),
            max_result_len=self._sub_agent_max_token,
        )
        self._last_cmd_should_exit = False

        # 上下文压缩（新功能：长对话中段摘要）
        from buddyMe.context.compressor import ContextCompressor
        self._compressor = ContextCompressor(keep_first=2, keep_last=5)

        # 任务执行引擎（依赖注入，消除 self._a 反向通道）
        from buddyMe.agent_moudle.task_pipeline import TaskPipeline
        from buddyMe.session.state import SessionState
        self._state = SessionState()
        _args = model_config.ModelConfig.get_args()

        self._pipeline = TaskPipeline(
            client=self._client,
            sub_client=self._sub_client,
            executor=self._executor,
            skill_loader=self._skill_loader,
            memory_store=self._memory_store,
            workspace_dir=self._WORKSPACE_DIR,
            output_dir=self._DEFAULT_OUTPUT_DIR,
            prompt_builder=self._prompt_builder,
            state=self._state,
            system_prompt=self.system_prompt,
            max_steps=self.max_steps,
            max_messages_length=self.max_messages_length,
            max_search_calls=_args["MAX_SEARCH_CALLS"],
            max_tools_compress_len=_args["MAX_TOOLS_COMPRESS_LEN"],
            max_subtask_result_len=self._sub_agent_max_token,
            agent_max_token=self._agent_max_token,
            sub_agent_max_token=self._sub_agent_max_token,
            compressor=self._compressor,
        )
        self._runner = TaskRunner(
            pipeline=self._pipeline,
            subtask_mgr=self._subtask_mgr,
            state=self._state,
            conv_logger=self.conv_logger,
            skill_loader=self._skill_loader,
            client=self._client,
            project_root=str(self._PROJECT_ROOT),
            context_summary_max_chars=self._context_summary_max_chars,
            agent_max_token=self._agent_max_token,
        )

        # 命令系统
        from buddyMe.cmd_library import create_registry
        self.cmd_registry = create_registry()

    # ==================================================================
    # System Prompt
    # ==================================================================

    def _rebuild_system_prompt(self):
        from buddyMe.context.prompt_builder import PromptBuilder
        brain_dir = str(self._PROJECT_ROOT / "initspace" / "brain")
        self._prompt_builder = PromptBuilder(brain_dir=brain_dir)
        memory_text = self._memory.prefetch("")
        self.system_prompt = self._prompt_builder.build(
            tool_schemas=self._executor.get_all_schemas(),
            skill_metadata=self._skill_loader.get_metadata_prompt(),
            memory_prompt=memory_text,
        )

    def reload_skills(self):
        added = self._skill_loader.reload()
        if added > 0:
            self._rebuild_system_prompt()
            logger.info("[Agent] system prompt 已刷新，新增 %d 个 Skill", added)
        return added

    # ==================================================================
    # 工具管理
    # ==================================================================

    def _register_tools(self):
        try:
            from buddyMe.tool_moudle.bash_tool import (
                BashTool, EditFileTool, GlobTool, GrepTool,
                ReadFileTool, WriteFileTool,
            )
            for tool in [BashTool(), ReadFileTool(), WriteFileTool(), EditFileTool(), GrepTool(), GlobTool()]:
                tool.set_model_name(self.model_name)
                self._executor.register(tool)
        except ImportError as e:
            logger.warning("[Agent] 无法导入工具模块: %s", e)

    def register_tool(self, tool):
        tool.set_model_name(self.model_name)
        self._executor.register(tool)
        logger.info("[Agent] 后注册工具: %s", tool.name)

    def unregister_tool(self, tool_name: str) -> bool:
        ok = self._executor.unregister(tool_name)
        if ok:
            logger.info("[Agent] 已注销工具: %s", tool_name)
        return ok

    def _get_tool_schemas(self) -> List[Dict]:
        return self._executor.get_all_schemas()

    # ==================================================================
    # LLM
    # ==================================================================

    def call_llm_sync(self, system_prompt: str, user_message: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            response = asyncio.run(self._client.chat(messages=messages))
            texts = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
            return "\n".join(texts).strip()
        except Exception as e:
            logger.error("[Agent] call_llm_sync 失败: %s", e)
            return ""

    # ==================================================================
    # 工作空间
    # ==================================================================

    def _init_user_workspace(self):
        dst = self._USER_DATA_DIR
        src = self._PACKAGE_DIR
        skill_dst = os.path.join(dst, "skill_library", "skills")
        if os.path.exists(skill_dst) and os.listdir(skill_dst):
            return
        logger.info("[初始化] 首次运行，部署用户数据到 %s", dst)
        for rel in ["initspace", "skill_library"]:
            src_dir = os.path.join(src, rel)
            dst_dir = os.path.join(dst, rel)
            if os.path.exists(src_dir):
                self._copy_tree(src_dir, dst_dir)
        logger.info("[初始化] 部署完成")

    @staticmethod
    def _copy_tree(src_dir: str, dst_dir: str):
        os.makedirs(dst_dir, exist_ok=True)
        for item in os.listdir(src_dir):
            s = os.path.join(src_dir, item)
            d = os.path.join(dst_dir, item)
            if os.path.isdir(s):
                AgentMain._copy_tree(s, d)
            elif os.path.isfile(s) and not os.path.exists(d):
                shutil.copy2(s, d)

    # ==================================================================
    # 对话管理
    # ==================================================================

    def add_message(self, role: str, content: str):
        self._message_history.add(role, content)

    def reset(self):
        self._message_history.reset()

    # ==================================================================
    # 模型切换
    # ==================================================================

    def close(self):
        self._memory.on_session_end()
        for attr in ("_client", "_sub_client"):
            client = getattr(self, attr, None)
            if client and hasattr(client, "close"):
                try:
                    client.close()
                except Exception:
                    pass

    def switch_model(self, new_model: str):
        if new_model == self.model_name:
            return
        if self._client and hasattr(self._client, "close"):
            try:
                self._client.close()
            except Exception:
                pass
        self._client = self._create_client(new_model)
        old, self.model_name = self.model_name, new_model
        self._agent_max_token = self._client.max_tokens
        self._sub_agent_max_token = self._agent_max_token // 4
        if hasattr(self, "_executor"):
            for tool in self._executor._tools.values():
                if hasattr(tool, "set_model_name"):
                    tool.set_model_name(new_model)
        logger.info("[Agent] 模型已切换: %s -> %s", old, new_model)

    # ==================================================================
    # 执行入口
    # ==================================================================

    def invoke(self, user_input: str) -> str:
        cmd_result = self.cmd_registry.dispatch(user_input, self)
        if cmd_result is not None:
            self._last_cmd_should_exit = getattr(cmd_result, 'should_exit', False)
            return cmd_result.message

        self._state.reset_episode()
        start_time = time.time()

        # Memory prefetch: 预制相关记忆注入 system prompt
        memory_text = self._memory.prefetch(user_input)
        if memory_text:
            self.system_prompt = self._prompt_builder.build(
                tool_schemas=self._executor.get_all_schemas(),
                skill_metadata=self._skill_loader.get_metadata_prompt(),
                memory_prompt=memory_text,
            )
            self._pipeline._system_prompt = self.system_prompt

        result = asyncio.run(self._runner.run(user_input))

        cost = round(time.time() - start_time, 2)

        if self._state.written_files:
            file_list = "\n".join(f"  - {p}" for p in self._state.written_files)
            result += f"\n\n{'=' * 40}\n项目已生成到:\n{file_list}"

        if self._state.used_skills:
            logger.info(
                "[Skill] 本次任务共使用 %d 个技能: %s",
                len(self._state.used_skills), ", ".join(self._state.used_skills),
            )

        self.conv_logger.log(
            query=user_input, response=result, model=self.model_name,
            tool_calls=self._state.used_tools,
            extra={
                "execute_cost_time": cost,
                "tool_call_count": len(self._state.used_tools),
                "used_skills": self._state.used_skills,
                "subtask_count": len(self._state.last_episode),
                "episode": self._state.last_episode,
            },
        )

        # Memory sync: 同步本轮对话到记忆
        self._memory.sync_turn(user_input, result[:500])

        for attr in ("_client", "_sub_client"):
            c = getattr(self, attr, None)
            if c and hasattr(c, "close"):
                try:
                    c.close()
                except Exception:
                    pass
        return result

    # ==================================================================
    # 向后兼容属性
    # ==================================================================

    @property
    def messages(self) -> List[Dict[str, Any]]:
        return self._message_history.get_messages()

    @messages.setter
    def messages(self, value: List[Dict[str, Any]]):
        self._message_history.replace_all(value)

    @property
    def _subtask_file(self) -> str:
        return self._subtask_mgr.file_path

    @property
    def user_memory(self):
        """向后兼容：返回 MemoryStore 实例供命令处理器使用。"""
        return self._memory_store

    @property
    def _token_in(self) -> int:
        return self._state.token_in

    @property
    def _token_out(self) -> int:
        return self._state.token_out

    @property
    def _used_tools(self) -> list:
        return self._state.used_tools

    @property
    def _used_skills(self) -> list:
        return self._state.used_skills

    @property
    def _written_files(self) -> list:
        return self._state.written_files

    @property
    def _last_episode(self) -> list:
        return self._state.last_episode


# ==============================================================================
# 主程序
# ==============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Agent — 多模型智能体 + Skill")
    print("输入 /help 查看可用命令")
    print("=" * 60)
    agent = AgentMain(model_name="glm")
    from buddyMe.tool_moudle.baidu_search_tool import BaiduSearchTool
    agent.register_tool(BaiduSearchTool())
    while True:
        inp = input("query: ")
        reply = agent.invoke(inp)
        if reply:
            print(reply)
