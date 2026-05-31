from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import yaml

from .models import Source, Topic


STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "for",
    "this",
    "that",
    "정부",
    "발표",
    "지원",
    "관련",
    "안내",
}

CATEGORY_SEEDS = {
    "living": ["지원금", "청년", "신청방법", "제철음식", "생활비", "혜택"],
    "tech": ["AI", "아이폰", "갤럭시", "노트북", "스펙", "비교"],
    "finance": ["금리", "환율", "부동산", "대출", "연금", "세금"],
    "local": ["서울 맛집", "부산 여행", "제주 카페", "강릉 여행", "전주 맛집"],
}


class TrendScout:
    def __init__(self, state_dir: Path, source_file: Path | None = None) -> None:
        self.state_dir = state_dir
        self.source_file = source_file or Path(__file__).with_name("sources.yml")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def scout(self, limit: int) -> list[Topic]:
        seen = self._load_seen_keywords()
        topics: list[Topic] = []
        topics.extend(self._topics_from_rss(seen))
        topics.extend(self._seed_topics(seen))
        ranked = sorted(
            topics,
            key=lambda item: (item.trend_score, -item.competition_score),
            reverse=True,
        )
        unique: list[Topic] = []
        used: set[str] = set()
        category_counts: Counter[str] = Counter()
        deferred: list[Topic] = []
        for topic in ranked:
            key = topic.keyword.lower()
            if key in used or key in seen:
                continue
            if category_counts[topic.category] >= 2:
                deferred.append(topic)
                continue
            used.add(key)
            category_counts[topic.category] += 1
            unique.append(topic)
            if len(unique) >= limit:
                break
        for topic in deferred:
            if len(unique) >= limit:
                break
            key = topic.keyword.lower()
            if key in used or key in seen:
                continue
            used.add(key)
            unique.append(topic)
        return unique

    def remember(self, topics: list[Topic]) -> None:
        path = self.state_dir / "published_keywords.json"
        seen = self._load_seen_keywords()
        seen.update(topic.keyword.lower() for topic in topics)
        path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_seen_keywords(self) -> set[str]:
        path = self.state_dir / "published_keywords.json"
        if not path.exists():
            return set()
        return set(json.loads(path.read_text(encoding="utf-8")))

    def _topics_from_rss(self, seen: set[str]) -> list[Topic]:
        config = yaml.safe_load(self.source_file.read_text(encoding="utf-8"))
        topics: list[Topic] = []
        for category, source_config in config.items():
            for rss_url in source_config.get("rss", []):
                try:
                    parsed = feedparser.parse(rss_url)
                except Exception:
                    continue
                for entry in parsed.entries[:10]:
                    title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
                    if not title:
                        continue
                    keyword = self._keyword_from_title(title)
                    if keyword.lower() in seen:
                        continue
                    published = self._published_at(entry)
                    recency = self._recency_score(published)
                    language_fit = 20 if re.search(r"[가-힣]", title) else -20
                    topics.append(
                        Topic(
                            keyword=keyword,
                            title_hint=title,
                            category=category,
                            trend_score=55 + recency + language_fit,
                            competition_score=0.35,
                            rationale="RSS 신규성과 공식/전문 매체 출처 기반",
                            sources=[
                                Source(
                                    title=title,
                                    url=entry.get("link", rss_url),
                                    published_at=published,
                                    summary=entry.get("summary", ""),
                                    authority=4 if "korea.kr" in rss_url or ".go.kr" in rss_url else 3,
                                )
                            ],
                        )
                    )
        return topics

    def _seed_topics(self, seen: set[str]) -> list[Topic]:
        month = datetime.now().strftime("%m월")
        counter = Counter()
        for category, seeds in CATEGORY_SEEDS.items():
            for seed in seeds:
                counter[(category, f"{month} {seed}")] += 1
        return [
            Topic(
                keyword=keyword,
                title_hint=f"{keyword} 핵심 정리",
                category=category,
                trend_score=95 + score,
                competition_score=0.45,
                rationale="월별 반복 검색 수요가 있는 evergreen 키워드",
            )
            for (category, keyword), score in counter.items()
            if keyword.lower() not in seen
        ]

    @staticmethod
    def _keyword_from_title(title: str) -> str:
        korean_tokens = re.findall(r"[가-힣]{2,}", title)
        if korean_tokens:
            return " ".join([token for token in korean_tokens[:4] if token not in STOPWORDS])
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
        filtered = [token for token in tokens if token.lower() not in STOPWORDS]
        return " ".join(filtered[:3]) if filtered else title[:30]

    @staticmethod
    def _published_at(entry: dict) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime(*parsed[:6])

    @staticmethod
    def _recency_score(published_at: datetime | None) -> float:
        if not published_at:
            return 5
        age = datetime.now() - published_at
        if age < timedelta(days=1):
            return 30
        if age < timedelta(days=3):
            return 20
        if age < timedelta(days=7):
            return 10
        return 3
