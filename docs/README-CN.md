# giki

知识库的 CI/CD。

<p align="center">
<a href="https://github.com/MeloMei/giki/actions/workflows/ci.yml"><img src="https://github.com/MeloMei/giki/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/giki-gitwiki/"><img src="https://img.shields.io/pypi/v/giki-gitwiki" alt="PyPI"></a>
<img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

<p align="center">
<a href="../README.md">English</a>
</p>

---

你的代码有 CI/CD —— 每次 push 都会跑 lint、测试、review，没问题才能合并进 main。你的知识库也应该有同样的待遇。

大多数 LLM wiki 工具到生成 markdown 就停了。把文档丢给大模型，它吐出 wiki 页面，完事。但你拿到的是一堆没人把关的内容——没有质量检查，没有审计记录，页面之间的矛盾发现不了，幻觉出来的事实也没人挡。团队越依赖这个知识库，风险越大。

giki 把知识当代码管。它通过 LLM 流水线把文档编译成结构化的 wiki 页面，然后对每一次变更跑自动化质量门禁——机械检查零误报，语义审查能抓矛盾、违规和断链。一切都是 git-native 的：每次修改都是一条可回滚、可审计的 commit。

名字来自 "git wiki"。如果说 Karpathy 的 LLM Wiki 定义了编译步骤，giki 加的就是 CI/CD。


## 功能演示

**新建一个知识库：**

```bash
mkdir my-kb && cd my-kb && git init
giki init
```

<p align="center"><img src="screenshots/init-demo.png" alt="giki init 输出" width="650"></p>

这会帮你建好目录结构：配置文件、审查规则（`wiki-rules.md`）、空的 `wiki/` 和 `sources/` 目录，还有自动维护的索引和日志。所有文件自动提交。

**把一篇文档编译成 wiki 页面：**

把 markdown 文件或 PDF 丢进 `sources/`，然后运行：

```bash
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

<p align="center"><img src="screenshots/ingest-demo.png" alt="giki ingest 输出" width="650"></p>

giki 会分析源文档，提议候选页面，通过 LLM 生成结构化内容，在相关概念之间添加双向链接，更新索引，然后把所有改动提交到一个分支上。整个流水线分三步：分析、综合、关联。滑动窗口分片意味着长文档也能完整处理。

**合并之前审查改动：**

```bash
giki review --base main
```

<p align="center"><img src="screenshots/review-demo.png" alt="giki review 输出" width="650"></p>

这是 giki 真正值钱的地方。审查机器人跑两阶段：

1. **机械检查** —— 断链、frontmatter 格式、索引同步、slug 规范、类型化 wikilink 校验。零误报。相当于 linter 能抓到的问题。
2. **语义审查** —— 逐页 LLM 分析，对照你的 `wiki-rules.md` 规则，并带入相邻页面（通过 wikilink 关联）的上下文。然后对所有变更页面做跨页面分析，检测事实矛盾和语义重复。cite 具体规则锚点。

结论分三种：`approve`（通过）、`comment`（建议）、`request-changes`（驳回）。审查机器人和编译引擎可以用不同的 LLM——这是刻意设计的。跨模型交叉验证能发现单一模型可能遗漏的幻觉。

**在 Obsidian 里浏览结果：**

把 Obsidian 指向 `wiki/` 目录，立刻获得完整的图谱视图、反向链接和本地搜索。不需要导出——giki 的 wiki 页面就是标准的 markdown + YAML frontmatter。

<p align="center"><img src="screenshots/obsidian-graph.png" alt="Obsidian 图谱视图" width="650"></p>

**清楚每次运行花了多少钱：**

每次 `giki ingest` 和 `giki review` 结束时都会显示 LLM 用量面板——调用次数、输入/输出 token 数、按内置刊例价估算的美元成本（未收录的模型显示 `n/a`；部分模型定价未知时显示 `>= $X` 作为下限）。每次调用还会追加到本地账本 `.giki-state/usage.jsonl`——通过 MCP 工具（`giki_ingest` / `giki_review`）发起的调用也会同样入账。随时运行 `giki usage` 可以查看累计总量、按命令和按模型的明细，以及最近的运行记录。用 `giki usage --since 2026-07-01` 回答"我这个月花了多少"（或 `--since 30d` 看最近 30 天滚动窗口），加 `--json` 输出机器可读结果，方便 CI 预算检查和脚本化报表。再加 `--budget USD` 就变成预算门禁——例如 `giki usage --since 30d --budget 5`，当月估算花费超过 $5 时以非零码退出。门禁只比较定价已知的模型花费，定价未知的调用会被标记但不计入。账本是本地文件，在 CI 里需要通过 cache 或 artifact 持久化 `.giki-state/`，门禁才能看到历史花费。

## 工作原理

1. 原始文档放进 `sources/`
2. giki 的 LLM 引擎提取概念，生成结构化的 wiki 页面
3. 自动在相关页面之间添加双向链接
4. `index.md`（分类目录）和 `log.md`（时间线）自动更新
5. 所有改动提交为一条干净的 git commit
6. 准备好了就跑 `giki review`，合并之前检查有没有问题

整个东西就是一个 git 仓库。版本历史、分支、审计记录天然就有——没有私有数据库，没有供应商锁定。你的知识库是可移植、可 diff 的。

## 开始使用

**用 AI 编程助手？** 把这句话贴给你的 agent：

> 请阅读 https://github.com/MeloMei/giki/blob/main/SETUP.md 并按照里面的步骤帮我把 giki 项目克隆到本地并配置好所有环境。

或手动安装：

```bash
pip install giki-gitwiki
```

初始化知识库，然后在 `.giki/config.yaml` 里配置你的 LLM：

```yaml
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: openai
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
```

支持 Claude、GPT、Ollama，以及任何 OpenAI 兼容接口。

## 命令

| 命令 | 作用 |
|---|---|
| `giki init [--with-action]` | 初始化知识库。加 `--with-action` 会生成 GitHub Actions 自动审查。 |
| `giki ingest <path...> [--branch NAME] [--yes]` | 把源文档编译成 wiki 页面。 |
| `giki review [--base BRANCH] [--pr N] [--json]` | 两阶段审查：机械检查 + LLM 语义分析。 |
| `giki lint [--fix]` | 检查 wiki 健康：断链、孤立页、frontmatter 问题。`--fix` 自动修复。 |
| `giki usage [--root PATH] [--since DATE\|Nd] [--json] [--budget USD]` | 查看本地账本中的累计 LLM 用量和估算成本。`--budget` 超预算时非零退出。 |
| `giki config show \| set <key> <value>` | 查看或修改配置。 |
| `giki mcp-serve` | 启动 MCP 服务器，供平台集成。 |

## MCP 服务器

giki 可以作为 MCP（Model Context Protocol）服务器运行，让你直接在 Claude Code、QoderWork、Codex 或任何 MCP 兼容平台里使用。平台内置的 LLM 负责编排工具调用；流水线实际调用的是你 `.giki/config.yaml` 里配置的 LLM——按该 endpoint 计费，并同样计入用量账本。

```bash
pip install giki-gitwiki
```

然后在平台的 MCP 配置里添加：

```json
{
  "mcpServers": {
    "giki": {
      "command": "giki",
      "args": ["mcp-serve"]
    }
  }
}
```

重启后，让平台初始化知识库、导入文档、审查改动就行。

## 贡献

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"
pytest -q
```

详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

| 方案 | 知识处理方式 | 版本管理能力 | 协作模式 | 内容校验机制 | 界面形态 | 知识库互通 | 笔记工具兼容 |
|----------|--------------|--------------|----------|--------------|----------|------------|--------------|
| giki | ✅ 编译式 | ✅ Git 全生命周期管理 | ✅ PR/分支协作 | ✅ 语义分析+规则校验 | ✅ 本地无依赖运行 | ✅ 联合索引互通 | ✅ Obsidian 原生兼容 |
| 传统 RAG 方案 | ❌ 检索式查询 | ❌ 无版本管理 | ❌ 不支持团队协作 | ❌ 无自动审查 | ✅ 云端访问 | ❌ 无法跨库融合 | ❌ 不兼容 Obsidian |
| 单人 LLM Wiki  | ✅ 支持知识编译 | ✅ 单用户版本管理 | ❌ 无团队协作能力 | ❌ 无自动校验 | ⚠️ 部分功能支持 | ❌ 无法跨库互通 | ✅ 兼容 Obsidian |
| Gollum | ❌ 无知识编译 | ✅ Git 版本控制 | ✅ 团队协作模式 | ❌ 无自动审查 | ✅ Web 界面 | ❌ 不支持跨库融合 | ✅ 兼容 Obsidian |


## 许可证

MIT
