#!/usr/bin/env bash
# deploy.sh — 一键部署 find-new-tech
# 用法: bash deploy.sh [--upgrade]
#   --upgrade  强制重新安装/升级所有依赖

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${RESET}"; }

# ── 参数解析 ─────────────────────────────────────────────
UPGRADE=false
for arg in "$@"; do
  [[ "$arg" == "--upgrade" ]] && UPGRADE=true
done

# ── 工作目录 ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}=====================================${RESET}"
echo -e "${BOLD}   find-new-tech 部署脚本${RESET}"
echo -e "${BOLD}=====================================${RESET}"

# ── 1. Python 版本检查 ───────────────────────────────────
step "检查 Python 版本"

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=${ver%%.*}; minor=${ver##*.}
    if [[ $major -ge 3 && $minor -ge 10 ]]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  error "需要 Python 3.10 或更高版本，请先安装。"
  exit 1
fi
success "使用 $PYTHON ($("$PYTHON" --version))"

# ── 2. 创建虚拟环境 ──────────────────────────────────────
step "配置虚拟环境 (.venv)"

VENV_DIR="$SCRIPT_DIR/.venv"
if [[ -d "$VENV_DIR" && "$UPGRADE" == false ]]; then
  info "虚拟环境已存在，跳过创建（使用 --upgrade 可强制重建）"
else
  if [[ -d "$VENV_DIR" ]]; then
    info "删除旧虚拟环境..."
    rm -rf "$VENV_DIR"
  fi
  info "创建虚拟环境..."
  "$PYTHON" -m venv "$VENV_DIR"
  success "虚拟环境创建完成: $VENV_DIR"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
PIP="$VENV_DIR/bin/pip"

# ── 3. 安装依赖 ──────────────────────────────────────────
step "安装 Python 依赖"

"$PIP" install --upgrade pip --quiet
if [[ "$UPGRADE" == true ]]; then
  info "升级模式：重新安装所有依赖..."
  "$PIP" install --upgrade -r requirements.txt
else
  "$PIP" install -r requirements.txt --quiet
fi
success "依赖安装完成"

# ── 4. 配置环境变量 ──────────────────────────────────────
step "配置环境变量 (.env)"

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  warn ".env 文件已从 .env.example 创建，请编辑并填入必要配置："
  warn "  API_KEY=your_key_here"
  warn "  编辑命令: \$EDITOR $SCRIPT_DIR/.env"
else
  info ".env 文件已存在，跳过创建"
fi

# 检查 API_KEY 是否已设置
if grep -q "^API_KEY=your" "$SCRIPT_DIR/.env" 2>/dev/null || \
   grep -qE "^API_KEY=\s*$" "$SCRIPT_DIR/.env" 2>/dev/null; then
  warn "API_KEY 尚未配置，服务启动后将无法生成报告。"
  warn "请编辑 .env 文件并填入有效的 API Key。"
else
  success "API_KEY 已配置"
fi

# ── 5. 创建必要目录 ──────────────────────────────────────
step "创建运行时目录"

mkdir -p "$SCRIPT_DIR/reports"
mkdir -p "$SCRIPT_DIR/logs"
success "目录就绪: reports/, logs/"

# ── 6. 验证应用能否导入 ──────────────────────────────────
step "验证应用模块"

if "$VENV_DIR/bin/python" -c "from app.main import app" 2>/dev/null; then
  success "应用模块验证通过"
else
  error "应用模块导入失败，请检查代码或依赖是否完整。"
  exit 1
fi

# ── 完成 ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}=====================================${RESET}"
echo -e "${GREEN}${BOLD}   部署完成！${RESET}"
echo -e "${GREEN}${BOLD}=====================================${RESET}"
echo ""
echo -e "  启动服务:   ${CYAN}bash service.sh start${RESET}"
echo -e "  查看状态:   ${CYAN}bash service.sh status${RESET}"
echo -e "  查看日志:   ${CYAN}bash service.sh logs${RESET}"
echo -e "  访问地址:   ${CYAN}http://localhost:8000${RESET}"
echo ""
