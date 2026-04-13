import re
import shutil
from pathlib import Path

from app.models import ReportMetadata, ResearchMetadata

_REPORTS_DIR = Path("reports")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RESEARCH_RE = re.compile(r"^research-(\d+)$")
# 兼容旧版平铺文件名（2026-04-13-zh.md / 2026-04-13-en.md / 2026-04-13.md）
_LEGACY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(-(?:zh|en))?$")


def ensure_reports_dir() -> None:
    _REPORTS_DIR.mkdir(exist_ok=True)


def _day_dir(date_str: str) -> Path:
    return _REPORTS_DIR / date_str


def save_report(date_str: str, zh_content: str, en_content: str) -> None:
    day = _day_dir(date_str)
    day.mkdir(parents=True, exist_ok=True)
    (day / "zh.md").write_text(zh_content, encoding="utf-8")
    (day / "en.md").write_text(en_content, encoding="utf-8")


def load_report(date_str: str, lang: str = "zh") -> str:
    # 新布局: reports/{date}/{lang}.md
    lang_path = _day_dir(date_str) / f"{lang}.md"
    if lang_path.exists():
        return lang_path.read_text(encoding="utf-8")
    # 旧布局: reports/{date}-{lang}.md
    legacy_lang = _REPORTS_DIR / f"{date_str}-{lang}.md"
    if legacy_lang.exists():
        return legacy_lang.read_text(encoding="utf-8")
    # 最旧布局: reports/{date}.md（仅中文）
    legacy_flat = _REPORTS_DIR / f"{date_str}.md"
    if legacy_flat.exists():
        return legacy_flat.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Report not found: {date_str} (lang={lang})")


def list_reports() -> list[ReportMetadata]:
    ensure_reports_dir()
    dates: dict[str, dict] = {}

    # 新布局: reports/{date}/zh.md, en.md
    for day_dir in _REPORTS_DIR.iterdir():
        if not day_dir.is_dir() or not _DATE_RE.match(day_dir.name):
            continue
        date_str = day_dir.name
        total = 0
        has_zh = False
        has_en = False
        for f in day_dir.glob("*.md"):
            if f.stem.startswith("research-"):
                continue
            total += f.stat().st_size
            if f.stem == "zh":
                has_zh = True
            elif f.stem == "en":
                has_en = True
        if has_zh or has_en:
            dates[date_str] = {"has_zh": has_zh, "has_en": has_en, "total_bytes": total}

    # 旧版平铺布局（兼容）
    for path in _REPORTS_DIR.glob("*.md"):
        m = _LEGACY_RE.match(path.stem)
        if not m:
            continue
        date_str = m.group(1)
        if date_str in dates:  # 新布局已覆盖，跳过
            continue
        suffix = m.group(2)
        if date_str not in dates:
            dates[date_str] = {"has_zh": False, "has_en": False, "total_bytes": 0}
        dates[date_str]["total_bytes"] += path.stat().st_size
        if suffix == "-zh":
            dates[date_str]["has_zh"] = True
        elif suffix == "-en":
            dates[date_str]["has_en"] = True
        else:
            dates[date_str]["has_zh"] = True  # 旧合并文件视为中文版

    return [
        ReportMetadata(
            date=date_str,
            size_kb=round(d["total_bytes"] / 1024, 1),
            has_zh=d["has_zh"],
            has_en=d["has_en"],
        )
        for date_str in sorted(dates.keys(), reverse=True)
        for d in [dates[date_str]]
    ]


def delete_report(date_str: str) -> None:
    deleted = False
    # 新布局
    day = _day_dir(date_str)
    if day.exists() and day.is_dir():
        shutil.rmtree(day)
        deleted = True
    # 旧版平铺
    for suffix in ("-zh", "-en", ""):
        path = _REPORTS_DIR / f"{date_str}{suffix}.md"
        if path.exists():
            path.unlink()
            deleted = True
    if not deleted:
        raise FileNotFoundError(f"Report not found: {date_str}")


def report_exists(date_str: str) -> bool:
    day = _day_dir(date_str)
    if day.is_dir() and any(day.glob("*.md")):
        return True
    return any(
        (_REPORTS_DIR / f"{date_str}{suffix}.md").exists()
        for suffix in ("-zh", "-en", "")
    )


# ── 调研报告 ─────────────────────────────────────────────


def _next_research_id(date_str: str) -> str:
    """生成下一个调研报告 ID，如 research-1, research-2..."""
    day = _day_dir(date_str)
    if not day.exists():
        return "research-1"
    existing = [
        int(m.group(1))
        for f in day.glob("research-*.md")
        if (m := _RESEARCH_RE.match(f.stem))
    ]
    next_num = max(existing, default=0) + 1
    return f"research-{next_num}"


def _extract_topic(path: Path) -> str:
    """从调研报告 Markdown 中提取主题（第一个 # 标题）。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                # 去掉常见前缀如 "📋 调研报告："
                for prefix in ("📋 调研报告：", "📋 调研报告:", "📋 "):
                    if title.startswith(prefix):
                        title = title[len(prefix) :]
                return title[:80]
    except Exception:
        pass
    return path.stem


def save_research(date_str: str, content: str) -> str:
    """保存调研报告，返回 research_id（如 'research-1'）。"""
    day = _day_dir(date_str)
    day.mkdir(parents=True, exist_ok=True)
    research_id = _next_research_id(date_str)
    (day / f"{research_id}.md").write_text(content, encoding="utf-8")
    return research_id


def load_research(date_str: str, research_id: str) -> str:
    path = _day_dir(date_str) / f"{research_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Research not found: {date_str}/{research_id}")
    return path.read_text(encoding="utf-8")


def delete_research(date_str: str, research_id: str) -> None:
    path = _day_dir(date_str) / f"{research_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Research not found: {date_str}/{research_id}")
    path.unlink()
    # 如果日期目录空了，也删掉
    day = _day_dir(date_str)
    if day.exists() and not any(day.iterdir()):
        day.rmdir()


def list_researches() -> list[ResearchMetadata]:
    """列出所有调研报告。"""
    ensure_reports_dir()
    results: list[ResearchMetadata] = []
    for day_dir in sorted(_REPORTS_DIR.iterdir(), reverse=True):
        if not day_dir.is_dir() or not _DATE_RE.match(day_dir.name):
            continue
        for f in sorted(day_dir.glob("research-*.md"), reverse=True):
            if not _RESEARCH_RE.match(f.stem):
                continue
            results.append(
                ResearchMetadata(
                    id=f.stem,
                    date=day_dir.name,
                    topic=_extract_topic(f),
                    size_kb=round(f.stat().st_size / 1024, 1),
                )
            )
    return results


def update_research(date_str: str, research_id: str, content: str) -> None:
    """覆盖更新已有的调研报告。"""
    path = _day_dir(date_str) / f"{research_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Research not found: {date_str}/{research_id}")
    path.write_text(content, encoding="utf-8")
