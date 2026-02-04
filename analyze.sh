#!/bin/bash
#
# 日志和截图分析工具
# 使用 Ollama + Qwen3-VL 本地分析
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 检查 Ollama 是否运行
check_ollama() {
    if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
        echo "⚠️  Ollama 服务未运行"
        echo ""
        echo "请先启动 Ollama:"
        echo "  ollama serve"
        echo ""
        echo "或者使用以下命令启动并后台运行:"
        echo "  ollama serve &"
        exit 1
    fi
}

# 显示帮助
show_help() {
    echo "日志和截图分析工具 (Qwen3-VL)"
    echo ""
    echo "用法:"
    echo "  ./analyze.sh [选项]"
    echo ""
    echo "选项:"
    echo "  --date YYYY-MM-DD   分析指定日期的数据"
    echo "  --today             分析今天的数据 (默认)"
    echo "  --image PATH        分析单张截图，生成同名 txt"
    echo "  --images            批量分析图片，每张生成同名 txt"
    echo "  --limit N           限制分析条目数"
    echo "  --no-skip           不跳过已有 txt 的图片"
    echo "  --dir PATH          指定数据目录 (默认: ~/auto-capture)"
    echo "  --help              显示帮助"
    echo ""
    echo "示例:"
    echo "  ./analyze.sh --today"
    echo "  ./analyze.sh --images --today            # 批量分析今天的图片"
    echo "  ./analyze.sh --images --date 2026-02-01  # 批量分析指定日期"
    echo "  ./analyze.sh --images --limit 10         # 只分析 10 张"
    echo "  ./analyze.sh --image ~/auto-capture/2026-02-01/click_103045.webp"
}

# 默认参数
DATE=""
IMAGE=""
IMAGES=""
LIMIT=""
DIR="~/auto-capture"
NO_SKIP=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --date)
            DATE="$2"
            shift 2
            ;;
        --today)
            DATE=$(date +%Y-%m-%d)
            shift
            ;;
        --image)
            IMAGE="$2"
            shift 2
            ;;
        --images)
            IMAGES="true"
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --no-skip)
            NO_SKIP="true"
            shift
            ;;
        --dir)
            DIR="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# 检查 Ollama
check_ollama

echo "=========================================="
echo "日志和截图分析器 (Qwen3-VL:4b)"
echo "=========================================="
echo ""

# 构建命令
CMD="python3 src/log_screenshot_analyzer.py"
CMD="$CMD --dir \"$DIR\""

if [ -n "$IMAGE" ]; then
    CMD="$CMD --image \"$IMAGE\""
else
    # 设置日期
    if [ -n "$DATE" ]; then
        CMD="$CMD --date \"$DATE\""
    else
        CMD="$CMD --date $(date +%Y-%m-%d)"
    fi

    # 批量分析图片模式
    if [ -n "$IMAGES" ]; then
        CMD="$CMD --images"
    fi

    # 不跳过已有 txt
    if [ -n "$NO_SKIP" ]; then
        CMD="$CMD --no-skip"
    fi
fi

if [ -n "$LIMIT" ]; then
    CMD="$CMD --limit $LIMIT"
fi

# 执行
eval $CMD
