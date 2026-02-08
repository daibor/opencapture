# Agent-Based Analysis Pipeline Design

> OpenCapture 的分析流程从脚本化管道重构为 agent 驱动的工具调用循环，日志文件作为入口，MEMORY.md 作为长期记忆载体。

## 一、现状与问题

当前 `Analyzer.analyze_day()` 是一个**硬编码流水线**：

```
images_batch → audios_batch → parse_log → generate_reports
```

问题：
- 图片、音频、日志三者独立分析，无交叉引用
- 日志中的键盘输入不经过 LLM（仅原文出现在报告中）
- 无法根据上下文动态调整分析策略（如发现用户在开会，则重点分析音频）
- 无长期记忆，每天的分析互不关联

## 二、目标架构

```
                    ┌─────────────────────┐
                    │     Agent Loop      │
                    │  (LLM + Tool Calls) │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
        │  read_log  │   │analyze_img│   │transcribe │
        │            │   │  (VL)     │   │  (ASR)    │
        └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
              │                │                │
              │          .webp → .txt      .wav → .txt
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   analyze_text      │
                    │   (LLM for log      │
                    │    blocks, audio     │
                    │    transcripts,      │
                    │    daily summary)    │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │   write_file        │
                    │   (reports,         │
                    │    MEMORY.md)       │
                    └─────────────────────┘
```

核心变化：**分析逻辑从 Python 函数移到 agent 的推理层**。Agent 读取日志，自主决定分析顺序和策略，通过工具调用完成实际操作。

## 三、处理流程

### 3.1 总体流程

```
1. Agent 加载 MEMORY.md（长期记忆）
2. Agent 读取 YYYY-MM-DD.log（当日入口）
3. Agent 解析日志，发现引用的截图和音频文件
4. Agent 逐个处理：
   a. 截图 → analyze_image → 写入 .txt
   b. 音频 → transcribe_audio → analyze_text → 写入 .txt
   c. 日志块 → analyze_text → 理解上下文
5. Agent 综合所有分析结果，生成日报
6. Agent 提取长期重要事项，更新 MEMORY.md
```

### 3.2 截图处理流程

```
click_143052_123_left_x500_y300.webp
        │
        ▼
┌─────────────────────────────────────┐
│ analyze_image(path, prompt)         │
│                                     │
│ 输入: .webp 文件路径 + 上下文 prompt │
│ 处理: VL 模型（qwen3-vl / gpt-4o） │
│ 输出: 行为意图描述                   │
└─────────────────┬───────────────────┘
                  ▼
click_143052_123_left_x500_y300.txt
```

**txt 格式**:
```
timestamp: 14:30:52
action: click
position: (500, 300)
window: Chrome | GitHub - Pull Requests
---
用户在 GitHub PR 列表页点击了一个 Pull Request 标题，
准备查看代码变更详情。当前正在进行代码审查工作。
```

Agent 在调用 `analyze_image` 时，会将日志上下文（当前在哪个 app、之前做了什么）作为 prompt 的一部分传入，使 VL 模型的分析更准确。

### 3.3 音频处理流程

```
mic_143500_789_zoom_dur300.wav
        │
        ▼
┌─────────────────────────────────┐
│ transcribe_audio(path)          │
│                                 │
│ 输入: .wav 文件路径             │
│ 处理: ASR (Whisper API)        │
│ 输出: 原始转录文本              │
└─────────────────┬───────────────┘
                  ▼
┌─────────────────────────────────┐
│ analyze_text(transcript, prompt)│
│                                 │
│ 输入: 转录文本 + 上下文         │
│ 处理: LLM 分析                  │
│ 输出: 会议/通话摘要             │
└─────────────────┬───────────────┘
                  ▼
mic_143500_789_zoom_dur300.txt
```

**txt 格式**:
```
timestamp: 14:35:00
app: Zoom
duration: 300s
---
[transcription]
团队站会讨论了 OpenCapture 的分析模块重构进度。
主要结论：1) 决定采用 agent 架构替代流水线；
2) 下周三前完成原型；3) 需要评估 Ollama 本地推理延迟。

[summary]
项目周会，讨论技术架构决策和排期。涉及 OpenCapture 分析模块重构。
```

两阶段设计的原因：ASR 输出的原始文本通常冗长且含口误、重复，需要 LLM 提炼出结构化的摘要。

### 3.4 日志分析流程

日志是 agent 的**入口文件**。Agent 不是简单地把整个日志扔给 LLM，而是：

```
YYYY-MM-DD.log
      │
      ▼
Agent 解析日志结构
      │
      ├── 识别窗口切换块（按 \n\n\n 分隔）
      ├── 发现引用的 .webp 文件 → 调用 analyze_image
      ├── 发现引用的 .wav 文件 → 调用 transcribe_audio + analyze_text
      │
      ▼
Agent 逐块分析键盘输入
      │
      ├── 窗口块 1: VSCode | analyzer.py → 分析代码编辑意图
      ├── 窗口块 2: Chrome | GitHub → 分析浏览行为
      ├── 窗口块 3: Terminal | zsh → 分析命令操作
      │
      ▼
Agent 综合分析：日志 + 截图分析结果 + 音频摘要
      │
      ▼
生成日报 + 更新 MEMORY.md
```

关键：Agent 可以在分析某个窗口块时，主动读取该时段的截图 .txt 来获得视觉上下文，实现**跨模态关联**。

## 四、Agent 工具定义

### 4.1 工具清单

| 工具 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `read_file` | path | 文件内容 | 读取日志、.txt sidecar、MEMORY.md |
| `list_files` | dir, pattern | 文件列表 | 列出目录下的 .webp / .wav / .txt |
| `analyze_image` | image_path, prompt | 分析文本 | VL 模型分析截图 |
| `transcribe_audio` | audio_path | 转录文本 | ASR 语音转文字 |
| `analyze_text` | text, prompt | 分析文本 | LLM 文本分析 |
| `write_file` | path, content | 成功/失败 | 写入 .txt sidecar、报告、MEMORY.md |

### 4.2 工具定义（JSON Schema 格式，兼容 OpenClaw）

```json
{
  "name": "analyze_image",
  "description": "Analyze a screenshot using a vision-language model. Returns a text description of user behavior and intent.",
  "parameters": {
    "type": "object",
    "properties": {
      "image_path": {
        "type": "string",
        "description": "Absolute path to the .webp screenshot file"
      },
      "context": {
        "type": "string",
        "description": "Context from the log: which app, what the user was doing before/after"
      }
    },
    "required": ["image_path"]
  }
}
```

```json
{
  "name": "transcribe_audio",
  "description": "Transcribe an audio recording using ASR (speech-to-text). Returns raw transcription.",
  "parameters": {
    "type": "object",
    "properties": {
      "audio_path": {
        "type": "string",
        "description": "Absolute path to the .wav audio file"
      }
    },
    "required": ["audio_path"]
  }
}
```

```json
{
  "name": "analyze_text",
  "description": "Analyze text content using an LLM. Used for log analysis, audio transcript summarization, and report generation.",
  "parameters": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "The text to analyze"
      },
      "task": {
        "type": "string",
        "enum": ["summarize_transcript", "analyze_log_block", "generate_daily_report", "extract_memory"],
        "description": "The analysis task type"
      },
      "context": {
        "type": "string",
        "description": "Additional context (window info, time range, prior analysis results)"
      }
    },
    "required": ["text", "task"]
  }
}
```

### 4.3 OpenClaw Skill 工具桥接

当 OpenClaw agent 调用 OpenCapture skill 时，走的是 shell 命令路径：

```
OpenClaw Agent
  → exec("opencapture analyze today")        # 触发 OpenCapture 内部 agent
  → exec("cat ~/opencapture/reports/2026-02-08.md")  # 读取结果
```

当 OpenCapture 内部 agent 运行时，直接调用 Python 工具函数（不走 shell）：

```
OpenCapture Agent Loop
  → analyze_image(path, context)     # 直接调用 LLMRouter.analyze_image()
  → transcribe_audio(path)           # 直接调用 ASRClient.transcribe()
  → analyze_text(text, task)         # 直接调用 LLMRouter.analyze_text()
```

两层 agent 互不干扰，通过文件系统（日报 + MEMORY.md）交换信息。

## 五、MEMORY.md 设计

### 5.1 位置与作用

```
~/opencapture/MEMORY.md    ← 长期记忆文件，agent 每次分析时加载
```

MEMORY.md 是 OpenCapture analysis agent 的**持久记忆**，跨天保持。每次分析时：
1. Agent 加载 MEMORY.md 作为上下文
2. Agent 利用历史记忆来更好地理解当天活动
3. 分析完成后，Agent 将重要发现回填到 MEMORY.md

### 5.2 文件格式

```markdown
# OpenCapture Memory

> Auto-maintained by the analysis agent. Manual edits are preserved.

## User Profile

- Primary work: Software development (Python, TypeScript)
- Main projects: OpenCapture, internal API service
- Work hours: typically 09:00-18:00, occasional evening sessions
- Languages: Chinese (primary), English (code/docs)

## Recurring Patterns

- Daily standup on Zoom at 10:00 (~15 min)
- Code review in GitHub PRs most afternoons
- Uses VSCode for development, Chrome for research
- Frequently switches between Claude Code and VSCode during design work

## Active Projects

- **OpenCapture**: Refactoring analysis pipeline to agent-based architecture
  - Last worked: 2026-02-08
  - Key files: src/opencapture/analyzer.py, src/opencapture/agent.py
  - Status: Design phase, prototype due next Wednesday

- **Internal API**: Maintenance mode
  - Last worked: 2026-02-05
  - Key files: api/routes/, api/middleware/

## Notable Decisions

- 2026-02-08: Decided to use agent architecture instead of scripted pipeline for analysis
- 2026-02-06: Chose Ollama qwen3-vl:4b as default local vision model
- 2026-02-04: Adopted OpenClaw SKILL.md format for ecosystem integration

## Pending Items

- [ ] Evaluate local ASR latency with faster-whisper
- [ ] Test MEMORY.md update loop for data drift
- [ ] Draft weekly report aggregation design
```

### 5.3 更新策略

Agent 在完成每日分析后，执行一个专用的 `extract_memory` 步骤：

```
Agent 输入:
  - 当天日报内容
  - 当前 MEMORY.md

Agent 指令:
  对比当天活动与现有记忆，更新以下内容（仅在有变化时更新）：
  1. User Profile — 是否有新的工作习惯或偏好？
  2. Recurring Patterns — 是否有新的重复模式？
  3. Active Projects — 项目状态是否有变化？新项目？
  4. Notable Decisions — 是否做了重要决策？
  5. Pending Items — 是否有新的待办？已完成的待办？

  规则：
  - 保留现有内容，不要删除人工编辑
  - 仅追加或更新有变化的条目
  - 每个条目标注日期
  - 控制总长度在 2000 tokens 以内（淘汰过旧条目）
```

### 5.4 与 OpenClaw MEMORY.md 的关系

```
~/opencapture/MEMORY.md          ← OpenCapture agent 的记忆（活动模式、项目状态）
~/.openclaw/workspace/MEMORY.md  ← OpenClaw agent 的记忆（用户偏好、对话历史）
```

两者是**独立的**。OpenClaw 通过 OpenCapture skill 间接消费分析结果（读取日报），不直接读取 OpenCapture 的 MEMORY.md。

如果用户希望深度集成，可以配置 OpenCapture 将日报同时写入 OpenClaw 的 memory 目录：

```yaml
# ~/.opencapture/config.yaml
reports:
  output_dir: reports
  # 可选：同步到 OpenClaw workspace
  openclaw_sync_dir: ~/.openclaw/workspace/memory
```

这样 OpenClaw 的 `memory_search` 可以直接检索 OpenCapture 的日报内容。

## 六、Agent Loop 实现

### 6.1 执行模型

```python
class AnalysisAgent:
    """Agent-based daily analysis with tool-calling loop."""

    def __init__(self, config: Config, llm_router: LLMRouter):
        self.config = config
        self.llm = llm_router
        self.tools = {
            "read_file": self._tool_read_file,
            "list_files": self._tool_list_files,
            "analyze_image": self._tool_analyze_image,
            "transcribe_audio": self._tool_transcribe_audio,
            "analyze_text": self._tool_analyze_text,
            "write_file": self._tool_write_file,
        }

    async def analyze_day(self, date_str: str) -> dict:
        """Run the agent loop for a full day analysis."""
        date_dir = self._resolve_date_dir(date_str)
        memory = self._load_memory()
        log_content = self._read_log(date_dir, date_str)

        # System prompt with tool definitions and instructions
        system = self._build_system_prompt(memory)

        # Initial user message: the day's log
        messages = [
            {"role": "user", "content": self._build_analysis_request(
                date_str, log_content, date_dir
            )}
        ]

        # Agent loop: LLM generates tool calls, we execute them,
        # feed results back, repeat until LLM stops calling tools
        while True:
            response = await self.llm.chat(system, messages)

            if not response.tool_calls:
                # Agent is done — final response is the daily report
                break

            # Execute tool calls and append results
            for tool_call in response.tool_calls:
                result = await self._execute_tool(tool_call)
                messages.append({"role": "tool", "content": result})

            messages.append({"role": "assistant", "content": response.content})

        return self._parse_final_output(response.content)
```

### 6.2 System Prompt 结构

```
你是 OpenCapture 的分析 agent。你的任务是分析用户一天的桌面活动数据，
生成行为洞察报告，并维护长期记忆。

## 可用工具

{tool_definitions}

## 分析步骤

1. 阅读日志文件，理解当天活动轮廓
2. 列出当日目录中的截图和音频文件
3. 对每张未分析的截图调用 analyze_image，传入日志上下文
4. 对每个未转录的音频调用 transcribe_audio，然后用 analyze_text 生成摘要
5. 综合所有分析结果（截图描述、音频摘要、键盘输入），生成日报
6. 对比 MEMORY.md 中的长期记忆，提取新的重要事项并更新

## 长期记忆

以下是用户的历史活动记忆，帮助你更好地理解当天活动：

{memory_content}

## 分析要求

- 理解用户意图，而非罗列表面操作
- 关联前后事件，形成连贯叙事
- 识别跨模态信息（日志中提到的文件 + 对应截图 + 相关音频）
- 使用具体名词（项目名、文件名、功能名），便于后续检索
- 对敏感信息（密码、token）脱敏处理
```

### 6.3 跨模态关联示例

Agent 在日志中看到：

```
[14:30:52] Chrome | GitHub - Pull Requests (com.google.Chrome)
[14:30:55] 📷 click (500, 300) click_143055_123_left_x500_y300.webp
[14:31:10] ⌨️ LGTM, nice refactoring of the config module
```

Agent 的行为：

1. 读取这个窗口块，理解用户在 GitHub 做代码审查
2. 调用 `analyze_image("click_143055_123_left_x500_y300.webp", context="User is reviewing a PR on GitHub")`
3. 截图分析结果说 "用户在查看一个关于 config 模块重构的 PR diff"
4. 结合键盘输入 "LGTM, nice refactoring"，agent 理解到用户审核通过了这个 PR
5. 写入日报："14:30 — 在 GitHub 审查并通过了 config 模块重构的 Pull Request"

这种关联在硬编码管道中无法实现，因为截图分析和键盘输入分析是独立的。

## 七、并发与性能

### 7.1 分析策略

图片和音频可以并发处理（互不依赖），但需要限制并发数避免压垮 LLM 服务：

```
Phase 1 — 素材分析（可并发）
├── analyze_image × N (concurrency=3)
├── transcribe_audio × M (concurrency=2)
│     └── analyze_text per transcript (sequential after transcription)
│
Phase 2 — 日志分析（顺序，依赖 Phase 1 的 .txt 结果）
├── read .txt sidecars for cross-modal context
├── analyze log blocks with screenshot/audio context
│
Phase 3 — 综合（顺序，依赖 Phase 1 + 2）
├── generate daily report
└── update MEMORY.md
```

### 7.2 幂等性

- 已存在 .txt sidecar 的文件跳过（与当前行为一致）
- MEMORY.md 更新是 merge 操作，非覆盖
- 日报可重新生成（覆盖旧报告）

### 7.3 增量分析

Agent 可以检测 "上次分析以来新增的文件"，只处理增量：

```python
def _get_unprocessed_files(self, date_dir: Path) -> dict:
    images = [f for f in date_dir.glob("*.webp")
              if not f.with_suffix(".txt").exists()]
    audios = [f for f in date_dir.glob("mic_*.wav")
              if not f.with_suffix(".txt").exists()]
    return {"images": images, "audios": audios}
```

## 八、Agent vs 脚本模式

提供两种运行模式，用户可选择：

```yaml
# ~/.opencapture/config.yaml
analysis:
  mode: agent     # "agent" | "pipeline"
```

| 维度 | Pipeline 模式（现有） | Agent 模式（新增） |
|------|----------------------|-------------------|
| 分析逻辑 | Python 函数硬编码 | LLM 推理 + 工具调用 |
| 跨模态关联 | 无 | 有（截图+日志+音频） |
| 长期记忆 | 无 | MEMORY.md |
| LLM 调用次数 | N_images + 1_summary | N_images + N_audios + ~10_log_blocks + 1_report + 1_memory |
| 成本 | 低 | 较高（更多 LLM 调用） |
| 离线可用 | Ollama 即可 | 需要支持 tool-calling 的模型 |
| 可预测性 | 高（确定性流程） | 中（agent 可能选择不同路径） |

保留 pipeline 模式作为 fallback，特别是在 Ollama 等本地模型不支持 tool-calling 时。

## 九、与 OpenClaw 的对接

### 9.1 两层 Agent 架构

```
┌────────────────────────────────────────────┐
│              OpenClaw Agent                 │
│                                            │
│  用户: "帮我看看今天做了什么"                │
│    ↓                                       │
│  Agent 读取 SKILL.md 指令                   │
│    ↓                                       │
│  exec("opencapture analyze today")          │
│    ↓                                       │
│  ┌──────────────────────────────────────┐  │
│  │       OpenCapture Analysis Agent     │  │
│  │                                      │  │
│  │  read_log → analyze_image ×N         │  │
│  │           → transcribe_audio ×M      │  │
│  │           → analyze log blocks       │  │
│  │           → generate report          │  │
│  │           → update MEMORY.md         │  │
│  └──────────────────────────────────────┘  │
│    ↓                                       │
│  exec("cat ~/opencapture/reports/today.md") │
│    ↓                                       │
│  Agent 将报告摘要返回给用户                  │
└────────────────────────────────────────────┘
```

### 9.2 OpenClaw memory 同步（可选）

```
~/opencapture/
├── MEMORY.md                           ← OpenCapture agent 的记忆
├── 2026-02-08/
│   ├── 2026-02-08.log
│   ├── *.webp + *.txt
│   └── *.wav + *.txt
└── reports/
    └── 2026-02-08.md                   ← 日报

         │ (配置 openclaw_sync_dir 后)
         ▼

~/.openclaw/workspace/memory/
└── 2026-02-08-opencapture.md           ← OpenClaw 可检索的日报副本
```

### 9.3 更新 SKILL.md

Agent 模式上线后，skill 的 "When to Use" 部分新增：

```markdown
## Analysis Modes

OpenCapture supports two analysis modes:

- **Pipeline mode** (default): Fast, deterministic. Analyzes images and audio
  independently, generates reports.
  `opencapture analyze today`

- **Agent mode**: Deeper analysis with cross-modal correlation and long-term
  memory. Reads the log as entry point, correlates screenshots with keyboard
  input, maintains MEMORY.md across sessions.
  `opencapture analyze today --mode agent`
```

## 十、文件系统布局（最终态）

```
~/opencapture/
├── MEMORY.md                              ← 长期记忆（agent 维护）
├── 2026-02-08/
│   ├── 2026-02-08.log                     ← 当日统一日志（入口文件）
│   ├── click_143055_123_left_x500_y300.webp    ← 截图
│   ├── click_143055_123_left_x500_y300.txt     ← VL 分析结果
│   ├── dblclick_150200_456_left_x200_y100.webp
│   ├── dblclick_150200_456_left_x200_y100.txt
│   ├── mic_100030_789_zoom_dur900.wav          ← 音频录制
│   └── mic_100030_789_zoom_dur900.txt          ← ASR + LLM 分析结果
├── 2026-02-07/
│   └── ...
└── reports/
    ├── 2026-02-08.md                      ← 日报（agent 生成）
    ├── 2026-02-08_images.md               ← 图片分析详情（可选）
    └── 2026-02-07.md
```

## 十一、实施路径

### Phase 1: 工具层

在现有 `LLMRouter` 基础上封装 agent 可调用的工具函数，每个工具返回纯文本结果。

涉及文件:
- 新增 `src/opencapture/tools.py` — 工具注册与执行
- 修改 `src/opencapture/llm_client.py` — 添加 `chat()` 方法支持 tool-calling

### Phase 2: Agent Loop

实现核心 agent 循环，支持 tool-calling 模型（OpenAI / Anthropic / Ollama with tool support）。

涉及文件:
- 新增 `src/opencapture/agent.py` — AnalysisAgent 类
- 新增 `src/opencapture/prompts/agent_system.md` — system prompt 模板

### Phase 3: MEMORY.md

实现长期记忆的加载、更新逻辑。

涉及文件:
- 在 `src/opencapture/agent.py` 中添加 memory 相关方法
- Agent system prompt 中包含 memory 更新指令

### Phase 4: CLI 集成

将 agent 模式接入 CLI。

涉及文件:
- 修改 `src/opencapture/cli.py` — 添加 `--mode agent` 选项
- 修改 `src/opencapture/analyzer.py` — 根据 mode 选择 pipeline 或 agent

### Phase 5: OpenClaw 对接

更新 skill 定义，添加 memory 同步配置。

涉及文件:
- 修改 `skills/opencapture/SKILL.md`
- 修改 `src/opencapture/config.py` — 添加 openclaw 相关配置项
