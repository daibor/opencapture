# OpenCapture

[![PyPI](https://img.shields.io/pypi/v/opencapture)](https://pypi.org/project/opencapture/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[English](README.md)

自动截图 + AI 图片理解工具。记录键盘输入、鼠标操作、麦克风音频，并使用 AI 分析所有内容。

## 功能特性

- **键盘记录** - 全局按键监听，按活跃窗口聚合，20 秒时间聚类
- **鼠标截图** - 支持单击、双击、拖拽检测，WebP 格式压缩
- **窗口追踪** - 自动检测活跃窗口，截图标注蓝色边框
- **麦克风采集** - 当外部应用使用麦克风时自动录制，通过 macOS AudioProcess API 识别进程
- **AI 分析** - 支持本地 Ollama 或远程 API（OpenAI、Anthropic Claude）
- **语音转文字** - 基于 Whisper 的音频转录
- **报告生成** - 从采集数据自动生成每日 Markdown 报告
- **隐私安全** - 所有数据默认本地处理存储

## 安装

**方式一：pip install**（推荐）

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

## 使用方法

### 采集模式

```bash
# 启动采集（前台运行）
opencapture

# 指定存储目录
opencapture -d ~/my-captures

# 或使用 Python 直接运行（从克隆的仓库）
python run.py
```

按 `Ctrl+C` 停止。

### 服务管理（macOS）

```bash
opencapture start                      # 后台启动服务
opencapture stop                       # 停止服务
opencapture restart                    # 重启服务
opencapture status                     # 查看运行状态和今日统计
opencapture log                        # 查看最近日志
opencapture log -f                     # 实时追踪日志
```

### 分析模式

```bash
# 分析今天的数据
opencapture --analyze today

# 分析指定日期
opencapture --analyze 2026-02-01
opencapture --analyze yesterday

# 分析单张图片
opencapture --image path/to/screenshot.webp

# 转录单个音频文件
opencapture --audio path/to/mic.wav

# 使用远程 API
export OPENAI_API_KEY=sk-xxx
opencapture --provider openai --analyze today

# 跳过报告生成
opencapture --analyze today --no-reports

# 检查 LLM 服务状态
opencapture --health-check

# 列出可用日期
opencapture --list-dates

# 查看帮助
opencapture --help
```

## 系统要求

- **macOS** 10.15+（采集 + 分析）
- **Linux / Windows**（仅分析功能）
- Python 3.11+
- 8GB+ 内存（本地 AI 分析需要）
- 10GB+ 磁盘空间（本地模型存储）

### macOS 权限

首次运行需在「系统设置 → 隐私与安全性」中授权：

| 权限 | 用途 |
|---|---|
| **辅助功能** | 监听键鼠事件 |
| **屏幕录制** | 截取屏幕 |
| **麦克风** | 音频录制（如启用） |

## 数据存储

默认存储位置：`~/opencapture/`

```
~/opencapture/
├── 2026-02-01/
│   ├── 2026-02-01.log                              # 统一日志
│   ├── click_103045_123_left_x800_y600.webp        # 单击截图
│   ├── dblclick_103046_456_left_x800_y600.webp     # 双击截图
│   ├── drag_103050_789_left_x100_y200_to_x500_y400.webp  # 拖拽截图
│   └── mic_103100_000_zoom_dur30.wav               # 麦克风录音
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
| 方向键 | ↑↓←→ |

## 配置

编辑 `~/.opencapture/config.yaml`：

```bash
vim ~/.opencapture/config.yaml
```

主要配置项：

| 配置项 | 说明 |
|---|---|
| `llm.default_provider` | LLM 提供商（`ollama` / `openai` / `anthropic`） |
| `llm.*.model` | 各提供商的模型选择 |
| `capture.output_dir` | 存储目录 |
| `capture.mic_enabled` | 启用麦克风采集 |
| `privacy.allow_online` | 允许远程 API 提供商 |
| `prompts.*` | 自定义分析提示词 |

环境变量：

| 变量 | 用途 |
|---|---|
| `OPENAI_API_KEY` | 启用 OpenAI |
| `ANTHROPIC_API_KEY` | 启用 Anthropic Claude |
| `OLLAMA_API_URL` | 自定义 Ollama API 地址 |
| `OLLAMA_MODEL` | Ollama 模型选择 |
| `OPENCAPTURE_ALLOW_ONLINE` | 允许远程提供商 |

## 卸载

```bash
pip uninstall opencapture
```

同时删除采集数据：`rm -rf ~/opencapture`
删除配置：`rm -rf ~/.opencapture`

## 隐私警告

本工具会记录所有键盘输入（包括密码）和屏幕内容。请：

- 确保存储目录访问权限安全
- 定期清理历史数据
- 仅用于个人用途
- 远程提供商需在配置中显式设置 `privacy.allow_online: true`

## 许可证

[MIT](LICENSE)
