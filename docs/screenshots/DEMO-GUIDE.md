# giki 演示截图指南

README 里预留了 4 张截图的位置（用 `<!-- TODO -->` 注释标记）。按照下面的步骤操作并截图。

## 准备工作

- 终端主题：推荐用深色背景（One Dark / Dracula / Tokyo Night），字号 14-16pt
- 终端宽度：拉到 100-120 列左右，让输出完整显示不折行
- 推荐工具：用 [Carbon](https://carbon.now.sh) 或 [snappify](https://snappify.com) 把终端截图美化（加窗口装饰、圆角、阴影）
- 保存位置：`docs/screenshots/` 目录

---

## 截图 1：`giki init` — 初始化知识库

**文件名**：`init-demo.png`

**操作步骤**：

```bash
# 找一个干净的临时目录
mkdir ~/giki-demo && cd ~/giki-demo && git init
giki init
```

**截取内容**：从 `giki init` 命令开始，到输出 `Next steps:` 结束。展示创建的目录结构和文件列表。

---

## 截图 2：`giki ingest` — 编译文档为 Wiki 页面

**文件名**：`ingest-demo.png`

**这是最重要的一张截图**，展示 giki 的核心能力。

**操作步骤**：

```bash
cd ~/giki-demo

# 准备一份有内容的源文档（建议 2000-5000 字的主题）
# 比如用一篇关于"设计模式"的笔记：
cat > sources/design-patterns.md << 'EOF'
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
EOF

# 设置 API Key（用你自己的 key）
export ANTHROPIC_API_KEY=sk-ant-...
# 或 export OPENAI_API_KEY=sk-...

# 运行 ingest（--yes 跳过交互确认）
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

**截取内容**：从 `giki ingest` 命令开始，到最终输出 `1 sources processed, N pages created...` 和 commit 信息。重点展示候选页面列表和生成结果。

---

## 截图 3：`giki review` — AI 审查

**文件名**：`review-demo.png`

**操作步骤**：

```bash
# 确保在 wiki/design-patterns 分支上
# 先手动改一个 wiki 页面，引入一个"问题"让 review 检测到
# 比如在一个页面里加一个断链：
echo -e "\nSee [[nonexistent-page]] for more details." >> wiki/singleton.md

git add wiki/singleton.md
git commit -m "add reference to nonexistent page"

# 运行 review
giki review
```

**截取内容**：从 `giki review` 命令开始，展示机械检查发现的断链、语义审查的发现（引用规则编号如 R-2），以及最终的 verdict（`request-changes`）。

---

## 截图 4：Obsidian 图谱视图

**文件名**：`obsidian-graph.png`

**操作步骤**：

1. 打开 Obsidian
2. 选择 `Open folder as vault` → 选择 `~/giki-demo/wiki/` 目录
3. 点击左侧的 **Graph View**（图谱视图）图标
4. 调整缩放让所有节点和连线都可见
5. 可以打开几个页面让它们的链接关系在图谱中高亮

**截取内容**：Obsidian 的图谱视图，展示 wiki 页面之间的 `[[wikilink]]` 连接关系。节点应该有标签，连线清晰。

---

## 截图完成后

1. 把 4 张截图保存到 `docs/screenshots/` 目录
2. 编辑 `README.md` 和 `docs/README-CN.md`，找到 `<!-- TODO: screenshot -->` 注释，取消下面 `<img>` 标签的注释
3. 提交并推送

```bash
cd ~/oss-contrib/giki   # 或你的 giki 仓库路径
git add docs/screenshots/ README.md docs/README-CN.md
git commit -m "docs: add demo screenshots"
git push origin main
```
