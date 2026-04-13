#!/usr/bin/env bash
# publish.sh — 将 reports/ 下的 Markdown 报告发布到 GitHub Pages
#
# 用法:
#   bash publish.sh                  # 仅发布新增报告
#   bash publish.sh --all            # 重新发布所有报告
#   bash publish.sh --repo <url>     # 临时指定 GitHub 仓库地址
#
# 配置（在 .env 中设置）:
#   GITHUB_PAGES_REPO=https://github.com/<user>/<repo>.git

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${RESET}"; }

# ── 路径常量 ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="$SCRIPT_DIR/reports"
TEMPLATE_DIR="$SCRIPT_DIR/_site_template"
GH_PAGES_DIR="$SCRIPT_DIR/_gh_pages"

# ── 参数解析 ─────────────────────────────────────────────
PUBLISH_ALL=false
REPO_URL_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)          PUBLISH_ALL=true; shift ;;
    --repo)         REPO_URL_ARG="$2"; shift 2 ;;
    -h|--help)      grep "^#" "$0" | head -15 | sed 's/^# \?//'; exit 0 ;;
    *) error "未知参数: $1"; exit 1 ;;
  esac
done

# ── 读取配置 ─────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^[[:space:]]*$' | xargs)
fi

GITHUB_PAGES_REPO="${REPO_URL_ARG:-${GITHUB_PAGES_REPO:-}}"

if [[ -z "$GITHUB_PAGES_REPO" ]]; then
  error "未配置 GitHub Pages 仓库地址。"
  error "请在 .env 中添加：GITHUB_PAGES_REPO=https://github.com/<user>/<repo>.git"
  error "或使用参数：bash publish.sh --repo https://github.com/<user>/<repo>.git"
  exit 1
fi

# ── 检查依赖 ─────────────────────────────────────────────
if ! command -v git &>/dev/null; then
  error "需要安装 git"; exit 1
fi

# ── 工具函数 ─────────────────────────────────────────────

# 从 Markdown 文件提取第一个 # 标题，作为文章标题
extract_title() {
  local file="$1"
  local title
  title=$(grep -m1 "^#[^#]" "$file" | sed 's/^#[[:space:]]*//' | tr -d '"')
  if [[ -z "$title" ]]; then
    # 回退：用日期作标题
    title="Tech Digest $(basename "$file" .md)"
  fi
  echo "$title"
}

# 提取正文（跳过第一个 # 标题行，避免与 Jekyll title 重复）
extract_body() {
  local file="$1"
  # 如果第一行是 # 标题，从第二行开始；否则保留全文
  if head -1 "$file" | grep -q "^#[^#]"; then
    tail -n +2 "$file"
  else
    cat "$file"
  fi
}

# 将报告文件注入 Jekyll Front Matter 并写入目标路径
convert_to_post() {
  local src="$1"       # 源文件，如 reports/2026-04-13.md
  local dest="$2"      # 目标文件，如 _gh_pages/_posts/2026-04-13-daily-digest.md
  local date_str="$3"  # 2026-04-13

  local title
  title=$(extract_title "$src")

  # 写入 front matter + 正文
  {
    echo "---"
    echo "layout: post"
    echo "title: \"$title\""
    echo "date: ${date_str} 09:00:00 +0800"
    echo "categories: digest"
    echo "---"
    echo ""
    extract_body "$src"
  } > "$dest"
}

# ── Step 1: 准备本地 GitHub Pages 仓库 ──────────────────
step "准备 GitHub Pages 本地仓库"

if [[ -d "$GH_PAGES_DIR/.git" ]]; then
  info "拉取最新内容..."
  git -C "$GH_PAGES_DIR" pull --quiet origin HEAD 2>/dev/null || true
else
  info "首次克隆仓库：$GITHUB_PAGES_REPO"
  if git clone "$GITHUB_PAGES_REPO" "$GH_PAGES_DIR" 2>/dev/null; then
    success "克隆成功"
  else
    info "仓库为空或不存在，初始化本地仓库..."
    mkdir -p "$GH_PAGES_DIR"
    git -C "$GH_PAGES_DIR" init
    git -C "$GH_PAGES_DIR" remote add origin "$GITHUB_PAGES_REPO"
  fi
fi

# ── Step 2: 初始化 Jekyll 骨架（仅首次） ────────────────
step "检查 Jekyll 站点配置"

POSTS_DIR="$GH_PAGES_DIR/_posts"
mkdir -p "$POSTS_DIR"

INITIALIZED=false
if [[ ! -f "$GH_PAGES_DIR/_config.yml" ]]; then
  info "首次初始化，复制 Jekyll 模板..."
  cp "$TEMPLATE_DIR/_config.yml" "$GH_PAGES_DIR/_config.yml"
  cp "$TEMPLATE_DIR/index.md"    "$GH_PAGES_DIR/index.md"
  cp "$TEMPLATE_DIR/Gemfile"     "$GH_PAGES_DIR/Gemfile"

  # 写入 .gitignore（忽略 Jekyll 构建产物）
  cat > "$GH_PAGES_DIR/.gitignore" <<'EOF'
_site/
.sass-cache/
.jekyll-cache/
.jekyll-metadata
vendor/
Gemfile.lock
EOF
  INITIALIZED=true
  success "Jekyll 骨架初始化完成"
else
  info "Jekyll 配置已存在，跳过初始化"
fi

# ── Step 3: 转换并复制报告 ───────────────────────────────
step "处理报告文件"

if [[ ! -d "$REPORTS_DIR" ]] || [[ -z "$(ls "$REPORTS_DIR"/*.md 2>/dev/null)" ]]; then
  warn "reports/ 目录为空，暂无报告可发布。"
  warn "请先通过 Web UI 或 API 生成报告，再运行此脚本。"
  exit 0
fi

NEW_COUNT=0
SKIP_COUNT=0

for report in "$REPORTS_DIR"/*.md; do
  date_str=$(basename "$report" .md)

  # 校验文件名格式为 YYYY-MM-DD
  if ! [[ "$date_str" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    warn "跳过非标准文件名: $(basename "$report")"
    continue
  fi

  dest="$POSTS_DIR/${date_str}-daily-digest.md"

  if [[ "$PUBLISH_ALL" == false && -f "$dest" ]]; then
    SKIP_COUNT=$((SKIP_COUNT + 1))
    continue
  fi

  convert_to_post "$report" "$dest" "$date_str"
  info "已转换: $(basename "$report") → _posts/$(basename "$dest")"
  NEW_COUNT=$((NEW_COUNT + 1))
done

if [[ $NEW_COUNT -eq 0 && "$INITIALIZED" == false ]]; then
  success "所有报告已是最新状态（跳过 ${SKIP_COUNT} 篇），无需推送。"
  exit 0
fi

echo ""
info "新增/更新: ${NEW_COUNT} 篇，跳过: ${SKIP_COUNT} 篇"

# ── Step 4: 提交并推送 ──────────────────────────────────
step "提交并推送到 GitHub"

git -C "$GH_PAGES_DIR" add -A

# 检查是否有实际变更
if git -C "$GH_PAGES_DIR" diff --cached --quiet; then
  success "没有变更需要提交。"
  exit 0
fi

COMMIT_MSG="docs: publish ${NEW_COUNT} report(s) on $(date +%Y-%m-%d)"
git -C "$GH_PAGES_DIR" commit -m "$COMMIT_MSG"

info "推送到 GitHub..."
if git -C "$GH_PAGES_DIR" push origin HEAD 2>&1; then
  success "推送成功！"
else
  # 首次推送，指定分支
  git -C "$GH_PAGES_DIR" push -u origin main 2>&1 || \
  git -C "$GH_PAGES_DIR" push -u origin master 2>&1
  success "推送成功！"
fi

# ── 完成 ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}=====================================${RESET}"
echo -e "${GREEN}${BOLD}   发布完成！${RESET}"
echo -e "${GREEN}${BOLD}=====================================${RESET}"
echo ""
REPO_WEB="${GITHUB_PAGES_REPO%.git}"
REPO_WEB="${REPO_WEB/git@github.com:/https://github.com/}"
# 提取 GitHub Pages URL
GH_USER=$(echo "$REPO_WEB" | sed 's|https://github.com/||' | cut -d'/' -f1)
GH_REPO=$(echo "$REPO_WEB" | sed 's|https://github.com/||' | cut -d'/' -f2)

echo -e "  仓库地址:   ${CYAN}${REPO_WEB}${RESET}"
echo -e "  Pages 地址: ${CYAN}https://${GH_USER}.github.io/${GH_REPO}/${RESET}"
echo ""
echo -e "  ${YELLOW}提示：首次部署需在 GitHub 仓库 Settings → Pages 中${RESET}"
echo -e "  ${YELLOW}将 Source 设置为 'Deploy from a branch'，Branch 选 main${RESET}"
echo ""
