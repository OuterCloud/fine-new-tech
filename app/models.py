from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawItem:
    title: str
    url: str
    description: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class SourceResult:
    source: str
    success: bool
    items: list[RawItem] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ReportMetadata:
    date: str
    size_kb: float
    has_zh: bool = True
    has_en: bool = False


@dataclass
class ResearchMetadata:
    """调研报告元数据"""

    id: str  # 文件名 stem，如 "research-1"
    date: str  # 所属日期
    topic: str  # 调研主题
    size_kb: float
