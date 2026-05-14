# Emergence PaperOrchestra Skill

一种面向 Agent 经济的高严谨性、多 Agent 学术写作框架。由 **涌现科学 (Emergence Science)** 开发，该技能实现了 **PaperOrchestra** (arXiv:2604.05018v1) 方法论，用于自主文稿生成和专业创作。

## 概述

与标准的 LLM 撰写不同，**Emergence PaperOrchestra** 扮演的是 **研究合作伙伴** 的角色。它将写作过程分解为专门的角色——总调度、搜索 Agent、章节撰写人和评审员——以确保：
- **零幻觉 (Zero Hallucination)**：严格的“数字字面主义”和“数据链式验证”。
- **学院派严谨**：基于 Semantic Scholar/DOI 验证的引用库。
- **Agent 开发者体验 (Agent-DX)**：针对模块化解析和长期项目持久性进行了优化。

## 核心特性

- **多轮访谈**：通过对话式脚手架捕获人类的隐性知识。
- **模块化撰写**：逐章构建，以保持高语义密度。
- **便携式脚手架**：提供的 Shell 脚本可用于在任何 Ubuntu/macOS 虚拟机上初始化环境。

## 使用方法

使用提供的脚手架初始化新项目：
```bash
./scripts/scaffold.sh "我的研究项目"
```

然后，调用配备 **PaperOrchestra 协议** 的 Agent 开始第 0 阶段访谈。

## 署名

本框架是 PaperOrchestra 方法论的一种实现。如果您将其用于学术目的，请引用：

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

---
© 2026 涌现科学 (Emergence Science). 为自主学术发现的未来而建。
