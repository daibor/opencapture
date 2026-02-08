# OpenCapture

[English](#english) | [中文](#中文)

---

## English

Automatic screenshot + AI understanding tool. Records keyboard input, mouse actions, and uses AI to analyze screenshot content.

### Features

- **Keyboard Logging** - Global key listening, window aggregation, 20-second time clustering
- **Mouse Screenshots** - Single click, double click, drag detection, WebP compression
- **Window Tracking** - Auto-detect active window, blue border annotation
- **AI Analysis** - Local Ollama or remote APIs (OpenAI, Claude)
- **Privacy First** - All data processed and stored locally

### Install

**Option 1: pip install** (recommended for Python users)

```bash
pip install opencapture
```

**Option 2: Clone and develop**

```bash
git clone https://github.com/daibor/opencapture.git
cd opencapture
pip install -e ".[dev]"
```

**Option 3: Download .app** (macOS)

Download from [GitHub Releases](https://github.com/daibor/opencapture/releases).

### Usage

```bash
# Start capture (foreground)
opencapture

# Service management (macOS)
opencapture start                      # Start as background service
opencapture stop                       # Stop service
opencapture status                     # Show running state

# Analyze existing screenshots
opencapture --analyze today
opencapture --analyze 2026-02-01

# Analyze single image
opencapture --image path/to/screenshot.webp

# Use remote API
export OPENAI_API_KEY=sk-xxx
opencapture --provider openai --analyze today

# Show help
opencapture --help
```

Or run directly with Python (from cloned repo):

```bash
python run.py
python run.py -d ~/my-captures
```

Press `Ctrl+C` to stop.

### System Requirements

- **macOS** 10.15+ (capture + analysis)
- **Linux / Windows** (analysis only)
- Python 3.11+
- 8GB+ RAM (for AI analysis)
- 10GB+ disk space (for model storage)

#### macOS Permissions

First run requires authorization in System Settings > Privacy & Security:
- **Accessibility** - For keyboard/mouse event listening
- **Screen Recording** - For screen capture
- **Microphone** - For audio recording (if enabled)

### Data Storage

Default location: `~/opencapture/`

```
~/opencapture/
├── 2026-02-01/
│   ├── 2026-02-01.log                              # Unified log
│   ├── click_103045_123_left_x800_y600.webp
│   ├── dblclick_103046_456_left_x800_y600.webp
│   └── drag_103050_789_left_x100_y200_to_x500_y400.webp
├── reports/
│   ├── 2026-02-01.md                               # Daily report
│   └── 2026-02-01_images.md                        # Image analysis
└── 2026-02-02/
    └── ...
```

### Configuration

Edit `~/.opencapture/config.yaml` to customize:

```bash
vim ~/.opencapture/config.yaml
```

Key settings:
- `llm.default_provider` - LLM provider (ollama/openai/anthropic)
- `llm.*.model` - Model selection
- `capture.output_dir` - Storage directory
- `prompts.*` - Custom analysis prompts

Environment variables:
- `OPENAI_API_KEY` - Enable OpenAI
- `ANTHROPIC_API_KEY` - Enable Claude

### Uninstall

```bash
pip uninstall opencapture
```

To also remove captured data: `rm -rf ~/opencapture`
To remove config: `rm -rf ~/.opencapture`

### Privacy Warning

This tool records all keyboard input (including passwords) and screen content. Please:
- Ensure storage directory access is secured
- Regularly clean up historical data
- Use for personal purposes only

---

## 中文

自动截图 + AI 图片理解工具。记录键盘输入、鼠标操作，并使用 AI 分析截图内容。

### 功能特性

- **键盘记录** - 全局按键监听，按窗口聚合，20 秒时间聚类
- **鼠标截图** - 支持单击、双击、拖拽检测，WebP 格式压缩
- **窗口追踪** - 自动检测活跃窗口，截图标注蓝色边框
- **AI 分析** - 支持本地 Ollama 或远程 API（OpenAI、Claude）
- **隐私安全** - 所有数据本地处理存储

### 安装

**方式一：pip install**（推荐 Python 用户）

```bash
pip install opencapture
```

**方式二：克隆开发**

```bash
git clone https://github.com/daibor/opencapture.git
cd opencapture
pip install -e ".[dev]"
```

**方式三：下载 .app**（macOS）

从 [GitHub Releases](https://github.com/daibor/opencapture/releases) 下载。

### 使用方法

```bash
# 启动采集（前台运行）
opencapture

# 服务管理（macOS）
opencapture start                      # 后台启动
opencapture stop                       # 停止服务
opencapture status                     # 查看运行状态

# 分析已有截图
opencapture --analyze today
opencapture --analyze 2026-02-01

# 分析单张图片
opencapture --image path/to/screenshot.webp

# 使用远程 API
export OPENAI_API_KEY=sk-xxx
opencapture --provider openai --analyze today

# 查看帮助
opencapture --help
```

或使用 Python 直接运行（从克隆的仓库）：

```bash
python run.py
python run.py -d ~/my-captures
```

按 `Ctrl+C` 停止。

### 系统要求

- **macOS** 10.15+（采集 + 分析）
- **Linux / Windows**（仅分析功能）
- Python 3.11+
- 8GB+ 内存（AI 分析需要）
- 10GB+ 磁盘空间（模型存储）

#### macOS 权限

首次运行需在「系统设置 → 隐私与安全性」中授权：
- **辅助功能** - 监听键鼠事件
- **屏幕录制** - 截取屏幕
- **麦克风** - 音频录制（如启用）

### 数据存储

默认存储位置：`~/opencapture/`

```
~/opencapture/
├── 2026-02-01/
│   ├── 2026-02-01.log                              # 统一日志
│   ├── click_103045_123_left_x800_y600.webp
│   ├── dblclick_103046_456_left_x800_y600.webp
│   └── drag_103050_789_left_x100_y200_to_x500_y400.webp
├── reports/
│   ├── 2026-02-01.md                               # 每日报告
│   └── 2026-02-01_images.md                        # 图片分析
└── 2026-02-02/
    └── ...
```

### 日志格式

键盘输入和鼠标截图记录在同一日志文件，以三个换行分隔不同窗口：

```
[2026-02-01 10:23:40] Visual Studio Code | index.ts - my-project (com.microsoft.VSCode)
[10:23:45] hello world↩
[10:23:50] ⌘s
[10:23:51] 📷 click (800,600) click_102351_123_left_x800_y600.webp


[2026-02-01 10:25:32] Terminal | zsh (com.apple.Terminal)
[10:25:35] npm run dev↩
[10:26:00] ⌃c
```

### 按键符号

| 键 | 符号 |
|---|---|
| Command | ⌘ |
| Control | ⌃ |
| Option | ⌥ |
| Shift | ⇧ |
| Enter | ↩ |
| Tab | ⇥ |
| Backspace | ⌫ |
| Escape | ⎋ |
| Arrow Keys | ↑↓←→ |

### 配置

编辑 `~/.opencapture/config.yaml`：

```bash
vim ~/.opencapture/config.yaml
```

主要配置项：
- `llm.default_provider` - LLM 提供商 (ollama/openai/anthropic)
- `llm.*.model` - 模型选择
- `capture.output_dir` - 存储目录
- `prompts.*` - 自定义分析提示词

环境变量：
- `OPENAI_API_KEY` - 启用 OpenAI
- `ANTHROPIC_API_KEY` - 启用 Claude

### 卸载

```bash
pip uninstall opencapture
```

同时删除采集数据：`rm -rf ~/opencapture`
删除配置：`rm -rf ~/.opencapture`

### 隐私警告

本工具会记录所有键盘输入（包括密码）和屏幕内容。请：
- 确保存储目录访问权限安全
- 定期清理历史数据
- 仅用于个人用途

---

## License

MIT
