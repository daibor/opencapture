#!/bin/bash
#
# OpenCapture installer
# Supports macOS and Linux
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/daibor/opencapture/main/install.sh | bash
#   or
#   ./install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Config
REPO_URL="https://github.com/daibor/opencapture.git"
INSTALL_DIR="$HOME/.opencapture"
BIN_DIR="$HOME/.local/bin"
PYTHON_MIN_VERSION="3.9"

# Print helpers
print_banner() {
    echo ""
    echo -e "${CYAN}  ┌──────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}  │                                          │${NC}"
    echo -e "${CYAN}  │   ${GREEN}${BOLD}OpenCapture${NC}${CYAN}                            │${NC}"
    echo -e "${CYAN}  │   Keyboard & Mouse Recorder + AI Analyst │${NC}"
    echo -e "${CYAN}  │                                          │${NC}"
    echo -e "${CYAN}  └──────────────────────────────────────────┘${NC}"
    echo ""
}

info()    { echo -e "  ${BLUE}→${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${YELLOW}!${NC} $1"; }
error()   { echo -e "  ${RED}✗${NC} $1"; }
step()    { echo -e "\n${BOLD}[$1/$TOTAL_STEPS] $2${NC}"; }

# Detect OS
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
            error "Unsupported OS: $(uname -s)"
            exit 1
            ;;
    esac
    success "Detected ${BOLD}$OS${NC} (package manager: $PACKAGE_MANAGER)"
}

# Install Homebrew (macOS)
install_homebrew() {
    [[ "$OS" != "macos" ]] && return

    if ! command -v brew &> /dev/null; then
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f "/usr/local/bin/brew" ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        success "Homebrew installed"
    else
        success "Homebrew found"
    fi
}

# Install Python
install_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
            success "Python $PYTHON_VERSION"
            return
        fi
        warn "Python $PYTHON_VERSION is too old (need >= $PYTHON_MIN_VERSION)"
    fi

    info "Installing Python..."
    case "$PACKAGE_MANAGER" in
        brew) brew install python@3.11 ;;
        apt) sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip ;;
        dnf) sudo dnf install -y python3.11 python3-pip ;;
        pacman) sudo pacman -Sy --noconfirm python python-pip ;;
        *) error "Please install Python >= $PYTHON_MIN_VERSION manually"; exit 1 ;;
    esac
    success "Python installed"
}

# Install system dependencies
install_system_deps() {
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
    success "System dependencies ready"
}

# Clone or update project
clone_project() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    IS_LOCAL_SOURCE=false

    # Check if running from a local source tree (has run.py + src/)
    if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/run.py" && -d "$SCRIPT_DIR/src" ]]; then
        IS_LOCAL_SOURCE=true
    fi

    # Resolve real paths for comparison
    local real_script real_install
    real_script="$(cd "$SCRIPT_DIR" 2>/dev/null && pwd -P)"
    real_install="$(cd "$INSTALL_DIR" 2>/dev/null && pwd -P 2>/dev/null)"

    if [[ -d "$INSTALL_DIR" ]]; then
        if [[ "$IS_LOCAL_SOURCE" == true && "$real_script" != "$real_install" ]]; then
            # Running from a separate dev directory — sync local code
            info "Syncing from local directory..."
            rsync -a --exclude='venv' --exclude='__pycache__' --exclude='.git' \
                "$SCRIPT_DIR/" "$INSTALL_DIR/"
        else
            # Running from install dir itself or remote — pull from GitHub
            info "Updating from remote..."
            cd "$INSTALL_DIR"
            git pull origin main 2>/dev/null || true
        fi
    elif [[ "$IS_LOCAL_SOURCE" == true ]]; then
        info "Installing from local directory..."
        mkdir -p "$INSTALL_DIR"
        rsync -a --exclude='venv' --exclude='__pycache__' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
    else
        git clone "$REPO_URL" "$INSTALL_DIR" || {
            error "Failed to clone $REPO_URL"
            error "Check your network connection or clone manually, then run ./install.sh"
            exit 1
        }
    fi
    success "Source code ready"
}

# Set up Python virtual environment
setup_python_env() {
    cd "$INSTALL_DIR"

    [[ ! -d "venv" ]] && python3 -m venv venv

    source venv/bin/activate
    pip install --upgrade pip -q

    if [[ -f "requirements.txt" ]]; then
        if [[ "$OS" == "linux" ]]; then
            grep -v "^pyobjc" requirements.txt | pip install -r /dev/stdin -q
        else
            pip install -r requirements.txt -q
        fi
    fi

    success "Python environment configured"
}

# Create launcher script
create_launcher() {
    mkdir -p "$BIN_DIR"

    cat > "$BIN_DIR/opencapture" << 'LAUNCHER'
#!/bin/bash
#
# OpenCapture launcher
#

INSTALL_DIR="$HOME/.opencapture"
PLIST_LABEL="com.opencapture.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
LOG_DIR="$INSTALL_DIR/logs"
DATA_DIR="$HOME/opencapture"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "Error: OpenCapture is not installed."
    echo "Run the install script first."
    exit 1
fi

# ── Helpers ────────────────────────────────────────

activate_venv() {
    cd "$INSTALL_DIR"
    source venv/bin/activate
}

ensure_ollama() {
    for arg in "$@"; do
        [[ "$arg" == "--provider" ]] && return
    done

    if ! command -v ollama &> /dev/null; then
        echo ""
        echo "  Ollama is not installed (required for local AI analysis)."
        echo ""
        echo "  Install:  brew install ollama"
        echo "  Or use:   opencapture --provider openai --analyze today"
        echo ""
        return 1
    fi

    if ! pgrep -x "ollama" > /dev/null 2>&1; then
        echo "Starting Ollama..."
        ollama serve &> /dev/null &
        sleep 2
    fi
}

# ── LaunchAgent ────────────────────────────────────

create_plist() {
    mkdir -p "$LOG_DIR"
    mkdir -p "$(dirname "$PLIST_PATH")"
    local APP_EXEC="$INSTALL_DIR/OpenCapture.app/Contents/MacOS/OpenCapture"
    cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_EXEC</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/output.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLIST
}

get_service_pid() {
    local info
    info=$(launchctl list 2>/dev/null | grep "$PLIST_LABEL")
    if [[ -n "$info" ]]; then
        echo "$info" | awk '{print $1}'
    fi
}

is_service_running() {
    local pid
    pid=$(get_service_pid)
    [[ -n "$pid" && "$pid" != "-" ]]
}

# ── Commands ───────────────────────────────────────

cmd_start() {
    if is_service_running; then
        echo -e "  OpenCapture is already running (PID $(get_service_pid))"
        return 0
    fi

    local APP_EXEC="$INSTALL_DIR/OpenCapture.app/Contents/MacOS/OpenCapture"

    if [[ ! -x "$APP_EXEC" ]]; then
        echo -e "  ${RED}App bundle not found. Run install.sh to create it.${NC}"
        return 1
    fi

    # Clear old logs before starting
    mkdir -p "$LOG_DIR"
    : > "$LOG_DIR/output.log" 2>/dev/null
    : > "$LOG_DIR/error.log" 2>/dev/null

    # Start background service
    # Permission dialog is handled by the .app process itself —
    # macOS shows "OpenCapture" in the permission dialog thanks to the .app bundle
    create_plist
    launchctl load -w "$PLIST_PATH" 2>/dev/null

    sleep 2
    if is_service_running; then
        echo -e "  ${GREEN}${BOLD}OpenCapture started${NC} (PID $(get_service_pid))"
        echo -e "  Auto-start on login: enabled"
        echo ""
        echo -e "  If this is the first run, grant ${BOLD}OpenCapture${NC} access in:"
        echo -e "  ${CYAN}System Settings → Privacy & Security → Accessibility${NC}"
        echo ""
        echo -e "  Logs:   ${CYAN}opencapture log${NC}"
        echo -e "  Status: ${CYAN}opencapture status${NC}"
        echo -e "  Stop:   ${CYAN}opencapture stop${NC}"
    else
        echo -e "  ${RED}Failed to start OpenCapture${NC}"
        echo -e "  Check logs: ${CYAN}opencapture log${NC}"
    fi
}

cmd_stop() {
    if [[ ! -f "$PLIST_PATH" ]]; then
        echo "  OpenCapture is not running"
        return 0
    fi

    launchctl unload "$PLIST_PATH" 2>/dev/null
    echo -e "  ${BOLD}OpenCapture stopped${NC}"
    echo "  Auto-start on login: disabled"
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    echo ""
    echo -e "  ${BOLD}OpenCapture${NC}"
    echo ""

    # Running state
    local pid
    pid=$(get_service_pid)
    if [[ -n "$pid" && "$pid" != "-" ]]; then
        echo -e "  State:      ${GREEN}Running${NC} (PID $pid)"
    elif [[ -n "$pid" ]]; then
        echo -e "  State:      ${YELLOW}Loaded but not running${NC}"
    else
        echo -e "  State:      Stopped"
    fi

    # Auto-start
    if [[ -f "$PLIST_PATH" ]] && launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
        echo -e "  Auto-start: ${GREEN}Enabled${NC}"
    else
        echo -e "  Auto-start: Disabled"
    fi

    # Data
    echo -e "  Data:       $DATA_DIR"

    # Today's stats
    local today
    today=$(date +%Y-%m-%d)
    local today_dir="$DATA_DIR/$today"
    if [[ -d "$today_dir" ]]; then
        local screenshots logs recordings
        screenshots=$(ls "$today_dir"/*.webp 2>/dev/null | wc -l | tr -d ' ')
        logs=$(ls "$today_dir"/*.log 2>/dev/null | wc -l | tr -d ' ')
        recordings=$(ls "$today_dir"/*.wav 2>/dev/null | wc -l | tr -d ' ')
        echo -e "  Today:      ${screenshots} screenshots, ${logs} logs, ${recordings} recordings"
    else
        echo -e "  Today:      No data yet"
    fi
    echo ""
}

cmd_log() {
    local out_log="$LOG_DIR/output.log"
    local err_log="$LOG_DIR/error.log"

    if [[ ! -f "$out_log" && ! -f "$err_log" ]]; then
        echo "  No logs yet. Start the service first: opencapture start"
        return
    fi

    if [[ "${2:-}" == "-f" ]]; then
        tail -f "$out_log" "$err_log" 2>/dev/null
    else
        echo -e "  ${BOLD}── Recent output ──${NC}"
        tail -30 "$out_log" 2>/dev/null || echo "  (empty)"
        echo ""
        if [[ -s "$err_log" ]]; then
            echo -e "  ${BOLD}── Recent errors ──${NC}"
            tail -10 "$err_log" 2>/dev/null
            echo ""
        fi
        echo -e "  Tip: ${CYAN}opencapture log -f${NC} to follow in real-time"
    fi
}

cmd_uninstall() {
    echo ""
    echo -e "  ${BOLD}Uninstall OpenCapture${NC}"
    echo ""

    # Stop service
    if is_service_running || [[ -f "$PLIST_PATH" ]]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null
        rm -f "$PLIST_PATH"
        echo "  Stopped service and removed LaunchAgent"
    fi

    # Reset TCC permissions
    tccutil reset Accessibility com.opencapture.agent 2>/dev/null || true
    tccutil reset ScreenCapture com.opencapture.agent 2>/dev/null || true
    tccutil reset Microphone com.opencapture.agent 2>/dev/null || true

    # Remove install dir
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        echo "  Removed $INSTALL_DIR"
    fi

    # Data directory
    if [[ -d "$DATA_DIR" ]]; then
        echo ""
        read -p "  Delete captured data ($DATA_DIR)? [y/N] " -n 1 -r < /dev/tty
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$DATA_DIR"
            echo "  Removed $DATA_DIR"
        else
            echo "  Kept $DATA_DIR"
        fi
    fi

    # Remove self (launcher script)
    local self_path
    self_path="$(realpath "$0" 2>/dev/null || echo "$0")"
    if [[ -f "$self_path" ]]; then
        rm -f "$self_path"
        echo "  Removed $self_path"
    fi

    echo ""
    echo -e "  ${GREEN}Uninstall complete.${NC}"
    echo ""
}

cmd_help() {
    cat << 'HELP'

  OpenCapture - Keyboard & Mouse Recorder + AI Analyst

  Usage: opencapture <command> [options]

  Service:
    start               Start capturing (requests permissions on first run)
    stop                Stop service
    restart             Restart service
    status              Show running state and today's stats
    log [-f]            Show logs (-f to follow in real-time)

  Analysis:
    analyze DATE        Analyze data (today / yesterday / YYYY-MM-DD)
    image FILE          Analyze a single screenshot
    audio FILE          Transcribe a single audio file
    health-check        Check LLM service status
    list-dates          List available dates

  Analysis options:
    --provider NAME     Choose LLM (ollama / openai / anthropic / custom)
    --no-reports        Skip Markdown report generation

  Other:
    uninstall           Uninstall OpenCapture
    -c, --config FILE   Specify config file
    -d, --dir DIR       Specify storage directory
    help                Show this help

  Paths:
    Config:   ~/.opencapture/config.yaml
    Data:     ~/opencapture/
    Reports:  ~/opencapture/reports/

  Examples:
    opencapture start                                 # start capturing
    opencapture status                                # check state
    opencapture stop                                  # stop
    opencapture analyze today                         # analyze today
    opencapture analyze today --provider openai       # use OpenAI
    opencapture image screenshot.webp                 # analyze image

HELP
}

# ── Main dispatch ──────────────────────────────────

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    log|logs)
        cmd_log "$@"
        ;;
    help|--help|-h)
        cmd_help
        ;;
    uninstall)
        cmd_uninstall
        ;;
    analyze)
        shift
        activate_venv
        ensure_ollama "$@"
        python run.py --analyze "$@"
        ;;
    image)
        shift
        activate_venv
        ensure_ollama "$@"
        python run.py --image "$@"
        ;;
    audio)
        shift
        activate_venv
        python run.py --audio "$@"
        ;;
    health-check)
        activate_venv
        ensure_ollama
        python run.py --health-check
        ;;
    list-dates)
        activate_venv
        python run.py --list-dates
        ;;
    run)
        # Foreground capture (undocumented, for debugging)
        if is_service_running; then
            echo ""
            echo -e "  ${YELLOW}OpenCapture is already running in background (PID $(get_service_pid))${NC}"
            echo ""
            echo -e "  Stop it first:  ${CYAN}opencapture stop${NC}"
            exit 1
        fi
        activate_venv
        python run.py
        ;;
    "")
        cmd_help
        ;;
    *)
        activate_venv
        python run.py "$@"
        ;;
esac
LAUNCHER

    chmod +x "$BIN_DIR/opencapture"
    success "Launcher created at $BIN_DIR/opencapture"
}

# Configure PATH
configure_path() {
    if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
        success "PATH already configured"
        return
    fi

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

    success "Added to $SHELL_RC"
    warn "Run: source $SHELL_RC"
}

# Create .app bundle for macOS TCC permission recognition
#
# macOS Accessibility checks the calling process's code identity.
# Python must be inside the .app for TCC to attribute it to "OpenCapture".
create_app_bundle() {
    [[ "$OS" != "macos" ]] && return

    local APP_DIR="$INSTALL_DIR/OpenCapture.app"
    local CONTENTS_DIR="$APP_DIR/Contents"
    local MACOS_DIR="$CONTENTS_DIR/MacOS"

    mkdir -p "$MACOS_DIR"

    # Info.plist
    cat > "$CONTENTS_DIR/Info.plist" << 'INFOPLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.opencapture.agent</string>
    <key>CFBundleName</key>
    <string>OpenCapture</string>
    <key>CFBundleDisplayName</key>
    <string>OpenCapture</string>
    <key>CFBundleExecutable</key>
    <string>OpenCapture</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
INFOPLIST

    # Copy Python binary into .app (required for TCC Accessibility)
    local VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
    if [[ ! -x "$VENV_PYTHON" ]]; then
        error "venv Python not found at $VENV_PYTHON"
        return 1
    fi
    cp "$VENV_PYTHON" "$MACOS_DIR/python3"

    # Detect Python paths for environment setup
    local PYTHON_PREFIX PYTHON_VERSION
    PYTHON_PREFIX=$("$VENV_PYTHON" -c "import sys; print(sys.base_prefix)")
    PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

    # Shell wrapper: sets PYTHONHOME/PYTHONPATH, exec's in-bundle python3
    cat > "$MACOS_DIR/OpenCapture" << WRAPPER
#!/bin/bash
DIR="\$(dirname "\$0")"
INSTALL_DIR="\$HOME/.opencapture"
VENV="\$INSTALL_DIR/venv"

export PYTHONHOME="$PYTHON_PREFIX"
export PYTHONPATH="\$INSTALL_DIR:\$VENV/lib/python$PYTHON_VERSION/site-packages"

exec "\$DIR/python3" "\$INSTALL_DIR/run.py" "\$@"
WRAPPER
    chmod +x "$MACOS_DIR/OpenCapture"

    # Ad-hoc sign so macOS TCC recognizes the bundle
    codesign --force --sign - "$APP_DIR" 2>/dev/null || true

    success "App bundle created"
}

# Create config file
create_config() {
    CONFIG_FILE="$INSTALL_DIR/config.yaml"

    if [[ ! -f "$CONFIG_FILE" ]] && [[ -f "$INSTALL_DIR/config/example.yaml" ]]; then
        cp "$INSTALL_DIR/config/example.yaml" "$CONFIG_FILE"
        success "Config created at $CONFIG_FILE"
    else
        success "Config already exists"
    fi
}

# Print completion message
print_success() {
    echo ""
    echo -e "  ${GREEN}${BOLD}Installation complete!${NC}"
    echo ""
    echo -e "  ${BOLD}Start capturing:${NC}"
    echo ""
    echo -e "    ${CYAN}opencapture start${NC}              Start (auto-runs on login)"
    echo -e "    ${CYAN}opencapture status${NC}             Check running state"
    echo -e "    ${CYAN}opencapture stop${NC}               Stop"
    echo ""
    echo -e "  ${BOLD}AI Analysis:${NC}"
    echo ""
    echo -e "  Analysis requires an LLM. We support local Ollama and remote APIs."
    echo ""
    echo -e "    Local (Ollama):  ${CYAN}brew install ollama && ollama pull qwen3-vl:4b${NC}"
    echo -e "    Remote (OpenAI): ${CYAN}export OPENAI_API_KEY=sk-xxx${NC}"
    echo ""
    echo -e "    ${CYAN}opencapture analyze today${NC}                        Analyze today"
    echo -e "    ${CYAN}opencapture analyze today --provider openai${NC}      Use OpenAI"
    echo ""
    echo -e "  ${CYAN}opencapture help${NC}  for all commands"
    echo ""
    echo -e "  Config:  ${BLUE}~/.opencapture/config.yaml${NC}"
    echo -e "  Data:    ${BLUE}~/opencapture/${NC}"
    echo ""
}

# Main
main() {
    TOTAL_STEPS=6

    print_banner

    echo -e "  This will install:"
    echo -e "    • Python 3.9+ (if needed)"
    echo -e "    • OpenCapture"
    echo ""
    echo -e "  Ollama and AI models are ${BOLD}not${NC} required for recording."
    echo -e "  They will be needed only when you run analysis."
    echo ""

    read -p "  Continue? [Y/n] " -n 1 -r < /dev/tty
    echo
    [[ $REPLY =~ ^[Nn]$ ]] && exit 0

    step 1 "Detecting environment"
    detect_os
    [[ "$OS" == "macos" ]] && install_homebrew

    step 2 "Installing dependencies"
    install_system_deps
    install_python

    step 3 "Downloading OpenCapture"
    clone_project

    step 4 "Setting up Python environment"
    setup_python_env

    step 5 "Configuring"
    create_app_bundle
    create_config
    create_launcher
    configure_path

    step 6 "Done"
    print_success
}

main "$@"
