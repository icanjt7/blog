from __future__ import annotations

import re
from html.parser import HTMLParser

import requests

from .config import Settings
from .models import Source, Topic
from .tourapi import TourApiClient

_FALLBACK_SOURCES = {
    "생활": Source(
        title="대한민국 정책브리핑",
        url="https://www.korea.kr/",
        summary="정부 정책과 생활 혜택 확인용 공식 포털",
        authority=5,
    ),
    "기술": Source(
        title="제조사 공식 홈페이지와 개발자 블로그",
        url="https://developers.googleblog.com/",
        summary="제품/기술 발표 원문 확인용",
        authority=4,
    ),
    "정책": Source(
        title="금융위원회 보도자료",
        url="https://www.fsc.go.kr/",
        summary="금융 정책과 제도 변경 확인용 공식 포털",
        authority=5,
    ),
    "정치": Source(
        title="중앙선거관리위원회 선거통계시스템",
        url="https://info.nec.go.kr/",
        summary="선거 결과, 당선인, 득표율 등 선거 통계 확인용 공식 서비스",
        authority=5,
    ),
    "핫이슈": Source(
        title="한국관광공사 VisitKorea",
        url="https://korean.visitkorea.or.kr/",
        summary="지역 여행 정보 확인용 공식 포털",
        authority=4,
    ),
}


class _TextExtractor(HTMLParser):
    """간단한 HTML → 텍스트 추출기 (stdlib만 사용)."""

    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _fetch_body(url: str, max_chars: int = 2000) -> str:
    """URL에서 본문 텍스트를 가져온다. 실패하면 빈 문자열."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; blog-agent/1.0)"},
            timeout=6,
            allow_redirects=True,
        )
        resp.raise_for_status()
        raw = resp.text[:65536]
        parser = _TextExtractor()
        parser.feed(raw)
        text = re.sub(r"\s{2,}", " ", parser.get_text()).strip()
        return text[:max_chars]
    except Exception:
        return ""


class FactRetriever:
    def __init__(self, settings: Settings | None = None) -> None:
        self.tourapi = TourApiClient(settings) if settings else None

    def enrich(self, topic: Topic) -> Topic:
        if not topic.sources:
            topic.sources.append(_FALLBACK_SOURCES[topic.category])

        if self.tourapi:
            tour_summary = self.tourapi.enrich(topic)
            if tour_summary.sources:
                topic.sources = [
                    *tour_summary.sources,
                    *[source for source in topic.sources if "google.com/search" not in str(source.url)],
                ]
                topic.rationale = (
                    f"{topic.rationale} / TourAPI 연관 관광지 {tour_summary.related_count}건"
                    f"{', 집중률 ' + str(tour_summary.rate_count) + '건' if tour_summary.rate_count else ''} 활용"
                ).strip(" /")

        # 각 소스의 본문을 가져와서 summary를 보강한다
        for source in topic.sources:
            if source.summary and len(source.summary) > 300:
                continue  # 이미 충분한 요약이 있으면 스킵
            if not source.url or source.url.endswith("/"):
                continue  # 루트 URL은 스킵
            body = _fetch_body(source.url)
            if body and len(body) > len(source.summary):
                source.summary = body

        return topic
