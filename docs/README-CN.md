# giki

Git 驱动的 LLM Wiki -- 像管理代码一样管理知识。

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
Andrej Kaparthy 提出的 LLM WIKI 已经成为知识管理新范式，让知识库建设从基于向量的 RAG 变成了大模型自己驱动的知识编译
但是，团队知识库需要安全的共建和标准的质量门禁

如果把文档丢给 LLM，它吐出 wiki 页面。但是到此为止，拿到一堆 markdown，却没办法防范低质量知识注入，没办法让团队协作维护，出了问题也没有追溯记录。

giki 取名源自 git wiki 
把软件工程的 git 管理放进知识库建设，把知识当代码来管。

每次 AI 修改都是一条可回滚可审计的 git commit。
团队在分支上工作，通过 PR 合并。
一个像 github 自动审查的机制会在任何改动进入主干之前，检查断链、语义矛盾和规则违规，就像知识库的 CI/CD

| 方案 | 知识处理方式 | 版本管理能力 | 协作模式 | 内容校验机制 | 界面形态 | 知识库互通 | 笔记工具兼容 |
|----------|--------------|--------------|----------|--------------|----------|------------|--------------|
| giki | ✅ 编译式 | ✅ Git 全生命周期管理 | ✅ PR/分支协作 | ✅ 语义分析+规则校验 | ✅ 本地无依赖运行 | ✅ 联合索引互通 | ✅ Obsidian 原生兼容 |
| 传统 RAG 方案 | ❌ 检索式查询 | ❌ 无版本管理 | ❌ 不支持团队协作 | ❌ 无自动审查 | ✅ 云端访问 | ❌ 无法跨库融合 | ❌ 不兼容 Obsidian |
| 单人 LLM Wiki  | ✅ 支持知识编译 | ✅ 单用户版本管理 | ❌ 无团队协作能力 | ❌ 无自动校验 | ⚠️ 部分功能支持 | ❌ 无法跨库互通 | ✅ 兼容 Obsidian |
| Gollum | ❌ 无知识编译 | ✅ Git 版本控制 | ✅ 团队协作模式 | ❌ 无自动审查 | ✅ Web 界面 | ❌ 不支持跨库融合 | ✅ 兼容 Obsidian |

## 功能演示

**新建一个知识库：**

```bash
mkdir my-kb && cd my-kb && git init
giki init
```

<p align="center"><img src="screenshots/init-demo.png" alt="giki init 输出" width="650"></p>

这会帮你建好目录结构：配置文件、审查规则、空的 `wiki/` 和 `sources/` 目录，还有自动维护的索引和日志。

**把一篇文档编译成 wiki 页面：**

把 markdown 文件（或 PDF）丢进 `sources/`，然后运行：

```bash
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

<p align="center"><img src="screenshots/ingest-demo.png" alt="giki ingest 输出" width="650"></p>

giki 会分析源文档，提议候选页面，通过 LLM 生成内容，在相关概念之间添加双向链接，更新索引，然后把所有改动提交到一个分支上。整个流水线分三步：分析、综合、关联。滑动窗口分片意味着长文档也能完整处理，不会被截断。

**合并之前审查改动：**

```bash
giki review --base main
```

<p align="center"><img src="screenshots/review-demo.png" alt="giki review 输出" width="650"></p>

审查机器人先跑机械检查（断链、frontmatter 格式、索引同步）——这些检查零误报。然后逐页做语义审查，对照你的 `wiki-rules.md` 规则逐条评估。结论分三种：`approve`（通过）、`comment`（建议）、`request-changes`（驳回）。

**在 Obsidian 里浏览结果：**

把 Obsidian 指向 `wiki/` 目录，立刻获得完整的图谱视图、反向链接和本地搜索。不需要导出。

<p align="center"><img src="screenshots/obsidian-graph.png" alt="Obsidian 图谱视图" width="650"></p>

**启动本地 Web UI：**

```bash
giki serve
```

<p align="center"><img src="screenshots/serve-ui.png" alt="giki serve Web UI" width="650"></p>

D3 知识图谱可视化、全文搜索、Markdown 页面查看器——全在浏览器 `localhost:8080`。纯 Python stdlib，无额外依赖。

**向知识库提问：**

```bash
giki chat "观察者模式有什么应用场景？"
```

<p align="center"><img src="screenshots/chat.png" alt="giki chat 问答" width="650"></p>

BM25 检索相关页面，LLM 基于 wiki 内容生成回答。

## 工作原理

核心流程：

1. 原始文档放进 `sources/`
2. giki 的 LLM 引擎提取概念，生成结构化的 wiki 页面
3. 自动在相关页面之间添加双向链接
4. `index.md`（分类目录）和 `log.md`（时间线）自动更新
5. 所有改动提交为一条干净的 git commit
6. 开 PR 时，审查机器人检查有没有问题
7. 团队讨论、改进、合并

审查机器人和编译引擎可以用不同的 LLM——这是刻意设计的。跨模型交叉验证能发现单一模型可能遗漏的幻觉。

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
| `giki review [--pr N] [--post] [--json]` | 跑机械检查 + 语义审查。 |
| `giki branch list \| create \| switch` | 管理知识编译分支。 |
| `giki pr create \| list \| review \| merge` | 管理 Pull Request（需要 gh CLI）。 |
| `giki lint [--fix]` | 检查 wiki 健康：断链、孤立页、frontmatter 问题。`--fix` 自动修复。 |
| `giki serve [--port N]` | 启动本地 Web UI，含 D3 知识图谱和搜索。 |
| `giki chat ["问题"]` | 向知识库提问。BM25 检索 + LLM RAG。 |
| `giki config show \| set <key> <value>` | 管理配置。 |
| `giki mcp-serve` | 启动 MCP 服务器，供平台集成。 |

## MCP 服务器（Claude Code / Codex）

giki 可以作为 MCP（Model Context Protocol）服务器运行，让你直接在 Codex、Claude Code 或任何 MCP 兼容平台里使用——不需要自己的 LLM API key。

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

重启平台后，就可以让平台初始化知识库、导入文档、审查改动——平台内置的 LLM 会驱动 giki 的流水线。

## 贡献

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"
pytest -q
```

详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 许可证

MIT
