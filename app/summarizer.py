import asyncio
from datetime import date

from openai import AsyncOpenAI

from app.config import settings
from app.models import SourceResult

# ── 中文版提示词 ──────────────────────────────────────────

_ZH_SYSTEM = """你是技术趋势分析师，请用纯中文撰写完整的每日技术动态报告。
所有内容（标题、正文、列表）均使用中文，技术术语附加英文原名（括号标注）。
若某来源数据标记为 UNAVAILABLE，请在对应章节说明暂不可用，禁止伪造数据。"""

_ZH_FORMAT = """请按以下格式生成完整中文报告（Markdown 格式）：

**第一步**：在报告最前面输出「今日财经速递」区块。
- 从 FINANCE_NEWS 数据中筛选可能影响科技股、大盘或宏观经济的重要消息
- 每条直接写结论，不超过 25 字，共 5-8 条，按重要程度排序
- 若 FINANCE_NEWS 标记为 UNAVAILABLE，跳过此区块
- 格式（严格照此输出，不要改动符号）：

> 📊 **今日财经速递**
>
> - <结论1>
> - <结论2>
> - ...
>
> ---

**第二步**：生成完整的 9 章节报告：

1. 标题（格式：# DailyPulse · 每日脉搏 | YYYY-MM-DD）
2. 执行摘要（3-5 句总结今日技术动态）
3. 今日主题（识别 3-5 个跨来源共同趋势）
4. GitHub 热门亮点（Top 5 仓库，含通俗说明）
5. Hacker News 亮点（Top 5 故事，含说明）
6. 学术论文（Top 3-5 篇，用通俗语言解释研究内容）
7. Product Hunt 精选（Top 3-5 产品，含简介）
8. 今日技术焦点（最重要技术的深度分析，400-600 字）
9. 实践建议（3-5 条可操作建议）"""

# ── 英文版提示词 ──────────────────────────────────────────

_EN_SYSTEM = """You are a technology trend analyst. Write a complete daily tech digest entirely in English.
All content (headings, body text, lists) must be in English.
If a data source is marked UNAVAILABLE, note it in the relevant section. Never fabricate data."""

_EN_FORMAT = """Generate a complete English report in Markdown format:

**Step 1**: Output a "Market Briefing" block at the very top of the report.
- From FINANCE_NEWS data, select the most market-moving headlines (macro, rates, major stocks, commodities)
- Each bullet: one concise conclusion, max 15 words, 5-8 bullets total, ordered by importance
- If FINANCE_NEWS is UNAVAILABLE, skip this block
- Format (output exactly as shown):

> 📊 **Market Briefing**
>
> - <conclusion1>
> - <conclusion2>
> - ...
>
> ---

**Step 2**: Generate the full 9-section report:

1. Title (format: # DailyPulse · 每日脉搏 | YYYY-MM-DD)
2. Executive Summary (3-5 sentences summarizing today's tech highlights)
3. Today's Themes (3-5 cross-source common trends)
4. GitHub Trending Highlights (Top 5 repos with plain-language descriptions)
5. Hacker News Highlights (Top 5 stories with descriptions)
6. Academic Papers (Top 3-5 papers, explained in plain language)
7. Product Hunt Picks (Top 3-5 products with brief descriptions)
8. Tech Focus of the Day (in-depth analysis of the most important technology, 400-600 words)
9. Practical Takeaways (3-5 actionable recommendations)"""


# ── 数据序列化 ────────────────────────────────────────────


def _serialize_source(result: SourceResult) -> str:
    if not result.success or not result.items:
        reason = result.error or "no items fetched"
        return f"[{result.source.upper()}] UNAVAILABLE: {reason}\n"

    lines = [f"[{result.source.upper()}] {len(result.items)} items:"]
    for i, item in enumerate(result.items, 1):
        line = f"{i}. {item.title} | {item.url}"
        if item.description:
            line += f" | {item.description}"
        if item.extra:
            extras = ", ".join(f"{k}={v}" for k, v in item.extra.items() if v)
            if extras:
                line += f" | {extras}"
        lines.append(line)
    return "\n".join(lines)


# ── 自定义调研提示词 ─────────────────────────────────────────

_RESEARCH_SYSTEM = """你是一位资深的技术研究分析师。根据用户提供的主题，输出一份精炼、高信息密度的调研摘要。
要求：中文撰写，技术术语附英文原名（括号标注），Markdown 格式，不确定的信息明确标注。
切忌冗长啰嗦，每个要点一两句话说清楚即可。"""

_RESEARCH_FORMAT = """请对「{topic}」进行调研，按以下结构输出（总篇幅控制在 1500-2500 字）：

# 📋 调研报告：{topic}

## 1. 概述（3-5 句话说清楚是什么、为什么重要、当前阶段）

## 2. 核心技术解析（关键概念和原理，精炼说明，避免教科书式展开）

## 3. 市场格局（主要玩家/方案对比，用表格呈现更佳）

## 4. 典型应用场景（3-5 个场景，每个一两句话）

## 5. 优势与局限（各列 3-5 点，每点一句话）

## 6. 趋势与建议（未来方向 + 可操作的实践建议，合并为一节）

---
> 📝 本报告由 AI 生成，建议结合最新资料交叉验证。
"""


# ── 自定义调研生成（流式输出）────────────────────────────────


async def generate_research_stream(topic: str):
    """流式生成调研报告，逐步 yield 内容片段。"""
    client = AsyncOpenAI(
        api_key=settings.api_key,
        base_url=settings.api_base_url,
    )

    user_prompt = (
        f"请对以下主题进行调研：\n\n{topic}\n\n{_RESEARCH_FORMAT.format(topic=topic)}"
    )

    stream = await client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        stream=True,
        messages=[
            {"role": "system", "content": _RESEARCH_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


# ── 调研追问修订（流式输出）────────────────────────────────

_REFINE_SYSTEM = """你是一位资深的技术分析师。用户对之前的报告有疑问或修改意见。

你的任务：
1. 针对用户反馈修正、补充或深化相关部分
2. 输出完整的修订版报告（不是只输出修改部分）
3. 保留原报告中正确的内容和格式结构
4. 中文撰写，技术术语附英文原名"""


async def generate_refine_stream(existing_content: str, feedback: str):
    """基于已有调研报告和用户反馈，流式生成修订版。"""
    client = AsyncOpenAI(
        api_key=settings.api_key,
        base_url=settings.api_base_url,
    )

    user_prompt = (
        f"## 已有调研报告\n\n{existing_content}\n\n"
        f"---\n\n"
        f"## 用户反馈与修改意见\n\n{feedback}\n\n"
        f"---\n\n"
        f"请根据以上反馈，输出一份完整的修订版调研报告。保持完整的章节结构，不要省略任何部分。"
    )

    stream = await client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        stream=True,
        messages=[
            {"role": "system", "content": _REFINE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


# ── 生成入口（并行调用两次 LLM）────────────────────────────


async def generate_report(
    results: list[SourceResult], report_date: date
) -> tuple[str, str]:
    """返回 (zh_content, en_content) 两个完整的语言版本。"""
    client = AsyncOpenAI(
        api_key=settings.api_key,
        base_url=settings.api_base_url,
    )
    data_sections = "\n\n".join(_serialize_source(r) for r in results)
    date_label = report_date.strftime("%Y-%m-%d")

    async def call(system: str, fmt: str, date_hint: str) -> str:
        user_prompt = (
            f"日期/Date: {date_hint}\n\n原始数据/Raw data:\n{data_sections}\n\n{fmt}"
        )
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content

    zh_content, en_content = await asyncio.gather(
        call(_ZH_SYSTEM, _ZH_FORMAT, date_label),
        call(_EN_SYSTEM, _EN_FORMAT, date_label),
    )
    return zh_content, en_content
