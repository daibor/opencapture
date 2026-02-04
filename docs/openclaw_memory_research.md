# OpenClaw 个性化上下文管理系统分析

> 本文档记录对 OpenClaw 记忆系统的调研分析，作为 OpenCapture 设计的参考依据。

## 一、项目概述

OpenClaw 是一个开源的自主 AI 个人助手软件，运行在用户本地设备上并与消息平台集成。项目最初于 2025 年 11 月以 Clawdbot 名称发布，后因 Anthropic 商标请求更名为 Moltbot，2026 年初再次更名为 OpenClaw。GitHub 仓库已超过 149,000 stars。

- **GitHub**: https://github.com/openclaw/openclaw
- **官网**: https://openclaw.ai/
- **文档**: https://docs.openclaw.ai/

---

## 二、核心设计理念

OpenClaw 采用 **"文件优先"(File-First)** 的设计哲学：

> **Markdown 文件是唯一的真相来源**，AI 只能"记住"写入磁盘的内容。

这意味着：
- 没有复杂的专有格式，只有人类可读的文本文件
- 可版本控制、可人工检查、无供应商锁定
- 未保存的上下文会丢失

---

## 三、三层记忆架构

| 层级 | 文件位置 | 用途 | 加载策略 |
|------|----------|------|----------|
| **临时记忆** | `memory/YYYY-MM-DD.md` | 每日追加日志，记录日常活动 | 会话启动时加载今天+昨天 |
| **持久记忆** | `MEMORY.md` | 长期策划知识（偏好、决策、约定） | 仅私聊可访问，群聊不加载 |
| **会话记忆** | `sessions/YYYY-MM-DD-<slug>.md` | 自动索引的对话记录 | 通过 memory_search 检索 |

### 3.1 文件结构

```
~/.openclaw/workspace/  (或自定义 workspace root)
├── MEMORY.md                    # 长期记忆
├── memory/
│   ├── 2026-02-04.md           # 昨天的日志
│   └── 2026-02-05.md           # 今天的日志
└── sessions/
    └── 2026-02-05-openclaw-研究.md  # 会话记录
```

### 3.2 写入时机建议

- **持久事实和决策** → `MEMORY.md`
- **日常上下文和笔记** → `memory/YYYY-MM-DD.md`
- **用户主动请求保存** → 立即写入，不依赖 RAM

---

## 四、混合搜索实现

OpenClaw 结合两种检索方式，取**并集**（而非交集）：

```
finalScore = vectorWeight × vectorScore + textWeight × textScore
            (默认 70%)                    (默认 30%)
```

### 4.1 为什么需要混合搜索

| 搜索类型 | 优势 | 劣势 |
|----------|------|------|
| **向量搜索** | 语义相似（"我们决定用微服务"能匹配"架构决策是什么"） | 精确匹配差（commit hash、错误码） |
| **BM25 搜索** | 精确匹配（函数名、ID、错误码） | 语义理解差（换个说法就找不到） |

### 4.2 存储实现

- **SQLite 数据库**: `~/.openclaw/memory/<agentId>.sqlite`
- **向量存储**: 使用 `sqlite-vec` 扩展，余弦相似度
- **全文搜索**: SQLite FTS5 虚拟表
- **文件监听**: 1.5 秒防抖，会话启动或搜索时同步

### 4.3 数据库 Schema

```sql
-- chunks 表: 存储文本和 embedding
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    text TEXT,
    embedding BLOB  -- 1536 维向量
);

-- embedding_cache: 跨文件去重
CREATE TABLE embedding_cache (
    provider TEXT,
    model TEXT,
    content_hash TEXT,  -- SHA-256
    embedding BLOB,
    PRIMARY KEY (provider, model, content_hash)
);

-- FTS5 虚拟表: 全文搜索
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content=chunks);
```

---

## 五、Markdown 分块策略

### 5.1 分块参数

```
目标大小: ~400 tokens/chunk
重叠大小: ~80 tokens
```

### 5.2 滑动窗口算法

```
1. 按行读取 Markdown 文件
2. 累积 tokens 直到达到目标大小
3. 保持行边界完整（不在行中间切断）
4. 与前一个 chunk 保留 ~80 tokens 重叠
5. SHA-256 哈希去重，避免重复 embedding
```

### 5.3 为什么需要重叠

防止上下文在 chunk 边界断裂。例如：

```markdown
## 决策
我们决定采用微服务架构，原因如下：
--- chunk 边界 ---
1. 更好的可扩展性
2. 团队可以独立部署
```

没有重叠时，搜索"为什么选择微服务"可能只匹配到原因列表，丢失了上下文。

---

## 六、预压缩记忆刷新

### 6.1 问题背景

LLM 的上下文窗口有限。当 token 接近限制时，旧消息会被压缩（summarize and discard）。这是记忆丢失的关键时刻。

### 6.2 解决方案

OpenClaw 在压缩前触发一个**静默 agent 回合**，提示模型保存重要记忆：

```
触发条件: currentTokens ≥ contextWindow - reserveTokensFloor - softThresholdTokens
                                          (默认 20,000)         (默认 4,000)
```

### 6.3 配置选项

```json
{
  "compaction": {
    "memoryFlush": {
      "enabled": true,
      "softThresholdTokens": 4000,
      "systemPrompt": "你即将进行上下文压缩...",
      "prompt": "请将任何重要的、尚未保存的信息写入记忆文件..."
    }
  }
}
```

### 6.4 关键特性

- 使用 `NO_REPLY` 选项，用户看不到这个提示
- 每个压缩周期只运行一次
- 如果 workspace 只读则跳过

---

## 七、Embedding 提供商系统

### 7.1 自动选择优先级

```
1. local (如果 GGUF 路径存在)
2. openai (如果 API key 可用)
3. gemini (如果 GEMINI_API_KEY 可用)
4. 禁用
```

### 7.2 支持的后端

| 提供商 | 配置方式 | 特点 |
|--------|----------|------|
| **OpenAI** | API key + config | 支持 Batch API（成本降低 50%） |
| **Gemini** | `GEMINI_API_KEY` | 原生 embedding + 异步批处理 |
| **Local** | GGUF 路径或 `hf:` URI | 自动下载（默认模型约 600MB） |
| **Custom** | `remote.baseUrl`, `apiKey` | 支持 OpenRouter, vLLM, 代理 |

### 7.3 批处理优化

- SHA-256 去重，避免重复 embedding 相同内容
- OpenAI Batch API 成本降低 50%
- 并发批处理，自动降级
- Embedding 缓存防止冗余 API 调用

---

## 八、Memory 工具 API

### 8.1 可用工具

| 工具 | 用途 | 返回值 |
|------|------|--------|
| `memory_search` | 语义查询所有记忆文件 | 片段（~700 字符）、文件路径、行范围、评分、提供商 |
| `memory_get` | 按路径读取特定记忆文件 | 完整文件内容（仅 workspace 相对路径） |

### 8.2 重要行为

> **记忆不会自动注入每个提示**，agent 必须主动调用 `memory_search`。

这意味着：
- Agent 需要"意识到"何时需要检索记忆
- 未主动搜索的记忆不会影响回复
- 减少了不必要的上下文占用

### 8.3 引用配置

```json
{
  "memorySearch": {
    "citations": "auto"  // "auto" | "on" | "off"
  }
}
```

- `auto`: 根据上下文决定是否显示来源路径
- `on`: 始终显示
- `off`: 从不显示

---

## 九、会话管理

### 9.1 会话隔离

- **群聊**: 隔离会话，每个群独立上下文
- **私聊**: 合并到共享的 "main" 会话
- **激活模式**: mention-based（提及时响应）或 always-on（始终响应）

### 9.2 跨平台上下文

> 你可以在 WhatsApp 开始对话，然后在 Telegram 继续；AI 助手会保持完整的对话上下文。

### 9.3 实验性功能：会话索引

```json
{
  "memorySearch": {
    "experimental": { "sessionMemory": true },
    "sources": ["memory", "sessions"]
  }
}
```

- 异步索引会话记录（基于 delta 阈值）
- 通过 `memory_search` 可检索（不支持 `memory_get`）
- 每 agent 隔离，存储在 `~/.openclaw/agents/<agentId>/sessions/*.jsonl`

---

## 十、八种上下文管理技术

OpenClaw 使用八种技术来有效管理长期运行会话的记忆和上下文：

### 10.1 Memory Flush Before Compaction
压缩前刷新记忆（详见第六节）

### 10.2 Context Window Guards
上下文窗口保护，预留 reserve tokens

### 10.3 Tool Result Guard
工具结果保护，防止过大的工具输出占满上下文

### 10.4 Turn-Based History Limiting
基于轮次的历史限制

### 10.5 Cache-Aware Tool Result Pruning
缓存感知的工具结果修剪

### 10.6 Head/Tail Content Preservation
保留内容的头部和尾部（中间可丢弃）

### 10.7 Adaptive Chunk Ratio
自适应分块比例

### 10.8 Staged Summarization
分阶段摘要

> OpenClaw 不是截断（truncation），而是修剪（pruning）。截断是截肢：不管丢失什么都砍掉最旧的内容。修剪是手术：识别可丢弃的内容，保留语义相关的部分，并留下标记说明删除了什么。

---

## 十一、性能指标

| 指标 | 数值 |
|------|------|
| 本地 embedding 速度 | ~50 tokens/sec |
| OpenAI embedding 速度 | ~1000 tokens/sec（批处理） |
| 搜索延迟 | <100ms（10K chunks） |
| 索引大小 | ~5KB / 1K tokens（1536 维 embedding） |

---

## 十二、关键配置示例

```json
{
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": true,
        "provider": "openai",
        "model": "text-embedding-3-small",
        "remote": {
          "batch": { "enabled": true, "concurrency": 2 }
        },
        "query": {
          "hybrid": {
            "enabled": true,
            "vectorWeight": 0.7,
            "textWeight": 0.3
          }
        },
        "cache": { "enabled": true, "maxEntries": 50000 }
      },
      "compaction": {
        "memoryFlush": {
          "enabled": true,
          "softThresholdTokens": 4000
        }
      }
    }
  }
}
```

---

## 十三、对 OpenCapture 的启示

| OpenClaw 特性 | OpenCapture 借鉴 |
|--------------|-----------------|
| 文件作为真相来源 | 用 Markdown 存储分析记忆，便于人工检查和版本控制 |
| 混合搜索 | 结合语义+关键词检索历史分析报告 |
| 预压缩保存 | 在上下文压缩前自动提取关键信息 |
| 分层存储 | 日常活动日志 vs 长期用户偏好 |
| ~400 token 分块 | 每个活动记录控制在合适长度 |
| 自然语言描述 | 输出便于语义检索的行为描述 |

---

## 参考资料

- [OpenClaw GitHub Repository](https://github.com/openclaw/openclaw)
- [OpenClaw Memory Documentation](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw Memory System Deep Dive](https://snowan.gitbook.io/study-notes/ai-blogs/openclaw-memory-system-deep-dive)
- [OpenClaw Architecture Guide](https://rajvijayaraj.substack.com/p/openclaw-architecture-a-deep-dive)
- [8 Ways to Stop Agents from Losing Context](https://codepointer.substack.com/p/openclaw-stop-losing-context-8-techniques)
