from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


Category = Literal["local", "tech", "finance", "living"]


class Source(BaseModel):
    title: str
    url: HttpUrl | str
    published_at: datetime | None = None
    summary: str = ""
    authority: int = Field(default=2, ge=1, le=5)


class Topic(BaseModel):
    keyword: str
    title_hint: str
    category: Category
    trend_score: float = Field(default=0, ge=0)
    competition_score: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""
    sources: list[Source] = Field(default_factory=list)


class Draft(BaseModel):
    topic: Topic
    title: str
    slug: str
    excerpt: str
    body_markdown: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    quality_score: float = 0
    review_notes: list[str] = Field(default_factory=list)


class PublishResult(BaseModel):
    ok: bool
    destination: str
    url: str | None = None
    message: str = ""
