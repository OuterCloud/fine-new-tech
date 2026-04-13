import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from app.fetchers.base import AbstractFetcher
from app.models import RawItem, SourceResult

_PH_FEED_URL = "https://www.producthunt.com/feed"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_MAX_ITEMS = 20
# Product Hunt 时区为 PT（UTC-7/8），向前回溯 2 天避免时区边界漏抓
_LOOKBACK_DAYS = 2


class ProductHuntFetcher(AbstractFetcher):
    async def fetch(self) -> SourceResult:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(_PH_FEED_URL)
                resp.raise_for_status()

            root = ET.fromstring(resp.text)

            # Product Hunt 使用 Atom 格式（<feed>/<entry>），而非 RSS（<channel>/<item>）
            today_utc = datetime.now(timezone.utc).date()
            cutoff = today_utc - timedelta(days=_LOOKBACK_DAYS)
            raw_items: list[RawItem] = []

            for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
                published_el = entry.find(f"{{{_ATOM_NS}}}published")
                if published_el is None or published_el.text is None:
                    continue
                try:
                    pub_dt = datetime.fromisoformat(published_el.text)
                    pub_date = pub_dt.astimezone(timezone.utc).date()
                except Exception:
                    continue

                if pub_date < cutoff:
                    continue

                title_el = entry.find(f"{{{_ATOM_NS}}}title")
                title = (title_el.text or "").strip() if title_el is not None else ""

                # Atom 的链接在 <link rel="alternate" href="..."/>
                link_el = entry.find(f"{{{_ATOM_NS}}}link[@rel='alternate']")
                if link_el is None:
                    link_el = entry.find(f"{{{_ATOM_NS}}}link")
                url = link_el.attrib.get("href", "") if link_el is not None else ""

                summary_el = entry.find(f"{{{_ATOM_NS}}}summary")
                desc = (summary_el.text or "").strip() if summary_el is not None else ""
                desc = re.sub(r"<[^>]+>", "", desc).strip()

                raw_items.append(RawItem(title=title, url=url, description=desc))

                if len(raw_items) >= _MAX_ITEMS:
                    break

            return SourceResult(source="product_hunt", success=True, items=raw_items)
        except Exception as e:
            return SourceResult(source="product_hunt", success=False, error=str(e))
