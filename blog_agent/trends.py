from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import requests
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
    "are",
    "is",
    "was",
    "were",
    "to",
    "of",
    "on",
    "in",
    "as",
    "by",
    "ordered",
    "built",
    "host",
    "disabling",
    "next",
    "month",
    "free",
    "how",
    "humans",
    "react",
    "surprises",
    "road",
    "congress",
    "just",
    "gave",
    "tried",
    "actually",
    "works",
    "정부",
    "발표",
    "지원",
    "관련",
    "안내",
    "단호히",
    "성과",
    "가능",
    "대응",
    "써도",
    "하반기",
    "확대",
    "시행",
    "올",
}

CATEGORY_SEEDS = {
    "생활": ["지원금", "청년", "신청방법", "제철음식", "생활비", "혜택"],
    "기술": ["AI", "아이폰", "갤럭시", "노트북", "스펙", "비교"],
    "정책": ["금리", "환율", "부동산", "대출", "연금", "세금"],
    "정치": ["지방선거", "당선인 공약", "선거 결과", "국회", "정당"],
    "스포츠": [
        "2026 월드컵 48개국 일정",
        "한국 축구 대표팀 월드컵 일정",
        "2026 월드컵 조별리그 관전법",
    ],
    "핫이슈": [
        "서울 맛집",
        "부산 여행",
        "제주 카페",
        "강릉 여행",
        "전주 맛집",
        "서울 성수 카페 동선",
        "부산 해운대 여행 코스",
        "제주 반려동물 동반여행",
        "서울 의료관광 병원",
        "경주 당일치기 코스",
        "여수 밤바다 여행",
        "전주 한옥마을 먹거리 동선",
    ],
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
        max_per_category = self._env_int("BLOG_MAX_PER_CATEGORY_PER_RUN", 1, minimum=1)
        strict_category_diversity = os.getenv("BLOG_STRICT_CATEGORY_DIVERSITY", "true").lower() == "true"
        for topic in ranked:
            key = self._topic_key(topic.keyword)
            if self._is_seen_topic(topic.keyword, used) or self._is_seen_topic(topic.keyword, seen):
                continue
            if category_counts[topic.category] >= max_per_category:
                deferred.append(topic)
                continue
            used.add(key)
            category_counts[topic.category] += 1
            unique.append(topic)
            if len(unique) >= limit:
                break
        if strict_category_diversity:
            return unique
        for topic in deferred:
            if len(unique) >= limit:
                break
            key = self._topic_key(topic.keyword)
            if self._is_seen_topic(topic.keyword, used) or self._is_seen_topic(topic.keyword, seen):
                continue
            used.add(key)
            unique.append(topic)
        return unique

    def remember(self, topics: list[Topic]) -> None:
        path = self.state_dir / "published_keywords.json"
        seen = self._load_seen_keywords()
        seen.update(self._topic_key(topic.keyword) for topic in topics)
        path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_seen_keywords(self) -> set[str]:
        path = self.state_dir / "published_keywords.json"
        if not path.exists():
            return set()
        return {self._topic_key(keyword) for keyword in json.loads(path.read_text(encoding="utf-8"))}

    def _topics_from_rss(self, seen: set[str]) -> list[Topic]:
        config = yaml.safe_load(self.source_file.read_text(encoding="utf-8"))
        topics: list[Topic] = []
        for category, source_config in config.items():
            for rss_url in source_config.get("rss", []):
                try:
                    resp = requests.get(
                        rss_url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; blog-agent/1.0)"},
                        timeout=8,
                    )
                    resp.raise_for_status()
                    parsed = feedparser.parse(resp.content)
                except Exception:
                    continue
                for entry in parsed.entries[:10]:
                    title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
                    if not title:
                        continue
                    if re.search(r"보도\s*(자료|참고)|참고자료", title):
                        continue
                    keyword = self._keyword_from_title(title)
                    if self._is_seen_topic(keyword, seen):
                        continue
                    published = self._published_at(entry)
                    recency = self._recency_score(published)
                    language_fit = 20 if re.search(r"[가-힣]", title) else -20
                    refined_category = self._refine_category(category, title, rss_url)
                    topics.append(
                        Topic(
                            keyword=keyword,
                            title_hint=title,
                            category=refined_category,
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
            if category == "스포츠" and os.getenv("ENABLE_SPORTS_SEEDS", "false").lower() != "true":
                continue
            for seed in seeds:
                keyword = seed if category == "스포츠" else f"{month} {seed}"
                counter[(category, keyword)] += 1
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
            if not self._is_seen_topic(keyword, seen)
        ]

    @staticmethod
    def _keyword_from_title(title: str) -> str:
        quoted_terms = [
            re.sub(r"\s+", " ", term).strip(" '\"‘’“”")
            for term in re.findall(r"['‘’“\"]([^'‘’“\"]{2,})['‘’“\"]", title)
        ]
        quoted_terms = [
            term
            for term in quoted_terms
            if re.search(r"[가-힣A-Za-z0-9]", term) and not re.search(r"자료제공|문의", term)
        ]
        korean_tokens = re.findall(r"[가-힣]{2,}", title)
        if korean_tokens:
            filtered = [TrendScout._normalize_korean_token(token) for token in korean_tokens]
            filtered = [token for token in filtered if token and token not in STOPWORDS]
            if quoted_terms:
                quoted = TrendScout._normalize_korean_token(quoted_terms[0])
                rest = [token for token in filtered if token not in quoted]
                return " ".join([quoted, *rest[:3]]).strip() or title[:30]
            return " ".join(filtered[:4]) or title[:30]
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
        filtered = [token for token in tokens if token.lower() not in STOPWORDS]
        if not filtered:
            return title[:30]
        preferred = [
            token
            for token in filtered
            if re.search(r"[A-Z0-9]", token) or token.lower() in {"ai", "mac", "ios"}
        ]
        keyword_tokens = preferred[:4] if len(preferred) >= 2 else filtered[:4]
        return " ".join(keyword_tokens)

    @staticmethod
    def _normalize_korean_token(token: str) -> str:
        if len(token) >= 3 and token[-1] in "이가은는을를":
            return token[:-1]
        return token

    @classmethod
    def _topic_key(cls, value: str) -> str:
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", value.lower())
        normalized = [
            cls._normalize_korean_token(token)
            for token in tokens
            if token and token not in STOPWORDS
        ]
        return " ".join(normalized) or value.lower().strip()

    @classmethod
    def _is_seen_topic(cls, value: str, seen: set[str]) -> bool:
        key = cls._topic_key(value)
        if key in seen:
            return True
        tokens = set(key.split())
        if len(tokens) < 3:
            return False
        for prior in seen:
            prior_tokens = set(prior.split())
            if len(prior_tokens) < 3:
                continue
            overlap = tokens & prior_tokens
            if len(overlap) >= 3 and len(overlap) / min(len(tokens), len(prior_tokens)) >= 0.75:
                return True
        return False

    @staticmethod
    def _refine_category(category: str, title: str, rss_url: str) -> str:
        text = f"{title} {rss_url}"
        if re.search(r"이재명정부|대통령|국무총리|외교|국회|정당|선거|투표|공약", text):
            return "정치"
        if re.search(r"AI|인공지능|로봇|스마트건설|반도체|소프트웨어|클라우드|데이터|디지털|모빌리티", text, re.IGNORECASE):
            return "기술"
        if re.search(r"국세청|탈세|체납|세금|금융|예금|금리|대출|부동산|재정|경제|공정위|관세|고용여건|고용동향|취업자|부총리|전 부처|물가|원자재", text):
            return "정책"
        if re.search(r"월드컵|축구|야구|농구|경기|대표팀|선수|리그", text):
            return "스포츠"
        if re.search(r"여권|신분증|신청|복지|건강|안전|청년|가족|주거|교육", text):
            return "생활"
        return category

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

    @staticmethod
    def _env_int(name: str, default: int, minimum: int = 0) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(default))))
        except ValueError:
            return max(minimum, default)
