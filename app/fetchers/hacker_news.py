import asyncio
from datetime import datetime, timezone

import httpx

from app.fetchers.base import AbstractFetcher
from app.models import RawItem, SourceResult
from app.config import settings

_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"


class HackerNewsFetcher(AbstractFetcher):
    async def fetch(self) -> SourceResult:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_TOP_STORIES_URL)
                resp.raise_for_status()
                ids = resp.json()[: settings.max_hn_stories]

            semaphore = asyncio.Semaphore(10)

            async def fetch_item(client: httpx.AsyncClient, item_id: int):
                async with semaphore:
                    r = await client.get(_ITEM_URL.format(item_id))
                    r.raise_for_status()
                    return r.json()

            async with httpx.AsyncClient(timeout=15) as client:
                items = await asyncio.gather(
                    *[fetch_item(client, i) for i in ids],
                    return_exceptions=True,
                )

            today_utc = datetime.now(timezone.utc).date()
            raw_items: list[RawItem] = []

            for item in items:
                if isinstance(item, Exception) or item is None:
                    continue
                if item.get("type") != "story":
                    continue
                if item.get("title", "").startswith("Ask HN: Who is hiring"):
                    continue
                if "dead" in item and item["dead"]:
                    continue
                ts = item.get("time", 0)
                item_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                if item_date != today_utc:
                    continue

                raw_items.append(
                    RawItem(
                        title=item.get("title", ""),
                        url=item.get("url", f"https://news.ycombinator.com/item?id={item['id']}"),
                        description="",
                        extra={
                            "score": item.get("score", 0),
                            "comments": item.get("descendants", 0),
                        },
                    )
                )

            return SourceResult(source="hacker_news", success=True, items=raw_items)
        except Exception as e:
            return SourceResult(source="hacker_news", success=False, error=str(e))
