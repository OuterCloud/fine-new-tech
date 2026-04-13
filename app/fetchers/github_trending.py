import httpx
from bs4 import BeautifulSoup

from app.fetchers.base import AbstractFetcher
from app.models import RawItem, SourceResult
from app.config import settings

_GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class GitHubTrendingFetcher(AbstractFetcher):
    async def fetch(self) -> SourceResult:
        try:
            async with httpx.AsyncClient(timeout=20, headers=_HEADERS, follow_redirects=True) as client:
                resp = await client.get(_GITHUB_TRENDING_URL)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            articles = soup.find_all("article", class_="Box-row")

            raw_items: list[RawItem] = []

            for article in articles[: settings.max_github_repos]:
                # Repo name
                h2 = article.find("h2")
                if h2 is None:
                    continue
                a_tag = h2.find("a")
                if a_tag is None:
                    continue
                repo_path = a_tag.get("href", "").strip().lstrip("/")
                repo_name = repo_path.replace("/", " / ")
                url = f"https://github.com/{repo_path}"

                # Description
                desc_el = article.find("p")
                description = (desc_el.get_text(strip=True) if desc_el else "")

                # Language
                lang_el = article.find("span", itemprop="programmingLanguage")
                language = lang_el.get_text(strip=True) if lang_el else ""

                # Today's stars
                stars_today = ""
                for span in article.find_all("span"):
                    text = span.get_text(strip=True)
                    if "stars today" in text:
                        stars_today = text.replace("stars today", "").strip()
                        break

                raw_items.append(
                    RawItem(
                        title=repo_name,
                        url=url,
                        description=description,
                        extra={"language": language, "stars_today": stars_today},
                    )
                )

            return SourceResult(source="github_trending", success=True, items=raw_items)
        except Exception as e:
            return SourceResult(source="github_trending", success=False, error=str(e))
