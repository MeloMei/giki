# giki 全功能演示指南 (macOS)

> 在 Mac 上从零跑通 giki 全部 11 个命令，并在关键节点截图。
> 预计耗时：20-30 分钟。

## 准备工作

**终端设置：**
- 打开 **Terminal.app** 或 **iTerm2**（推荐 iTerm2）
- 深色主题（One Dark / Dracula / Tokyo Night）
- 字号 14pt，终端宽度 120 列
- 截图工具：macOS 自带 `Cmd+Shift+4` 框选截图

**环境依赖：**
- Python 3.11+
- Git
- Obsidian（已安装）
- gh CLI（可选，pr 命令需要）

---

## Step 1: 克隆项目并安装

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e .
```

验证安装：

```bash
giki --version
```

> **截图 1**：`giki --version` 的输出。展示安装成功。

---

## Step 2: 初始化知识库 (`giki init`)

在 giki 仓库外创建一个干净的演示目录：

```bash
mkdir ~/giki-demo && cd ~/giki-demo
git init
giki init
```

你会看到：
- ASCII art banner
- 绿色的 `+ created` 输出（目录和文件）
- "Next Steps" 面板

> **截图 2**：完整的 `giki init` 输出。这是 README 的第一张演示图。
> 保存为：`init-demo.png`

---

## Step 3: 配置 LLM (`giki config`)

```bash
# 查看当前配置
giki config show

# 修改为你的 LLM 提供商
# 示例：用 OpenAI
giki config set llm.compile.provider openai
giki config set llm.compile.model gpt-4o
giki config set llm.compile.base_url https://api.openai.com/v1
giki config set llm.compile.api_key_env OPENAI_API_KEY

# 审查用不同模型（交叉验证）
giki config set llm.review.provider openai
giki config set llm.review.model gpt-4o-mini
giki config set llm.review.base_url https://api.openai.com/v1
giki config set llm.review.api_key_env OPENAI_API_KEY

# 查看配置建议
giki config tips
```

设置 API Key：

```bash
export OPENAI_API_KEY="sk-..."
# 或 export ANTHROPIC_API_KEY="sk-ant-..."
```

> **截图 3**：`giki config show` 输出的 JSON。展示配置结构。

---

## Step 4: 准备源文档

创建一份有内容的 Markdown 源文档：

```bash
cat > sources/design-patterns.md << 'DOCEOF'
# 设计模式笔记

## 创建型模式

### 单例模式 (Singleton)
确保一个类只有一个实例，并提供全局访问点。常用于日志记录器、配置管理器、
线程池、数据库连接池等场景。

实现要点：私有构造函数、静态实例变量、公共获取方法。需注意线程安全和
延迟初始化的权衡。

### 工厂方法模式 (Factory Method)
定义创建对象的接口，让子类决定实例化哪个类。将对象的创建延迟到子类。

适用场景：当一个类不知道它需要创建的对象的类时，或当一个类希望它的
子类来指定它所创建的对象时。

### 观察者模式 (Observer)
定义对象间的一对多依赖关系，当一个对象的状态改变时，所有依赖于它的
对象都会收到通知并自动更新。

核心组件：Subject（被观察者）、Observer（观察者）、ConcreteSubject、
ConcreteObserver。发布-订阅模式是其变体。

## 结构型模式

### 适配器模式 (Adapter)
将一个类的接口转换成客户希望的另一个接口，使得原本由于接口不兼容而
不能一起工作的类可以一起工作。

分两类：类适配器（多重继承）和对象适配器（组合）。

### 装饰器模式 (Decorator)
动态地给一个对象添加一些额外的职责。比生成子类更为灵活。

与适配器模式的区别：适配器改变接口，装饰器增强功能但不改变接口。

## 行为型模式

### 策略模式 (Strategy)
定义一系列算法，把它们一个个封装起来，并且使它们可相互替换。

适用于：多个相关类只有行为不同的场景，需要在一个算法的多个变体间切换，
或算法使用了客户端不应该知道的数据。

### 命令模式 (Command)
将一个请求封装为一个对象，从而可以用不同的请求对客户进行参数化，
对请求排队或记录请求日志，以及支持可撤销的操作。
DOCEOF
```

先提交初始化脚手架：

```bash
git add -A
git commit -m "init: scaffold knowledge base"
```

---

## Step 5: 编译文档 (`giki ingest`)

```bash
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

这会花 1-3 分钟。你会看到：
- `i ingesting design-patterns.md ...`
- 候选页面列表
- 逐页生成进度
- 最终的 Ingest Summary 面板

完成后检查生成的页面：

```bash
ls wiki/
```

> **截图 4**：完整的 `giki ingest` 输出（从命令到 Ingest Summary）。这是最重要的截图。
> 保存为：`ingest-demo.png`

---

## Step 6: 分支管理 (`giki branch`)

```bash
# 查看当前分支
giki branch list

# 切回 master 准备做 review 演示
giki branch switch master
```

> **截图 5**：`giki branch list` 输出，显示当前分支标记 `*`。

---

## Step 7: AI 审查 (`giki review`)

先故意在 wiki 页面里引入一个问题：

```bash
# 查看生成了哪些页面
ls wiki/

# 选一个实际存在的页面（比如 singleton-pattern.md）
# 往里面加一个断链
echo "" >> wiki/singleton-pattern.md
echo "See [[nonexistent-page]] for more details." >> wiki/singleton-pattern.md
git add wiki/
git commit -m "add broken reference for demo"
```

运行审查：

```bash
giki review --base master
```

你会看到：
- Review Verdict 面板（红色 REQUEST CHANGES）
- 机械检查发现断链 `[[nonexistent-page]]`
- 语义审查结果

> **截图 6**：完整的 `giki review` 输出，包含 verdict 面板和 findings。
> 保存为：`review-demo.png`

---

## Step 8: 知识库健康检查 (`giki lint`)

```bash
# 检查当前 wiki 的健康状态
giki lint

# 自动修复能修的问题
giki lint --fix
```

你会看到：
- 断链、孤立页、frontmatter 问题等检查结果
- `--fix` 后的修复报告

> **截图 7**：`giki lint` 的输出（修复前），展示发现的各种问题。

---

## Step 9: 本地 Web UI (`giki serve`)

```bash
giki serve --port 8080
```

然后在浏览器打开 `http://localhost:8080`

你会看到：
- **D3 知识图谱**：节点是 wiki 页面，边是 wikilinks
- **搜索栏**：输入关键词，实时搜索
- **页面查看器**：点击节点查看 markdown 渲染的内容

操作演示：
1. 在搜索栏输入 "观察者" 或 "observer"
2. 点击搜索结果查看页面内容
3. 拖动图谱节点，观察力导向布局

> **截图 8**：浏览器中的 Web UI 全屏截图，展示 D3 图谱 + 搜索结果。
> 按 `Ctrl+C` 关闭服务器。

---

## Step 10: 智能问答 (`giki chat`)

```bash
# 单次提问
giki chat "观察者模式和发布-订阅模式有什么区别？"

# 进入交互模式
giki chat
> 单例模式有哪些实现要点？
> 适配器模式和装饰器模式的区别是什么？
> Ctrl+D 退出
```

> **截图 9**：`giki chat` 的问答输出，展示 LLM 基于 wiki 内容的回答。

---

## Step 11: Obsidian 图谱视图

```bash
# 用 Obsidian 打开 wiki 目录
open -a Obsidian ~/giki-demo/wiki/
```

在 Obsidian 中：
1. 点击左侧 **Graph View**（图谱视图）图标
2. 调整缩放让所有节点和连线都可见
3. 点击几个节点，观察高亮的链接关系

> **截图 10**：Obsidian 图谱视图，展示 wikilinks 构成的知识图谱。
> 保存为：`obsidian-graph.png`

---

## Step 12: MCP 服务器（可选）

```bash
giki mcp-serve
```

服务器启动后会等待 stdio 输入（看起来像挂起了）。这是正常的——它等待 MCP 客户端连接。

> 如需截图：打开另一个终端窗口，用 `ps aux | grep giki` 展示进程在运行。
> 按 `Ctrl+C` 关闭。

---

## 截图清单

| # | 文件名 | 内容 | 用途 |
|---|--------|------|------|
| 1 | `version.png` | `giki --version` | 安装验证 |
| 2 | `init-demo.png` | `giki init` 完整输出 | README 演示图 |
| 3 | `config-show.png` | `giki config show` JSON | 配置展示 |
| 4 | `ingest-demo.png` | `giki ingest` 完整输出 | README 演示图（最重要） |
| 5 | `branch-list.png` | `giki branch list` | 分支管理 |
| 6 | `review-demo.png` | `giki review` 含 verdict | README 演示图 |
| 7 | `lint-output.png` | `giki lint` 检查结果 | 健康检查 |
| 8 | `serve-ui.png` | 浏览器 Web UI | Web UI 展示 |
| 9 | `chat-qa.png` | `giki chat` 问答输出 | Q&A 展示 |
| 10 | `obsidian-graph.png` | Obsidian 图谱视图 | README 演示图 |

---

## 截图完成后

把截图复制到 giki 项目的 `docs/screenshots/` 目录：

```bash
cd ~/giki   # 你的 giki 仓库
cp ~/Desktop/init-demo.png docs/screenshots/
cp ~/Desktop/ingest-demo.png docs/screenshots/
cp ~/Desktop/review-demo.png docs/screenshots/
cp ~/Desktop/obsidian-graph.png docs/screenshots/
# ... 其他截图
```

然后更新 README 中对应的 `<img>` 标签（如果需要的话）。
