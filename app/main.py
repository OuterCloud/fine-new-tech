import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import report_store
from app.config import get_settings_display, settings, update_settings
from app.fetchers.arxiv import ArxivFetcher
from app.fetchers.finance_news import FinanceNewsFetcher
from app.fetchers.github_trending import GitHubTrendingFetcher
from app.fetchers.hacker_news import HackerNewsFetcher
from app.fetchers.product_hunt import ProductHuntFetcher
from app.models import SourceResult
from app.publisher import _pages_url, publish_reports
from app.summarizer import (
    generate_refine_stream,
    generate_report,
    generate_research_stream,
)

app = FastAPI(title="find-new-tech")

report_store.ensure_reports_dir()

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("app/static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/api/reports")
async def get_reports():
    reports = report_store.list_reports()
    return [
        {"date": r.date, "size_kb": r.size_kb, "has_zh": r.has_zh, "has_en": r.has_en}
        for r in reports
    ]


@app.get("/api/reports/{date_str}")
async def get_report(date_str: str, lang: str = "zh"):
    if lang not in ("zh", "en"):
        raise HTTPException(status_code=400, detail="lang 参数只接受 zh 或 en")
    try:
        content = report_store.load_report(date_str, lang)
        return {"date": date_str, "content": content, "lang": lang}
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Report {date_str} ({lang}) not found"
        )


@app.delete("/api/reports/{date_str}")
async def delete_report(date_str: str):
    try:
        report_store.delete_report(date_str)
        return {"deleted": date_str}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report {date_str} not found")


@app.post("/api/research")
async def research(request: dict):
    topic = request.get("topic", "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="请输入调研主题")
    if len(topic) > 500:
        raise HTTPException(status_code=400, detail="主题不能超过 500 字")

    date_str = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

    async def event_stream():
        yield f"data: {json.dumps({'status': 'start', 'topic': topic})}\n\n"
        try:
            full_content = ""
            async for chunk in generate_research_stream(topic):
                full_content += chunk
                yield f"data: {json.dumps({'status': 'streaming', 'chunk': chunk})}\n\n"

            # 保存到本地
            research_id = report_store.save_research(date_str, full_content)
            yield f"data: {json.dumps({'status': 'complete', 'date': date_str, 'research_id': research_id, 'total_length': len(full_content)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/researches")
async def get_researches():
    items = report_store.list_researches()
    return [
        {"id": r.id, "date": r.date, "topic": r.topic, "size_kb": r.size_kb}
        for r in items
    ]


@app.get("/api/researches/{date_str}/{research_id}")
async def get_research(date_str: str, research_id: str):
    try:
        content = report_store.load_research(date_str, research_id)
        return {"date": date_str, "id": research_id, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research not found")


@app.delete("/api/researches/{date_str}/{research_id}")
async def delete_research_api(date_str: str, research_id: str):
    try:
        report_store.delete_research(date_str, research_id)
        return {"deleted": f"{date_str}/{research_id}"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research not found")


@app.post("/api/research/refine")
async def refine_research(request: dict):
    date_str = request.get("date", "").strip()
    research_id = request.get("research_id", "").strip()
    feedback = request.get("feedback", "").strip()
    if not date_str or not research_id:
        raise HTTPException(status_code=400, detail="缺少 date 或 research_id")
    if not feedback:
        raise HTTPException(status_code=400, detail="请输入你的疑问或修改意见")

    try:
        existing_content = report_store.load_research(date_str, research_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="调研报告不存在")

    async def event_stream():
        yield f"data: {json.dumps({'status': 'start'})}\n\n"
        try:
            full_content = ""
            async for chunk in generate_refine_stream(existing_content, feedback):
                full_content += chunk
                yield f"data: {json.dumps({'status': 'streaming', 'chunk': chunk})}\n\n"

            # 覆盖保存
            report_store.update_research(date_str, research_id, full_content)
            yield f"data: {json.dumps({'status': 'complete', 'date': date_str, 'research_id': research_id, 'total_length': len(full_content)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/reports/refine")
async def refine_report(request: dict):
    date_str = request.get("date", "").strip()
    lang = request.get("lang", "zh").strip()
    feedback = request.get("feedback", "").strip()
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    if not feedback:
        raise HTTPException(status_code=400, detail="请输入你的疑问或修改意见")

    try:
        existing_content = report_store.load_report(date_str, lang)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="报告不存在")

    async def event_stream():
        yield f"data: {json.dumps({'status': 'start'})}\n\n"
        try:
            full_content = ""
            async for chunk in generate_refine_stream(existing_content, feedback):
                full_content += chunk
                yield f"data: {json.dumps({'status': 'streaming', 'chunk': chunk})}\n\n"

            # 覆盖保存对应语言版本
            day = report_store._day_dir(date_str)
            day.mkdir(parents=True, exist_ok=True)
            (day / f"{lang}.md").write_text(full_content, encoding="utf-8")
            yield f"data: {json.dumps({'status': 'complete', 'date': date_str, 'lang': lang, 'total_length': len(full_content)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/settings")
async def get_settings():
    return get_settings_display()


@app.get("/api/pages-url")
async def get_pages_url():
    url = _pages_url(settings.github_pages_repo) if settings.github_pages_repo else ""
    return {"url": url}


@app.put("/api/settings")
async def put_settings(request: dict):
    try:
        update_settings(request)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/publish")
async def publish(force: bool = False):
    async def event_stream():
        async for event in publish_reports(
            repo_url=settings.github_pages_repo,
            github_token=settings.github_token,
            force_all=force,
        ):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/generate")
async def generate(force: bool = False, date: Optional[str] = None):
    if date:
        try:
            report_date = datetime.strptime(date, "%Y-%m-%d").date()
            date_str = date
        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD"
            )
    else:
        report_date = datetime.now(timezone.utc).date()
        date_str = report_date.strftime("%Y-%m-%d")

    if report_store.report_exists(date_str) and not force:

        async def already_exists():
            yield f"data: {json.dumps({'status': 'complete', 'date': date_str, 'cached': True})}\n\n"

        return StreamingResponse(already_exists(), media_type="text/event-stream")

    async def event_stream():
        fetcher_specs = [
            ("finance_news", FinanceNewsFetcher()),
            ("github_trending", GitHubTrendingFetcher()),
            ("hacker_news", HackerNewsFetcher()),
            ("arxiv", ArxivFetcher()),
            ("product_hunt", ProductHuntFetcher()),
        ]

        for source_name, _ in fetcher_specs:
            yield f"data: {json.dumps({'status': 'fetching', 'source': source_name})}\n\n"

        raw_results = await asyncio.gather(
            *[fetcher.fetch() for _, fetcher in fetcher_specs],
            return_exceptions=True,
        )

        results: list[SourceResult] = []
        for (source_name, _), result in zip(fetcher_specs, raw_results):
            if isinstance(result, Exception):
                results.append(
                    SourceResult(source=source_name, success=False, error=str(result))
                )
            else:
                results.append(result)

        yield f"data: {json.dumps({'status': 'summarizing'})}\n\n"

        try:
            zh_content, en_content = await generate_report(results, report_date)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
            return

        report_store.save_report(date_str, zh_content, en_content)
        yield f"data: {json.dumps({'status': 'complete', 'date': date_str})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
