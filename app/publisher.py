"""
publisher.py — 将 reports/ 下的 Markdown 报告发布到 GitHub Pages（Jekyll 博客）
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import AsyncGenerator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FLAT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(-(?:zh|en))?$")
_RESEARCH_RE = re.compile(r"^research-\d+$")
# 同步时兼容旧格式（research-1.md）和新格式（research-1-slug.md）
_POST_FILE_RE_RESEARCH = re.compile(r"^(\d{4}-\d{2}-\d{2})-(research-\d+)(?:-.+)?\.md$")

_SCRIPT_DIR = Path(__file__).parent.parent
_REPORTS_DIR = _SCRIPT_DIR / "reports"
_TEMPLATE_DIR = _SCRIPT_DIR / "_site_template"
_GH_PAGES_DIR = _SCRIPT_DIR / "_gh_pages"


# ── 工具函数 ──────────────────────────────────────────────


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _git(*args: str, cwd: Path = _GH_PAGES_DIR) -> tuple[int, str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


def _push_url(repo_url: str, token: str) -> str:
    """将 GitHub token 嵌入 HTTPS URL，用于无交互推送。"""
    if token and repo_url.startswith("https://github.com/"):
        return repo_url.replace("https://", f"https://oauth2:{token}@")
    return repo_url


def _extract_title(path: Path) -> str:
    date_str = path.parent.name if _DATE_RE.match(path.parent.name) else ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            candidate = line[2:].strip().replace('"', "'")
            # 日报标题
            if "DailyPulse" in candidate or "Daily Tech" in candidate:
                return candidate
            # 调研报告：提取实际主题作为标题
            for prefix in ("📋 调研报告：", "📋 调研报告:", "📋 "):
                if candidate.startswith(prefix):
                    topic = candidate[len(prefix):].strip()
                    return f"DailyPulse · 调研 | {topic}" if topic else f"DailyPulse · 调研报告 | {date_str}"
            break
    # fallback：根据文件名生成标准标题
    stem = path.stem
    if "research" in stem:
        return f"DailyPulse · 调研报告 | {date_str}" if date_str else "DailyPulse · 调研报告"
    return f"DailyPulse · 每日脉搏 | {date_str}" if date_str else "DailyPulse · 每日脉搏"


def _title_slug(title: str, maxlen: int = 30) -> str:
    """从标题生成文件名 slug，保留中文和英文字母数字，去除 emoji 和特殊符号。"""
    cleaned = re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9 ]", "", title)
    cleaned = re.sub(r" +", "-", cleaned.strip())
    return cleaned[:maxlen].strip("-")


def _research_slug(src: Path) -> str:
    """从调研报告中提取主题 slug，用于 GitHub 文件名。"""
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            for prefix in ("📋 调研报告：", "📋 调研报告:", "📋 ", "Research Report: ", "Research: "):
                if title.startswith(prefix):
                    title = title[len(prefix):]
            return _title_slug(title)
    return ""


def _extract_body(path: Path) -> str:
    """返回正文：标题行前的内容（如财经速递）+ 标题行后的内容，标题行本身被 front matter 替代。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            pre = "".join(lines[:i]).strip()
            post = "".join(lines[i + 1 :]).lstrip("\n")
            return (pre + "\n\n" + post) if pre else post
    # 没有 # 标题行，整个文件内容作为正文
    return path.read_text(encoding="utf-8").strip()


def _build_post(
    src: Path, date_str: str, lang: str = "zh", is_research: bool = False
) -> str:
    title = _extract_title(src)
    body = _extract_body(src)

    # Chirpy theme front matter
    if is_research:
        categories = "  - Research"
        tags = f"  - research\n  - {lang}"
    else:
        categories = "  - Digest"
        tags = f"  - {lang}\n  - daily"

    return (
        f"---\n"
        f'title: "{title}"\n'
        f"date: {date_str} 09:00:00 +0800\n"
        f"categories:\n{categories}\n"
        f"tags:\n{tags}\n"
        f"---\n\n{body}"
    )


def _write_post_if_changed(
    src: Path, dest: Path, date_str: str, lang: str = "zh", is_research: bool = False,
    force: bool = False,
) -> bool:
    """写入 post 文件，内容未变则跳过。返回是否实际写入。"""
    content = _build_post(src, date_str, lang, is_research)
    if not force and dest.exists() and dest.read_text(encoding="utf-8") == content:
        return False
    dest.write_text(content, encoding="utf-8")
    return True


# ── 主流程 ────────────────────────────────────────────────


async def publish_reports(
    repo_url: str,
    github_token: str = "",
    force_all: bool = False,
    site_email: str = "",
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

    # 3. 同步模板文件（每次发布都更新，确保最新配置）
    initialized = not (_GH_PAGES_DIR / "_config.yml").exists()
    if initialized:
        yield _sse({"status": "initializing", "message": "初始化 Jekyll 站点..."})
    if _TEMPLATE_DIR.exists():
        for src in sorted(_TEMPLATE_DIR.rglob("*")):
            if src.is_file():
                rel = src.relative_to(_TEMPLATE_DIR)
                dest = _GH_PAGES_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                new_content = src.read_text(encoding="utf-8")
                # _config.yml 做占位符替换
                if rel == Path("_config.yml"):
                    new_content = _render_config(new_content, repo_url, site_email)
                # 只在内容变化时写入
                if not dest.exists() or dest.read_text(encoding="utf-8") != new_content:
                    dest.write_text(new_content, encoding="utf-8")

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
        changed = False
        if files["zh"]:
            dest = posts_dir / f"{date_str}-zh.md"
            changed |= _write_post_if_changed(files["zh"], dest, date_str, "zh", force=force_all)
        if files["en"]:
            dest = posts_dir / f"{date_str}-en.md"
            changed |= _write_post_if_changed(files["en"], dest, date_str, "en", force=force_all)
        if changed:
            new_count += 1

    # 发布调研报告（research-*.md），文件名包含标题 slug 方便在 GitHub 上识别
    if _REPORTS_DIR.exists():
        for day_dir in _REPORTS_DIR.iterdir():
            if not day_dir.is_dir() or not _DATE_RE.match(day_dir.name):
                continue
            d_str = day_dir.name
            for src in day_dir.glob("research-*.md"):
                if not _RESEARCH_RE.match(src.stem):
                    continue
                slug = _research_slug(src)
                dest_name = (
                    f"{d_str}-{src.stem}-{slug}.md" if slug else f"{d_str}-{src.stem}.md"
                )
                new_dest = posts_dir / dest_name
                # 清理同一篇报告的旧版本（slug 可能因标题修改而变化）
                for old in posts_dir.glob(f"{d_str}-{src.stem}*.md"):
                    if old != new_dest:
                        old.unlink()
                if _write_post_if_changed(
                    src, new_dest, d_str, "zh", is_research=True, force=force_all
                ):
                    new_count += 1

    yield _sse({"status": "copying", "new": new_count, "skip": 0})

    # 5. git config（防止 CI 环境无 user 配置报错）
    await _git("config", "user.email", "daily-pulse-bot@noreply")
    await _git("config", "user.name", "daily-pulse")

    # 6. Commit（如有未提交变更）
    await _git("add", "-A")
    code_diff, _, _ = await _git("diff", "--cached", "--quiet")
    if code_diff != 0:
        msg = f"docs: publish {new_count} report(s)"
        await _git("commit", "-m", msg)

    # 7. 检查是否有未推送的 commit（涵盖上次 push 失败的情况）
    # @{u} 指向远端追踪分支；若不存在（首次推送）则视为需要推送
    code_ahead, out_ahead, _ = await _git("rev-list", "--count", "@{u}..HEAD")
    has_unpushed = code_ahead != 0 or out_ahead.strip() not in ("0", "")

    if code_diff == 0 and not has_unpushed:
        yield _sse({"status": "complete", "new": 0, "url": _pages_url(repo_url)})
        return

    # 8. Push
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


def _render_config(content: str, repo_url: str, site_email: str = "") -> str:
    """将 _config.yml 中的 {{ }} 占位符替换为从 GITHUB_PAGES_REPO 推导出的实际值。"""
    url = repo_url.removesuffix(".git").replace("https://github.com/", "")
    parts = url.split("/")
    if len(parts) == 2:
        user, repo = parts
        site_url = f"https://{user.lower()}.github.io"
        site_baseurl = f"/{repo}"
        github_username = user
        social_link = f"https://github.com/{user}"
    else:
        site_url = site_baseurl = github_username = social_link = ""

    for placeholder, value in {
        "{{ SITE_URL }}": site_url,
        "{{ SITE_BASEURL }}": site_baseurl,
        "{{ GITHUB_USERNAME }}": github_username,
        "{{ SITE_EMAIL }}": site_email,
        "{{ SITE_SOCIAL_LINK }}": social_link,
    }.items():
        content = content.replace(placeholder, value)
    return content


def _pages_url(repo_url: str) -> str:
    """从 git remote URL 推导 GitHub Pages 访问地址。"""
    url = repo_url.removesuffix(".git")
    url = url.replace("https://github.com/", "")
    parts = url.split("/")
    if len(parts) == 2:
        user, repo = parts
        return f"https://{user}.github.io/{repo}/"
    return ""


# ── 从 GitHub Pages 仓库同步回本地 reports/ ────────────────

# 兼容旧格式（research-1.md）和新格式（research-1-slug.md）
# group(1)=date, group(2)=kind(zh/en/research-N), group(3)=可选slug
_POST_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(zh|en|research-\d+)(?:-(.+))?\.md$")


def _strip_front_matter(path: Path) -> str:
    """去除 Jekyll front matter，恢复 '# 标题' 行，返回原始 Markdown 内容。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    front_matter = text[4:end]
    body = text[end + 5:].lstrip("\n")

    title = ""
    for line in front_matter.splitlines():
        if line.startswith("title:"):
            title = line[6:].strip().strip('"').strip("'")
            break

    if title:
        return f"# {title}\n\n{body}"
    return body


async def sync_from_remote(
    repo_url: str,
    github_token: str = "",
) -> AsyncGenerator[str, None]:
    """
    从 GitHub Pages 仓库的 _posts/ 目录同步文章回本地 reports/ 目录。
    异步生成器，依次 yield SSE 事件字符串。
    事件类型: cloning | syncing | complete | error
    """
    if not repo_url:
        yield _sse({"status": "error", "message": "未配置 GITHUB_PAGES_REPO"})
        return

    # 1. Clone 或 Pull
    clone_url = _push_url(repo_url, github_token)
    if (_GH_PAGES_DIR / ".git").exists():
        yield _sse({"status": "cloning", "message": "拉取最新内容..."})
        await _git("pull", "--quiet", "origin", "HEAD")
    else:
        yield _sse({"status": "cloning", "message": f"克隆仓库 {repo_url}..."})
        _GH_PAGES_DIR.mkdir(parents=True, exist_ok=True)
        code, _, err = await _git("clone", clone_url, ".", cwd=_GH_PAGES_DIR)
        if code != 0:
            yield _sse({"status": "error", "message": err.strip() or "克隆失败"})
            return

    posts_dir = _GH_PAGES_DIR / "_posts"
    if not posts_dir.exists():
        yield _sse({"status": "complete", "synced": 0, "skipped": 0})
        return

    yield _sse({"status": "syncing", "message": "正在解析并同步文章..."})

    # 2. 解析 _posts/ 写入 reports/
    _REPORTS_DIR.mkdir(exist_ok=True)
    synced = 0
    skipped = 0

    for post_file in sorted(posts_dir.glob("*.md")):
        m = _POST_FILE_RE.match(post_file.name)
        if not m:
            continue
        date_str, kind = m.group(1), m.group(2)
        content = _strip_front_matter(post_file)
        day_dir = _REPORTS_DIR / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        dest = day_dir / f"{kind}.md"
        if dest.exists() and dest.read_text(encoding="utf-8") == content:
            skipped += 1
            continue
        dest.write_text(content, encoding="utf-8")
        synced += 1

    yield _sse({"status": "complete", "synced": synced, "skipped": skipped})
