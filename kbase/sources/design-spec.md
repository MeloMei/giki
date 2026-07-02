# giki v0.1 设计文档

**项目代号**：giki（git + wiki）
**版本**：v0.1（首个开源 release）
**作者**：MeloMei
**日期**：2026-06-30
**状态**：Design Approved，待写实现计划

---

## 1. 项目定位

> **giki 用软件工程方法做 LLM Wiki。**

把 Andrej Karpathy 提出的 LLM Wiki 模式（"摄入时编译为结构化知识"而非"查询时检索"）与现代软件工程的协作流程（git 版本控制 + Pull Request + CI 审查）结合起来，让团队可以像协作开发代码一样协作建设知识库。

### 1.1 差异化主张

市面上的 LLM 知识工具分两类：

- **单人本地 LLM Wiki 工具**：实现了"编译式"理念，但无团队协作、无质量门禁
- **传统 RAG / Notion AI / NotebookLM**：云端、检索式、有协作但非编译式

giki 占据**第三个象限**：编译式 + Git 原生协作 + AI 质量审查。其中"Git 原生协作 + AI Review"是当前市场空白。

### 1.2 一句话定位

> 用软件工程方法做 LLM Wiki —— 知识的持续集成（Knowledge CI/CD）。

---

## 2. 范围（v0.1）

### 2.1 v0.1 必须有（🔴 核心特性）

1. **两步编译流水线**：Analyze（提取候选页面）→ Synthesize（生成正文）→ Crosslink（补充双链）
2. **Git 原生版本控制**：每次 AI 修改产出一个清晰 commit，可 diff 可回滚
3. **PR Review Bot**：机械检查 + 逐页 LLM semantic review
4. **智能索引**：自动维护 `index.md`（分类目录）和 `log.md`（时间线）
5. **Obsidian 兼容**：标准 Markdown + `[[wikilink]]`，用户可直接用 Obsidian 浏览

### 2.2 v0.1 显式不做（推迟到后续版本）

- 类型化 Wikilink（`[[type::target]]`）→ v0.2
- AI Merge（解决 PR 冲突）→ v0.2
- `branch` / `pr` 等协作子命令 → v0.2
- 本地 Web UI（D3 图谱、全文搜索）→ v0.3
- Query-to-Wiki Q&A → v0.3
- 跨域知识融合（`.wiki-fusion.yaml`）→ v0.3
- 知识库 lint --fix → v0.3
- Token 预算预估提示 → 暂不规划，YAGNI
- 多语言 source（PDF OCR、网页抓取等）→ 长期不做

---

## 3. 架构铁律

这些约束驱动所有后续设计决策，任何方案违反任一条都需重新评估：

1. **无常驻进程**：每个 `giki` 命令是独立的短生命周期进程，跑完即退
2. **无 IPC**：不使用消息队列、共享内存、socket、文件锁
3. **状态只有两处**：git 仓库（内容 + 历史）+ 工作区文件（临时产物，可重建）
4. **审查两种模式**：本地手动 `giki review`，或 GitHub Actions（用户自配 API key）
5. **配置即文件**：`.giki/config.yaml`、`wiki-rules.md` 都在仓库里，跟着 git 走

---

## 4. 仓库布局

### 4.1 giki 项目仓库（开发者视角）

```
giki/                                  ← git 仓库根
├── pyproject.toml                     ← 入口点: giki = "giki.cli:app"
├── install.sh
├── README.md / LEGAL.md / CLAUDE.md
├── .gitignore
├── .github/workflows/
│   ├── wiki-review.yml                ← 对 kbase/ 跑 review
│   └── wiki-lint.yml                  ← 对 kbase/ 跑结构校验
│
├── src/giki/                          ← Python 包
│   ├── __init__.py
│   ├── cli.py                         ← Typer CLI 入口（v0.1 只注册 4 命令）
│   ├── config.py
│   ├── orchestrator.py                ← Ingest 流水线编排
│   ├── git_utils.py
│   ├── utils.py
│   │
│   ├── commands/                      ← 命令实现（薄层）
│   │   ├── init.py                    ← v0.1 ✅
│   │   ├── ingest.py                  ← v0.1 ✅
│   │   ├── review.py                  ← v0.1 ✅
│   │   ├── config_cmd.py              ← v0.1 ✅
│   │   ├── lint.py                    ← v0.3, NotImplementedError 占位
│   │   ├── merge.py                   ← v0.2, NotImplementedError 占位
│   │   ├── collab.py                  ← v0.2, NotImplementedError 占位
│   │   ├── serve.py                   ← v0.3, NotImplementedError 占位
│   │   ├── chat.py                    ← v0.3, NotImplementedError 占位
│   │   └── fusion.py                  ← v0.3, NotImplementedError 占位
│   │
│   ├── llm/
│   │   ├── __init__.py                ← build_client() 工厂
│   │   ├── base.py                    ← LLMAdapter ABC + LLMResponse
│   │   ├── claude.py                  ← Anthropic + 兼容 gateway
│   │   ├── openai.py                  ← OpenAI + 兼容 endpoint（含 Ollama）
│   │   ├── _retry.py                  ← 指数退避（max 3）
│   │   └── prompts.py                 ← PromptTemplate
│   │
│   ├── wiki/
│   │   ├── store.py                   ← WikiStore (CRUD + 搜索 + 路径防护)
│   │   ├── parser.py                  ← WikiParser (frontmatter + wikilink)
│   │   ├── linker.py                  ← Linker (两阶段 lookup + Related 块)
│   │   ├── index_log.py               ← index.md / log.md 维护
│   │   ├── review_agent.py            ← Mechanical + Semantic review
│   │   └── review_fmt.py              ← 报告格式化（markdown / json）
│   │
│   ├── sources/
│   │   └── loader.py                  ← SourceLoader + SHA-256 增量
│   │
│   └── templates/                     ← Prompt 模板 + init 脚手架
│       ├── analyze.md / synthesize.md / crosslink.md
│       ├── review.md / review-system.md
│       └── init/
│           ├── gitignore.txt
│           ├── index.md / log.md
│           ├── wiki-rules.md
│           ├── readme.md
│           └── config.yaml
│
├── tests/                             ← pytest
│
└── kbase/                             ← dog-fooding（共享外层 .git）
    ├── .giki/config.yaml
    ├── sources/
    ├── wiki/
    ├── wiki-rules.md
    ├── index.md
    ├── log.md
    └── README.md
```

**dog-fooding 工作流约定**（写入根 README）：

| 场景 | 分支策略 | 合并方式 |
|---|---|---|
| 代码开发 | `main` 或 `feature/<name>` | 直接 commit 或 squash merge |
| `kbase/` ingest | 必须 `giki ingest --branch wiki/<topic>` | PR + giki review → merge |
| `kbase/` 手工编辑 | 同上 | 同上 |

这样 `git log --first-parent main` 看到的就是干净的项目演进史，每一个 wiki PR 都是 giki "Knowledge CI/CD" 的活样本。

### 4.2 用户的 giki 知识库（用户视角）

```
my-knowledge-base/
├── .giki/
│   ├── config.yaml                    ← 模型配置、阈值
│   └── prompts/                       ← (可选) 用户覆盖默认 prompt
│
├── sources/                           ← 原始资料
├── wiki/                              ← LLM 编译产出（平铺，禁子目录）
│
├── index.md                           ← 自动维护的分类目录
├── log.md                             ← 自动维护的时间线
├── wiki-rules.md                      ← 用户定义的审查规则（仓库根，高频编辑）
│
├── .giki-state/                       ← 衍生状态（默认 gitignore）
│   ├── sources.json                   ← SHA-256 哈希追踪
│   └── index.json                     ← BM25 搜索索引（v0.3 chat 用）
│
└── .github/workflows/giki-review.yml  ← 可选（--with-action 生成）
```

---

## 5. CLI 命令（v0.1）

v0.1 在 `cli.py` 注册以下 4 个命令；其他 `commands/*.py` 文件存在但**不注册**，体内 `raise NotImplementedError`。

```
giki init [--with-action]
    初始化当前目录为 giki 知识库。幂等。

giki ingest <path...> [--branch <name>] [--yes | --dry-run] [--retry-failed]
    编译流水线入口。可接受 .md / .txt / .pdf。
    --branch  在指定分支上 ingest（强烈推荐）
    --yes     非交互模式，接受所有候选页面
    --dry-run 只输出候选页面，不写文件不调用 Synthesize
    --retry-failed  只重试上一次 ingest 中失败的页面

giki review [--pr <id>] [--post] [--json]
    PR Review Bot。默认对 HEAD vs main 的 wiki 改动审查。
    --pr <id>  指定 PR 编号（通过 gh CLI 拉取 diff）
    --post     将审查结果发表为 PR comment（需要本地 gh auth）
    --json     输出 JSON（CI 友好）
    退出码: approve=0, comment=0, request-changes=1

giki config show | set <key> <value> | tips
    管理 .giki/config.yaml。
```

CLI 命令名是 **`giki`**（短、易记）。PyPI 包名也是 `giki`。

---

## 6. 核心数据流：`giki ingest`

```
用户: giki ingest sources/manual.pdf --branch wiki/design-patterns
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 0  Bootstrap                                           │
│  · 加载 .giki/config.yaml                          [IO]      │
│  · open repo, 检查 worktree 干净                    [IO]      │
│  · 切到/创建 wiki/design-patterns 分支              [IO]      │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 1  Source Loading                                      │
│  · SourceLoader 按扩展名分派                        [纯函数]  │
│  · .pdf → pypdf 逐页提取 → <!--giki:page N--> 拼接 [IO+纯]   │
│  · .md/.txt → utf-8 直接读                         [IO]      │
│  · 计算 SHA-256，对比 .giki-state/sources.json     [纯函数]  │
│  · 已存在且 hash 未变 → 跳过并退出                 [终止]    │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 2  Analyze（滑动窗口分片）                              │
│  · 按 chunk_size=12000 char 切片，相邻重叠 500     [纯函数]  │
│  · 读取 wiki/ 现有页面 → 生成 index_summary        [IO+纯]   │
│  · 对每个 chunk 调用 analyze.md prompt              [LLM × M]│
│  · 合并 suggested_pages，slug 归一化去重           [纯函数]  │
│  · 输出: List[SuggestedPage]                                  │
│    { filename, title, action(create|update),                 │
│      hints, source_anchors(页码区间), aliases_suggested }    │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 3  Interactive Confirmation                            │
│  · stdin.isatty() and not --yes:                             │
│      展示候选列表，用户勾选                         [IO]      │
│  · --dry-run: 输出候选后退出                       [终止]    │
│  · --yes 或非 TTY: 全部接受                                   │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 4  Synthesize × N                                      │
│  · 每个 SuggestedPage 一次 LLM 调用                [LLM × N] │
│    create → (source 节选, hints, aliases)                    │
│    update → (旧页面全文, source 节选, hints,                 │
│              "未提及内容必须原样保留" 约束) → rewrite        │
│  · 写入 wiki/<filename>.md（.tmp → 原子 rename）   [IO]      │
│  · 失败页面不中断流水线（断点续传）                          │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 5  Crosslink × N                                       │
│  · 读取所有 wiki 页面标题 + aliases                [IO]      │
│  · 每个新建/更新页面一次 LLM 调用                  [LLM × N] │
│    LLM 输出"该加哪些 [[wikilink]]"，不重写正文                │
│  · Linker 应用补丁，邻居数 ≥1 才生成 ## Related   [纯函数]   │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 6  Index & Log（无 LLM）                                │
│  · 追加 index.md（按字母序插入分类块）             [纯+IO]   │
│  · 追加 log.md（## YYYY-MM-DD HH:MM ingest ...）  [IO]       │
│  · 更新 .giki-state/sources.json                   [IO]      │
│  · 重建 .giki-state/index.json (BM25)              [IO]      │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 7  Commit                                              │
│  · git add wiki/ index.md log.md .giki-state/      [IO]      │
│  · git commit -m "ingest: <source> → N of M pages"           │
│  · 提示用户后续动作                                          │
└──────────────────────────────────────────────────────────────┘
```

### 6.1 关键设计点

- **滑动窗口分片**解决"喂一本书只编译前 20 页"的硬伤
- **Phase 1 hash 短路**实现"增量编译"，类似 `make` 的依赖检查
- **Crosslink 独立于 Synthesize**：Synthesize 只关心当前页面质量，Crosslink 只需要标题列表（轻量上下文）
- **`source_anchors` 字段**记录 "概念页源自第 23-27 页"，为 v0.2 类型化 wikilink 埋钩子
- **失败处理**：断点续传，commit message 标 "N of M pages"，失败页面写入 log.md；用户可 `giki ingest --retry-failed` 重试

### 6.2 update 语义

`action: "update"` = **rewrite**。LLM 拿到旧页面全文 + 新 source，输出完整的新页面。约束机制：

1. Synthesize prompt 显式约束："未在 source 中提及的段落必须原样保留"
2. PR Review Bot 的机械检查计算 update diff 中"无关改动比例"，超过 `review.unrelated_edit_threshold`（默认 30%）时标记 `possible-unrelated-edit` warning

不采用 append（页面越来越乱）或 merge patch（LLM 输出格式难稳定）。

### 6.3 失败回滚策略

| 阶段 | 失败行为 |
|---|---|
| Phase 0-1 | 中止，无副作用 |
| Phase 2 (Analyze) | 任一 chunk 全部重试失败 → 中止，无副作用 |
| Phase 4 (Synthesize) | 单页面失败 → 跳过该页面，记录到 log.md，继续 |
| Phase 5 (Crosslink) | 单页面失败 → 该页面保留无 Related 块，记录，继续 |
| Phase 6-7 | 失败抛出，已写文件保留供下次提交 |

---

## 7. PR Review Bot

### 7.1 工作流

```
giki review [--pr <id>] [--post] [--json]
       │
       ▼
Phase 0  Context Loading
  · .giki/config.yaml 的 review.* 配置
  · wiki-rules.md (按 ## R-N 锚点拆分)
  · 确定 diff 范围 (HEAD vs main, 或 PR diff)
       │
       ▼
Phase 1  Change Classification（纯函数）
  · NEW / UPDATED / DELETED / RENAMED
  · index.md / log.md / .giki-state/ 单独处理
       │
       ▼
Phase 2  Mechanical Checks（无 LLM）
  · 断链检查（两阶段 lookup：filename → aliases）
  · Frontmatter schema 校验
  · index.md 同步检查（NEW 必须出现在 index 增量）
  · UPDATED 类型: "无关改动比例" 超阈值 → warn
  · 输出: List[MechanicalFinding]
       │
       ▼
Phase 3  Semantic Review × N（LLM 调用，每页一次）
  · 输入: wiki-rules.md + 页面 before/after + 邻居摘要 + MechanicalFinding
  · 输出 JSON: { findings: [{rule_id, severity, evidence, suggestion}],
                 overall_verdict: approve|request-changes|comment }
  · 手写页面（无 sources frontmatter）跳过此阶段
       │
       ▼
Phase 4  Aggregation（纯函数）
  · 任一 request-changes → 整体 request-changes
  · 任一 blocker severity → 整体 request-changes
  · 全 approve → 整体 approve
  · 否则 → comment
       │
       ▼
Phase 5  Output
  默认: markdown 到 stdout
  --post: gh CLI 发表 PR comment
  --json: 结构化输出
  退出码: approve=0, comment=0, request-changes=1
```

### 7.2 wiki-rules.md 格式

用户级"宪法"，每条规则用 `## R-N` 锚点。Review Bot 在 prompt 里要求 LLM 输出 `rule_id` 字段，让审查结果可追溯。

### 7.3 严重级（severity）

| 级别 | 含义 | 默认是否阻断 PR |
|---|---|---|
| `blocker` | 违反硬规则（如语义矛盾、断链） | ✅ 阻断 |
| `warn` | 需要注意但可放行（如风格） | ❌ 不阻断 |
| `nit` | 鸡毛蒜皮（如标点） | ❌ 不阻断，PR comment 折叠显示 |

阻断行为通过 `review.severity_blocking` 配置（默认 `[blocker]`）控制。

### 7.4 关键设计点

- **机械检查先跑**：能用规则杀掉的问题就别问 LLM（省 token + 零误报）
- **按页面隔离 review**：每页一次 LLM 调用，避免 10 页塞一次的"平均分配注意力"
- **编译 LLM 和审查 LLM 独立配置**：`llm.compile` 和 `llm.review` 是完整独立的配置块，可以用不同 provider/model 做交叉验证
- **手写页面豁免**：缺少 `sources` frontmatter 的页面只跑机械检查，不让审查 LLM 评价用户私人笔记
- **`--post` 走 gh CLI**：不内置 GitHub API，复用用户已装的 `gh`

---

## 8. LLM 适配层

### 8.1 抽象

```python
class LLMAdapter(ABC):
    name: str
    provider: str
    model: str

    @abstractmethod
    def chat(self, messages: list[Message], **opts) -> LLMResponse: ...

@dataclass
class LLMResponse:
    text: str
    raw: dict
    usage: dict | None
    finish_reason: str | None
```

### 8.2 实现

- **ClaudeAdapter** —— Anthropic Messages API，兼容 theta / evomap 等 Anthropic-compatible gateway（通过 `base_url`）
- **OpenAIAdapter** —— OpenAI Chat Completions API，兼容 Azure / 任何 OpenAI-compatible endpoint（**含 Ollama / vLLM / LM Studio**，无需专门 adapter）

不引入 `litellm` / `langchain`。两个 adapter 共约 300 行，依赖只有 `httpx`。

### 8.3 工厂

```python
build_client(cfg) -> LLMAdapter
```

唯一入口。`orchestrator.py` 和 `review_agent.py` 分别用 `cfg.llm.compile` 和 `cfg.llm.review` 构造各自的 client。

### 8.4 安全

- **API key 永远从环境变量读取**，配置文件里只存 `api_key_env` 字段（环境变量名）
- 任何错误日志中都不输出 raw header / API key

### 8.5 重试

- 指数退避：1s → 2s → 4s，max 3 retry（含首次共 4 次尝试）
- 可重试：429 / 503 / timeout / connection error
- 不可重试：401 / 400 / 422
- LLM 调用最终失败 → 抛出，**不做静默 fallback**（避免低质量页面毁掉信任）

### 8.6 JSON 输出鲁棒解析

Analyze / Review 阶段要求 LLM 返回 JSON。`utils.extract_json()`：

1. 用宽松正则提取首个完整 JSON 块（剥离 ```json``` 围栏和首尾杂文）
2. 解析失败 → 重试**一次**，附加 system 消息"请只返回 JSON 不要任何其他文字"
3. 再失败 → 当作 LLM 调用失败处理

---

## 9. Wiki 内容格式契约

### 9.1 文件名

- 平铺在 `wiki/` 目录，**禁止子目录**
- slug 模式：`[a-z0-9-]+`，max 80 字符
- slug 由 LLM 在 Analyze 阶段生成（语义化英文 slug，不机械音译）
- 冲突 → ingest 报错

### 9.2 文件结构

```markdown
---
title: 观察者模式
aliases: ["Observer Pattern", "观察者"]
tags: [design-pattern, behavioral]
created: 2026-06-30T14:20:00+08:00
updated: 2026-06-30T14:20:00+08:00
sources:
  - path: sources/books/manual.pdf
    pages: "23-27"
---

# 观察者模式

正文 ...

---

## Related
- [[reactive-streams]]
- [[publish-subscribe-pattern]]
```

#### Frontmatter schema（jsonschema 校验）

| 字段 | 必需 | 说明 |
|---|---|---|
| `title` | ✅ | 人类可读标题，任意语言 |
| `aliases` | ⬜ | 字符串数组，用于双链解析和搜索 |
| `tags` | ⬜ | 扁平字符串数组 |
| `created` | ✅ | ISO 8601 + tz，giki 自动维护 |
| `updated` | ✅ | ISO 8601 + tz，giki 自动维护 |
| `sources` | ⬜* | 数组；缺失视为"手写页面"，PR Review 跳过 semantic 阶段 |

*sources 在 LLM 编译页面中**必须**有，在手写页面中**允许缺失**。

#### 正文规则

- 只能有一个 `# H1`（等于 frontmatter.title）
- 段落中可混用 `[[wikilink]]`

#### Related 区块

由 Crosslink 阶段生成；当邻居数 `< wiki.related_min_neighbors`（默认 1）时**不生成**，连标题都不写。

### 9.3 Wikilink 语法（v0.1）

```
[[target-slug]]
[[target-slug|显示文本]]
```

不支持（v0.1）：`[[type::target]]`（v0.2）、`[[target#heading]]`（v0.2）、`![[embed]]`、`[[^block]]`。

### 9.4 Linker 解析

1. 正则提取 `\[\[([^\[\]\|]+)(?:\|([^\[\]]+))?\]\]`
2. 优先匹配 `wiki/<target>.md`
3. 否则扫所有页面 `aliases`，找命中
4. 都不命中 → 标记**断链**（Phase 2 机械检查的命中项）

两阶段 lookup 是 v0.1 兼容性核心：用户重命名页面只需在新 slug 下加 alias，旧链接自动指向新页。

### 9.5 Obsidian 兼容性

| 兼容项 | 状态 |
|---|---|
| 标准 frontmatter | ✅ |
| 平铺 `wiki/` 作 vault | ✅ |
| `[[slug]]` / `[[slug\|display]]` | ✅ |
| 标准 markdown | ✅ |
| `[[file#heading]]` | ⚠ giki 忽略 `#` 后内容，作为整页链接处理 |
| Obsidian graph 配置 | ⬜ 不写 `.obsidian/`，用户自行配 |
| Daily notes / templates 插件 | ❌ 不模仿 |

---

## 10. 配置与初始化

### 10.1 `giki init`

幂等。检测 git 仓库状态：已是 git repo 跳过，否则**交互式询问**（非 TTY 默认 y）"是否 git init？"。

输出：
- `.giki/config.yaml`
- `wiki-rules.md`（5 条 starter rule）
- `index.md`、`log.md`（空模板）
- `sources/`、`wiki/` 目录
- `.gitignore`（默认 ignore `.giki-state/*.json`）
- `README.md`（知识库导航）
- `.github/workflows/giki-review.yml`（仅 `--with-action` 显式启用）

### 10.2 默认 `.giki/config.yaml`

```yaml
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    max_retries: 3
    timeout_sec: 120
  review:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    max_retries: 3
    timeout_sec: 120

ingest:
  chunk_size: 12000
  chunk_overlap: 500
  synthesize_context: 6000
  interactive: auto                 # auto | always | never
  pdf:
    page_separator: "<!-- giki:page {n} -->"
    reject_scanned: true

review:
  unrelated_edit_threshold: 0.30
  severity_blocking: [blocker]
  pr_comment_collapse: true         # 折叠 nit findings

wiki:
  enforce_slug_pattern: "^[a-z0-9-]+$"
  max_slug_length: 80
  related_min_neighbors: 1
```

配置 schema 行为：缺失必需字段 → fail；未知字段 → warn 不 fail（小版本前向兼容）。

### 10.3 默认 `wiki-rules.md`

5 条 starter rule：一致性 / 引用完整性 / 命名规范 / 双链优先 / 段落长度。用户可任意删改。

### 10.4 GitHub Action 模板（`--with-action` 才生成）

```yaml
name: giki review
on:
  pull_request:
    paths: ['wiki/**', 'index.md', 'wiki-rules.md', '.giki/**']
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install giki
      - run: giki review --pr ${{ github.event.pull_request.number }} --post
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## 11. 测试策略

### 11.1 测试三档

| 档位 | 工具 | 覆盖 |
|---|---|---|
| 纯函数单测 | pytest | utils、Linker、SourceLoader、Phase 1/2/4 聚合逻辑、Aggregation |
| IO mock | pytest + tmp_path + GitPython | git 操作、文件 IO、init 幂等 |
| LLM 集成 | pytest + vcr.py（cassette 录制） | adapter、orchestrator end-to-end、review end-to-end |

不依赖真实 LLM API 跑 CI；cassette 提交到仓库，更新 cassette 需要 maintainer 手动 `pytest --record-mode=new_episodes` 重录。

### 11.2 测试覆盖目标

| 模块 | 目标 |
|---|---|
| utils / parser / linker | 95% |
| orchestrator / review_agent | 85%（含 cassette） |
| commands/*.py | 70%（薄层） |
| llm adapters | 80%（含 cassette） |

---

## 12. 已知限制与后续路线

### 12.1 v0.1 已知限制（写入 README）

1. PDF 不做 OCR，扫描型 PDF 会被拒绝
2. 不支持 URL / Notion / Confluence 等远程 source
3. Wikilink 不支持 `#heading` / `^block-id` / `embed`
4. wiki 目录平铺，不支持子目录归类（用 frontmatter.tags 替代）
5. 断点续传需要手动 `--retry-failed`
6. 不内置 token 预估，用户自行控制成本

### 12.2 v0.2 计划

- 类型化 Wikilink（`[[requires::X]]` 等 8 种关系）
- `giki branch` / `giki pr` 协作命令（"拉模式"，本地触发远端 PR）
- AI merge（解决 PR 冲突）

### 12.3 v0.3 计划

- 本地 Web UI（`giki serve`，D3 图谱 + 全文搜索，纯 stdlib）
- Q&A（`giki chat`，BM25 检索 + RAG）
- 跨域知识融合（`.wiki-fusion.yaml`）
- `giki lint --fix`

---

## 13. 决策记录（ADR-style，摘录）

| # | 决策 | 备选 | 理由 |
|---|---|---|---|
| D-1 | 一句话定位 = "用软件工程方法做 LLM Wiki"（双核心） | A 只主打 CI/CD，B 只主打编译图谱 | C 把"编译"和"协作"用一个隐喻串起来，差异化最强 |
| D-2 | 纯 CLI 形态 | daemon / server | 和"软件工程方法"定位最契合，冷启动友好，可后续加 |
| D-3 | v0.1 输入 = md/txt/pdf | 加 URL / Notion | YAGNI；PDF 用 pypdf 零系统依赖 |
| D-4 | 编译粒度 = LLM 自主决定的概念页 | 1:1 / 固定拆分 | 才是真正的"编译"，让 PR Review 有用武之地 |
| D-5 | update 语义 = rewrite | append / merge patch | 最简单透明，git diff 清晰 |
| D-6 | 滑动窗口分片解决截断 | 接受截断 / token 预算自适应 | 截断在开源首发杀伤力极大 |
| D-7 | 断点续传 + `--retry-failed` | 全有或全无 | 大文档体验 |
| D-8 | CLI 命令名 = `giki` | `llm-git-wiki` | 短命令是工具的命脉 |
| D-9 | commands/ 目录占位 NotImplementedError | 只放 v0.1 命令 | 架构地图一次画完 |
| D-10 | `kbase/` 共享外层 .git | submodule / 独立 repo | 用 `--first-parent` 看主干，wiki 细节在 PR |
| D-11 | wiki-rules.md 放仓库根 | 放 `.giki/` | 高频编辑的内容文件，不是配置 |
| D-12 | 三档 severity (blocker/warn/nit) | error/warn/info；两档 | 借 code review 工具命名习惯 |
| D-13 | 不写专门 OllamaAdapter | 单独写 / 不支持本地 | Ollama 是 OpenAI-compatible，README 说明即可 |
| D-14 | 重试 max 3（共 4 次） | 1 / 2 / 5 | 主流 SDK 默认 |
| D-15 | 允许手写页面（sources optional） | 强制 ingest | 给用户留口子；审查只跑机械检查 |
| D-16 | v0.1 支持 aliases 字段 | 推迟 | 对页面重命名兼容至关重要 |
| D-17 | Related 区块可选 | 强制每页 | 避免孤立页面的空 Related 占位 |
| D-18 | init 在非 git 目录交互询问 | 自动 init / 不允许 | 避免错误目录意外建 repo |
| D-19 | `.giki-state/*.json` 默认 ignore | 默认 commit | 衍生产物，PR diff 噪音问题 |
| D-20 | GitHub Action 模板需 `--with-action` | 默认生成 | 纯本地用户不被困惑 |

---

**End of design.** 下一步：用 writing-plans skill 生成实现计划。
