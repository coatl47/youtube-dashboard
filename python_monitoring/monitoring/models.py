from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["긍정", "중립", "부정"]
Risk = Literal["관찰", "주의", "긴급"]
Target = Literal["이사장", "국민연금", "연금제도", "영상", "기타"]
Topic = Literal[
    "기금 운용",
    "보험료 인상",
    "세대 형평",
    "노후 보장",
    "조직 신뢰",
    "정부 개입",
    "정보 공개",
    "지역 가입자",
    "기타",
]


@dataclass(frozen=True)
class Video:
    video_id: str
    channel_id: str | None
    channel_title: str
    title: str
    published_at: datetime
    canonical_url: str


@dataclass(frozen=True)
class MetricSnapshot:
    video_id: str
    observed_at: datetime
    view_count: int
    like_count: int | None
    comment_count: int | None


@dataclass(frozen=True)
class Comment:
    comment_id: str
    video_id: str
    thread_id: str
    parent_id: str | None
    is_reply: bool
    text: str
    published_at: datetime
    updated_at: datetime
    like_count: int
    reply_count: int
    stratum: str
    rank: int


class AnalysisItem(BaseModel):
    comment_id: str
    sentiment: Sentiment
    target: Target
    topic: Topic
    keyword: str = Field(min_length=1, max_length=30)
    spam: bool
    confidence: float = Field(ge=0, le=1)
    risk: Risk
    rationale: str = Field(min_length=1, max_length=160)


class AnalysisBatch(BaseModel):
    items: list[AnalysisItem]


@dataclass(frozen=True)
class CollectionResult:
    video_id: str
    fetched: int
    unique: int
    pages: int
    quota_units: int
    status: str
