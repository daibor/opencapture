#!/bin/bash
#
# OpenCapture 一键安装脚本
# 支持 macOS 和 Linux
#
# 使用方法:
#   curl -fsSL https://raw.githubusercontent.com/yourusername/opencapture/main/install.sh | bash
#   或
#   ./install.sh
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置
REPO_URL="https://github.com/yourusername/opencapture"
INSTALL_DIR="$HOME/.opencapture"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN_VERSION="3.9"

# 打印函数
print_banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                          ║${NC}"
    echo -e "${CYAN}║     ${GREEN}OpenCapture${CYAN} - 键鼠行为记录与 AI 分析              ║${NC}"
    echo -e "${CYAN}║                                                          ║${NC}"
    echo -e "${CYAN}║     支持: Ollama / OpenAI / Claude                       ║${NC}"
    echo -e "${CYAN}║                                                          ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# 检测操作系统
detect_os() {
    case "$(uname -s)" in
        Darwin*)
            OS="macos"
            PACKAGE_MANAGER="brew"
            ;;
        Linux*)
            OS="linux"
            if command -v apt-get &> /dev/null; then
                PACKAGE_MANAGER="apt"
            elif command -v dnf &> /dev/null; then
                PACKAGE_MANAGER="dnf"
            elif command -v pacman &> /dev/null; then
                PACKAGE_MANAGER="pacman"
            else
                PACKAGE_MANAGER="unknown"
            fi
            ;;
        *)
            error "不支持的操作系统: $(uname -s)"
            exit 1
            ;;
    esac
    info "系统: $OS | 包管理器: $PACKAGE_MANAGER"
}

# 安装 Homebrew (macOS)
install_homebrew() {
    [[ "$OS" != "macos" ]] && return

    if ! command -v brew &> /dev/null; then
        info "安装 Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f "/usr/local/bin/brew" ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        success "Homebrew 安装完成"
    else
        success "Homebrew 已安装"
    fi
}

# 安装 Python
install_python() {
    info "检查 Python..."

    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
            success "Python $PYTHON_VERSION"
            return
        fi
        warn "Python 版本过低 ($PYTHON_VERSION)，需要 >= $PYTHON_MIN_VERSION"
    fi

    info "安装 Python..."
    case "$PACKAGE_MANAGER" in
        brew) brew install python@3.11 ;;
        apt) sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip ;;
        dnf) sudo dnf install -y python3.11 python3-pip ;;
        pacman) sudo pacman -Sy --noconfirm python python-pip ;;
        *) error "请手动安装 Python >= $PYTHON_MIN_VERSION"; exit 1 ;;
    esac
    success "Python 安装完成"
}

# 安装 Ollama
install_ollama() {
    info "检查 Ollama..."

    if command -v ollama &> /dev/null; then
        success "Ollama 已安装"
        return
    fi

    info "安装 Ollama..."
    case "$OS" in
        macos) brew install ollama ;;
        linux) curl -fsSL https://ollama.ai/install.sh | sh ;;
    esac
    success "Ollama 安装完成"
}

# 安装系统依赖
install_system_deps() {
    info "安装系统依赖..."

    case "$PACKAGE_MANAGER" in
        apt)
            sudo apt-get update
            sudo apt-get install -y python3-dev python3-venv git
            ;;
        dnf)
            sudo dnf install -y python3-devel git
            ;;
        pacman)
            sudo pacman -Sy --noconfirm python git
            ;;
    esac
    success "系统依赖就绪"
}

# 获取项目代码
clone_project() {
    info "获取 OpenCapture..."

    if [[ -d "$INSTALL_DIR" ]]; then
        info "更新现有安装..."
        cd "$INSTALL_DIR"
        git pull origin main 2>/dev/null || true
    else
        git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
            # 如果 clone 失败（可能是本地安装），创建目录
            mkdir -p "$INSTALL_DIR"
            if [[ -d "$(dirname "$0")/src" ]]; then
                cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
            fi
        }
    fi
    success "代码准备完成"
}

# 配置 Python 环境
setup_python_env() {
    info "配置 Python 环境..."

    cd "$INSTALL_DIR"

    # 创建虚拟环境
    [[ ! -d "venv" ]] && python3 -m venv venv

    # 激活并安装依赖
    source venv/bin/activate
    pip install --upgrade pip -q

    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt -q
    fi

    success "Python 环境配置完成"
}

# 下载模型
download_model() {
    info "下载 AI 模型..."
    echo ""
    warn "模型大小约 4.5GB，首次下载需要较长时间"
    echo ""

    # 启动 Ollama
    if ! pgrep -x "ollama" > /dev/null; then
        ollama serve &> /dev/null &
        sleep 3
    fi

    if ollama list 2>/dev/null | grep -q "qwen2-vl"; then
        success "模型已存在"
    else
        ollama pull qwen2-vl:7b
        success "模型下载完成"
    fi
}

# 创建启动脚本
create_launcher() {
    info "创建启动脚本..."

    mkdir -p "$BIN_DIR"

    cat > "$BIN_DIR/opencapture" << 'LAUNCHER'
#!/bin/bash
#
# OpenCapture 启动器
#

INSTALL_DIR="$HOME/.opencapture"

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "错误: OpenCapture 未安装"
    echo "请运行安装脚本"
    exit 1
fi

cd "$INSTALL_DIR"
source venv/bin/activate

# 解析参数
case "${1:-}" in
    --no-ai|--simple)
        shift
        python run.py --no-ai "$@"
        ;;
    --analyze)
        shift
        python run.py --analyze "${1:-today}" "${@:2}"
        ;;
    --help|-h)
        cat << 'HELP'
OpenCapture - 键鼠行为记录与 AI 分析

用法: opencapture [选项]

采集模式:
  opencapture                   启动采集（带 AI 分析）
  opencapture --no-ai           启动采集（不带 AI）

分析模式:
  opencapture --analyze today   分析今天的数据
  opencapture --analyze DATE    分析指定日期 (YYYY-MM-DD)
  opencapture --image FILE      分析单张图片

LLM 选项:
  --provider ollama|openai|anthropic|custom
                                指定 LLM 提供商
  --health-check                检查 LLM 服务状态

其他选项:
  --list-dates                  列出可用日期
  --no-reports                  不生成 Markdown 报告
  -c, --config FILE             指定配置文件
  -d, --dir DIR                 指定存储目录
  -h, --help                    显示帮助

配置文件:
  ~/.opencapture/config/config.yaml
  或设置环境变量:
    OPENAI_API_KEY              使用 OpenAI
    ANTHROPIC_API_KEY           使用 Claude

数据目录: ~/auto-capture/
报告目录: ~/auto-capture/reports/

示例:
  opencapture                           # 开始记录
  opencapture --analyze today           # 分析今天
  opencapture --provider openai --analyze today  # 用 OpenAI 分析
  OPENAI_API_KEY=sk-xxx opencapture --analyze today

HELP
        ;;
    *)
        # 启动 Ollama（如果需要且未运行）
        if [[ "${1:-}" != "--provider" ]] || [[ "${2:-}" == "ollama" ]]; then
            if ! pgrep -x "ollama" > /dev/null 2>&1; then
                echo "启动 Ollama 服务..."
                ollama serve &> /dev/null &
                sleep 2
            fi
        fi
        python run.py "$@"
        ;;
esac
LAUNCHER

    chmod +x "$BIN_DIR/opencapture"
    success "启动脚本: $BIN_DIR/opencapture"
}

# 配置 PATH
configure_path() {
    info "配置 PATH..."

    if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
        success "PATH 已配置"
        return
    fi

    # 确定 shell 配置文件
    if [[ -f "$HOME/.zshrc" ]]; then
        SHELL_RC="$HOME/.zshrc"
    elif [[ -f "$HOME/.bashrc" ]]; then
        SHELL_RC="$HOME/.bashrc"
    else
        SHELL_RC="$HOME/.profile"
    fi

    echo '' >> "$SHELL_RC"
    echo '# OpenCapture' >> "$SHELL_RC"
    echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_RC"

    success "已添加到 $SHELL_RC"
    warn "请运行: source $SHELL_RC"
}

# 创建示例配置
create_config() {
    info "创建配置目录..."

    CONFIG_DIR="$INSTALL_DIR/config"
    mkdir -p "$CONFIG_DIR"

    if [[ ! -f "$CONFIG_DIR/config.yaml" ]] && [[ -f "$CONFIG_DIR/example.yaml" ]]; then
        cp "$CONFIG_DIR/example.yaml" "$CONFIG_DIR/config.yaml"
        success "已创建配置文件: $CONFIG_DIR/config.yaml"
    fi
}

# macOS 权限提示
macos_permissions() {
    [[ "$OS" != "macos" ]] && return

    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  macOS 权限设置                                          ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "OpenCapture 需要以下权限:"
    echo ""
    echo "  1. ${BLUE}辅助功能${NC} - 监听键鼠事件"
    echo "  2. ${BLUE}屏幕录制${NC} - 截取屏幕"
    echo ""
    echo "设置: 系统设置 → 隐私与安全性 → 对应项目"
    echo ""

    read -p "打开系统设置？[y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    fi
}

# 询问下载模型
ask_download_model() {
    echo ""
    echo -e "${YELLOW}AI 模型${NC}"
    echo ""
    echo "本地 AI 分析需要下载 Qwen2-VL 模型 (~4.5GB)"
    echo "也可以使用远程 API (OpenAI/Claude) 无需下载"
    echo ""

    read -p "下载本地模型？[Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        download_model
    else
        warn "跳过模型下载"
        echo "使用本地分析时运行: ollama pull qwen2-vl:7b"
        echo "或配置远程 API: export OPENAI_API_KEY=sk-xxx"
    fi
}

# 打印完成信息
print_success() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    安装完成！                            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "快速开始:"
    echo ""
    echo "  ${CYAN}opencapture${NC}                  # 开始记录"
    echo "  ${CYAN}opencapture --analyze today${NC}  # 分析今天"
    echo "  ${CYAN}opencapture --help${NC}           # 查看帮助"
    echo ""
    echo "使用远程 API:"
    echo ""
    echo "  ${CYAN}export OPENAI_API_KEY=sk-xxx${NC}"
    echo "  ${CYAN}opencapture --provider openai --analyze today${NC}"
    echo ""
    echo "数据目录: ${BLUE}~/auto-capture${NC}"
    echo "报告目录: ${BLUE}~/auto-capture/reports${NC}"
    echo ""
}

# 主流程
main() {
    print_banner

    echo "将安装:"
    echo "  • Python 3.11+ (如需要)"
    echo "  • Ollama (本地 AI)"
    echo "  • OpenCapture"
    echo "  • Qwen2-VL 模型 (可选)"
    echo ""

    read -p "继续？[Y/n] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Nn]$ ]] && exit 0

    echo ""

    detect_os
    [[ "$OS" == "macos" ]] && install_homebrew
    install_system_deps
    install_python
    install_ollama
    clone_project
    setup_python_env
    create_config
    ask_download_model
    create_launcher
    configure_path
    macos_permissions
    print_success
}

main "$@"
