# buddyMe Code — 多模型 AI 智能体编程框架

一个支持多模型切换、工具调用和技能系统的 Python AI Agent 框架。提供命令行交互界面，可自动拆解复杂任务并分步执行。

支持 6 大 LLM 供应商运行时热切换。分层人格、三级技能加载、心跳记忆，为需要灵活性的开发者而生。

支持多模型热切换 · 工具调用 · 技能系统 · 持久记忆 · 定时任务

[Blog](http://49.235.53.176/) 
</div>

---

## 项目简介

buddyMe 是一个 Python 实现的多模型 AI 智能体框架。它能够将复杂任务自动拆解为子任务，逐一规划、执行、验证，并合并结果。内置 25+ 技能、8 个工具、完整的记忆系统和定时调度能力，可作为编程助手或通用任务代理使用。

<div style="background-color: #f8f9fa; padding: 18px 22px; border-radius: 8px; margin: 28px 0; border-left: 4px solid #e67e22;">
  <p style="margin: 0 0 14px 0; line-height: 1.6;">欢迎访问 <a href="http://49.235.53.176/" style="color: #2563eb; text-decoration: none;">BuddyMe Blog</a> 阅读最新文章与技术分享。</p>
  <p style="color: #e67e22; font-size: 1.1em; font-weight: bold; margin: 0 0 12px 0;">📚 更新推荐阅读</p>
  <ul style="margin: 0; padding-left: 22px; line-height: 1.9;">
    <li><a href="http://49.235.53.176/blog/heartbeat-and-loop-skill-engine-deep-dive" style="color: #2563eb; text-decoration: none;">buddyMe 心跳系统与 Loop 引擎：让 AI 自己干活，还不花钱</a></li>
    <li><a href="http://49.235.53.176/blog/buddyme" style="color: #2563eb; text-decoration: none;">技术深度：buddyMe 框架任务拆解的 "盲拆" 问题与技能感知优化方案</a></li>
    <li><a href="http://49.235.53.176/blog/react-plan-and-execute-reflection" style="color: #2563eb; text-decoration: none;">ReAct、Plan-and-Execute 与 Reflection 的本质差异与落地指南</a></li>
  </ul>
</div>

## 核心特性

- **多模型支持** — 统一接口调用智谱 GLM、DeepSeek、百度千帆 ERNIE、小米 MiMo、阿里 Qwen 等国产大模型
- **双协议适配** — 自动检测 OpenAI / Anthropic 协议，对上层业务透明
- **任务管线** — 三阶段执行管线：上下文构建 → 任务规划 → 分步执行与结果合并
- **Skill 技能系统** — 内置 20+ 技能（前端设计、文章写作、学术论文、市场调研、天气查询等），支持热加载和动态注册
- **工具生态** — 文件读写编辑、代码搜索（grep/glob）、Bash 执行、百度搜索、Skill 调用
- **持久化记忆** — 用户画像（USER.md）、对话日志、记忆摘要，支持跨会话连续性
- **命令系统** — `/help`、`/model`、`/skills`、`/memory` 等内置命令，支持别名和分类

## 快速开始

### 安装

```bash
pip install -e .
```

### 运行

```bash
# CLI 模式（带 Rich spinner）
buddyme

# 或模块方式
python -m buddyMe
```

### 设置环境变量

```bash
# Windows PowerShell
$env:BUDDYME_MODEL = "deepseek"

# macOS / Linux
export BUDDYME_MODEL="deepseek"
```

首次运行时会自动部署用户数据目录（`initspace/` + `skill_library/`）。

## 支持的模型

| 模型标识 | 实际模型 | 协议 | 提供商 |
|---------|---------|------|-------|
| `glm` | GLM-5.1 | OpenAI | 智谱 |
| `glm_code_plan` | GLM-5.1 | Anthropic | 智谱 |
| `deepseek` | DeepSeek-V4-Pro | OpenAI | DeepSeek |
| `deepseek_code_plan` | DeepSeek-V4-Pro | Anthropic | DeepSeek |
| `ernie` | ERNIE-5.1 | OpenAI | 百度千帆 |
| `xiaomi` | MiMo-V2-Pro | OpenAI | 小米 |
| `qwen` | Qwen3.6-Plus | OpenAI | 阿里通义 |
| `sub_agent_code_plan` | GLM-4.7 | Anthropic | 智谱（子任务用） |

模型配置通过各自的 API Key 连接，使用前需在 `model_config.py` 中填入对应密钥。

## 架构概览

```
buddyMe/
├── main.py              # 启动入口（python -m buddyMe）
├── cli.py               # Rich CLI（buddyme 命令）
├── agent_moudle/        # Agent 核心与任务管线
│   ├── agent.py         # AgentMain — 状态管理、生命周期
│   ├── task_runner.py   # 任务执行管线编排
│   ├── task_pipeline.py # 三阶段管线（规划→执行→合并）
│   └── todo_manager.py  # 子任务管理器
├── llm_moudle/          # LLM 客户端层
│   ├── basic_llm.py     # 统一调用接口
│   └── model_config.py  # 模型配置（api_key/base_url/max_tokens）
├── anthropic_standard/  # 协议适配层
│   ├── basic_anthropic_client.py  # 客户端基类（OpenAI/Anthropic）
│   ├── basic_anthropic_tool.py    # 工具执行器
│   ├── unified_client.py         # 统一客户端（自动选择协议）
│   └── anthropic_code_plan_base.py
├── context/             # System Prompt 构建
│   ├── prompt_builder.py   # 按层次组装 System Prompt
│   ├── compressor.py       # 长对话中段压缩
│   └── brain_loader.py     # Brain 文件加载
├── memory/              # 记忆系统
│   ├── store.py         # 记忆存储（USER.md + 对话日志）
│   ├── manager.py       # 记忆生命周期管理
│   ├── extractor.py     # 记忆提取
│   └── provider.py      # 记忆提供者
├── session/             # 会话管理
│   ├── state.py              # 会话状态
│   ├── message_history.py    # 消息历史
│   ├── conversation_logger.py # 对话持久化
│   ├── subtasks_manager.py   # 子任务结果管理
│   └── todo_manager.py
├── tool_moudle/         # 工具模块
│   ├── bash_tool.py         # Bash / Read / Write / Edit / Grep / Glob
│   ├── baidu_search_tool.py # 百度搜索
│   └── invoke_skill_tool.py # Skill 调用
├── cmd_library/         # 命令系统
│   ├── registry.py         # 命令注册与分发
│   ├── base.py             # 命令基类
│   └── builtin/            # 内置命令（system/memory/skill）
├── initspace/           # 初始化数据
│   ├── brain/           # Brain 文件（AGENT.md/SOUL.md/IDENTITY.md/USER.md）
│   ├── memorys/         # 记忆文件（对话日志/摘要/子任务结果）
│   └── skill_loader.py  # Skill 加载器
├── skill_library/       # 技能库（20+ Skill）
│   └── skills/          # 各类 Skill 定义
└── utils/               # 工具函数（路径、原子操作）
```

### 执行流程

```
用户输入 → 命令拦截(/cmd) → Memory预取 → System Prompt构建
  → 任务规划(主LLM拆解子任务) → 分步执行(子Agent + 工具调用)
  → 结果合并 → 对话持久化 → 记忆同步 → 返回结果
```

### Skill 系统

内置技能覆盖多个领域，支持按需调用：

| 类别 | 技能 |
|------|------|
| 前端开发 | frontend-design、frontend-patterns、frontend-slides |
| 后端开发 | backend-patterns、api-design、content-hash-cache-pattern |
| 内容创作 | article-writing、market-research |
| 学术写作 | emergence-paper-orchestra（PaperOrchestra 方法论） |
| 开发流程 | coding-standards、code-reviewer、tdd-guide、continuous-learning |
| 工具集成 | markitdown（文件格式转换）、qqmail（QQ 邮箱）、weather-skill（天气） |
| Agent 优化 | autonomous-loops、strategic-compact、search-first、verification-loop、iterative-retrieval |

Skill 存放在 `skill_library/skills/` 下，可通过 `/skill` 命令热加载新 Skill。

### 命令系统

所有命令以 `/` 开头：

| 命令 | 说明 |
|------|------|
| `/help` | 查看所有命令 |
| `/model [name]` | 查看或切换模型 |
| `/models` | 列出所有可用模型 |
| `/skills` | 列出已加载的 Skill |
| `/skill reload` | 热加载 Skill |
| `/memory show` | 查看记忆 |
| `/memory update` | 更新记忆 |
| `/memory history` | 查看对话历史 |
| `/reset` | 重置会话 |
| `/clear` | 清屏 |
| `/exit` / `/quit` | 退出 |

## 依赖

- Python >= 3.9
- httpx（HTTP 客户端）
- rich（CLI spinner）

## 目录说明

| 路径 | 用途 |
|------|------|
| `buddyMe/` | 源码包 |
| `buddyMe/initspace/` | 首次运行自动复制的用户数据（Brain/记忆/对话日志） |
| `dist/` | 构建产物 |
| `pyproject.toml` | 项目配置与依赖 |
