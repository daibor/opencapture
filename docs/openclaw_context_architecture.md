# OpenCapture → OpenClaw 上下文架构设计

> 本文档描述 OpenCapture 如何为 OpenClaw 提供高质量、低冗余、语义丰富的用户行为上下文。

## 一、设计目标

```
原始事件流 → 结构化理解 → 可检索的行为上下文
     ↓              ↓              ↓
  截图+日志    LLM分析聚合    OpenClaw memory
```

**核心原则**：为 OpenClaw 的 `memory_search` 提供高质量、低冗余、语义丰富的用户行为上下文。

### 1.1 关键目标

| 目标 | 说明 |
|------|------|
| **意图优先** | 输出"用户想做什么"而非"屏幕上有什么" |
| **上下文连贯** | 结合前后事件推断完整行为链 |
| **语义丰富** | 使用可被向量检索匹配的自然语言描述 |
| **去冗余** | 避免重复元数据，提高信息密度 |

---

## 二、输出格式设计

### 2.1 分层存储结构

```
~/.openclaw/workspace/context/
├── YYYY-MM-DD.md          # 日级行为摘要 (OpenClaw 可直接索引)
├── sessions/
│   └── YYYY-MM-DD-HH.md   # 小时级活动记录 (细粒度上下文)
└── artifacts/
    └── YYYY-MM-DD/        # 原始素材 (按需引用，不主动索引)
        ├── screenshots/
        └── raw.jsonl
```

### 2.2 日级摘要格式 (`YYYY-MM-DD.md`)

设计为 OpenClaw `memory_search` 可直接检索的格式：

```markdown
# 2026-02-05 行为上下文

## 工作主题
- 上午：在 VSCode 中开发 OpenCapture 项目的分析模块
- 下午：调研 OpenClaw 记忆系统架构，整理设计文档

## 关键活动
- **09:15-11:30** 代码开发：修改 `src/opencapture/analyzer.py`，重构 LLM 调用逻辑
- **14:00-15:20** 文档阅读：浏览 OpenClaw 官方文档和 GitHub 源码
- **15:30-17:00** 设计讨论：在 Claude Code 中规划新的上下文架构

## 使用的工具和资源
- VSCode: src/opencapture/analyzer.py, src/opencapture/report_generator.py
- Chrome: docs.openclaw.ai, github.com/openclaw/openclaw
- Terminal: git, python

## 决策和想法
- 决定采用分层存储：日摘要 + 小时细节 + 原始素材
- 输出格式对齐 OpenClaw memory 的 Markdown 约定

## 未完成事项
- [ ] 实现新的 prompt 模板
- [ ] 测试与 OpenClaw memory_search 的集成
```

### 2.3 小时级记录格式 (`sessions/YYYY-MM-DD-HH.md`)

```markdown
# 2026-02-05 14:00-15:00 活动记录

## 上下文
正在调研 OpenClaw 的记忆系统实现

## 活动序列

### 14:03 Chrome | OpenClaw Memory Documentation
**动作**: 滚动浏览文档
**观察**: 用户正在阅读 Memory 配置部分，关注 hybrid search 的参数设置
**推断意图**: 了解如何配置向量+BM25混合检索

### 14:08 Chrome | GitHub - openclaw/openclaw
**动作**: 点击 src/memory 目录
**观察**: 用户进入源码目录，查看 MemoryIndexManager.ts
**推断意图**: 深入理解 memory 的技术实现

### 14:15 VSCode | notes.md
**输入**: "OpenClaw 采用文件优先策略..."
**观察**: 用户开始记录调研笔记
**推断意图**: 整理学习内容，为后续设计做准备

## 本时段总结
用户在调研 OpenClaw memory 系统，从文档阅读转向源码分析，并开始记录笔记。主要关注点是混合检索的配置和实现细节。
```

---

## 三、LLM Prompt 设计

### 3.1 设计原则

| 原则 | 说明 |
|------|------|
| **意图优先** | 输出"用户想做什么"而非"屏幕上有什么" |
| **上下文连贯** | 结合前后事件推断完整行为链 |
| **语义丰富** | 使用可被向量检索匹配的自然语言描述 |
| **去冗余** | 避免重复元数据（坐标、时间戳等已在结构中） |

### 3.2 图像分析 Prompt

#### System Prompt

```
你是用户行为理解专家。分析截图时，重点输出：
1. 用户正在做什么（动作+对象）
2. 推断的意图或目标
3. 与工作流的关联（如果能判断）

输出格式要求：
- 使用简洁的陈述句
- 避免描述 UI 元素细节
- 突出语义信息，便于后续检索
```

#### Click Prompt

```
用户在 {window} 中点击了位置 ({x}, {y})。

请分析：
1. 点击了什么元素或功能？
2. 这个操作的目的是什么？
3. 用一句话概括这个行为的意图。

输出示例：
"用户点击了文件树中的 analyzer.py，准备编辑分析模块代码"
```

#### Drag Prompt

```
用户在 {window} 中从 ({x1}, {y1}) 拖动到 ({x2}, {y2})。

请判断拖动类型并分析意图：
- 文本选择：选中了什么内容？
- 元素移动：移动了什么？目标位置的意义？
- 窗口调整：调整了什么窗口？

输出示例：
"用户选中了一段代码注释，可能准备复制或删除"
```

#### Double Click Prompt

```
用户在 {window} 中双击了位置 ({x}, {y})。

请分析：
1. 双击了什么元素？
2. 双击通常意味着什么操作（打开、选中、编辑）？
3. 用一句话概括这个行为的意图。

输出示例：
"用户双击打开了 config.yaml 文件，准备修改配置"
```

### 3.3 键盘输入分析 Prompt

#### System Prompt

```
你是用户输入理解专家。分析键盘输入时，关注：
1. 输入的内容类型（代码/文档/命令/对话）
2. 输入的核心语义（在写什么、做什么）
3. 与当前任务的关联

不要逐字复述输入内容，而是提炼语义。
```

#### Analysis Prompt

```
用户在 {window} 中输入了以下内容：

```
{content}
```

请分析：
1. 这是什么类型的输入？
2. 核心内容是什么？（一句话概括）
3. 推断用户正在进行的任务。

输出示例：
"用户在编写 Python 函数，实现图像分析结果的 JSON 序列化"
```

### 3.4 时段聚合 Prompt

```
以下是用户在 {time_range} 的活动序列：

{activities}

请生成该时段的行为摘要：

1. **主题**：这段时间用户在做什么？（一句话）
2. **关键活动**：列出 2-3 个主要活动节点
3. **意图推断**：用户的目标是什么？
4. **上下文关联**：这与之前/之后的工作有什么联系？

输出要求：
- 使用自然语言，便于语义检索
- 避免罗列细节，突出高层理解
```

### 3.5 日级总结 Prompt

```
以下是用户 {date} 的各时段活动摘要：

{session_summaries}

请生成当日行为上下文报告，包含：

## 工作主题
- 列出 2-3 个主要工作主题，按时间段组织

## 关键活动
- 列出重要的活动节点（时间+内容+意义）

## 使用的工具和资源
- 应用程序、文件、网站等

## 决策和想法
- 任何可观察到的决策、笔记、想法

## 未完成事项
- 可推断的待办或中断的任务

输出要求：
- 格式为 Markdown
- 每个要点独立成句，便于分块检索
- 使用具体名词（项目名、文件名、功能名）
```

---

## 四、信息流转架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Capture Layer                           │
│  KeyLogger + MouseCapture + WindowTracker + Screenshot      │
└─────────────────────────────────────────────────────────────┘
                              ↓
                     raw.jsonl (事件流)
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Analysis Layer                           │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Image VL     │    │ Keyboard     │    │ Window       │  │
│  │ Analysis     │    │ Analysis     │    │ Context      │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│           ↓                  ↓                  ↓           │
│         意图推断 ←──────── 语义融合 ────────→ 活动关联      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Aggregation Layer                         │
│                                                             │
│  Event Sequence → Session Summary → Daily Summary           │
│       (分钟)          (小时)           (天)                 │
│                                                             │
│  去重 + 合并 + 提炼 → 高信息密度上下文                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Output Layer                             │
│                                                             │
│  ~/.openclaw/workspace/context/                             │
│  ├── YYYY-MM-DD.md          ← memory_search 主索引          │
│  ├── sessions/YYYY-MM-DD-HH.md  ← 细粒度上下文              │
│  └── artifacts/             ← 原始素材（按需引用）           │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    OpenClaw memory_search
                    (向量 + BM25 混合检索)
```

---

## 五、与 OpenClaw 集成

### 5.1 集成点

| OpenClaw 组件 | OpenCapture 对接方式 |
|--------------|---------------------|
| `memory_search` | 日摘要和小时记录直接被索引 |
| `MEMORY.md` | 可选：导出长期用户偏好/习惯 |
| `memory/YYYY-MM-DD.md` | 日摘要直接写入此位置 |
| 混合检索 | 输出使用自然语言，支持语义+关键词匹配 |
| ~400 token 分块 | 每个活动记录控制在合适长度 |

### 5.2 输出路径配置

```yaml
# ~/.opencapture/config.yaml
output:
  # OpenClaw workspace 路径
  openclaw_workspace: ~/.openclaw/workspace

  # 上下文输出目录（相对于 workspace）
  context_dir: context

  # 是否同时保留本地副本
  keep_local_copy: true
  local_dir: ~/opencapture
```

### 5.3 与 OpenClaw Memory 格式对齐

OpenClaw 的 memory 系统特点：

1. **文件优先**：Markdown 文件是唯一真相来源
2. **三层结构**：日常日志 / 持久记忆 / 会话记忆
3. **混合检索**：向量 (70%) + BM25 (30%)
4. **分块策略**：~400 tokens/chunk，~80 tokens 重叠
5. **预压缩刷新**：上下文满时自动保存重要记忆

OpenCapture 输出需要：

- 使用纯 Markdown 格式
- 每个活动记录控制在合适长度（便于分块）
- 使用自然语言描述（便于语义检索）
- 包含具体名词（便于关键词匹配）

---

## 六、配置模板

### 6.1 完整配置示例

```yaml
# ~/.opencapture/config.yaml

# LLM 提供商配置
llm:
  provider: openai  # openai, anthropic, ollama
  model: gpt-4o-mini

# 图像分析 prompt
prompts:
  image:
    system: |
      你是用户行为理解专家。分析截图时，重点输出：
      1. 用户正在做什么（动作+对象）
      2. 推断的意图或目标
      3. 与工作流的关联（如果能判断）

      输出格式要求：
      - 使用简洁的陈述句
      - 避免描述 UI 元素细节
      - 突出语义信息，便于后续检索

    click: |
      用户在 {window} 中点击了位置 ({x}, {y})。

      请分析：
      1. 点击了什么元素或功能？
      2. 这个操作的目的是什么？
      3. 用一句话概括这个行为的意图。

    dblclick: |
      用户在 {window} 中双击了位置 ({x}, {y})。

      请分析：
      1. 双击了什么元素？
      2. 双击通常意味着什么操作？
      3. 用一句话概括这个行为的意图。

    drag: |
      用户在 {window} 中从 ({x1}, {y1}) 拖动到 ({x2}, {y2})。

      请判断拖动类型并分析意图：
      - 文本选择：选中了什么内容？
      - 元素移动：移动了什么？
      - 窗口调整：调整了什么窗口？

# 键盘分析 prompt
  keyboard:
    system: |
      你是用户输入理解专家。分析键盘输入时，关注：
      1. 输入的内容类型（代码/文档/命令/对话）
      2. 输入的核心语义（在写什么、做什么）
      3. 与当前任务的关联

      不要逐字复述输入内容，而是提炼语义。

    prompt: |
      用户在 {window} 中输入了以下内容：

      ```
      {content}
      ```

      请分析：
      1. 这是什么类型的输入？
      2. 核心内容是什么？（一句话概括）
      3. 推断用户正在进行的任务。

# 聚合 prompt
  aggregation:
    session: |
      以下是用户在 {time_range} 的活动序列：

      {activities}

      请生成该时段的行为摘要：
      1. **主题**：这段时间用户在做什么？
      2. **关键活动**：列出 2-3 个主要活动节点
      3. **意图推断**：用户的目标是什么？

    daily: |
      以下是用户 {date} 的各时段活动摘要：

      {session_summaries}

      请生成当日行为上下文报告，包含：
      - 工作主题
      - 关键活动
      - 使用的工具和资源
      - 决策和想法
      - 未完成事项

# 输出配置
output:
  openclaw_workspace: ~/.openclaw/workspace
  context_dir: context
  keep_local_copy: true
  local_dir: ~/opencapture
```

---

## 七、实施计划

### Phase 1: Prompt 更新
- [ ] 更新 `src/opencapture/config/example.yaml` 中的 prompt 模板
- [ ] 修改 `src/opencapture/config.py` 支持新的配置结构

### Phase 2: 输出格式重构
- [ ] 修改 `src/opencapture/report_generator.py` 实现新的 Markdown 格式
- [ ] 新增小时级记录生成逻辑

### Phase 3: 聚合层实现
- [ ] 新增 `src/opencapture/aggregator.py` 模块
- [ ] 实现事件 → 时段 → 日级的多层聚合

### Phase 4: OpenClaw 集成
- [ ] 配置输出路径对接 OpenClaw workspace
- [ ] 测试 `memory_search` 检索效果
- [ ] 优化输出格式以提升检索质量

---

## 八、参考资料

- [OpenClaw Memory Documentation](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw GitHub Repository](https://github.com/openclaw/openclaw)
- [OpenClaw Memory System Deep Dive](https://snowan.gitbook.io/study-notes/ai-blogs/openclaw-memory-system-deep-dive)
