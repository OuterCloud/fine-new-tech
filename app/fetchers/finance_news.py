"""
finance_news.py — 抓取今日热门财经新闻（Reuters Business / Yahoo Finance RSS）
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.fetchers.base import AbstractFetcher
from app.models import RawItem, SourceResult

# 按顺序尝试，取第一个成功且条目数足够的 feed
_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://finance.yahoo.com/rss/topstories",
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",  # MarketWatch
]
_MAX_ITEMS = 20
_LOOKBACK_DAYS = 3  # 周末无新内容时向前回溯


class FinanceNewsFetcher(AbstractFetcher):
    async def fetch(self) -> SourceResult:
        try:
            items: list[RawItem] = []
            seen: set[str] = set()
            today_utc = datetime.now(timezone.utc).date()
            cutoff = today_utc - timedelta(days=_LOOKBACK_DAYS)

            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; find-new-tech/1.0)"},
            ) as client:
                for feed_url in _FEEDS:
                    if len(items) >= _MAX_ITEMS:
                        break
                    try:
                        resp = await client.get(feed_url)
                        resp.raise_for_status()
                        root = ET.fromstring(resp.text)
                        channel = root.find("channel")
                        if channel is None:
                            continue

                        for item_el in channel.findall("item"):
                            if len(items) >= _MAX_ITEMS:
                                break

                            title_el = item_el.find("title")
                            title = (title_el.text or "").strip() if title_el is not None else ""
                            if not title or title in seen:
                                continue

                            # 日期过滤
                            pub_el = item_el.find("pubDate")
                            if pub_el is not None and pub_el.text:
                                try:
                                    pub_date = parsedate_to_datetime(pub_el.text).astimezone(timezone.utc).date()
                                    if pub_date < cutoff:
                                        continue
                                except Exception:
                                    pass

                            link_el = item_el.find("link")
                            url = (link_el.text or "").strip() if link_el is not None else ""

                            desc_el = item_el.find("description")
                            desc = (desc_el.text or "").strip() if desc_el is not None else ""
                            desc = re.sub(r"<[^>]+>", "", desc).strip()[:300]

                            seen.add(title)
                            items.append(RawItem(title=title, url=url, description=desc))

                    except Exception:
                        continue  # 当前 feed 失败，尝试下一个

            return SourceResult(source="finance_news", success=True, items=items)
        except Exception as e:
            return SourceResult(source="finance_news", success=False, error=str(e))
