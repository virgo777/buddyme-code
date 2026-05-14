---
name: emergence-paper-orchestra
title: Emergence PaperOrchestra (涌现 论文乐队)
description: 基于 PaperOrchestra 方法论的高严谨性、多 Agent 学术写作框架。
version: 1.0.0
homepage: https://gitee.com/bubble-universe/emergence-paper-orchestra
repository: https://gitee.com/bubble-universe/emergence-paper-orchestra
tags: [writing, research, academic, paper, paper-orchestra, emergence-science, chinese]
---

# Emergence PaperOrchestra Skill

这项技能将原始想法和非结构化数据转化为高严谨性、可直接提交的学术文稿。它作为一个 **研究伙伴**，主动澄清细节、进行批判并确保内容基于可验证的证据。

## 1. 核心工作流（模块化）

该过程专为在可能“狭窄”的即时通讯渠道（线性对话）中进行 **人机协作 (Human-in-the-Loop)** 而设计。

### 第 0 阶段：交互式访谈（骨架搭建）
Agent 启动 **访谈模式** 以捕获隐性知识。用户的每一个回答都将用于自动更新 `idea.md`。
- **批判人设**：Agent 扮演 **研究伙伴**，识别原始输入中的逻辑跳跃或缺失的数据点。

### 第 1 阶段：制度化规划（提纲 Agent）
将所有输入综合到一个 **JSON 主计划** 中（存储在 `metadata.json`）。

### 第 2 阶段：文献策略（搜索 Agent）
- **宏观搜索**：获取基础背景。
- **微观搜索**：通过 ID (DOI/arXiv) 进行竞品基准分析和引用验证。

### 第 3 阶段：模块化撰写（撰写 Agent）
严格按照章节构建并存入 `sections/` 目录，以防止上下文漂移。

### 第 4 阶段：同行细化（细化 Agent）
进行批判性评估，重点关注“数字字面主义 (Numerical Literalism)”和“零幻觉 (Zero Hallucination)”合规性。

---

## 2. Agent 角色

| 角色 | 人设目标 | 推荐系统提示词挂钩 |
| :--- | :--- | :--- |
| **总调度 (Orchestrator)** | 全局一致性 | "维护主计划。确保第 4 节回答了第 1 节中的假设。" |
| **搜索 Agent** | 验证与发现 | "通过精确查询记录前人工作的确切局限性。" |
| **章节撰写人** | 高密度创作 | "采用密集、客观、技术性的语气。不使用华丽辞藻。" |
| **评审员 (Reviewer)** | 批判性评估 | "扮演严苛的会议评审员。识别每一项没有证据支持的主张。" |
| **合作伙伴 (Partner)** | 批判与细化 | "挑战用户的假设。如果一个想法很模糊，请索要数据支持的细节。" |

---

## 3. 最佳实践

- **“访谈-持久化”循环**：通过自然对话构建 `idea.md` 作为事实来源。
- **脚手架目录**：使用提供的 `scaffold.sh` 初始化环境：
  - `idea.md`：方法论和用户提供的上下文。
  - `metadata.json`：主计划和经验证的引用库。
  - `content.md`：组装后的最终输出。
- **验证循环**：在将候选论文添加到 BibTeX 库之前，务必通过 ID (Semantic Scholar/DOI) 验证它们。

---

## 4. 署名与引用

如果您使用此框架进行科学发表，请引用原 PaperOrchestra 团队：

```bibtex
@misc{song2026paperorchestramultiagentframeworkautomated,
      title={PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing}, 
      author={Yiwen Song and Yale Song and Tomas Pfister and Jinsung Yoon},
      year={2026},
      eprint={2604.05018},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.05018}, 
}
```
