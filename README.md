# OpenCapture

自动截图 + AI 图片理解工具。记录键盘输入、鼠标操作，并使用本地 AI 模型分析截图内容。

## 功能特性

- **键盘记录** - 全局按键监听，按窗口聚合，20 秒时间聚类
- **鼠标截图** - 支持单击、双击、拖拽检测，WebP 格式压缩
- **窗口追踪** - 自动检测活跃窗口，截图标注蓝色边框
- **AI 理解** - 使用 Qwen3-VL 本地模型分析截图内容
- **隐私安全** - 所有数据本地处理，不上传云端

## 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/opencapture/main/install.sh | bash
```

或克隆后手动安装：

```bash
git clone https://github.com/yourusername/opencapture.git
cd opencapture
./install.sh
```

## 使用方法

```bash
# 启动（带 AI 分析）
opencapture

# 启动（不带 AI 分析，更轻量）
opencapture --no-ai

# 分析已有截图
opencapture --analyze today

# 查看帮助
opencapture --help
```

或使用 Python 直接运行：

```bash
source venv/bin/activate
python run.py

# 指定存储目录
python run.py -d ~/my-captures
```

按 `Ctrl+C` 停止。

## 系统要求

- **macOS** 10.15+ 或 **Linux**（Ubuntu 20.04+）
- Python 3.9+
- 8GB+ 内存（AI 分析需要）
- 10GB+ 磁盘空间（模型存储）

### macOS 权限

首次运行需在「系统设置 → 隐私与安全性」中授权：
- **辅助功能** - 监听键鼠事件
- **屏幕录制** - 截取屏幕

授权后重启终端。

## 数据存储

默认存储位置：`~/auto-capture/`

```
~/auto-capture/
├── 2026-02-01/
│   ├── 2026-02-01.log                              # 统一日志
│   ├── click_103045_123_left_x800_y600.webp
│   ├── dblclick_103046_456_left_x800_y600.webp
│   ├── drag_103050_789_left_x100_y200_to_x500_y400.webp
│   ├── analysis.jsonl                              # AI 分析结果
│   └── analysis_*.json                             # 单张图片分析
└── 2026-02-02/
    └── ...
```

### 统一日志格式

键盘输入和鼠标截图记录在同一个日志文件，以三个换行分隔不同窗口：

```
[2026-02-01 10:23:40] Visual Studio Code | index.ts - my-project (com.microsoft.VSCode)
[10:23:45] hello world↩
[10:23:50] ⌘s
[10:23:51] 📷 click (800,600) click_102351_123_left_x800_y600.webp


[2026-02-01 10:25:32] Terminal | zsh (com.apple.Terminal)
[10:25:35] npm run dev↩
[10:25:40] 📷 click (500,400) click_102540_456_left_x500_y400.webp
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

### 截图标注

- **蓝色边框** - 当前活跃窗口
- **灰色半透明矩形** - 拖拽区域

## 配置

复制示例配置并修改：

```bash
cp config/example.yaml config/config.yaml
```

主要配置项：
- `qwen.enabled` - 启用/禁用 AI 分析
- `qwen.model` - 模型选择（7b/14b）
- `capture.output_dir` - 存储目录

或编辑 `src/auto_capture.py` 中的常量：

```python
# KeyLogger
CLUSTER_INTERVAL = 20      # 键盘聚类间隔（秒）

# MouseCapture
THROTTLE_MS = 100          # 截图节流（毫秒）
DRAG_THRESHOLD = 10        # 拖拽判定距离（像素）
DOUBLE_CLICK_INTERVAL = 400  # 双击判定间隔（毫秒）
IMAGE_QUALITY = 80         # WebP 压缩质量
```

## 卸载

```bash
./uninstall.sh
```

## 隐私警告

本工具会记录所有键盘输入（包括密码）和屏幕内容。请：
- 确保存储目录访问权限安全
- 定期清理历史数据
- 仅用于个人用途

## License

MIT
