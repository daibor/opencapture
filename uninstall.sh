#!/bin/bash
#
# OpenCapture 卸载脚本
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="$HOME/.opencapture"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/opencapture"

echo ""
echo -e "${YELLOW}OpenCapture 卸载程序${NC}"
echo ""

# 确认卸载
echo "将删除以下内容:"
echo "  • 程序文件: $INSTALL_DIR"
echo "  • 启动脚本: $BIN_DIR/opencapture"
echo ""
echo -e "${YELLOW}注意: 截图数据 ($DATA_DIR) 不会被删除${NC}"
echo ""

read -p "是否继续卸载？[y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "卸载已取消"
    exit 0
fi

echo ""

# 停止运行中的进程
if pgrep -f "auto_capture" > /dev/null; then
    echo "正在停止 OpenCapture..."
    pkill -f "auto_capture" 2>/dev/null || true
fi

# 删除程序文件
if [[ -d "$INSTALL_DIR" ]]; then
    echo "删除程序文件..."
    rm -rf "$INSTALL_DIR"
fi

# 删除启动脚本
if [[ -f "$BIN_DIR/opencapture" ]]; then
    echo "删除启动脚本..."
    rm -f "$BIN_DIR/opencapture"
fi

echo ""
echo -e "${GREEN}卸载完成！${NC}"
echo ""
echo "以下内容需要手动处理:"
echo ""
echo "1. 如需删除截图数据:"
echo "   rm -rf $DATA_DIR"
echo ""
echo "2. 如需卸载 Ollama 和模型:"
echo "   ollama rm qwen2-vl:7b"
echo "   brew uninstall ollama  # macOS"
echo ""
echo "3. 清理 shell 配置文件中的 PATH 设置"
echo ""