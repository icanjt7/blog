from __future__ import annotations

from .models import Source, Topic


class FactRetriever:
    def enrich(self, topic: Topic) -> Topic:
        if topic.sources:
            return topic
        category_sources = {
            "living": Source(
                title="대한민국 정책브리핑",
                url="https://www.korea.kr/",
                summary="정부 정책과 생활 혜택 확인용 공식 포털",
                authority=5,
            ),
            "tech": Source(
                title="제조사 공식 홈페이지와 개발자 블로그",
                url="https://developers.googleblog.com/",
                summary="제품/기술 발표 원문 확인용",
                authority=4,
            ),
            "finance": Source(
                title="금융위원회 보도자료",
                url="https://www.fsc.go.kr/",
                summary="금융 정책과 제도 변경 확인용 공식 포털",
                authority=5,
            ),
            "local": Source(
                title="한국관광공사 VisitKorea",
                url="https://korean.visitkorea.or.kr/",
                summary="지역 여행 정보 확인용 공식 포털",
                authority=4,
            ),
        }
        topic.sources.append(category_sources[topic.category])
        return topic
