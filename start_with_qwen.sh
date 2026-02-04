#!/bin/bash
#
# 快速启动脚本 - 带 Qwen3-VL 图片理解功能
#

set -e

echo "=========================================="
echo "OpenCapture + Qwen3-VL 启动脚本"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    echo "请安装 Python 3.8 或更高版本"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"

# 检查 Ollama
check_ollama() {
    if ! command -v ollama &> /dev/null; then
        echo ""
        echo "⚠️  警告: 未找到 Ollama"
        echo ""
        echo "要启用图片分析功能，请安装 Ollama:"
        echo "  brew install ollama"
        echo ""
        echo "然后下载 Qwen3-VL 模型:"
        echo "  ollama pull qwen3-vl:4b"
        echo ""
        read -p "是否继续运行（不带分析功能）？[y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        return 1
    else
        echo "✅ Ollama 已安装"

        # 检查模型 (qwen3-vl:4b 约 3.3GB，适合 16GB 内存)
        if ollama list | grep -q "qwen3-vl:4b"; then
            echo "✅ Qwen3-VL 模型已下载"
        else
            echo "⚠️  Qwen3-VL 模型未找到"
            echo ""
            echo "正在下载模型（约 3.3GB）..."
            ollama pull qwen3-vl:4b
        fi

        # 启动 Ollama 服务
        if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
            echo "正在启动 Ollama 服务..."
            ollama serve &> /dev/null &
            sleep 3
        fi
        echo "✅ Ollama 服务运行中"
        return 0
    fi
}

# 安装依赖
install_dependencies() {
    echo ""
    echo "检查 Python 依赖..."

    # 创建虚拟环境（可选）
    if [ ! -d "venv" ]; then
        echo "创建虚拟环境..."
        python3 -m venv venv
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 更新 pip
    pip install --upgrade pip -q

    # 安装依赖
    echo "安装依赖包..."
    pip install -q \
        pynput>=1.7.6 \
        mss>=9.0.1 \
        Pillow>=10.0.0 \
        pyobjc-framework-Cocoa>=10.0 \
        pyobjc-framework-Quartz>=10.0 \
        aiohttp>=3.9.0 \
        pyyaml>=6.0

    echo "✅ 依赖安装完成"
}

# 生成默认配置
generate_config() {
    if [ ! -f "config/qwen_config.yaml" ]; then
        echo ""
        echo "生成默认配置文件..."
        mkdir -p config
        python3 -c "from src.config import generate_example_config; generate_example_config('config/qwen_config.yaml')"
        echo "✅ 配置文件已生成: config/qwen_config.yaml"
    fi
}

# 主流程
main() {
    # 检查并安装依赖
    install_dependencies

    # 生成配置
    generate_config

    # 检查 Ollama
    ENABLE_ANALYSIS=true
    if ! check_ollama; then
        ENABLE_ANALYSIS=false
    fi

    echo ""
    echo "=========================================="
    echo "准备就绪，启动 OpenCapture"
    echo "=========================================="
    echo ""
    echo "功能状态:"
    echo "  📷 截图捕获: 已启用"
    echo "  ⌨️  键盘记录: 已启用"

    if [ "$ENABLE_ANALYSIS" = true ]; then
        echo "  🤖 AI 分析: 已启用 (Qwen3-VL:4b, 适合 16GB 内存)"
    else
        echo "  🤖 AI 分析: 已禁用"
    fi

    echo ""
    echo "数据将保存到: ~/auto-capture"
    echo ""
    echo "按 Ctrl+C 停止"
    echo "=========================================="
    echo ""

    # 运行主程序
    if [ "$ENABLE_ANALYSIS" = true ]; then
        python3 src/auto_capture_enhanced.py -c config/qwen_config.yaml
    else
        python3 src/auto_capture_enhanced.py --no-analysis
    fi
}

# 清理函数
cleanup() {
    echo ""
    echo "正在清理..."

    # 停止 Ollama 服务（如果是我们启动的）
    if pgrep -x "ollama" > /dev/null; then
        echo "停止 Ollama 服务..."
        pkill -x ollama 2>/dev/null || true
    fi

    echo "清理完成"
    exit 0
}

# 设置信号处理
trap cleanup INT TERM

# 运行主函数
main