#!/usr/bin/env bash
# service.sh — find-new-tech 服务管理脚本
# 用法: bash service.sh <command> [options]
#
# Commands:
#   start   [--host HOST] [--port PORT] [--workers N]  启动服务
#   stop                                                停止服务
#   restart [--host HOST] [--port PORT] [--workers N]  重启服务
#   status                                              查看运行状态
#   logs    [-n LINES] [-f]                             查看日志
#   reload                                              热重载（仅开发模式）

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

# ── 常量 ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
UVICORN="$VENV_DIR/bin/uvicorn"
PID_FILE="$SCRIPT_DIR/.service.pid"
LOG_FILE="$SCRIPT_DIR/logs/app.log"
APP_MODULE="app.main:app"

DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8000"
DEFAULT_WORKERS="1"

# ── 辅助函数 ─────────────────────────────────────────────
check_venv() {
  if [[ ! -f "$UVICORN" ]]; then
    error "虚拟环境未找到，请先运行部署脚本："
    error "  bash deploy.sh"
    exit 1
  fi
}

get_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid=$(cat "$PID_FILE")
    # 验证进程确实存在
    if kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    else
      # PID 文件残留，清理
      rm -f "$PID_FILE"
    fi
  fi
  echo ""
}

is_running() {
  [[ -n "$(get_pid)" ]]
}

# 从进程命令行参数中读取实际监听端口
get_running_port() {
  local pid="$1"
  ps -p "$pid" -o args= 2>/dev/null \
    | grep -oE -- '--port [0-9]+' \
    | awk '{print $2}'
}

ensure_dirs() {
  mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/reports"
}

# ── 命令：start ───────────────────────────────────────────
cmd_start() {
  check_venv
  ensure_dirs

  # 参数解析
  local host="$DEFAULT_HOST"
  local port="$DEFAULT_PORT"
  local workers="$DEFAULT_WORKERS"
  local dev_mode=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host)    host="$2";    shift 2 ;;
      --port)    port="$2";    shift 2 ;;
      --workers) workers="$2"; shift 2 ;;
      --dev)     dev_mode=true; shift ;;
      *) error "未知参数: $1"; exit 1 ;;
    esac
  done

  if is_running; then
    local pid
    pid=$(get_pid)
    warn "服务已在运行中 (PID: $pid)"
    warn "如需重启，请使用: bash service.sh restart"
    exit 0
  fi

  info "启动 find-new-tech 服务..."
  info "  地址: http://${host}:${port}"
  info "  日志: $LOG_FILE"

  # 构建 uvicorn 命令
  local uvicorn_args=(
    "$APP_MODULE"
    "--host" "$host"
    "--port" "$port"
    "--log-level" "info"
  )

  if [[ "$dev_mode" == true ]]; then
    uvicorn_args+=("--reload")
    info "  模式: 开发模式（--reload）"
  else
    uvicorn_args+=("--workers" "$workers")
    info "  Workers: $workers"
  fi

  # 切换到项目根目录再启动（保证相对路径正确）
  cd "$SCRIPT_DIR"

  # 后台启动，输出重定向到日志
  nohup "$VENV_DIR/bin/python" -m uvicorn "${uvicorn_args[@]}" \
    >> "$LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" > "$PID_FILE"

  # 等待服务就绪
  local retries=15
  local ready=false
  while [[ $retries -gt 0 ]]; do
    sleep 0.5
    if kill -0 "$pid" 2>/dev/null; then
      # 尝试 HTTP 检查
      if command -v curl &>/dev/null; then
        if curl -sf "http://localhost:${port}/" -o /dev/null 2>/dev/null; then
          ready=true
          break
        fi
      else
        ready=true
        break
      fi
    else
      error "进程启动后立即退出，请检查日志："
      error "  bash service.sh logs"
      rm -f "$PID_FILE"
      exit 1
    fi
    retries=$((retries - 1))
  done

  if [[ "$ready" == true ]]; then
    success "服务启动成功 (PID: $pid)"
    echo -e "  访问地址: ${CYAN}http://localhost:${port}${RESET}"
  else
    success "服务已启动 (PID: $pid)，正在初始化..."
    echo -e "  访问地址: ${CYAN}http://localhost:${port}${RESET}"
    echo -e "  查看日志: ${CYAN}bash service.sh logs -f${RESET}"
  fi
}

# ── 命令：stop ────────────────────────────────────────────
cmd_stop() {
  if ! is_running; then
    warn "服务未运行"
    return 0
  fi

  local pid
  pid=$(get_pid)
  info "正在停止服务 (PID: $pid)..."

  kill -TERM "$pid" 2>/dev/null || true

  # 等待进程退出
  local retries=20
  while kill -0 "$pid" 2>/dev/null && [[ $retries -gt 0 ]]; do
    sleep 0.5
    retries=$((retries - 1))
  done

  if kill -0 "$pid" 2>/dev/null; then
    warn "进程未响应 SIGTERM，发送 SIGKILL..."
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
  fi

  rm -f "$PID_FILE"
  success "服务已停止"
}

# ── 命令：restart ─────────────────────────────────────────
cmd_restart() {
  info "重启服务..."
  cmd_stop
  sleep 1
  cmd_start "$@"
}

# ── 命令：status ──────────────────────────────────────────
cmd_status() {
  echo -e "${BOLD}find-new-tech 服务状态${RESET}"
  echo "────────────────────────────"

  if is_running; then
    local pid
    pid=$(get_pid)
    success "运行中 (PID: $pid)"

    # 进程信息
    if command -v ps &>/dev/null; then
      local cpu mem start_time
      cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ' || echo "N/A")
      mem=$(ps -p "$pid" -o %mem= 2>/dev/null | tr -d ' ' || echo "N/A")
      start_time=$(ps -p "$pid" -o lstart= 2>/dev/null | xargs || echo "N/A")
      echo -e "  CPU 占用: ${cpu}%"
      echo -e "  内存占用: ${mem}%"
      echo -e "  启动时间: $start_time"
    fi

    # HTTP 可达性（使用进程实际监听端口）
    local port
    port=$(get_running_port "$pid")
    port="${port:-$DEFAULT_PORT}"
    if command -v curl &>/dev/null; then
      if curl -sf "http://localhost:${port}/" -o /dev/null 2>/dev/null; then
        echo -e "  HTTP 状态: ${GREEN}可访问 http://localhost:${port}${RESET}"
      else
        echo -e "  HTTP 状态: ${YELLOW}进程运行但 HTTP 未就绪${RESET}"
      fi
    fi
  else
    echo -e "  状态: ${RED}未运行${RESET}"
  fi

  # 报告统计
  local report_count=0
  if [[ -d "$SCRIPT_DIR/reports" ]]; then
    report_count=$(find "$SCRIPT_DIR/reports" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  fi
  echo -e "  已生成报告: ${report_count} 篇"

  # 日志大小
  if [[ -f "$LOG_FILE" ]]; then
    local log_size
    log_size=$(du -sh "$LOG_FILE" 2>/dev/null | cut -f1 || echo "N/A")
    echo -e "  日志大小: $log_size ($LOG_FILE)"
  fi

  echo "────────────────────────────"
}

# ── 命令：logs ────────────────────────────────────────────
cmd_logs() {
  local lines=50
  local follow=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n) lines="$2"; shift 2 ;;
      -f|--follow) follow=true; shift ;;
      *) error "未知参数: $1"; exit 1 ;;
    esac
  done

  if [[ ! -f "$LOG_FILE" ]]; then
    warn "日志文件不存在: $LOG_FILE"
    warn "请先启动服务: bash service.sh start"
    exit 0
  fi

  if [[ "$follow" == true ]]; then
    info "实时追踪日志（Ctrl+C 退出）..."
    tail -n "$lines" -f "$LOG_FILE"
  else
    tail -n "$lines" "$LOG_FILE"
  fi
}

# ── 命令：reload（开发用） ────────────────────────────────
cmd_reload() {
  if ! is_running; then
    warn "服务未运行，无法热重载"
    exit 1
  fi
  local pid
  pid=$(get_pid)
  info "发送 SIGHUP 信号以触发热重载 (PID: $pid)..."
  kill -HUP "$pid" 2>/dev/null || {
    warn "SIGHUP 不支持，改用 restart..."
    cmd_restart
  }
  success "热重载信号已发送"
}

# ── 帮助信息 ─────────────────────────────────────────────
cmd_help() {
  echo -e "${BOLD}用法: bash service.sh <command> [options]${RESET}"
  echo ""
  echo -e "${BOLD}命令:${RESET}"
  echo "  start    启动服务"
  echo "           --host HOST      监听地址 (默认: 0.0.0.0)"
  echo "           --port PORT      监听端口 (默认: 8000)"
  echo "           --workers N      Worker 数量 (默认: 1)"
  echo "           --dev            开发模式（启用 --reload）"
  echo "  stop     停止服务"
  echo "  restart  重启服务（支持与 start 相同的选项）"
  echo "  status   查看运行状态"
  echo "  logs     查看日志"
  echo "           -n LINES         显示最近 N 行 (默认: 50)"
  echo "           -f, --follow     实时追踪日志"
  echo "  reload   热重载（发送 SIGHUP，开发模式有效）"
  echo ""
  echo -e "${BOLD}示例:${RESET}"
  echo "  bash service.sh start"
  echo "  bash service.sh start --port 9000 --workers 2"
  echo "  bash service.sh start --dev"
  echo "  bash service.sh status"
  echo "  bash service.sh logs -f"
  echo "  bash service.sh restart --port 9000"
  echo "  bash service.sh stop"
}

# ── 入口 ─────────────────────────────────────────────────
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
  start)   cmd_start   "$@" ;;
  stop)    cmd_stop        ;;
  restart) cmd_restart "$@" ;;
  status)  cmd_status      ;;
  logs)    cmd_logs    "$@" ;;
  reload)  cmd_reload      ;;
  help|-h|--help) cmd_help ;;
  *)
    error "未知命令: $COMMAND"
    echo ""
    cmd_help
    exit 1
    ;;
esac
