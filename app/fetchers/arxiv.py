import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from app.fetchers.base import AbstractFetcher
from app.models import RawItem, SourceResult

_ARXIV_URL = (
    "https://export.arxiv.org/api/query"
    "?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.CV"
    "&sortBy=submittedDate&sortOrder=descending&max_results=50"
)
_ATOM_NS = "http://www.w3.org/2005/Atom"
_MAX_ITEMS = 20
_MAX_DESC = 300
# arXiv 周末不发论文，向前最多回溯 7 天
_LOOKBACK_DAYS = 7


class ArxivFetcher(AbstractFetcher):
    async def fetch(self) -> SourceResult:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(_ARXIV_URL)
                resp.raise_for_status()

            root = ET.fromstring(resp.text)
            today_utc = datetime.now(timezone.utc).date()
            cutoff = today_utc - timedelta(days=_LOOKBACK_DAYS)

            raw_items: list[RawItem] = []
            # 记录实际抓到的最新日期，用于在报告中说明
            latest_date = None

            for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
                published_el = entry.find(f"{{{_ATOM_NS}}}published")
                if published_el is None or published_el.text is None:
                    continue
                pub_date = datetime.fromisoformat(
                    published_el.text.replace("Z", "+00:00")
                ).date()

                # 超出回溯窗口则停止
                if pub_date < cutoff:
                    break

                # 只取最新一批（与第一篇同一天）
                if latest_date is None:
                    latest_date = pub_date
                elif pub_date < latest_date:
                    break

                title_el = entry.find(f"{{{_ATOM_NS}}}title")
                title = (title_el.text or "").strip() if title_el is not None else ""

                summary_el = entry.find(f"{{{_ATOM_NS}}}summary")
                summary = (summary_el.text or "").strip() if summary_el is not None else ""
                if len(summary) > _MAX_DESC:
                    summary = summary[:_MAX_DESC] + "..."

                link_el = entry.find(f"{{{_ATOM_NS}}}link[@type='text/html']")
                if link_el is None:
                    link_el = entry.find(f"{{{_ATOM_NS}}}link")
                url = link_el.attrib.get("href", "") if link_el is not None else ""

                authors = [
                    (a.find(f"{{{_ATOM_NS}}}name").text or "")
                    for a in entry.findall(f"{{{_ATOM_NS}}}author")
                    if a.find(f"{{{_ATOM_NS}}}name") is not None
                ]

                raw_items.append(
                    RawItem(
                        title=title,
                        url=url,
                        description=summary,
                        extra={"authors": authors[:5], "date": str(pub_date)},
                    )
                )

                if len(raw_items) >= _MAX_ITEMS:
                    break

            return SourceResult(source="arxiv", success=True, items=raw_items)
        except Exception as e:
            return SourceResult(source="arxiv", success=False, error=str(e))
