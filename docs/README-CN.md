# giki

<h4 align="center">

📚 Git 驱动的 LLM Wiki · 像管理代码一样管理知识

</h4>

<p align="center">
<a href="#-为什么需要-giki">为什么</a> •
<a href="#-核心特性">特性</a> •
<a href="#-快速开始">快速开始</a> •
<a href="#-工作原理">原理</a> •
<a href="#-与其他方案对比">对比</a> •
<a href="#-路线图">路线图</a>
</p>

<p align="center">
<a href="https://github.com/MeloMei/giki/actions/workflows/ci.yml"><img src="https://github.com/MeloMei/giki/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/giki-gitwiki/"><img src="https://img.shields.io/pypi/v/giki-gitwiki" alt="PyPI"></a>
<img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

<p align="center">
<a href="../README.md">English</a> · <a href="superpowers/specs/2026-06-30-giki-v0.1-design.md">设计文档</a>
</p>

---

## 🤔 为什么需要 giki？

Andrej Karpathy 提出的 **LLM Wiki** 模式正在改变知识管理——大模型不再在查询时从碎片中临场拼凑答案（"解释器"），而是在摄入时就将知识"编译"成结构化、互相关联的 Wiki 页面（"编译器"）。

然而，现有实现几乎都是**单人本地工具**，缺少两样东西：

1. **团队协作**——无法让团队安全地共建同一本"活百科"
2. **质量门禁**——AI 写知识很快，但谁来审查对不对？未经检查的盲目编译失败率高达 53%～60%（WiCER, 2026）

**giki** 将软件工程的协作方法注入 LLM Wiki：

- 每次 AI 修改都是一条可审计、可回滚的 `git commit`
- 团队在分支上让 LLM 自由编译，通过 Pull Request 审核后汇入主干
- **LLM 自动审查**作为第一道质量防线，在 PR 时自动检查语义矛盾和规则合规性

> 用软件工程的协作方法，做知识的持续集成（Knowledge CI/CD）。

<!-- TODO: 截图——giki ingest 终端输出 -->
<!-- <p align="center"><img src="screenshots/ingest-demo.png" alt="giki ingest 演示" width="700"></p> -->

---

## ✨ 核心特性

**🧠 三步编译流水线**
Analyze（分析文档，提取候选概念）→ Synthesize（生成结构化 Wiki 页面）→ Crosslink（补充双向链接）。滑动窗口分片处理，一本书也能完整编译不截断。

**🛡️ AI 自动审查（PR Review Bot）**
机械检查先跑（零误报）：断链检测、frontmatter 格式校验、index 同步、无关编辑预警。然后逐页 LLM 语义审查，依据 `wiki-rules.md` 的规则逐项评估，输出 `approve` / `comment` / `request-changes`。

**🔄 Git 原生版本控制**
每次 ingest 产出干净 commit（`ingest: observer.md — 3 of 3 pages`）。`--branch` 分支隔离，完整支持 `git diff` / `git revert` / `git rebase`。

**📇 智能索引**
自动维护 `index.md`（分类目录）和 `log.md`（时间线），知识库全貌一目了然，无需手动维护。

**🔗 Obsidian 原生兼容**
标准 YAML frontmatter + `[[wikilink]]` 语法，Obsidian 打开即用，直接浏览知识图谱。

**🔌 多模型可插拔**
支持 Claude、GPT-4/OpenAI、Ollama 及任何 OpenAI 兼容接口。编译 Agent 和审查 Agent 独立配置，可用不同模型交叉验证。

---

## ⚡ 快速开始

### 安装

```bash
pip install giki-gitwiki
```

### 初始化知识库

```bash
mkdir my-kb && cd my-kb && git init
giki init
```

<!-- TODO: 截图——giki init 输出 -->
<!-- <p align="center"><img src="screenshots/init-demo.png" alt="giki init" width="600"></p> -->

这会在当前目录创建 `.giki/config.yaml`、`wiki-rules.md`、`wiki/`、`sources/`、`index.md`、`log.md`。

### 配置 LLM

编辑 `.giki/config.yaml`：

```yaml
llm:
  compile:
    provider: claude          # 或 "openai"（兼容 Ollama 等）
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: openai          # 审查可以用不同模型交叉验证
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
```

设置 API Key：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 导入文档

```bash
cp ~/notes/design-patterns.md sources/
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

<!-- TODO: 截图——giki ingest 显示候选页面和 commit -->
<!-- <p align="center"><img src="screenshots/ingest-demo.png" alt="giki ingest" width="700"></p> -->

giki 会分析源文档、提议 Wiki 页面、通过 LLM 生成正文、补充双向链接、更新 `index.md` 和 `log.md`，最后把所有变更提交到 `wiki/design-patterns` 分支。

### 审查变更

```bash
# 本地审查（HEAD vs main）
giki review

# 审查 GitHub PR 并发布评论
giki review --pr 42 --post

# JSON 输出（CI 友好）
giki review --json
```

<!-- TODO: 截图——giki review 显示审查发现 -->
<!-- <p align="center"><img src="screenshots/review-demo.png" alt="giki review" width="700"></p> -->

### 在 Obsidian 中浏览

```bash
open -a Obsidian wiki/
```

<!-- TODO: 截图——Obsidian 图谱视图展示 wiki 页面和链接关系 -->
<!-- <p align="center"><img src="screenshots/obsidian-graph.png" alt="Obsidian 图谱" width="700"></p> -->

---

## 🧠 工作原理

```
sources/  ──►  [LLM 编译引擎]  ──►  wiki/（结构化知识库）
 原始文档      Analyze → Synthesize       自动更新 index.md + log.md
                 → Crosslink

└──────────────────── Git 管理 ──────────────────────┘
   每次修改产出干净 commit；分支协作走 PR 流程

┌──────────── AI 自动审查（PR 触发）────────────────┐
│  读取 wiki-rules.md → 获取 diff → 机械检查       │
│  → LLM 语义审查 → 发布审查 Comment               │
│  (approve / comment / request-changes)           │
└──────────────────────────────────────────────────┘
```

1. **摄入**——LLM 阅读源文档，提取关键概念和实体
2. **综合**——结合已有知识，生成或更新 Wiki 页面，包含完整的 frontmatter 元数据
3. **关联**——在相关页面间自动创建 `[[双向链接]]`，生成 `## Related` 区块
4. **索引**——同步更新 `index.md`（分类目录）和 `log.md`（时间线）
5. **提交**——所有变更通过 `git commit` 固化
6. **审查**——PR 触发审查 Agent：先跑机械检查，再逐页 LLM 语义审查
7. **协作**——团队基于审查意见讨论、修正、合并

---

## 👥 与其他方案对比

| 特性 | **giki** | 传统 RAG（NotebookLM 等）| 单人 LLM Wiki 工具 | Git Wiki（Gollum 等）|
| :--- | :---: | :---: | :---: | :---: |
| 知识编译 | ✅ 编译式 | ❌ 检索式 | ✅ | ❌ |
| 版本控制 | ✅ Git 全流程 | ❌ | ✅ 单用户 | ✅ |
| 团队协作 | ✅ 分支 + PR | ❌ | ❌ | ✅ |
| AI 审查 | ✅ 机械 + 语义 | ❌ | ❌ | ❌ |
| Obsidian 兼容 | ✅ | ❌ | ✅ | ✅ |
| 智能索引 | ✅ 自动目录 + 时间线 | ❌ | 部分 | ❌ |
| GitHub Actions | ✅ PR 自动审查 | ❌ | ❌ | ❌ |

---

## 📖 命令参考

| 命令 | 说明 |
|---|---|
| `giki init [--with-action]` | 初始化知识库。`--with-action` 同时生成 GitHub Actions 工作流。 |
| `giki ingest <path...> [--branch NAME] [--yes] [--dry-run] [--retry-failed]` | 编译原始文档为 Wiki 页面。 |
| `giki review [--pr N] [--post] [--json] [--base BRANCH]` | 两层审查：机械检查 + LLM 语义审查。 |
| `giki config show \| set <key> <value> \| tips` | 管理 `.giki/config.yaml` 配置。 |

`review` 退出码：`0` = approve 或 comment，`1` = request-changes。

---

## 🗺️ 路线图

- [x] **v0.1 核心**——三步编译流水线、PR Review Bot、Git 原生工作流、Obsidian 兼容
- [x] **v0.1 Dog-fooding**——`kbase/` 目录：giki 用自己的文档作为源材料，演示完整工作流
- [ ] **v0.2 类型化 Wikilink**——`[[requires::X]]`、`[[contradicts::Y]]`，8 种关系类型
- [ ] **v0.2 协作命令**——`giki branch` / `giki pr`，AI 辅助解决合并冲突
- [ ] **v0.3 Web UI**——`giki serve` 启动本地管理页面（D3 知识图谱 + 全文搜索）
- [ ] **v0.3 智能问答**——`giki chat`，BM25 检索 + RAG
- [ ] **v0.3 跨域融合**——多知识库联邦索引（`.wiki-fusion.yaml`）

---

## 🤝 贡献

详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"
pytest -q
```

---

## 📄 许可证

[MIT License](../LICENSE)

<p align="center"><sub>献给那些相信"知识应该持续增值"的人。</sub></p>
