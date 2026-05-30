from __future__ import annotations

import hashlib
import re
from datetime import datetime

from openai import OpenAI

from .config import Settings
from .models import Draft, Topic


STYLE_RULES = {
    "living": "친절한 생활정보 블로거. 신청 조건, 준비물, 주의사항을 짧은 문단으로 설명한다.",
    "tech": "차분한 테크 리뷰어. 스펙, 장단점, 구매 판단 기준을 표와 체크리스트로 정리한다.",
    "finance": "보수적인 금융 정보 큐레이터. 투자 권유처럼 보이지 않게 사실과 확인 경로를 분리한다.",
    "local": "데이터 분석형 로컬 큐레이터. 직접 방문한 척하지 않고 공개 정보와 리뷰 경향을 정리한다.",
}


class WriterAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def write(self, topic: Topic) -> Draft:
        if self.client:
            return self._write_with_llm(topic)
        return self._write_fallback(topic)

    def _write_with_llm(self, topic: Topic) -> Draft:
        sources = "\n".join(
            f"- {source.title}: {source.url} ({source.summary[:240]})"
            for source in topic.sources
        )
        prompt = f"""
한국 블로그용 정보성 글을 작성해 주세요.

주제: {topic.title_hint}
핵심 키워드: {topic.keyword}
카테고리: {topic.category}
문체: {STYLE_RULES[topic.category]}

조건:
- 직접 경험하지 않은 일을 경험한 것처럼 쓰지 않는다.
- 출처에서 확인 가능한 사실과 일반 조언을 분리한다.
- 제목 1개, 2문장 요약, 본문 Markdown을 만든다.
- 본문은 1,200~1,800자 정도로 작성한다.
- AI가 쓴 티가 나는 과장된 표현, 반복 접속사, 판에 박힌 결론을 피한다.
- 키워드는 자연스럽게 4~7회만 사용한다.
- 마지막에는 확인해야 할 공식 경로를 짧게 둔다.

참고 출처:
{sources}

응답 형식:
TITLE:
EXCERPT:
BODY:
"""
        response = self.client.responses.create(
            model=self.settings.openai_model,
            input=prompt,
        )
        text = response.output_text
        title = self._extract(text, "TITLE", default=topic.title_hint)
        excerpt = self._extract(text, "EXCERPT", default=topic.rationale)
        body = self._extract(text, "BODY", default=text)
        return Draft(
            topic=topic,
            title=title,
            slug=self._slug(topic.keyword),
            excerpt=excerpt,
            body_markdown=body.strip(),
            tags=self._tags(topic),
        )

    def _write_fallback(self, topic: Topic) -> Draft:
        source_lines = "\n".join(f"- [{s.title}]({s.url})" for s in topic.sources)
        topic_with_subject = self._with_particle(topic.keyword, "은", "는")
        body = f"""## 한눈에 보기

{topic_with_subject} 최근 검색 수요가 꾸준히 생기는 주제입니다. 이 글은 공개된 자료를 기준으로 핵심만 정리한 정보성 콘텐츠입니다.

## 왜 지금 볼 만한가

- 주제 성격: {topic.rationale or "반복 검색 수요가 있는 키워드"}
- 확인 포인트: 조건, 비용, 일정, 공식 안내 변경 여부
- 읽는 사람: 빠르게 비교하고 결정 기준을 잡고 싶은 독자

{topic.keyword}를 볼 때는 먼저 "지금 나에게 적용되는 정보인지"를 확인하는 편이 좋습니다. 검색 결과 상단의 글이 오래된 안내를 그대로 담고 있는 경우가 있고, 특히 가격, 신청 기간, 운영 시간, 대상 조건은 짧은 기간에도 바뀔 수 있습니다.

## 핵심 정리

| 항목 | 확인할 내용 |
| --- | --- |
| 기본 정보 | 공식 안내와 최신 공지 확인 |
| 장점 | 시간을 줄이고 선택 기준을 세우기 쉬움 |
| 주의점 | 날짜, 가격, 운영 시간, 조건은 변동 가능 |

## 이렇게 확인하면 편합니다

{topic.keyword} 관련 글을 여러 개 열어볼 때는 공통으로 반복되는 내용과 출처가 분명한 내용을 먼저 남기세요. 블로그 후기나 커뮤니티 글은 실제 체감 정보를 얻는 데 도움이 되지만, 최종 판단은 공식 페이지나 원문 공지를 함께 보는 것이 안전합니다.

생활정보나 지원금이라면 신청 기간과 대상 조건을, 테크 제품이라면 출시일과 국내 모델명을, 금융 정보라면 기준일과 고시 기관을 확인해야 합니다. 지역/여행 정보는 영업시간, 휴무일, 예약 가능 여부처럼 방문 직전에 바뀌는 항목을 다시 확인하는 것이 좋습니다.

## 체크리스트

1. 공식 페이지에서 최신 날짜를 확인합니다.
2. 여러 출처의 공통 내용을 먼저 봅니다.
3. 비용이나 신청 조건처럼 바뀌기 쉬운 정보는 다시 검증합니다.
4. {topic.keyword}와 함께 지역명, 연도, 모델명 같은 보조 키워드를 붙여 검색합니다.

## 참고한 곳

{source_lines}
"""
        return Draft(
            topic=topic,
            title=f"{topic.keyword} 핵심 정리: 지금 확인할 포인트",
            slug=self._slug(topic.keyword),
            excerpt=f"{topic.keyword} 관련 정보를 공식 자료 중심으로 간단히 정리했습니다.",
            body_markdown=body,
            tags=self._tags(topic),
        )

    @staticmethod
    def _extract(text: str, label: str, default: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z]+:|\Z)"
        match = re.search(pattern, text, flags=re.S)
        return match.group(1).strip() if match else default

    @staticmethod
    def _slug(keyword: str) -> str:
        cleaned = re.sub(r"[^가-힣a-zA-Z0-9]+", "-", keyword).strip("-").lower()
        suffix = hashlib.sha1(f"{keyword}-{datetime.now().date()}".encode()).hexdigest()[:8]
        return f"{cleaned}-{suffix}"

    @staticmethod
    def _tags(topic: Topic) -> list[str]:
        base = [topic.category, *topic.keyword.split()[:4]]
        return list(dict.fromkeys(base))

    @staticmethod
    def _with_particle(text: str, consonant_particle: str, vowel_particle: str) -> str:
        if not text:
            return text
        last = text[-1]
        code = ord(last)
        if 0xAC00 <= code <= 0xD7A3:
            has_final = (code - 0xAC00) % 28 != 0
            return text + (consonant_particle if has_final else vowel_particle)
        return text + vowel_particle
