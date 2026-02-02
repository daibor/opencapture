# OpenCapture

自动截图 + AI 图片理解工具。记录键盘输入、鼠标操作，并使用本地 AI 模型分析截图内容。

## 功能特性

- **键盘记录** - 记录全局键盘输入，按窗口和时间聚合
- **鼠标截图** - 点击/双击/拖拽时自动截图，标注活动窗口
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

## 系统要求

- **macOS** 10.15+ 或 **Linux**（Ubuntu 20.04+）
- Python 3.9+
- 8GB+ 内存（AI 分析需要）
- 10GB+ 磁盘空间（模型存储）

### macOS 权限

首次运行需在「系统偏好设置 → 安全性与隐私 → 隐私」中授权：
- **辅助功能** - 监听键鼠事件
- **屏幕录制** - 截取屏幕

## 数据存储

默认存储位置：`~/auto-capture/`

```
~/auto-capture/
├── 2024-02-03/
│   ├── keys.log                    # 键盘日志
│   ├── click_103045_left_x800_y600.webp
│   ├── analysis.jsonl              # AI 分析结果
│   └── analysis_*.json             # 单张图片分析
```

## 配置

复制示例配置并修改：

```bash
cp config/example.yaml config/config.yaml
```

主要配置项：
- `qwen.enabled` - 启用/禁用 AI 分析
- `qwen.model` - 模型选择（7b/14b）
- `capture.output_dir` - 存储目录

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