"""
publisher.py — 将 reports/ 下的 Markdown 报告发布到 GitHub Pages（Jekyll 博客）
"""

import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FLAT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(-(?:zh|en))?$")
_RESEARCH_RE = re.compile(r"^research-\d+$")

_SCRIPT_DIR = Path(__file__).parent.parent
_REPORTS_DIR = _SCRIPT_DIR / "reports"
_TEMPLATE_DIR = _SCRIPT_DIR / "_site_template"
_GH_PAGES_DIR = _SCRIPT_DIR / "_gh_pages"


# ── 工具函数 ──────────────────────────────────────────────


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _git(*args: str, cwd: Path = _GH_PAGES_DIR) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


def _push_url(repo_url: str, token: str) -> str:
    """将 GitHub token 嵌入 HTTPS URL，用于无交互推送。"""
    if token and repo_url.startswith("https://github.com/"):
        return repo_url.replace("https://", f"https://{token}@")
    return repo_url


def _extract_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip().replace('"', "'")
    return f"Tech Digest {path.stem}"


def _extract_body(path: Path) -> str:
    """返回正文：标题行前的内容（如财经速递）+ 标题行后的内容，标题行本身被 front matter 替代。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            pre = "".join(lines[:i]).strip()
            post = "".join(lines[i + 1 :]).lstrip("\n")
            return (pre + "\n\n" + post) if pre else post
    return path.read_text(encoding="utf-8")


def _build_post(src: Path, date_str: str, lang: str = "zh") -> str:
    title = _extract_title(src)
    body = _extract_body(src)
    return (
        f'---\nlayout: post\ntitle: "{title}"\n'
        f"date: {date_str} 09:00:00 +0800\ncategories: digest\nlang: {lang}\n---\n\n{body}"
    )


def _write_post_if_changed(
    src: Path, dest: Path, date_str: str, lang: str = "zh"
) -> bool:
    """写入 post 文件，内容未变则跳过。返回是否实际写入。"""
    content = _build_post(src, date_str, lang)
    if dest.exists() and dest.read_text(encoding="utf-8") == content:
        return False
    dest.write_text(content, encoding="utf-8")
    return True


# ── 主流程 ────────────────────────────────────────────────


async def publish_reports(
    repo_url: str,
    github_token: str = "",
    force_all: bool = False,
) -> AsyncGenerator[str, None]:
    """
    异步生成器，依次 yield SSE 事件字符串。
    事件类型: cloning | initializing | copying | pushing | complete | error
    """
    if not repo_url:
        yield _sse({"status": "error", "message": "未配置 GITHUB_PAGES_REPO"})
        return

    # 1. 确保 reports/ 有内容（新布局：子目录；旧布局：平铺 .md）
    has_content = _REPORTS_DIR.exists() and (
        any(d.is_dir() and _DATE_RE.match(d.name) for d in _REPORTS_DIR.iterdir())
        or any(_REPORTS_DIR.glob("*.md"))
    )
    if not has_content:
        yield _sse({"status": "error", "message": "reports/ 目录为空，请先生成报告"})
        return

    # 2. Clone 或 Pull
    posts_dir = _GH_PAGES_DIR / "_posts"
    if (_GH_PAGES_DIR / ".git").exists():
        yield _sse({"status": "cloning", "message": "拉取最新内容..."})
        await _git("pull", "--quiet", "origin", "HEAD")
    else:
        yield _sse({"status": "cloning", "message": f"克隆仓库 {repo_url}..."})
        _GH_PAGES_DIR.mkdir(parents=True, exist_ok=True)
        code, _, err = await _git("clone", repo_url, ".", cwd=_GH_PAGES_DIR)
        if code != 0:
            # 仓库为空时 clone 失败，改为 init
            await _git("init", cwd=_GH_PAGES_DIR)
            await _git("remote", "add", "origin", repo_url, cwd=_GH_PAGES_DIR)

    posts_dir.mkdir(parents=True, exist_ok=True)

    # 3. 同步模板文件（每次发布都更新，确保最新布局/样式/JS）
    initialized = not (_GH_PAGES_DIR / "_config.yml").exists()
    if initialized:
        yield _sse({"status": "initializing", "message": "初始化 Jekyll 站点..."})
        (_GH_PAGES_DIR / ".gitignore").write_text(
            "_site/\n.sass-cache/\n.jekyll-cache/\n.jekyll-metadata\nvendor/\nGemfile.lock\n",
            encoding="utf-8",
        )
    if _TEMPLATE_DIR.exists():
        for src in sorted(_TEMPLATE_DIR.rglob("*")):
            if src.is_file():
                rel = src.relative_to(_TEMPLATE_DIR)
                dest = _GH_PAGES_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # 4. 收集可发布的报告（新布局优先，旧版平铺兼容）
    # publishable: date_str -> {"zh": Path|None, "en": Path|None}
    publishable: dict[str, dict[str, Path | None]] = {}
    # 新布局: reports/{date}/zh.md, en.md
    if _REPORTS_DIR.exists():
        for day_dir in _REPORTS_DIR.iterdir():
            if not day_dir.is_dir() or not _DATE_RE.match(day_dir.name):
                continue
            zh = day_dir / "zh.md"
            en = day_dir / "en.md"
            if zh.exists() or en.exists():
                publishable[day_dir.name] = {
                    "zh": zh if zh.exists() else None,
                    "en": en if en.exists() else None,
                }
    # 旧版平铺: reports/{date}-zh.md / {date}-en.md / {date}.md
    for path in sorted(_REPORTS_DIR.glob("*.md")):
        m = _FLAT_RE.match(path.stem)
        if not m:
            continue
        date_key = m.group(1)
        if date_key in publishable:
            continue  # 已有新布局版本，跳过
        if date_key not in publishable:
            publishable[date_key] = {"zh": None, "en": None}
        suffix = m.group(2)
        if suffix == "-en":
            publishable[date_key]["en"] = path
        else:  # "-zh" 或无后缀旧合并文件，均视为中文
            publishable[date_key]["zh"] = path

    new_count = 0
    for date_str, files in sorted(publishable.items()):
        dest_dir = posts_dir / date_str
        dest_dir.mkdir(parents=True, exist_ok=True)
        changed = False
        if files["zh"]:
            changed |= _write_post_if_changed(
                files["zh"], dest_dir / f"{date_str}-zh.md", date_str, "zh"
            )
        if files["en"]:
            changed |= _write_post_if_changed(
                files["en"], dest_dir / f"{date_str}-en.md", date_str, "en"
            )
        if changed:
            new_count += 1

    # 发布调研报告（research-*.md）
    if _REPORTS_DIR.exists():
        for day_dir in _REPORTS_DIR.iterdir():
            if not day_dir.is_dir() or not _DATE_RE.match(day_dir.name):
                continue
            d_str = day_dir.name
            for src in day_dir.glob("research-*.md"):
                if not _RESEARCH_RE.match(src.stem):
                    continue
                dest_dir = posts_dir / d_str
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_name = f"{d_str}-{src.stem}.md"
                if _write_post_if_changed(src, dest_dir / dest_name, d_str, "zh"):
                    new_count += 1

    yield _sse({"status": "copying", "new": new_count, "skip": 0})

    # 5. git config（防止 CI 环境无 user 配置报错）
    await _git("config", "user.email", "find-new-tech-bot@noreply")
    await _git("config", "user.name", "find-new-tech")

    # 6. Commit
    await _git("add", "-A")
    code, _, _ = await _git("diff", "--cached", "--quiet")
    if code == 0:  # 无变更
        yield _sse({"status": "complete", "new": 0, "url": _pages_url(repo_url)})
        return

    msg = f"docs: publish {new_count} report(s)"
    await _git("commit", "-m", msg)

    # 7. Push
    yield _sse({"status": "pushing", "message": "推送到 GitHub..."})
    push_url = _push_url(repo_url, github_token)
    code, _, err = await _git("push", push_url, "HEAD:main")
    if code != 0:
        # 首次推送，尝试 --set-upstream
        code, _, err = await _git("push", "-u", push_url, "HEAD:main")
    if code != 0:
        yield _sse({"status": "error", "message": err.strip() or "推送失败"})
        return

    pages_url = _pages_url(repo_url)
    yield _sse({"status": "complete", "new": new_count, "url": pages_url})


def _pages_url(repo_url: str) -> str:
    """从 git remote URL 推导 GitHub Pages 访问地址。"""
    url = repo_url.removesuffix(".git")
    url = url.replace("https://github.com/", "")
    parts = url.split("/")
    if len(parts) == 2:
        user, repo = parts
        return f"https://{user}.github.io/{repo}/"
    return ""
