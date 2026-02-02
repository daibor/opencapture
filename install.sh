#!/bin/bash
#
# OpenCapture + Qwen3-VL 一键安装脚本
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
NC='\033[0m' # No Color

# 配置
REPO_URL="https://github.com/yourusername/opencapture"
INSTALL_DIR="$HOME/.opencapture"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN_VERSION="3.9"

# 打印函数
print_banner() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                                          ║${NC}"
    echo -e "${BLUE}║     ${GREEN}OpenCapture + Qwen3-VL 一键安装程序${BLUE}                 ║${NC}"
    echo -e "${BLUE}║                                                          ║${NC}"
    echo -e "${BLUE}║     自动截图 + AI 图片理解                               ║${NC}"
    echo -e "${BLUE}║                                                          ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

error() {
    echo -e "${RED}[✗]${NC} $1"
}

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
            elif command -v yum &> /dev/null; then
                PACKAGE_MANAGER="yum"
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

    info "检测到系统: $OS (包管理器: $PACKAGE_MANAGER)"
}

# 检查并安装 Homebrew (macOS)
install_homebrew() {
    if [[ "$OS" != "macos" ]]; then
        return
    fi

    if ! command -v brew &> /dev/null; then
        info "正在安装 Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # 添加到 PATH
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

# 检查并安装 Python
install_python() {
    info "检查 Python 环境..."

    # 检查现有 Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
            success "Python $PYTHON_VERSION 已安装"
            return
        else
            warn "Python 版本过低 ($PYTHON_VERSION)，需要 >= $PYTHON_MIN_VERSION"
        fi
    fi

    info "正在安装 Python..."

    case "$PACKAGE_MANAGER" in
        brew)
            brew install python@3.11
            ;;
        apt)
            sudo apt-get update
            sudo apt-get install -y python3.11 python3.11-venv python3-pip
            ;;
        dnf|yum)
            sudo $PACKAGE_MANAGER install -y python3.11 python3-pip
            ;;
        pacman)
            sudo pacman -Sy --noconfirm python python-pip
            ;;
        *)
            error "无法自动安装 Python，请手动安装 Python >= $PYTHON_MIN_VERSION"
            exit 1
            ;;
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

    info "正在安装 Ollama..."

    case "$OS" in
        macos)
            brew install ollama
            ;;
        linux)
            curl -fsSL https://ollama.ai/install.sh | sh
            ;;
    esac

    success "Ollama 安装完成"
}

# 安装系统依赖
install_system_deps() {
    info "安装系统依赖..."

    case "$PACKAGE_MANAGER" in
        brew)
            # macOS 通常不需要额外依赖
            ;;
        apt)
            sudo apt-get update
            sudo apt-get install -y \
                python3-dev \
                python3-venv \
                libxcb-xinerama0 \
                libxcb-cursor0 \
                libxkbcommon-x11-0
            ;;
        dnf|yum)
            sudo $PACKAGE_MANAGER install -y \
                python3-devel \
                libxcb \
                xorg-x11-server-Xvfb
            ;;
        pacman)
            sudo pacman -Sy --noconfirm \
                python \
                libxcb \
                xorg-server-xvfb
            ;;
    esac

    success "系统依赖安装完成"
}

# 克隆或更新项目
clone_project() {
    info "获取 OpenCapture 代码..."

    if [[ -d "$INSTALL_DIR" ]]; then
        info "更新现有安装..."
        cd "$INSTALL_DIR"
        git pull origin main 2>/dev/null || true
    else
        info "下载项目..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi

    success "项目代码准备完成"
}

# 创建虚拟环境并安装依赖
setup_python_env() {
    info "配置 Python 环境..."

    cd "$INSTALL_DIR"

    # 创建虚拟环境
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 更新 pip
    pip install --upgrade pip -q

    # 安装依赖
    info "安装 Python 依赖..."

    if [[ -f "requirements_enhanced.txt" ]]; then
        pip install -r requirements_enhanced.txt -q
    elif [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt -q
        # 安装额外的 Qwen 相关依赖
        pip install aiohttp pyyaml -q
    fi

    success "Python 环境配置完成"
}

# 下载 Qwen 模型
download_model() {
    info "下载 AI 模型 (Qwen2-VL)..."
    echo ""
    warn "模型大小约 4.5GB，首次下载可能需要较长时间"
    echo ""

    # 启动 Ollama 服务
    if ! pgrep -x "ollama" > /dev/null; then
        ollama serve &> /dev/null &
        sleep 3
    fi

    # 检查模型是否已下载
    if ollama list 2>/dev/null | grep -q "qwen2-vl:7b"; then
        success "模型已存在"
    else
        info "开始下载模型..."
        ollama pull qwen2-vl:7b
        success "模型下载完成"
    fi
}

# 创建启动脚本
create_launcher() {
    info "创建启动脚本..."

    # 确保 bin 目录存在
    mkdir -p "$BIN_DIR"

    # 创建启动脚本
    cat > "$BIN_DIR/opencapture" << 'EOF'
#!/bin/bash
#
# OpenCapture 启动脚本
#

INSTALL_DIR="$HOME/.opencapture"

# 检查安装目录
if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "错误: OpenCapture 未安装"
    echo "请运行: curl -fsSL https://raw.githubusercontent.com/yourusername/opencapture/main/install.sh | bash"
    exit 1
fi

cd "$INSTALL_DIR"

# 激活虚拟环境
source venv/bin/activate

# 启动 Ollama 服务（如果未运行）
if ! pgrep -x "ollama" > /dev/null; then
    echo "正在启动 AI 服务..."
    ollama serve &> /dev/null &
    sleep 2
fi

# 解析参数
case "${1:-}" in
    --no-ai|--simple)
        echo "以简单模式运行（无 AI 分析）"
        python src/auto_capture_enhanced.py --no-analysis "${@:2}"
        ;;
    --analyze)
        echo "分析已有截图..."
        python src/auto_capture_enhanced.py --analyze-existing "${2:-today}"
        ;;
    --help|-h)
        echo "OpenCapture - 自动截图 + AI 理解"
        echo ""
        echo "用法: opencapture [选项]"
        echo ""
        echo "选项:"
        echo "  --no-ai, --simple   禁用 AI 分析功能"
        echo "  --analyze [日期]    分析指定日期的截图 (默认: today)"
        echo "  -d, --dir <目录>    指定存储目录 (默认: ~/auto-capture)"
        echo "  -h, --help          显示帮助信息"
        echo ""
        echo "示例:"
        echo "  opencapture                    # 正常启动"
        echo "  opencapture --no-ai            # 不使用 AI 分析"
        echo "  opencapture --analyze today    # 分析今天的截图"
        echo "  opencapture -d ~/my-captures   # 自定义存储目录"
        ;;
    *)
        python src/auto_capture_enhanced.py "$@"
        ;;
esac
EOF

    chmod +x "$BIN_DIR/opencapture"

    success "启动脚本创建完成: $BIN_DIR/opencapture"
}

# 配置 PATH
configure_path() {
    info "配置环境变量..."

    # 检查 PATH 是否已包含
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        # 确定 shell 配置文件
        if [[ -f "$HOME/.zshrc" ]]; then
            SHELL_RC="$HOME/.zshrc"
        elif [[ -f "$HOME/.bashrc" ]]; then
            SHELL_RC="$HOME/.bashrc"
        elif [[ -f "$HOME/.bash_profile" ]]; then
            SHELL_RC="$HOME/.bash_profile"
        else
            SHELL_RC="$HOME/.profile"
        fi

        # 添加到 PATH
        echo '' >> "$SHELL_RC"
        echo '# OpenCapture' >> "$SHELL_RC"
        echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_RC"

        success "已添加到 $SHELL_RC"
        warn "请运行 'source $SHELL_RC' 或重新打开终端"
    else
        success "PATH 已配置"
    fi
}

# macOS 权限提示
macos_permissions() {
    if [[ "$OS" != "macos" ]]; then
        return
    fi

    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  macOS 权限设置                                          ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "OpenCapture 需要以下权限才能正常工作:"
    echo ""
    echo "  1. ${BLUE}辅助功能权限${NC} (Accessibility)"
    echo "     用于：监听键盘和鼠标事件"
    echo ""
    echo "  2. ${BLUE}屏幕录制权限${NC} (Screen Recording)"
    echo "     用于：截取屏幕画面"
    echo ""
    echo "设置方法:"
    echo "  系统偏好设置 → 安全性与隐私 → 隐私"
    echo "  → 分别在「辅助功能」和「屏幕录制」中添加终端应用"
    echo ""

    read -p "是否现在打开系统偏好设置？[y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    fi
}

# 打印安装完成信息
print_success() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                          ║${NC}"
    echo -e "${GREEN}║     安装完成！                                           ║${NC}"
    echo -e "${GREEN}║                                                          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "快速开始:"
    echo ""
    echo "  ${BLUE}opencapture${NC}              # 启动（带 AI 分析）"
    echo "  ${BLUE}opencapture --no-ai${NC}      # 启动（不带 AI 分析）"
    echo "  ${BLUE}opencapture --help${NC}       # 查看帮助"
    echo ""
    echo "数据存储位置: ${BLUE}~/auto-capture${NC}"
    echo ""
    echo "提示: 首次运行需要授予系统权限（见上方说明）"
    echo ""
}

# 询问是否下载模型
ask_download_model() {
    echo ""
    echo -e "${YELLOW}AI 模型下载${NC}"
    echo ""
    echo "Qwen2-VL 模型大小约 4.5GB"
    echo "如果暂时不需要 AI 分析功能，可以跳过此步骤"
    echo ""

    read -p "是否现在下载 AI 模型？[Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        download_model
        return 0
    else
        warn "跳过模型下载"
        echo "稍后可以运行: ollama pull qwen2-vl:7b"
        return 1
    fi
}

# 主安装流程
main() {
    print_banner

    echo "此脚本将安装以下组件:"
    echo "  • Python 3.11+ (如果需要)"
    echo "  • Ollama (本地 AI 运行时)"
    echo "  • OpenCapture 应用"
    echo "  • Qwen2-VL 模型 (可选, ~4.5GB)"
    echo ""

    read -p "是否继续安装？[Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "安装已取消"
        exit 0
    fi

    echo ""
    info "开始安装..."
    echo ""

    # 检测系统
    detect_os

    # 安装依赖
    if [[ "$OS" == "macos" ]]; then
        install_homebrew
    fi

    install_system_deps
    install_python
    install_ollama

    # 获取项目代码
    clone_project

    # 配置 Python 环境
    setup_python_env

    # 询问是否下载模型
    ask_download_model

    # 创建启动脚本
    create_launcher

    # 配置 PATH
    configure_path

    # macOS 权限提示
    macos_permissions

    # 打印完成信息
    print_success
}

# 运行安装
main "$@"