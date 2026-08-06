from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from html import unescape as html_unescape

from openai import OpenAI

from .config import Settings
from .models import Draft, Topic


PERSONAS = {
    "생활": (
        "당신은 서울에 사는 30대 직장인으로, 생활 혜택과 지원 정책에 관심이 많습니다. "
        "친구에게 얘기하듯 쓰되, 중요한 조건과 신청 방법은 빠짐없이 짚어줍니다. "
        "관공서 말투는 쓰지 않고, '~해요'체와 짧은 구어체를 섞어 씁니다."
    ),
    "기술": (
        "당신은 IT 기기를 10년째 리뷰해온 프리랜서 에디터입니다. "
        "스펙 수치보다 '실제로 쓰면 어떤지'를 중심에 두고, "
        "장단점을 솔직하게 나열하되 구매 판단 기준을 명확히 제시합니다. "
        "업계 전문 용어는 쓰되 풀어서 설명합니다."
    ),
    "정책": (
        "당신은 재테크 커뮤니티 운영자로, 공식 자료를 직접 확인하고 요약해 전달합니다. "
        "투자 권유처럼 들리지 않도록 사실과 판단을 분리하고, "
        "독자가 스스로 결정할 수 있도록 확인 경로를 안내합니다."
    ),
    "정치": (
        "당신은 선거와 의회 정보를 중립적으로 정리하는 공공정보 큐레이터입니다. "
        "특정 후보나 정당을 지지하거나 비판하지 않고, 공식 자료의 확인 경로와 "
        "유권자가 점검할 기준을 차분하게 설명합니다. 검증되지 않은 당선인명, 득표율, "
        "공약 수치는 쓰지 않습니다."
    ),
    "스포츠": (
        "당신은 축구와 주요 스포츠 이벤트를 데이터와 경기 맥락으로 풀어주는 스포츠 에디터입니다. "
        "확정 명단, 일정, 공식 기록은 출처 기준일을 분명히 밝히고, 전술 평가는 사실과 해석을 구분합니다. "
        "팬들이 경기 전에 바로 확인할 수 있도록 핵심 선수, 변수, 관전 포인트를 간결하게 정리합니다."
    ),
    "핫이슈": (
        "당신은 전국 맛집·여행지 데이터를 분석하는 콘텐츠 큐레이터입니다. "
        "직접 방문한 척하지 않고, 공개된 리뷰 경향과 공식 정보를 정리해 '가볼 만한 이유'를 설명합니다. "
        "방문자들이 자주 언급하는 포인트를 구체적으로 적습니다."
    ),
}

HOOK_STYLES = [
    "질문으로 시작: 독자가 이 글을 클릭한 이유를 한 문장 질문으로 열어라.",
    "숫자나 구체적 사실로 시작: 인상적인 수치나 잘 알려지지 않은 사실 한 줄로 시작해라.",
    "공감 상황 묘사로 시작: 독자가 겪었을 법한 상황을 짧게 그려라.",
    "역설이나 반전으로 시작: '의외로', '사실은' 같은 뒤집기로 관심을 끌어라.",
]


class WriterAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None
        self._model: str = ""
        self._providers: list[tuple[OpenAI, str]] = []
        self._init_client()

    def _init_client(self) -> None:
        s = self.settings
        timeout = s.llm_timeout_seconds
        provider_limit = self._env_int("BLOG_LLM_PROVIDER_LIMIT", 0)
        providers: list[tuple[str, OpenAI, str]] = []

        def add(name: str, client: OpenAI, model: str) -> None:
            providers.append((name, client, model))

        if s.motif_api_key:
            add(
                "motif",
                OpenAI(
                    api_key=s.motif_api_key,
                    base_url=s.motif_base_url,
                    timeout=timeout,
                    max_retries=0,
                ),
                s.motif_model,
            )
        if s.groq_api_key:
            add(
                "groq",
                OpenAI(
                    api_key=s.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.groq_model,
            )
        if s.nvidia_api_key:
            add(
                "nvidia",
                OpenAI(
                    api_key=s.nvidia_api_key,
                    base_url=s.nvidia_base_url,
                    timeout=timeout,
                    max_retries=0,
                ),
                s.nvidia_model,
            )
        if s.gemini_api_key:
            add(
                "gemini",
                OpenAI(
                    api_key=s.gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.gemini_model,
            )
        if s.openrouter_api_key:
            add(
                "openrouter",
                OpenAI(
                    api_key=s.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.openrouter_model,
            )
        if s.openai_api_key:
            add("openai", OpenAI(api_key=s.openai_api_key, timeout=timeout, max_retries=0), s.openai_model)
        if s.github_token:
            add(
                "github",
                OpenAI(
                    api_key=s.github_token,
                    base_url="https://models.github.ai/inference",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.github_model,
            )
        order = self._provider_order()
        rank = {name: index for index, name in enumerate(order)}
        providers.sort(key=lambda item: rank.get(item[0], len(rank)))
        for _name, client, model in providers:
            if provider_limit and len(self._providers) >= provider_limit:
                break
            self._providers.append((client, model))
            if self._client is None:
                self._client = client
                self._model = model

    def write(self, topic: Topic) -> Draft:
        if self._providers:
            last_error: Exception | None = None
            for client, model in self._providers:
                try:
                    return self._write_with_llm(topic, client, model)
                except Exception as exc:
                    last_error = exc
                    continue
            draft = self._write_fallback(topic)
            if last_error:
                draft.review_notes.append(f"LLM 작성 실패로 규칙 기반 초안 사용: {type(last_error).__name__}")
            return draft
        return self._write_fallback(topic)

    def _write_with_llm(self, topic: Topic, client: OpenAI | None = None, model: str | None = None) -> Draft:
        client = client or self._client
        model = model or self._model
        if not client:
            try:
                return self._write_fallback(topic)
            except Exception:
                raise
        today = datetime.now().strftime("%Y-%m-%d")
        sources = "\n".join(self._source_prompt_line(source) for source in topic.sources)
        tourism_instruction = ""
        if self._has_tourapi_source(topic):
            tourism_instruction = f"""
[TourAPI 관광 글 작성 지침]
- 참고 출처에 한국관광공사 TourAPI 데이터가 있으면 본문에 반드시 반영한다.
- 국문 관광정보는 장소명, 주소, 분류, 개요, 운영시간, 휴무, 주차, 대표 이미지 유무를 동선과 비교표에 반영한다.
- 영문 관광정보는 외국인 독자를 위한 영문 장소명, 영문 주소, 영문 개요를 보조 정보로 반영한다.
- 연관 관광지 정보는 '함께 묶을 곳', '동선 순서', '주변에서 볼 것'으로 풀어 쓴다.
- 관광지 집중률 정보는 혼잡 가능성을 보는 보조 지표로만 설명하고, 실제 방문자 수처럼 단정하지 않는다.
- 의료관광 정보는 주소, 문의, 운영정보, 주차, 예약 전 확인할 점 중심으로 안내한다.
- 치료 효과, 안전성, 가격, 진료 가능 여부는 출처에 있어도 단정하지 말고 기관 확인이 필요하다고 쓴다.
- 반려동물 동반여행 정보는 동반 조건, 목줄·이동장, 실내외 가능 구역, 숙박 객실 조건, 추가요금, 예약 확인 중심으로 안내한다.
- 반려동물 동반 가능 여부는 운영 정책이 바뀔 수 있으므로 단정하지 말고 당일 업체 확인을 권한다.
- "{topic.keyword}" 제목이 동선/코스/카페거리라면 일반적인 검색 확인법 대신 실제 이동 순서와 현장에서 볼 요소를 먼저 제시한다.
"""
        hook_style = HOOK_STYLES[hash(topic.keyword) % len(HOOK_STYLES)]
        persona = PERSONAS[topic.category]
        prompt = f"""[페르소나]
{persona}

[제목 작성 규칙 — 가장 중요]
- 검색자가 클릭하고 싶어지는 제목을 만든다.
- 아래 패턴 중 하나를 골라 쓴다:
  · 숫자 포함: "3가지만 알면", "5분 만에 정리", "월 10만원 아끼는"
  · 궁금증 유발: "왜 아무도 안 알려줄까", "이것만 모르면 손해"
  · 반전/의외성: "의외로 간단한", "사실 이게 핵심이었다"
  · 독자 상황 공감: "신청했는데 안 됐던 이유", "이 조건 해당되면 바로 신청"
  · 구체적 혜택: "지금 신청하면 최대 XX 절약", "이 타이밍 놓치면 1년 기다려야"
- '핵심 정리', '알아보자', '총정리', '완벽 정리' 같은 진부한 표현 금지.
- 제목은 30자 이내로 압축한다.

[글 작성 지침]
- 오늘 기준일: {today}
- 도입부: {hook_style}
- 문장 길이를 의도적으로 섞는다. 짧은 문장(5~10자)과 긴 문장(40~60자)을 번갈아 쓴다.
- '이번 포스팅에서는', '알아보겠습니다', '결론적으로', '매우 중요합니다', '다양한' 금지.
- 직접 경험하지 않은 일을 경험한 것처럼 쓰지 않는다.
- 출처에 없는 구체 수치는 추가하지 않는다.
- 출처 제목, 요약, 발행일에 없는 연도나 월을 만들지 않는다.
- "2024년 기준", "2024년 6월 기준", "2024년부터" 같은 과거 기준일은 출처가 해당 연도를 명시할 때만 쓴다.
- 최신 안내를 말해야 하는데 출처 발행일이 불명확하면 연도를 임의로 넣지 말고 "원문 공개일 기준" 또는 "공식 안내 기준"이라고 쓴다.
- "A사/B사/C사", "제품 A", "가상의 모델"처럼 실제 출처를 확인할 수 없는 익명 비교표를 만들지 않는다.
- 핵심 키워드 "{topic.keyword}"는 4~7회만 자연스럽게 쓴다.
- 본문 1,400~1,800자. 표 1개 이상 포함.
- 마지막 문단은 독자에게 하나의 행동 권고나 확인 경로로 마무리.
- 원문을 문장 순서대로 다시 말하는 방식은 금지한다. 반드시 독자가 얻는 판단 기준, 배경 설명, 실제 확인 순서를 추가한다.
- 참고 출처가 보도자료라면 발표 내용과 독자에게 의미 있는 영향·제한·후속 확인 경로를 분리해서 쓴다.
- 각 글에는 주제 고유의 "왜 지금 봐야 하는지", "누가 영향을 받는지", "무엇을 확인해야 하는지"가 드러나야 한다.
- 출처가 1개뿐이면 더 조심해서 쓴다. 원문에 없는 해석을 사실처럼 단정하지 말고, 확인 가능한 범위와 한계를 함께 밝힌다.
- "원문 안내의 시행일과 적용 대상을 먼저 봅니다", "신청, 예약, 방문, 자동 적용 중 어떤 방식인지 구분합니다"처럼 모든 글에 붙일 수 있는 범용 체크리스트는 금지한다.
- 체크리스트를 쓰려면 참고 출처에서 확인되는 고유명사, 숫자, 기간, 대상, 기관명, 절차를 최소 5개 이상 넣어 주제별로 다르게 쓴다.
{tourism_instruction}

[맥락 심화 — 반드시 포함]
글에 등장하는 인물·작품·기업·제도가 있다면 독자가 처음 듣는 사람이라고 가정하고 아래를 설명한다:
- 인물: 이름 + 어떤 사람인지(직업·경력·배경) + 왜 지금 주목받는지
- 작품(영화·책·앱 등): 장르·줄거리 한 줄 + 주요 관계자(감독·저자 등)
- 기업/브랜드: 어떤 회사인지 + 이번 소식과의 연결점
- 제도/정책: 대상이 누구인지 + 이전과 무엇이 달라졌는지
독자가 "그게 뭐야?"라고 물을 만한 모든 용어에 한 줄 설명을 붙인다.

[애드센스 품질 기준]
- 빈약한 페이지처럼 보이지 않게 도입, 배경, 비교표, 확인 방법, 참고 출처가 자연스럽게 이어져야 한다.
- 다른 사이트나 보도자료를 복제한 것처럼 보이지 않도록 독자 상황별 해석, 주의할 예외, 다음 행동을 추가한다.
- 광고 클릭을 유도하는 표현, 과장된 혜택, 낚시성 제목은 쓰지 않는다.

[주제]
키워드: {topic.keyword}
힌트: {topic.title_hint}
카테고리: {topic.category}

[참고 출처]
{sources}

[응답 형식 — 반드시 아래 레이블로 시작]
TITLE:
EXCERPT:
BODY:
"""
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=2048,
        )
        text = response.choices[0].message.content or ""
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
        if self._has_tourapi_source(topic):
            return self._write_tourism_fallback(topic)
        if topic.category == "기술" and topic.sources:
            return self._write_tech_news_fallback(topic)
        source_lines = "\n".join(f"- [{s.title}]({s.url})" for s in topic.sources)
        frame = self._fallback_frame(topic)
        body = self._fallback_body(topic, frame, source_lines)
        return Draft(
            topic=topic,
            title=frame["title"],
            slug=self._slug(topic.keyword),
            excerpt=frame["excerpt"],
            body_markdown=body,
            tags=self._tags(topic),
        )

    def _fallback_body(self, topic: Topic, frame: dict[str, str], source_lines: str) -> str:
        source = topic.sources[0] if topic.sources else None
        source_title = source.title if source else topic.title_hint
        source_summary = self._clean_summary(source.summary if source else "")
        category = topic.category

        if category == "생활":
            living = self._living_context(topic, source_title, source_summary)
            return f"""## 무엇이 달라졌나

{source_title} 소식은 {living["lead"]} 먼저 제목의 혜택 표현보다 실제로 누가, 언제, 어떤 절차로 움직여야 하는지 나눠 보는 편이 좋습니다.

{source_summary or frame["opening"]}

## 이번 글에서 바로 볼 항목

| 항목 | 이번 소식에서 확인할 내용 |
| --- | --- |
{living["table_rows"]}

## 숫자와 대상은 이렇게 읽으면 쉽습니다

{living["detail_1"]}

{living["detail_2"]}

{living["detail_3"]}

## 실제 확인 순서

{living["steps"]}

## 마무리

{living["closing"]}

## 참고한 곳

{source_lines}
"""

        if category in {"정책", "정치"}:
            return f"""## 이 이슈의 핵심

{source_title}는 제도 변화나 공공 집행 방향을 보여주는 자료입니다. {topic.keyword}를 볼 때는 발표 문장보다 실제 적용 대상, 집행 방식, 후속 조치가 더 중요합니다.

{source_summary or frame["opening"]}

## 정책 읽는 순서

| 구분 | 봐야 할 질문 |
| --- | --- |
| 대상 | {frame["target_check"]} |
| 시점 | {frame["timing_check"]} |
| 영향 | {frame["cost_check"]} |
| 예외 | {frame["exception_check"]} |

## 독자가 이해해야 할 배경

{frame["detail_1"]}

{frame["detail_2"]}

세금, 체납, 금융, 지원 제도는 같은 단어라도 행정 단계가 다를 수 있습니다. 조사 착수, 제도 발표, 실제 집행, 신청 접수, 사후 점검은 모두 다른 단계입니다. {topic.keyword}도 지금 어느 단계의 소식인지 먼저 구분해야 과하게 해석하지 않습니다.

## 확인 포인트

1. 담당 기관과 발표일을 확인합니다.
2. 개인, 사업자, 기관 중 누구에게 영향을 주는지 나눕니다.
3. 단속, 지원, 신고, 신청 중 어떤 행동으로 이어지는지 봅니다.
4. 금액이나 비율이 있다면 한도와 기간을 함께 확인합니다.
5. 원문 자료의 후속 링크나 담당 부서를 확인합니다.

## 마무리

{topic.keyword}는 자극적인 제목보다 적용 범위가 중요합니다. 실제 행동이 필요한지는 원문에서 시행일, 대상, 담당 기관을 확인한 뒤 판단하는 것이 좋습니다.

## 참고한 곳

{source_lines}
"""

        if category == "스포츠":
            return f"""## 지금 보는 이유

{topic.keyword}는 2026 FIFA 월드컵을 볼 때 먼저 확인해야 할 기본 정보와 맞닿아 있습니다. 이번 대회는 2026년 6월 11일부터 7월 19일까지 캐나다·멕시코·미국에서 열리고, 참가국은 48개국, 전체 경기는 104경기입니다.

32개국 체제에 익숙한 독자라면 조별리그 통과 방식, 32강 토너먼트, 개최 도시 이동 거리부터 다시 봐야 합니다. 대표팀 전력 평가는 그다음입니다.

## 기본 구조

| 항목 | 2026 월드컵 기준 |
| --- | --- |
| 개최 기간 | 2026년 6월 11일~7월 19일 |
| 개최국 | 캐나다, 멕시코, 미국 |
| 참가국 | 48개국 |
| 총 경기 수 | 104경기 |
| 핵심 변화 | 48개국 확대와 32강 토너먼트 |

## 관전 포인트

{frame["detail_1"]}

{frame["detail_2"]}

{topic.keyword}를 볼 때는 우승 후보보다 조 편성, 이동 거리, 휴식일, 부상 변수를 먼저 보는 것이 좋습니다. 북중미 3개국 개최라 현지 날짜와 한국 시간이 달라질 수 있고, 장거리 이동이 많은 팀은 선수단 운영 부담도 커질 수 있습니다.

## 헷갈리기 쉬운 부분

2026 월드컵은 2022 카타르 대회와 다릅니다. 32개 팀, 64경기 기준으로 설명하는 글은 이번 대회 기준으로 오래된 정보입니다. 또한 예비 명단, 최종 명단, 경기 당일 엔트리는 서로 다른 단계이므로 대표팀 글을 볼 때 발표일을 반드시 확인해야 합니다.

## 체크리스트

1. 경기 시간은 한국 시간으로 다시 확인합니다.
2. 조별리그 순위표에서 3위 팀 조건을 함께 봅니다.
3. 개최 도시 이동 거리가 긴 팀을 체크합니다.
4. 최종 명단과 부상 소식은 경기 직전까지 확인합니다.
5. 일정과 기록은 FIFA 공식 페이지를 기준으로 봅니다.

## 참고한 곳

{source_lines}
"""

        return f"""## 동선부터 잡아야 하는 이유

{source_title}를 볼 때는 이름난 장소를 많이 넣는 것보다 이동이 자연스러운지가 더 중요합니다. {topic.keyword} 같은 지역·여행 주제는 시간대, 휴무, 예약 여부에 따라 만족도가 크게 달라집니다.

{source_summary or frame["opening"]}

## 방문 전 비교표

| 구분 | 확인할 점 |
| --- | --- |
| 동선 | {frame["target_check"]} |
| 시간 | {frame["timing_check"]} |
| 비용 | {frame["cost_check"]} |
| 변수 | {frame["exception_check"]} |

## 추천 동선과 주변 포인트

{frame["detail_1"]}

{frame["detail_2"]}

처음 가는 지역이라면 대표 관광지 하나를 기준으로 주변 포인트를 2~3곳만 묶는 편이 좋습니다. 아이나 가족, 반려동물과 함께라면 이동 거리보다 쉬는 지점, 화장실, 식사 대기 시간, 실내 대체 장소를 먼저 넣어야 일정이 무너지지 않습니다.

## 체크리스트

1. 첫 장소와 마지막 장소를 지도에서 먼저 찍습니다.
2. 식사와 휴식 시간을 일정 중간에 넣습니다.
3. 주차, 대중교통, 우천 대안을 함께 확인합니다.
4. 예약이 필요한 곳은 방문 전날 다시 확인합니다.
5. 후기는 참고하되 운영 시간은 공식 안내를 기준으로 봅니다.

## 참고한 곳

{source_lines}
"""

    def _fallback_frame(self, topic: Topic) -> dict[str, str]:
        keyword = topic.keyword
        if topic.category == "생활":
            return {
                "title": f"{keyword}, 신청 전 확인할 것",
                "excerpt": f"{keyword}를 실제로 이용하기 전 적용 대상, 기간, 비용 조건을 나눠 정리했습니다.",
                "rationale": "생활 속에서 바로 행동으로 이어지는 검색 주제",
                "opening": "생활 정보는 작은 조건 하나 때문에 결과가 달라집니다. 혜택, 신청, 예약, 사용량, 지역 조건을 나눠 보면 실제로 필요한 행동이 더 또렷해집니다.",
                "first_check": "대상자, 준비물, 접수 또는 이용 기준일",
                "reader": "바로 신청하거나 이용하기 전에 빠르게 기준을 잡고 싶은 사람",
                "target_check": "개인, 가구, 지역, 사용량 등 적용 대상",
                "timing_check": "시행일, 신청 기간, 적용 기간, 처리 소요 시간",
                "cost_check": "지원 금액, 수수료, 준비물, 계정 또는 인증 조건",
                "exception_check": "지역 제한, 사전 신청, 자동 적용 여부, 중복 혜택 제한",
                "detail_1": "생활 정보는 '가능하다'는 말보다 '누가 어떤 조건에서 가능한가'가 중요합니다. 자동 적용인지, 직접 신청인지, 특정 지역이나 기간에만 가능한지부터 나눠 보세요.",
                "detail_2": "숫자로 표시된 혜택은 기준을 같이 봐야 합니다. 최대 금액, 절감률, 신청 기간, 적용 시점이 함께 맞아야 실제 혜택으로 이어집니다.",
            }
        if topic.category == "정책":
            return {
                "title": f"{keyword}, 적용 범위가 핵심",
                "excerpt": f"{keyword} 이슈를 담당 기관, 적용 대상, 실제 집행 단계 중심으로 정리했습니다.",
                "rationale": "제도와 일정에 따라 해석이 달라지는 공공 정보",
                "opening": "정책 정보는 제목보다 적용 범위가 중요합니다. 발표 자료의 취지가 좋아 보여도 실제 대상과 시행 시점이 다르면 내 상황에는 바로 적용되지 않을 수 있습니다.",
                "first_check": "대상 범위, 시행일, 담당 기관의 후속 안내",
                "reader": "정책 변화가 생활비, 금융, 세금, 행정 절차에 영향을 주는지 확인하려는 사람",
                "target_check": "개인, 가구, 사업자, 기관 중 누구에게 적용되는지",
                "timing_check": "발표일과 시행일이 같은지, 유예 기간이 있는지",
                "cost_check": "지원 규모, 부담 변화, 신청 또는 신고 절차",
                "exception_check": "소득, 지역, 업종, 기존 이용자 여부에 따른 예외",
                "detail_1": "정책 발표는 방향과 실제 집행 사이에 시간이 생길 수 있습니다. 보도자료의 문장만 보지 말고 시행령, 고시, 신청 페이지가 열렸는지까지 이어서 봐야 합니다.",
                "detail_2": "숫자가 있는 정책은 기준을 함께 봐야 합니다. 지원 금액, 비율, 한도, 적용 기간 중 어느 값인지 구분하지 않으면 실제 체감과 다르게 이해하기 쉽습니다.",
            }
        if topic.category == "정치":
            return {
                "title": f"{keyword}, 발언보다 맥락 보기",
                "excerpt": f"{keyword} 이슈를 발언 배경, 이해관계자, 후속 일정 중심으로 정리했습니다.",
                "rationale": "정부 운영과 정치 일정에 따라 해석이 달라지는 공공 이슈",
                "opening": "정치 정보는 발언 한 줄보다 맥락과 후속 일정이 중요합니다. 누가 말했는지, 어떤 자리에서 나온 이야기인지, 실제 제도나 외교 일정으로 이어지는지 나눠 봐야 합니다.",
                "first_check": "발언 주체, 발표 장소, 후속 일정, 이해관계자",
                "reader": "정치·외교 이슈가 정책 방향이나 생활 변화로 이어지는지 확인하려는 독자",
                "target_check": "정부, 국회, 정당, 부처, 외교 상대국 중 어느 주체가 관련되는지",
                "timing_check": "발표일, 회담일, 법안 처리 일정, 후속 브리핑 여부",
                "cost_check": "예산, 산업 영향, 외교 협력, 규제 변화 가능성",
                "exception_check": "정치적 해석과 확정된 제도 변화를 구분할 필요",
                "detail_1": "정치 이슈는 찬반 평가보다 확인 가능한 사실을 먼저 봐야 합니다. 공식 발표, 회의 결과, 법안 문안, 후속 브리핑이 있는지 확인하세요.",
                "detail_2": "외교나 산업 이슈가 섞인 정치 뉴스는 구체적인 협력 분야와 실제 실행 일정이 중요합니다. 수사적 표현과 실행 계획을 분리해서 보는 편이 안전합니다.",
            }
        if topic.category == "스포츠":
            return {
                "title": f"{keyword}, 일정과 규칙 먼저 보기",
                "excerpt": f"{keyword}를 경기 일정, 대회 구조, 관전 변수 중심으로 빠르게 정리했습니다.",
                "rationale": "일정과 명단 변화에 따라 관심이 반복되는 스포츠 검색 주제",
                "opening": "스포츠 정보는 확정된 사실과 예상이 섞여 보이는 경우가 많습니다. 경기 일정, 명단, 중계, 부상 변수는 각각 확인 시점이 다릅니다.",
                "first_check": "공식 일정, 참가 명단, 중계 또는 기록 확인 경로",
                "reader": "경기 전 핵심 변수와 확인 경로를 빠르게 잡고 싶은 팬",
                "target_check": "48개국 확대, 32강 토너먼트, 조별리그 3위 조건",
                "timing_check": "2026년 6월 11일 개막, 7월 19일 결승",
                "cost_check": "중계 채널, 한국 시간 변환, 경기장 이동 거리",
                "exception_check": "부상, 징계, 일정 변경, 개최 도시 이동 변수",
                "detail_1": "경기 전 정보는 발표 시점이 중요합니다. 예비 명단과 최종 명단, 평가전과 공식전, 현지 시간과 한국 시간을 구분해야 착오가 줄어듭니다.",
                "detail_2": "전술 전망은 해석이고, 일정과 기록은 사실입니다. 2026년 대회는 규모가 커진 만큼 조 편성, 휴식일, 이동 거리까지 함께 봐야 합니다.",
            }
        return {
            "title": f"{keyword}, 동선부터 잡는 법",
            "excerpt": f"{keyword}를 동선, 시간대, 비용, 운영 조건 중심으로 확인하는 방법을 정리했습니다.",
            "rationale": "여행과 지역 소비에서 반복 검색되는 주제",
            "opening": "지역 정보는 실제 동선과 운영 조건이 맞아야 쓸모가 있습니다. 유명하다는 말만으로는 이동 시간, 대기, 비용을 판단하기 어렵습니다.",
            "first_check": "위치, 운영 시간, 이동 동선, 예약 필요 여부",
            "reader": "짧은 시간 안에 실패 가능성을 줄이고 싶은 방문 예정자",
            "target_check": "아이 동반, 가족 여행, 반려동물 동반, 혼잡 시간대",
            "timing_check": "운영 시간, 휴무일, 계절별 혼잡 시간",
            "cost_check": "입장료, 주차비, 예약금, 식사 예산",
            "exception_check": "우천, 성수기, 대기, 예약 마감, 반려동물 제한",
            "detail_1": "여행 글은 직접 방문 후기와 공개 데이터를 구분해서 봐야 합니다. 이 글은 방문 경험을 꾸미지 않고, 확인해야 할 조건을 중심으로 정리합니다.",
            "detail_2": "가족이나 아이와 함께 움직인다면 이동 거리를 짧게 잡는 것이 우선입니다. 유명 장소를 많이 넣는 것보다 쉬는 지점과 식사 시간을 동선 중간에 두는 편이 만족도가 높습니다.",
        }

    def _write_tech_news_fallback(self, topic: Topic) -> Draft:
        source_lines = "\n".join(f"- [{s.title}]({s.url})" for s in topic.sources)
        context = self._tech_news_context(topic)
        title = context["title"] or f"{topic.keyword}: 무엇이 달라졌나"
        body = f"""## 무슨 소식인가

{context["summary"]}

## 먼저 알아둘 배경

{context["background"]}

## 왜 기술 이슈인가

{context["why_it_matters"]}

## 확인할 기준

| 항목 | 구체 내용 |
| --- | --- |
| 직접 대상 | {context["target"]} |
| 기술 맥락 | {context["tech_context"]} |
| 사용자 영향 | {context["user_impact"]} |
| 다음 확인 | {context["next_check"]} |

## 독자가 이해해야 할 포인트

1. {context["point_1"]}
2. {context["point_2"]}
3. {context["point_3"]}
4. 원문 요약만으로 부족하면 공식 보도자료, 후속 공지, 실제 적용 사례까지 같이 확인하는 편이 안전합니다.

## 참고한 곳

{source_lines}
"""
        return Draft(
            topic=topic,
            title=title,
            slug=self._slug(topic.keyword),
            excerpt=context["excerpt"],
            body_markdown=body,
            tags=self._tags(topic),
        )

    def _tech_news_context(self, topic: Topic) -> dict[str, str]:
        primary = topic.sources[0]
        title_text = primary.title or topic.title_hint or topic.keyword
        summary_text = primary.summary or topic.rationale or ""
        blob = f"{topic.keyword} {topic.title_hint} {title_text} {summary_text}".lower()
        display_title = title_text.strip() or topic.keyword

        if "notion" in blob and "anthropic" in blob:
            return {
                "title": "Notion AI 장애, 실제 영향은?",
                "excerpt": "Notion이 Anthropic Claude 모델 접근을 일시 중단했다가 복구한 사건을 AI 서비스 의존성 관점에서 정리했습니다.",
                "summary": (
                    "Notion AI에서 Anthropic의 Claude 계열 모델을 선택한 일부 사용자가 실패율 증가를 겪었고, "
                    "Notion은 문제 대응 과정에서 Anthropic 모델 사용을 잠시 막았다가 약 12시간 뒤 복구했습니다. "
                    "핵심은 모델 성능 논란이라기보다 Notion 같은 생산성 도구가 외부 AI 모델 인프라에 얼마나 기대고 있는지 드러난 사건입니다."
                ),
                "background": (
                    "Notion은 문서, 데이터베이스, 프로젝트 관리를 한곳에서 쓰는 업무용 협업 도구입니다. "
                    "Anthropic은 Claude 모델을 제공하는 AI 기업이고, Notion AI는 이런 외부 모델을 붙여 문서 요약, 초안 작성, 검색 보조 기능을 제공합니다. "
                    "따라서 모델 제공사 쪽 오류가 생기면 Notion 자체 앱이 살아 있어도 AI 기능만 따로 흔들릴 수 있습니다."
                ),
                "why_it_matters": (
                    "AI 기능이 부가 기능에서 업무 흐름의 일부로 들어오면서 장애의 의미가 달라졌습니다. "
                    "예전에는 문서 편집기가 열리면 서비스가 정상이라고 봤지만, 지금은 요약, 자동 작성, 내부 지식 검색까지 함께 동작해야 사용자가 정상으로 느낍니다. "
                    "기업 고객 입장에서는 단일 모델 제공사 의존도, 장애 시 대체 모델 전환, 상태 공지 속도까지 계약과 운영 기준으로 봐야 합니다."
                ),
                "target": "Notion AI 사용자, Anthropic Claude 모델을 붙인 SaaS 서비스, 기업 IT 관리자",
                "tech_context": "외부 LLM API, SaaS 통합, 모델 장애 대응, 멀티벤더 AI 아키텍처",
                "user_impact": "문서 요약·작성 같은 AI 기능 실패율이 올라가거나 특정 모델 선택지가 잠시 사라질 수 있음",
                "next_check": "Notion과 Anthropic의 상태 공지, 장애 원인 설명, 재발 방지책, 대체 모델 제공 여부",
                "point_1": "이번 사건은 Notion 전체 서비스 중단보다 'Notion 안의 Claude 기능' 장애에 가깝습니다.",
                "point_2": "업무 도구가 AI 모델을 외부에서 호출하면 앱 회사와 모델 회사의 안정성이 함께 중요해집니다.",
                "point_3": "기업 도입 전에는 특정 모델이 막혔을 때 다른 모델로 자동 전환되는지 확인해야 합니다.",
            }

        if "tokenpocalypse" in blob or ("copilot" in blob and "token" in blob):
            return {
                "title": "AI 토큰 과금, 왜 부담 커지나",
                "excerpt": "GitHub Copilot 가격 변화와 'Tokenpocalypse' 논의를 AI 서비스 비용 전가 문제로 풀었습니다.",
                "summary": (
                    "TechCrunch의 'Tokenpocalypse' 논의는 GitHub Copilot 같은 AI 개발 도구가 정액제처럼 보이던 사용 경험에서 "
                    "토큰 사용량과 고성능 모델 비용을 더 직접적으로 반영하는 방향으로 움직이는 흐름을 다룹니다. "
                    "토큰은 AI 모델이 텍스트를 읽고 생성할 때 세는 기본 단위라서, 긴 코드베이스 분석이나 반복 호출이 많을수록 비용이 커집니다."
                ),
                "background": (
                    "GitHub Copilot은 개발자가 코드 자동완성, 설명, 테스트 작성 등을 할 때 쓰는 Microsoft 계열 AI 코딩 도구입니다. "
                    "그동안 많은 AI 서비스는 투자금과 클라우드 계약 덕분에 실제 추론 비용보다 낮은 가격으로 사용자를 모았습니다. "
                    "하지만 AI 기업들이 수익성, IPO, 고성능 모델 운영비를 설명해야 하는 단계가 오면 사용량 제한과 가격 인상이 나타날 가능성이 커집니다."
                ),
                "why_it_matters": (
                    "AI 서비스 비용은 소프트웨어 구독료만의 문제가 아닙니다. "
                    "모델 추론에는 GPU 서버, 메모리, 전력, 네트워크, 모델 운영 인력이 들어가고, 긴 컨텍스트나 에이전트식 반복 작업은 호출량을 빠르게 늘립니다. "
                    "개발팀은 이제 '몇 명이 쓰는가'뿐 아니라 '얼마나 많은 토큰을 쓰는가'를 예산 항목으로 관리해야 합니다."
                ),
                "target": "GitHub Copilot 사용자, AI 코딩 도구를 도입한 개발팀, SaaS 예산 담당자",
                "tech_context": "LLM 토큰 과금, 추론 비용, AI 코딩 도구, 고성능 모델 사용 제한",
                "user_impact": "무제한처럼 쓰던 기능에 사용량 한도, 모델별 추가 비용, 팀 단위 예산 관리가 붙을 수 있음",
                "next_check": "Copilot 요금제 세부 조건, 토큰·프리미엄 요청 제한, 기업 계약의 초과 과금 기준",
                "point_1": "Tokenpocalypse는 실제 제품명이 아니라 AI 토큰 비용 부담이 커지는 현상을 비유한 표현입니다.",
                "point_2": "코드 에이전트처럼 여러 번 읽고 고치는 기능은 일반 챗봇보다 토큰을 더 빨리 씁니다.",
                "point_3": "팀 단위 도입 때는 월 구독료와 함께 고성능 모델 사용량, 초과 요금, 로그 확인 기능을 봐야 합니다.",
            }

        if ("nasa" in blob and "prada" in blob) or "lcvg" in blob or "axemu" in blob:
            return {
                "title": "NASA의 Prada 우주복, 핵심은 냉각",
                "excerpt": "Axiom Space와 Prada가 공개한 Artemis IV용 LCVG를 우주복 생명유지 기술 관점에서 설명했습니다.",
                "summary": (
                    "NASA 우주비행사가 달에서 입게 될 장비로 언급된 것은 겉옷 패션이 아니라 Axiom Space와 Prada가 공개한 "
                    "Liquid Cooling and Ventilation Garment, 즉 LCVG입니다. "
                    "이 옷은 AxEMU 우주복 안쪽에 입는 베이스 레이어로, 달 표면 활동 중 몸에서 나는 열을 빼고 호흡 공기 흐름을 관리하는 역할을 합니다."
                ),
                "background": (
                    "Axiom Space는 NASA의 달 탐사 프로그램에 쓰일 차세대 우주복 AxEMU를 개발하는 민간 우주 인프라 기업입니다. "
                    "Prada는 이름 때문에 패션 협업처럼 보이지만, 이번에는 고기능 섬유, 패턴 설계, 3D 모델링 경험을 우주복 내부 의복 설계에 보탠 사례입니다. "
                    "Artemis IV는 NASA가 달 표면 활동을 다시 확대하려는 Artemis 프로그램의 후속 임무로 거론됩니다."
                ),
                "why_it_matters": (
                    "우주복은 단순한 방한복이 아니라 작은 생명유지 시스템입니다. "
                    "달 표면에서는 햇빛, 그림자, 먼지, 운동량에 따라 체온 관리가 어려워지고, 밀폐된 옷 안에서는 이산화탄소와 습기도 처리해야 합니다. "
                    "LCVG 같은 내부 냉각·환기층은 우주비행사가 장시간 선외활동을 버틸 수 있게 만드는 핵심 부품입니다."
                ),
                "target": "NASA Artemis 임무, Axiom Space 우주복 개발팀, 고기능 섬유·웨어러블 기술 업계",
                "tech_context": "우주복 생명유지, 액체 냉각 의복, 환기 시스템, 고기능 섬유와 3D 패턴 설계",
                "user_impact": "일반 소비자 제품은 아니지만 극한환경 웨어러블과 냉각 섬유 기술의 실증 사례가 됨",
                "next_check": "Axiom Space의 시험 일정, NASA 인증 과정, Artemis IV 일정, 실제 달 표면 운용 결과",
                "point_1": "기사의 'Prada long johns'는 속옷 농담에 가깝고, 실제로는 우주복 내부 냉각·환기 장비를 뜻합니다.",
                "point_2": "물이 흐르는 관이 주요 근육 부위의 열을 가져가고, 별도 환기 흐름이 호흡과 이산화탄소 제거를 돕습니다.",
                "point_3": "패션 브랜드 협업의 의미는 로고보다 소재 선택, 착용감, 재봉·패턴 설계 역량에 있습니다.",
            }

        return self._generic_tech_news_context(topic, display_title, summary_text, blob)

    def _generic_tech_news_context(self, topic: Topic, display_title: str, summary_text: str, blob: str) -> dict[str, str]:
        clean_summary = self._clean_summary(summary_text)
        angle = self._tech_angle(blob)
        subject = self._humanize_tech_subject(display_title or topic.keyword)
        title = angle["title_template"].format(subject=subject)
        return {
            "title": title,
            "excerpt": angle["excerpt_template"].format(subject=subject),
            "summary": (
                f"{display_title} 소식입니다. "
                f"{clean_summary or angle['summary_fallback'].format(subject=subject)}"
            ),
            "background": angle["background"].format(subject=subject),
            "why_it_matters": angle["why_it_matters"].format(subject=subject),
            "target": angle["target"],
            "tech_context": angle["tech_context"],
            "user_impact": angle["user_impact"],
            "next_check": angle["next_check"],
            "point_1": angle["point_1"].format(subject=subject),
            "point_2": angle["point_2"].format(subject=subject),
            "point_3": angle["point_3"].format(subject=subject),
        }

    @staticmethod
    def _tech_angle(blob: str) -> dict[str, str]:
        angles = [
            (
                ("스마트건설", "건설현장", "건설 로봇", "ai 건설", "construction robot"),
                {
                    "title_template": "AI 건설로봇 혁신센터, 무엇이 달라지나",
                    "excerpt_template": "{subject} 소식을 건설현장 자동화, 지역 혁신센터, 중소기업 기술 확산 관점에서 정리했습니다.",
                    "summary_fallback": "{subject}는 AI와 로봇을 건설현장에 적용해 안전, 생산성, 지역 기술 생태계를 함께 바꾸려는 스마트건설 이슈입니다.",
                    "background": "전북·전주 건설현장은 반복 작업, 위험 구역, 숙련 인력 부족, 공정 관리가 함께 얽힌 산업 현장입니다. AI와 로봇이 들어오면 단순히 장비가 새로 생기는 것이 아니라 측량, 점검, 자재 이동, 위험 감지, 공정 데이터 관리 방식이 바뀔 수 있습니다.",
                    "why_it_matters": "스마트건설은 수도권 대기업만의 기술 도입으로 끝나면 효과가 제한됩니다. 지역 대학, 연구기관, 지자체, 중소 건설사가 함께 쓰는 실증 거점이 만들어져야 현장 적용 사례가 늘고 안전 개선도 이어질 수 있습니다.",
                    "target": "건설사, 스마트건설 장비 기업, 지자체 산업 담당자, 건설 현장 안전 담당자",
                    "tech_context": "AI 건설로봇, 스마트건설 실증센터, 현장 자동화, 안전 모니터링, 지역 기술 확산",
                    "user_impact": "건설 현장의 안전 점검, 작업 효율, 지역 기업의 기술 도입 기회, 공공 인프라 사업 방식에 영향",
                    "next_check": "혁신센터 설립 일정, 참여 기관 역할, 입주기업 지원 방식, 실제 현장 실증 과제, 안전 규정 반영 여부",
                    "point_1": "{subject}의 핵심은 로봇 자체보다 현장에서 어떤 작업을 대신하거나 보조하는지입니다.",
                    "point_2": "스마트건설 센터는 장비 전시장보다 실증, 교육, 기업 지원 기능이 작동해야 의미가 있습니다.",
                    "point_3": "AI·로봇 도입은 생산성뿐 아니라 사고 예방과 숙련 인력 부족 대응 효과를 함께 봐야 합니다.",
                },
            ),
            (
                ("dhs", "ice", "cbp", "homeland security", "70 billion", "immigration enforcement"),
                {
                    "title_template": "미 DHS 700억 달러 증액, 어디에 쓰이나",
                    "excerpt_template": "미국 DHS 추가 예산을 이민 집행, 국경 관리, 감시 기술, 사이버안보 우선순위 관점에서 정리했습니다.",
                    "summary_fallback": "미국 의회가 DHS에 대규모 추가 예산을 배정하면서 이민 집행과 국경 관리, 감시 기술 확대를 둘러싼 논쟁이 커졌습니다.",
                    "background": "DHS는 미국 국토안보부로 ICE, CBP, TSA, CISA 같은 기관을 거느립니다. 예산은 이민 집행뿐 아니라 공항 보안, 사이버 방어, 국경 관리, 재난 대응까지 연결됩니다. 따라서 DHS 예산 증액은 단순 행정비보다 넓은 정책·기술 이슈입니다.",
                    "why_it_matters": "대규모 이민 집행 예산은 현장 인력만 늘리는 문제가 아닙니다. 데이터베이스, 생체정보, 카메라, 드론, 차량 번호판 인식, 사건 관리 시스템 같은 기술 인프라 확장과 연결될 수 있습니다. 동시에 CISA 같은 사이버안보 기능의 우선순위가 어떻게 달라지는지도 봐야 합니다.",
                    "target": "미국 정책을 보는 독자, 보안·감시 기술 업계, 공공 예산 흐름을 확인하는 독자",
                    "tech_context": "DHS 예산, ICE·CBP 집행 역량, 감시 기술, 데이터 시스템, 사이버안보 예산",
                    "user_impact": "미국 내 이민 집행 강도, 국경 관리 시스템, 개인정보·시민권 논쟁, 공공 보안 기술 투자에 영향",
                    "next_check": "세부 예산 항목, 의회 감독 장치, ICE·CBP 집행 결과, CISA 등 사이버안보 예산 변화",
                    "point_1": "이 이슈는 해킹 사고가 아니라 미국 국토안보 예산과 집행 권한 확대 문제입니다.",
                    "point_2": "이민 집행 예산은 감시·데이터 기술 확장과 함께 움직일 수 있어 기술 독자도 볼 필요가 있습니다.",
                    "point_3": "정책 평가는 찬반 구호보다 예산 항목, 감독 장치, 실제 집행 결과를 나눠 봐야 합니다.",
                },
            ),
            (
                ("siri ai", "apple intelligence", "ios 27", "wwdc", "actually works"),
                {
                    "title_template": "Siri AI, 이번엔 정말 쓸 만해졌나",
                    "excerpt_template": "WWDC26 이후 Siri AI 초기 사용기를 개인 맥락 이해, 앱 작업 실행, 한국 사용자 제한 조건 중심으로 정리했습니다.",
                    "summary_fallback": "Apple이 Siri AI와 차세대 Apple Intelligence를 공개하며 화면 이해, 앱 작업 실행, 개인 맥락 활용을 다시 강조했습니다.",
                    "background": "Siri는 오래된 Apple 음성 비서지만 생성형 AI 경쟁 이후 답답하다는 평가를 받아 왔습니다. Apple은 Apple Intelligence를 통해 Siri가 화면 내용을 이해하고, 앱 안 작업을 수행하고, 일정·메일·사진 같은 개인 맥락을 더 잘 활용하도록 만들겠다고 설명합니다.",
                    "why_it_matters": "AI 비서는 답변을 멋지게 쓰는 능력보다 실제 행동을 안정적으로 끝내는지가 중요합니다. 일정 추가, 알림 설정, 메시지 작성 같은 작업에서 실패가 적어야 사용자가 신뢰합니다. Apple은 온디바이스 처리와 Private Cloud Compute를 함께 내세워 편의성과 개인정보 보호를 동시에 강조합니다.",
                    "target": "iPhone·iPad·Mac 사용자, Apple Intelligence 기능을 기다리는 사용자, iOS 앱 개발자",
                    "tech_context": "Siri AI, Apple Intelligence, 개인 맥락 이해, 앱 작업 실행, Private Cloud Compute",
                    "user_impact": "일정·메일·사진·지도 같은 기본 앱 작업 자동화, 지원 언어·기기 조건, 개인정보 처리 신뢰도에 영향",
                    "next_check": "지원 기기, 한국어 지원 시점, EU 등 지역 제한, 정식 배포 후 작업 성공률",
                    "point_1": "Siri AI는 챗봇 답변보다 iPhone 안의 실제 작업을 얼마나 잘 처리하는지가 관건입니다.",
                    "point_2": "발표 기능이 있어도 한국어와 국내 계정에서 바로 되는지는 별도로 확인해야 합니다.",
                    "point_3": "Apple의 차별점은 생태계 통합이지만, 기능 지연과 지역 제한이 체감 품질을 좌우합니다.",
                },
            ),
            (
                ("whatsapp", "rival ai assistant", "third-party ai", "meta whatsapp", "chatbot ban"),
                {
                    "title_template": "EU가 WhatsApp에 경쟁 AI 개방 명령",
                    "excerpt_template": "EU의 Meta·WhatsApp 임시 명령을 AI 플랫폼 접근권과 반독점 규제 관점에서 정리했습니다.",
                    "summary_fallback": "EU 집행위원회는 Meta가 반독점 조사를 받는 동안 WhatsApp에서 경쟁 AI 비서의 접근을 복구해야 한다고 봤습니다.",
                    "background": "WhatsApp은 개인 메신저이면서 기업 고객 응대에 쓰이는 WhatsApp Business API를 가진 플랫폼입니다. AI 비서 회사가 이 통로를 쓰면 사용자는 별도 앱을 설치하지 않고도 메신저 안에서 상담, 예약, 요약, 추천 같은 기능을 받을 수 있습니다. Meta가 자체 AI를 키우는 동시에 외부 AI의 접근 조건을 바꾸면 메신저 유통망을 가진 회사가 경쟁 AI의 입구를 통제하는 문제가 생깁니다.",
                    "why_it_matters": "AI 경쟁은 모델 성능만으로 결정되지 않습니다. 사용자가 매일 여는 앱 안에 들어갈 수 있느냐가 중요합니다. EU의 이번 조치는 대형 플랫폼이 자사 AI를 밀기 위해 API 접근권과 비용 조건을 조정할 때 어느 선까지 규제할 수 있는지 보여주는 사례입니다.",
                    "target": "WhatsApp Business 이용 기업, AI 챗봇 개발사, 플랫폼 규제를 보는 독자",
                    "tech_context": "WhatsApp Business API, Meta AI, 제3자 AI 비서, EU 반독점 임시조치, 플랫폼 접근권",
                    "user_impact": "메신저 안에서 선택할 수 있는 AI 비서, 기업 고객센터 자동화 비용, 외부 AI 서비스의 유통 경로에 영향",
                    "next_check": "Meta의 이행 방식, API 이용료, 접근 제한 조건, EU 최종 반독점 판단, Meta의 항소 여부",
                    "point_1": "이번 쟁점은 WhatsApp에 새 챗봇이 붙는다는 수준보다 '메신저 플랫폼을 누가 통제하느냐'에 가깝습니다.",
                    "point_2": "무료 접근이 복구돼도 속도 제한, 심사 절차, API 범위가 다르면 실제 경쟁 효과는 달라질 수 있습니다.",
                    "point_3": "국내 메신저에 AI 비서가 들어올 때도 자사 AI 우대와 외부 AI 접근권은 비슷한 쟁점이 될 수 있습니다.",
                },
            ),
            (
                ("waymo", "virtual driver", "reference driver", "red", "surprises on the road"),
                {
                    "title_template": "Waymo의 가상 운전자, 자율주행 안전 실험",
                    "excerpt_template": "Waymo의 Reference Driver 모델을 자율주행 안전 검증과 인간 운전자 비교 기준으로 설명했습니다.",
                    "summary_fallback": "Waymo는 도로 위 돌발 상황에서 사람이 위험을 보고 반응하는 방식을 시뮬레이션하는 가상 운전자 모델을 만들었습니다.",
                    "background": "Waymo는 Alphabet 계열 자율주행 기업입니다. 실제 도로에서 모든 사고 가능성을 직접 시험할 수 없기 때문에 자율주행 개발에는 시뮬레이션이 필수입니다. Reference Driver는 완벽한 운전자가 아니라 사람이 가진 인지 지연, 놀람, 조작 지연을 넣어 위험 상황의 비교 기준을 만들려는 모델입니다.",
                    "why_it_matters": "자율주행 안전 논쟁에서 어려운 질문은 '무엇과 비교해 안전한가'입니다. 회사가 자체 기준만 내세우면 신뢰를 얻기 어렵고, 무사고만 요구하면 기술 검증이 멈춥니다. 인간 운전자 반응을 현실적으로 모델링하면 자율주행차가 위험을 얼마나 일찍 보고 피했는지 더 구체적으로 비교할 수 있습니다.",
                    "target": "자율주행 기술을 보는 독자, 로보택시 이용자, 교통 안전 연구자",
                    "tech_context": "자율주행 시뮬레이션, 인간 운전자 모델, 위험 인지, 충돌 회피, 안전 벤치마크",
                    "user_impact": "로보택시 안전성 평가, 규제기관 검증 방식, 사고 설명 기준에 영향",
                    "next_check": "모델 공개 범위, 연구자 검증, 실제 사고 데이터와의 비교, 규제기관 채택 여부",
                    "point_1": "ReD는 Waymo 차량을 직접 운전하는 기능이 아니라 사람 운전자와 비교하기 위한 기준 모델입니다.",
                    "point_2": "주행거리 숫자만으로 자율주행 안전성을 판단하기 어렵기 때문에 상황별 비교 기준이 필요합니다.",
                    "point_3": "한국에서도 자율주행 실증이 늘면 '사람이라면 피했을까'를 설명할 기준이 중요해집니다.",
                },
            ),
            (
                ("office 2019 for mac", "microsoft is disabling", "license certificate", "no edit", "end of support"),
                {
                    "title_template": "Office 2019 Mac, 7월부터 편집 제한",
                    "excerpt_template": "Office 2019 for Mac의 인증서 만료와 편집 제한 가능성을 Mac 사용자 대응 관점에서 정리했습니다.",
                    "summary_fallback": "Microsoft Office 2019 for Mac은 라이선스 검증 인증서 만료 이후 문서 열람은 가능해도 편집과 저장이 제한될 수 있습니다.",
                    "background": "Office 2019 for Mac은 한 번 구매해 쓰는 영구 라이선스 제품이지만, 앱은 정품 여부를 확인하기 위해 인증서와 라이선스 검증 체계에 의존합니다. 해당 버전은 이미 공식 지원이 끝난 상태라 인증서 갱신 업데이트를 받지 못하면 핵심 기능이 제한될 수 있습니다.",
                    "why_it_matters": "이 문제는 오래된 앱의 새 기능 중단이 아니라 구매한 생산성 도구의 편집·저장 기능이 막힐 수 있다는 점에서 민감합니다. 학교, 소규모 회사, 개인 사업자처럼 오래된 Mac과 영구 라이선스 Office를 계속 쓰는 사용자에게 실제 업무 차질이 생길 수 있습니다.",
                    "target": "Office 2019 for Mac 사용자, 학교·소규모 회사 IT 담당자, Mac 생산성 도구 사용자",
                    "tech_context": "라이선스 검증 인증서, Office 지원 종료, 영구 라이선스, Microsoft 365 전환",
                    "user_impact": "Word·Excel·PowerPoint 문서 편집, 저장, 새 파일 작성 업무에 영향 가능",
                    "next_check": "사용 중인 Office 버전, macOS 버전, 백업, Office 2024 또는 Microsoft 365 전환 비용, 대체 앱 호환성",
                    "point_1": "Office 2019 for Mac은 앱이 완전히 사라지는 것이 아니라 읽기 중심으로 기능이 줄어들 수 있습니다.",
                    "point_2": "영구 라이선스라도 인증서와 서버 검증 체계에 의존하면 사용 가능성이 외부 조건에 묶입니다.",
                    "point_3": "7월 전에 버전 확인, 중요 파일 백업, 대체 편집 환경 테스트를 해두는 편이 안전합니다.",
                },
            ),
            (
                ("apple ai pitch", "private cloud compute", "privacy promise", "apple intelligence"),
                {
                    "title_template": "Apple AI의 승부수, 개인정보 약속",
                    "excerpt_template": "Apple AI 전략을 Apple Intelligence, Private Cloud Compute, Siri 개인정보 처리 관점에서 정리했습니다.",
                    "summary_fallback": "Apple의 AI 전략은 기능 경쟁만이 아니라 개인정보 보호 약속을 실제 서비스 구조로 증명할 수 있는지가 핵심입니다.",
                    "background": "Apple Intelligence는 iPhone, iPad, Mac에서 문서 요약, 알림 정리, 이미지 생성, Siri 명령 이해 같은 기능을 제공하려는 Apple의 AI 기능 묶음입니다. Apple은 기기 안 처리와 Private Cloud Compute를 함께 내세워 클라우드를 쓰더라도 사용자 요청을 오래 저장하거나 임의로 들여다보지 않겠다고 설명합니다.",
                    "why_it_matters": "AI 비서는 일정, 메일, 사진, 파일처럼 민감한 개인 맥락을 다룰수록 쓸모가 커집니다. Apple AI를 볼 때는 모델 성능뿐 아니라 어떤 요청이 기기 안에서 끝나는지, 어떤 요청이 클라우드로 가는지, 외부 검증이 가능한지 확인해야 합니다.",
                    "target": "iPhone·Mac 사용자, Siri 개선을 기다리는 사용자, Apple 생태계 개발자",
                    "tech_context": "Apple Intelligence, Siri, 온디바이스 AI, Private Cloud Compute, 개인정보 보호 설계",
                    "user_impact": "AI 기능의 편의성, 개인 데이터 처리 신뢰도, 지원 언어·기기 조건에 영향",
                    "next_check": "한국어 지원 여부, 지원 기기 목록, Siri 실제 작업 성공률, Private Cloud Compute 검증 자료",
                    "point_1": "Apple AI의 핵심 메시지는 가장 빠른 AI가 아니라 개인정보를 덜 넘기는 AI입니다.",
                    "point_2": "Private Cloud Compute는 클라우드 처리와 개인정보 보호 사이의 불신을 줄이기 위한 장치입니다.",
                    "point_3": "Siri 개선은 발표 문구보다 일상 작업 성공률, 앱 연동 범위, 지역·언어 지원으로 판단해야 합니다.",
                },
            ),
            (
                ("rivian r2", "rivian", "r2 is too much fun"),
                {
                    "title_template": "Rivian R2, 자율주행보다 운전 재미",
                    "excerpt_template": "Rivian R2 시승기를 전기 SUV 대중화, 운전 경험, Rivian의 사업 확장 관점에서 정리했습니다.",
                    "summary_fallback": "Rivian R2는 로보택시나 완전 자율주행보다 사람이 직접 몰고 싶은 전기 SUV라는 포지션을 보여주는 모델입니다.",
                    "background": "Rivian은 미국 전기차 제조사로 R1T 픽업트럭과 R1S SUV를 통해 아웃도어 성향의 고가 EV 브랜드 이미지를 만들었습니다. R2는 더 넓은 소비자층을 겨냥한 중형 전기 SUV로, Rivian이 팬층을 넘어 대중형 EV 시장으로 확장할 수 있는지 보여주는 차입니다.",
                    "why_it_matters": "전기차 경쟁은 배터리 용량만으로 끝나지 않습니다. 소프트웨어 UI, 운전자 보조 기능, 충전 경험, 가격, 생산 일정, 실제 운전 감각이 함께 평가됩니다. Rivian R2는 자율주행 담론 속에서도 운전자가 직접 몰고 싶어지는 경험이 제품 경쟁력이 될 수 있음을 보여줍니다.",
                    "target": "전기 SUV 구매 예정자, Rivian 투자·산업 동향을 보는 독자, EV 시장 관심층",
                    "tech_context": "전기차 플랫폼, 운전자 보조, OTA 업데이트, 배터리 효율, 중형 SUV 시장",
                    "user_impact": "전기 SUV 선택 기준, 실제 구매 가격, 주행거리, 충전·서비스 경험 판단에 영향",
                    "next_check": "최종 가격, 배터리 옵션, 실제 주행거리, 생산·인도 일정, 운전자 보조 기능 구성",
                    "point_1": "Rivian R2의 핵심은 로보택시가 아니라 사람이 직접 몰고 싶은 전기 SUV라는 점입니다.",
                    "point_2": "R2는 Rivian이 고가 모험용 EV 브랜드에서 더 대중적인 브랜드로 내려올 수 있는 시험대입니다.",
                    "point_3": "구매 판단은 목표 가격보다 최종 사양, 보조금, 충전 조건, 인도 일정을 함께 봐야 합니다.",
                },
            ),
            (
                ("hack", "breach", "security", "privacy", "data", "wellness"),
                {
                    "title_template": "{subject}, 보안 리스크가 핵심",
                    "excerpt_template": "{subject} 이슈를 개인정보, 내부 도구 접근, 사고 대응 기준으로 정리했습니다.",
                    "summary_fallback": "{subject} 관련 보도는 제품 기능보다 데이터 접근과 사고 대응 절차를 먼저 봐야 하는 보안 이슈입니다.",
                    "background": "{subject} 같은 디지털 서비스는 앱 화면 뒤에서 계정, 내부 운영 도구, 고객 데이터 저장소가 함께 움직입니다. 보안 사고가 나면 해커가 어떤 권한으로 어디까지 접근했는지가 핵심입니다.",
                    "why_it_matters": "웨어러블·헬스케어·생산성 서비스는 단순 연락처보다 민감한 생활 패턴과 건강 지표를 다룰 수 있습니다. 따라서 {subject} 이슈는 기능 업데이트가 아니라 데이터 최소화, 내부 권한 통제, 사고 통지 체계의 문제로 읽어야 합니다.",
                    "target": "서비스 이용자, 보안 담당자, 개인정보 처리 서비스를 운영하는 스타트업",
                    "tech_context": "내부 관리도구 보안, 고객 데이터 접근권한, 침해사고 대응, 개인정보 최소화",
                    "user_impact": "계정 정보, 건강·활동 데이터, 알림 수신 여부, 비밀번호 재설정 같은 사후 조치에 영향 가능",
                    "next_check": "침해 범위, 노출 데이터 항목, 사용자 통지, 비밀번호·토큰 재설정, 감독기관 신고 여부",
                    "point_1": "{subject}에서 가장 먼저 볼 것은 '누가 어떤 내부 도구에 접근했나'입니다.",
                    "point_2": "서비스 회사가 빠르게 복구했다고 해도 노출 데이터 종류와 보관 기간은 별도 확인이 필요합니다.",
                    "point_3": "헬스·웨어러블 데이터는 광고 데이터보다 개인 생활을 더 자세히 드러낼 수 있습니다.",
                },
            ),
            (
                ("dreambeans", "cartoon", "image", "creator", "ai tool", "generative"),
                {
                    "title_template": "{subject}, 생성 AI의 다음 실험",
                    "excerpt_template": "{subject} 소식을 이미지 생성 AI, 개인정보, 크리에이터 도구 관점에서 풀었습니다.",
                    "summary_fallback": "{subject}는 사용자의 사진이나 일상 데이터를 창작물로 바꾸는 생성 AI 도구 흐름과 맞닿아 있습니다.",
                    "background": "Google 같은 플랫폼 기업은 검색·클라우드뿐 아니라 이미지, 영상, 생산성 도구에 생성 AI를 붙이고 있습니다. {subject}는 이름보다 어떤 입력 데이터를 받아 어떤 결과물을 만드는지가 더 중요합니다.",
                    "why_it_matters": "생성 AI 도구는 재미있는 기능처럼 보이지만, 사진·얼굴·취향 데이터를 다룰 때 개인정보와 저작권 문제가 함께 생깁니다. {subject}를 볼 때는 결과물 품질뿐 아니라 학습·저장·공유 설정을 확인해야 합니다.",
                    "target": "AI 이미지 도구 이용자, 크리에이터, Google 생태계 사용자",
                    "tech_context": "생성형 이미지 모델, 개인화 콘텐츠, 입력 데이터 보호, 플랫폼 내 AI 기능 통합",
                    "user_impact": "사진 변환, 캐릭터 생성, SNS 공유, 데이터 저장 설정 확인 필요",
                    "next_check": "공식 출시 지역, 입력 데이터 보관 정책, 상업적 이용 가능 여부, 워터마크·표시 정책",
                    "point_1": "{subject}는 이름보다 '내 사진과 생활 데이터를 어떻게 쓰는가'가 핵심입니다.",
                    "point_2": "무료 AI 기능이라도 결과물 공유권과 데이터 보관 조건은 서비스 약관에 달려 있습니다.",
                    "point_3": "크리에이터에게는 빠른 시안 제작 도구가 될 수 있지만 원본성 논란도 따라붙을 수 있습니다.",
                },
            ),
            (
                ("substack", "reply", "creator", "comment", "moderation"),
                {
                    "title_template": "Substack 답글 규칙, 왜 중요할까",
                    "excerpt_template": "Substack의 Reply Rules를 창작자 커뮤니티 운영과 댓글 관리 기능 관점에서 정리했습니다.",
                    "summary_fallback": "Substack의 새 답글 규칙 기능은 창작자가 독자 반응을 더 세밀하게 통제하도록 돕는 커뮤니티 관리 기능입니다.",
                    "background": "Substack은 뉴스레터와 구독형 글쓰기를 결합한 창작자 플랫폼입니다. 글 발행만이 아니라 댓글, 토론, 유료 구독자 커뮤니티가 수익 모델과 연결됩니다.",
                    "why_it_matters": "크리에이터 플랫폼의 경쟁력은 글쓰기 도구만으로 정해지지 않습니다. 악성 댓글을 줄이고, 유료 독자의 대화 품질을 지키고, 창작자가 번아웃 없이 운영할 수 있게 만드는 관리 기능이 점점 중요해집니다.",
                    "target": "Substack 작가, 뉴스레터 운영자, 유료 커뮤니티를 운영하는 창작자",
                    "tech_context": "댓글 권한 설정, 커뮤니티 모더레이션, 창작자 수익화 플랫폼, 구독자 관리",
                    "user_impact": "누가 답글을 달 수 있는지, 토론 품질이 어떻게 관리되는지, 유료 독자 경험이 달라질 수 있음",
                    "next_check": "Reply Rules 적용 범위, 무료·유료 독자 구분, 차단·승인 기능, 기존 댓글 정책과의 차이",
                    "point_1": "Substack의 핵심 고객은 글을 쓰는 사람이라서 댓글 통제권이 제품 경쟁력이 됩니다.",
                    "point_2": "답글 규칙은 검열 논쟁보다 커뮤니티 운영 비용을 줄이는 도구로 봐야 합니다.",
                    "point_3": "유료 구독 모델에서는 대화 품질이 콘텐츠만큼 재구독률에 영향을 줍니다.",
                },
            ),
            (
                ("google cloud", "cloud", "multiyear", "usage", "lovable"),
                {
                    "title_template": "{subject}, 클라우드 비용을 봐야",
                    "excerpt_template": "{subject} 소식을 AI 앱 성장, Google Cloud 계약, 인프라 비용 관점에서 정리했습니다.",
                    "summary_fallback": "{subject}는 AI 서비스가 빠르게 성장할 때 클라우드 사용량과 장기 계약이 어떻게 중요해지는지 보여주는 사례입니다.",
                    "background": "AI 앱은 사용자가 늘수록 모델 호출, 저장소, 빌드·배포, 보안 로그 비용이 함께 늘어납니다. {subject}처럼 클라우드 계약이 보도되는 이유는 제품 인기가 곧 인프라 비용으로 이어지기 때문입니다.",
                    "why_it_matters": "AI 스타트업은 기능 출시 속도만큼 단위 경제성이 중요합니다. 사용량을 5배 늘리는 계약은 성장 신호일 수 있지만, 동시에 클라우드 의존도와 비용 구조를 더 꼼꼼히 봐야 한다는 뜻입니다.",
                    "target": "AI 앱 사용자, 스타트업 투자자, 클라우드 비용을 관리하는 개발팀",
                    "tech_context": "Google Cloud 계약, AI 앱 추론·빌드 비용, 확장성, 클라우드 벤더 의존도",
                    "user_impact": "서비스 속도, 사용량 제한, 요금제 변화, 장애 대응 품질에 영향 가능",
                    "next_check": "계약 기간, 사용량 증가 근거, 가격 정책 변화, 멀티클라우드 여부, 실제 사용자 증가",
                    "point_1": "{subject}에서 '사용량 증가'는 제품 인기와 비용 부담을 동시에 뜻합니다.",
                    "point_2": "AI 앱은 사용자가 버튼을 한 번 누를 때도 모델 호출과 배포 인프라가 비용으로 잡힐 수 있습니다.",
                    "point_3": "장기 클라우드 계약은 안정성을 주지만 특정 벤더 의존도를 키울 수 있습니다.",
                },
            ),
            (
                ("carvana", "slate auto"),
                {
                    "title_template": "Carvana와 Slate Auto, 관전 포인트",
                    "excerpt_template": "Carvana와 Slate Auto 협력을 온라인 자동차 판매와 전기차 유통 변화로 정리했습니다.",
                    "summary_fallback": "Carvana와 Slate Auto의 협력은 중고차 온라인 판매 플랫폼이 신차·전기차 유통으로 확장할 가능성을 보여줍니다.",
                    "background": "Carvana는 차량 검색, 금융, 배송을 온라인으로 묶은 미국 자동차 거래 플랫폼입니다. Slate Auto는 전기차 시장에서 주목받는 신생 제조사로 알려져 있어, 두 회사의 협력은 단순 제휴보다 판매 채널 실험에 가깝습니다.",
                    "why_it_matters": "자동차 유통은 딜러망, 재고 금융, 배송, 보증이 얽혀 있어 플랫폼화가 쉽지 않습니다. Carvana가 신차 판매까지 넓히면 소비자는 온라인 구매 편의성을 얻을 수 있지만, 제조사와 딜러의 역할 분담도 달라질 수 있습니다.",
                    "target": "온라인 차량 구매자, 전기차 스타트업, 자동차 유통 플랫폼",
                    "tech_context": "온라인 자동차 거래, 전기차 직접 판매, 재고·배송 시스템, 자동차 금융 플랫폼",
                    "user_impact": "가격 비교, 차량 인도 방식, 보증·반품 조건, 금융 선택지가 달라질 수 있음",
                    "next_check": "판매 지역, 실제 차량 인도 일정, 보증 주체, 반품 조건, 기존 딜러망과의 관계",
                    "point_1": "Carvana 이슈는 앱 기능보다 자동차 판매망이 온라인으로 이동하는 흐름입니다.",
                    "point_2": "신차 판매가 붙으면 플랫폼은 재고 관리와 제조사 관계라는 더 어려운 문제를 다뤄야 합니다.",
                    "point_3": "소비자는 클릭 구매 편의성보다 보증, 배송, 반품 조건을 먼저 확인해야 합니다.",
                },
            ),
            (
                ("defense", "anduril", "military", "weapon", "drone"),
                {
                    "title_template": "방산 테크 투자, 오래 갈 기업은?",
                    "excerpt_template": "방산 테크 투자 열기를 제품 실증, 조달, 규제 리스크 관점에서 정리했습니다.",
                    "summary_fallback": "방산 테크 시장에는 자금이 몰리고 있지만 오래 살아남는 기업은 실제 조달과 현장 검증을 통과해야 합니다.",
                    "background": "방산 테크는 드론, 감시 센서, 자율 시스템, 사이버 방어, 군수 소프트웨어처럼 군과 안보 기관이 쓰는 기술을 다룹니다. 일반 SaaS보다 판매 주기가 길고 정부 조달 규칙의 영향을 크게 받습니다.",
                    "why_it_matters": "투자금이 많다는 사실만으로 방산 스타트업의 경쟁력이 증명되지는 않습니다. 실제 군 운용 환경에서 버티는 하드웨어, 보안 인증, 긴 조달 절차, 윤리·수출 규제가 모두 관문입니다.",
                    "target": "방산 스타트업, 투자자, 국방 기술 조달을 보는 독자",
                    "tech_context": "드론·자율 시스템, 군수 소프트웨어, 정부 조달, 보안 인증, 현장 실증",
                    "user_impact": "일반 소비자 영향은 제한적이지만 공공 예산, 안보 기술 경쟁, 민간 기술 이전과 연결됨",
                    "next_check": "실제 계약 규모, 시제품과 양산 차이, 조달 기관, 수출 통제, 현장 운용 사례",
                    "point_1": "방산 테크는 데모 영상보다 실제 납품과 유지보수 계약이 더 중요합니다.",
                    "point_2": "정부 고객은 빠른 성장보다 안정성, 보안, 장기 지원 능력을 봅니다.",
                    "point_3": "투자 열기가 커질수록 과장된 기술 주장과 실제 운용 성과를 구분해야 합니다.",
                },
            ),
            (
                ("apple", "wwdc", "watchos", "ipados", "macos", "siri", "visionos"),
                {
                    "title_template": "{subject}, 애플 사용자 변화",
                    "excerpt_template": "{subject} 소식을 WWDC 업데이트, 지원 기기, 실제 사용 변화 중심으로 정리했습니다.",
                    "summary_fallback": "{subject}는 애플 운영체제 업데이트가 기기 지원, Siri AI, 건강·생산성 기능에 어떤 변화를 주는지 봐야 하는 이슈입니다.",
                    "background": "WWDC는 애플이 iOS, iPadOS, macOS, watchOS, visionOS 같은 운영체제 변화를 개발자와 사용자에게 공개하는 행사입니다. {subject}는 새 기능 자체뿐 아니라 어떤 기기가 업데이트 대상에서 빠지는지까지 함께 봐야 합니다.",
                    "why_it_matters": "애플 운영체제 업데이트는 앱 호환성, 보안 패치, 배터리 체감, 건강·피트니스 기능에 직접 영향을 줍니다. {subject}를 볼 때는 신기능 목록보다 내 기기가 지원되는지, Siri AI 같은 기능이 지역·언어 제한을 받는지 확인하는 것이 먼저입니다.",
                    "target": "아이폰·아이패드·애플워치 사용자, iOS 앱 개발자, 애플 생태계 구매 예정자",
                    "tech_context": "운영체제 업데이트, 지원 기기 변경, Siri AI, 앱 호환성, 보안 패치",
                    "user_impact": "업데이트 가능 여부, 새 기능 사용 가능성, 오래된 기기 교체 판단에 영향",
                    "next_check": "공식 지원 기기 목록, 베타 릴리스 노트, 가을 정식 배포 일정, 지역별 AI 기능 제공 여부",
                    "point_1": "{subject}에서 가장 먼저 볼 것은 새 기능보다 내 기기가 업데이트 대상인지입니다.",
                    "point_2": "Siri AI 같은 기능은 발표됐더라도 언어, 지역, 기기 칩셋 조건에 따라 체감 시점이 달라질 수 있습니다.",
                    "point_3": "지원 종료 기기는 당장 못 쓰게 되는 것이 아니라 향후 보안 패치와 앱 호환성에서 점점 불리해집니다.",
                },
            ),
            (
                ("notebooklm", "gemini", "source", "sources", "cloud computer"),
                {
                    "title_template": "NotebookLM Gemini 업그레이드, 핵심은 출처",
                    "excerpt_template": "NotebookLM의 Gemini 업그레이드를 출처 탐색, 답변 신뢰도, 클라우드 작업 환경 중심으로 정리했습니다.",
                    "summary_fallback": "NotebookLM 업데이트는 AI 노트 앱이 더 정확한 답변과 출처 탐색 기능을 제공하려는 흐름입니다.",
                    "background": "NotebookLM은 사용자가 올린 문서와 자료를 바탕으로 요약, 질문 답변, 학습 노트를 만드는 Google의 AI 노트 도구입니다. Gemini 모델 업그레이드는 답변 품질뿐 아니라 자료를 찾고 근거를 연결하는 방식에도 영향을 줍니다.",
                    "why_it_matters": "AI 노트 앱은 단순 챗봇보다 출처 신뢰도가 중요합니다. {subject}에서 Gemini 성능이 좋아져도 사용자는 답변이 어떤 문서에 근거했는지, 외부 자료를 어떻게 찾았는지, 업무 자료가 어디에 저장되는지 확인해야 합니다.",
                    "target": "학생, 연구자, 문서 기반 업무 담당자, Google Workspace 사용자",
                    "tech_context": "문서 기반 RAG, Gemini 모델, 출처 탐색, AI 노트, 클라우드 작업공간",
                    "user_impact": "자료 요약 정확도, 출처 확인 시간, 리서치 흐름, 업무 문서 처리 방식에 영향",
                    "next_check": "지원 계정, 업로드 가능 파일, 출처 표시 방식, 데이터 보관 정책, 유료 기능 여부",
                    "point_1": "NotebookLM은 웹 전체를 아무렇게나 답하는 도구가 아니라 사용자가 지정한 자료를 중심으로 답하는 것이 강점입니다.",
                    "point_2": "Gemini 업그레이드의 체감은 답변 문장보다 출처를 얼마나 잘 찾고 연결하는지에서 갈립니다.",
                    "point_3": "회사 자료를 넣을 때는 계정 종류와 데이터 사용 정책을 먼저 확인해야 합니다.",
                },
            ),
            (
                ("father", "gift", "gadget", "bluetooth", "battery", "speaker"),
                {
                    "title_template": "아버지날 기프트 가이드, 기기는 이렇게 고르기",
                    "excerpt_template": "The Verge의 Father's Day 기프트 가이드를 실사용 기준과 기기 선택 체크포인트로 정리했습니다.",
                    "summary_fallback": "기프트 가이드는 단순 추천 목록보다 받는 사람의 생활 패턴과 기기 관리 난이도를 맞추는 것이 중요합니다.",
                    "background": "기술 매체의 선물 가이드는 이어폰, 배터리, 스마트홈, 게임 기기처럼 실제 구매 후보를 묶어 보여줍니다. {subject}는 신제품 발표가 아니라 선물 상황에서 어떤 기기가 실패 확률이 낮은지 보는 글입니다.",
                    "why_it_matters": "기술 선물은 사양보다 사용 습관과 유지관리 난이도가 더 중요합니다. 좋은 제품이라도 충전 방식, 앱 연동, 계정 설정, 호환 기기가 맞지 않으면 서랍에 들어갈 수 있습니다.",
                    "target": "선물을 고르는 독자, 가젯 입문자, 가족용 IT 기기를 찾는 사용자",
                    "tech_context": "소비자 가전, 배터리·충전 규격, 앱 연동, 호환성, 선물용 기기 선택",
                    "user_impact": "구매 실패 확률을 줄이고 실제로 오래 쓰는 기기를 고르는 데 도움",
                    "next_check": "반품 기간, 충전 규격, 스마트폰 호환성, 앱 계정 필요 여부, 국내 판매 여부",
                    "point_1": "선물용 기기는 최고 사양보다 받는 사람이 혼자 설정할 수 있는지가 중요합니다.",
                    "point_2": "배터리 제품은 USB-C, Qi2, 전용 충전기 여부를 확인해야 합니다.",
                    "point_3": "해외 추천 목록은 국내 가격과 AS 조건이 달라질 수 있어 구매 전 한 번 더 확인해야 합니다.",
                },
            ),
        ]
        for keywords, angle in angles:
            if any(keyword in blob for keyword in keywords):
                return angle
        return {
            "title_template": "{subject}, 사용자가 볼 변화",
            "excerpt_template": "{subject} 소식을 제품 변화와 실제 사용자 영향 중심으로 정리했습니다.",
            "summary_fallback": "{subject}는 제품 기능, 가격, 운영 안정성 중 무엇이 달라지는지 나눠 봐야 하는 기술 이슈입니다.",
            "background": "{subject}는 제품명, 회사명, 기능 변화가 함께 묶인 기술 뉴스입니다. 먼저 이 소식이 새 기능인지, 지원 종료인지, 가격 정책인지, 서비스 운영 변화인지 구분해야 실제 영향이 보입니다.",
            "why_it_matters": "{subject} 같은 기술 뉴스는 발표 문구보다 사용자가 오늘 바꿔야 할 설정, 구매 판단, 업무 흐름 변화로 이어질 때 의미가 있습니다. 기능 이름보다 적용 대상과 제한 조건을 보는 편이 정확합니다.",
            "target": "해당 제품 사용자, 도입을 검토하는 기업, 관련 개발·운영팀",
            "tech_context": "제품 기능 변화, 서비스 안정성, 가격·구독 구조, 플랫폼 의존성",
            "user_impact": "기능 사용 가능 여부, 요금 부담, 업무 흐름, 대체 서비스 선택에 영향 가능",
            "next_check": "공식 발표, 릴리스 노트, 상태 페이지, 가격표, 후속 보도",
            "point_1": "{subject}의 핵심은 제목보다 어떤 기능·비용·운영 조건이 달라졌는지입니다.",
            "point_2": "신기능인지 장애인지 가격 변화인지에 따라 사용자가 봐야 할 기준이 달라집니다.",
            "point_3": "AI·클라우드 기능은 한 회사의 앱 안에서도 여러 외부 서비스에 의존할 수 있습니다.",
        }

    @staticmethod
    def _humanize_tech_subject(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = cleaned.replace("’", "'")
        cleaned = re.sub(r":\s*지금 확인할 포인트$", "", cleaned)
        if len(cleaned) > 46:
            cleaned = cleaned[:46].rsplit(" ", 1)[0]
        return cleaned or "이번 기술 소식"

    @staticmethod
    def _clean_summary(text: str) -> str:
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = html_unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) <= 280:
            return cleaned
        return cleaned[:280].rsplit(" ", 1)[0] + "..."

    def _living_context(self, topic: Topic, source_title: str, source_summary: str) -> dict[str, str]:
        raw_context = self._clean_living_text(f"{source_title}. {source_summary}")
        numbers = self._extract_living_numbers(raw_context)
        targets = self._extract_living_targets(raw_context, topic.keyword)
        actions = self._extract_living_actions(raw_context)
        agency = self._extract_living_agency(raw_context)
        topic_label = self._with_particle(topic.keyword, "은", "는")
        primary_number = numbers[0] if numbers else "발표문에 나온 기준"
        second_number = numbers[1] if len(numbers) > 1 else "적용 시점"
        target_text = targets[0] if targets else topic.keyword
        target_topic = self._with_particle(target_text, "과", "와")
        agency_text = agency or "운영 주체"
        rows = [
            ("핵심 대상", target_text),
            ("확인할 수치", ", ".join(numbers[:4]) if numbers else "원문에 표시된 금액, 비율, 기간"),
            ("처리 방식", ", ".join(actions[:3]) if actions else "신청·방문·자동 적용 여부를 원문에서 확인"),
            ("담당 주체", agency_text),
        ]
        if len(numbers) >= 5:
            rows.append(("추가로 볼 숫자", ", ".join(numbers[4:8])))
        table_rows = "\n".join(f"| {name} | {value} |" for name, value in rows)
        number_sentence = (
            f"이번 소식에서 먼저 볼 숫자는 {', '.join(numbers[:5])}입니다. "
            if numbers
            else "이번 소식은 숫자가 제목에 크게 드러나지 않더라도 원문 안의 기준일과 대상 조건을 함께 봐야 합니다. "
        )
        target_sentence = (
            f"대상은 '{target_text}'으로 읽히는 부분부터 확인하면 됩니다. "
            if targets
            else f"{topic_label} 누구에게 적용되는지 원문 제목과 본문 첫 문단에서 먼저 확인해야 합니다. "
        )
        action_sentence = (
            f"행동 방식은 {', '.join(actions[:3])} 쪽에 가깝습니다. "
            if actions
            else "별도 신청인지, 안내를 확인만 하면 되는지, 기관이 자동으로 적용하는지는 원문 링크에서 한 번 더 봐야 합니다. "
        )
        detail_1 = (
            f"{number_sentence}{primary_number}만 따로 보면 실제 조건을 놓칠 수 있습니다. "
            f"{second_number}처럼 함께 나온 기간·비율·단위가 무엇을 기준으로 하는지 같이 봐야 합니다."
        )
        detail_2 = (
            f"{target_sentence}{topic.keyword}처럼 생활과 연결되는 정보는 전체 국민 대상인지, 특정 세대·가구·업종·연령대 대상인지가 다르면 행동이 달라집니다."
        )
        detail_3 = (
            f"{action_sentence}특히 {agency_text}가 운영하거나 발표한 사안이라면 원문 페이지의 첨부자료, 신청 페이지, 문의처가 실제 행동 기준이 됩니다."
        )
        steps = "\n".join(
            f"{idx}. {step}"
            for idx, step in enumerate(
                self._living_steps(topic.keyword, numbers, targets, actions, agency_text),
                start=1,
            )
        )
        return {
            "lead": f"{target_topic} 직접 연결되는지 확인해야 하는 생활 정보입니다.",
            "table_rows": table_rows,
            "detail_1": detail_1,
            "detail_2": detail_2,
            "detail_3": detail_3,
            "steps": steps,
            "closing": (
                f"{topic_label} '{primary_number}' 같은 눈에 띄는 표현보다 대상과 처리 방식이 더 중요합니다. "
                f"실제 신청이나 이용 전에는 {agency_text}의 원문 안내에서 최신 기준을 확인하세요."
            ),
        }

    @staticmethod
    def _clean_living_text(text: str) -> str:
        return re.sub(r"\s+", " ", html_unescape(re.sub(r"<[^>]+>", " ", text))).strip()

    @staticmethod
    def _extract_living_numbers(text: str) -> list[str]:
        patterns = [
            r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일",
            r"\d{1,2}\s*월\s*\d{1,2}\s*일",
            r"\d{1,2}\s*월(?:부터|까지|~\d{1,2}\s*월까지)?",
            r"\d+(?:\.\d+)?\s*%",
            r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원|억원|조원)",
            r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:건|명|개|곳|세대|가구|kg|㎏|kWh|회|년)",
            r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원)?\s*[~∼-]\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:원|만원|%)",
        ]
        found: list[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.I):
                value = re.sub(r"\s+", " ", match).strip()
                if value and value not in found:
                    found.append(value)
        return found[:10]

    @staticmethod
    def _extract_living_targets(text: str, keyword: str) -> list[str]:
        candidates: list[str] = []
        target_terms = (
            "주택용", "가정", "가구", "세대", "청년", "어르신", "노인", "아동", "미성년자", "부모",
            "학생", "대학생", "직장인", "소상공인", "자영업자", "사업자", "농어민",
            "장애인", "피해자", "종사자", "이용자", "국민",
        )
        for term in target_terms:
            if term in text or term in keyword:
                candidates.append(term)
        quoted = re.findall(r"'([^']{2,30})'", text)
        for value in quoted:
            if any(term in value for term in ("서비스", "제도", "캐시백", "부트캠프", "지원", "혜택")):
                candidates.append(value)
        return list(dict.fromkeys(candidates))[:5]

    @staticmethod
    def _extract_living_actions(text: str) -> list[str]:
        action_map = {
            "신청": "신청 필요",
            "접수": "접수 일정 확인",
            "예약": "예약 필요 여부 확인",
            "방문": "방문 전 운영 확인",
            "재발급": "재발급 절차 확인",
            "캐시백": "요금 차감 또는 캐시백 기준 확인",
            "차감": "요금 차감 방식 확인",
            "지급": "지급 방식 확인",
            "신고": "신고 또는 접수 경로 확인",
            "공모": "공모 신청 일정 확인",
            "모집": "모집 대상과 마감 확인",
            "확대": "확대 적용 시점 확인",
            "폐쇄": "이용 중단 또는 대체 경로 확인",
        }
        actions = [label for marker, label in action_map.items() if marker in text]
        return list(dict.fromkeys(actions))[:5]

    @staticmethod
    def _extract_living_agency(text: str) -> str:
        agencies = re.findall(r"([가-힣A-Za-z·]{2,30}(?:부|처|청|공사|공단|위원회|진흥원|재단|센터))", text)
        blocked = {"정부", "국민", "자료", "원문", "본문", "지난해"}
        for agency in agencies:
            if agency not in blocked and not agency.endswith("정부"):
                return agency
        return ""

    @staticmethod
    def _living_steps(keyword: str, numbers: list[str], targets: list[str], actions: list[str], agency: str) -> list[str]:
        first_number = numbers[0] if numbers else "원문 기준일"
        first_target = targets[0] if targets else keyword
        first_action = actions[0] if actions else "공식 안내 확인"
        steps = [
            f"{WriterAgent._with_particle(first_target, '이', '가')} 실제 대상에 포함되는지 원문 첫 문단에서 확인합니다.",
            f"'{first_number}' 표현이 금액인지, 비율인지, 시행 기간인지 단위를 나눠 적습니다.",
            f"처리 방식은 '{first_action}' 기준으로 보고 필요한 준비물을 역으로 확인합니다.",
        ]
        if len(numbers) >= 2:
            steps.append(f"'{numbers[1]}'도 함께 표시돼 있다면 적용 기간이나 한도인지 따로 확인합니다.")
        if len(targets) >= 2:
            steps.append(f"'{targets[1]}'처럼 보조 대상이 있으면 가족·세대·계정 단위 제한을 확인합니다.")
        steps.append(f"마지막으로 {agency} 원문 링크에서 첨부자료나 문의처가 있는지 확인합니다.")
        return steps[:6]

    @staticmethod
    def _provider_order() -> list[str]:
        raw = os.getenv(
            "BLOG_LLM_PROVIDER_ORDER",
            os.getenv("REFINE_LLM_PROVIDER_ORDER", "nvidia,motif,groq,gemini,openrouter,openai,github"),
        )
        return [item.strip().lower() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _source_prompt_line(source) -> str:
        published = ""
        if source.published_at:
            published = f" (발행일: {source.published_at:%Y-%m-%d})"
        return f"- {source.title}{published}: {source.url}\n  내용: {source.summary[:400]}"

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return max(0, int(os.getenv(name, str(default))))
        except ValueError:
            return max(0, default)

    def _write_tourism_fallback(self, topic: Topic) -> Draft:
        source_lines = "\n".join(f"- [{s.title}]({s.url})" for s in topic.sources)
        tour_summaries = [s.summary for s in topic.sources if "TourAPI" in s.title]
        summary_text = "\n".join(tour_summaries)[:1200]
        topic_with_subject = self._with_particle(topic.keyword, "은", "는")
        body = f"""## 한눈에 보기

{topic_with_subject} 카페나 명소 한 곳만 찍는 글보다 실제로 어떻게 움직이면 좋은지가 더 중요합니다. 한국관광공사 TourAPI의 연관 관광지 데이터를 기준으로 보면, 먼저 대표 지점을 정하고 주변에서 함께 묶을 곳을 고르는 방식이 가장 안전합니다.

## 추천 동선

| 순서 | 볼 것 | 판단 기준 |
| --- | --- | --- |
| 1 | 대표 관광지 또는 거리 초입 | 이동 기준점으로 삼기 좋음 |
| 2 | 국문 관광정보의 주소·분류가 분명한 장소 | 지도에서 실제 이동 순서 확인 |
| 3 | 카페·식사·휴식 지점 | 오래 머물 곳은 중간에 배치 |
| 4 | 산책·야경·시장 등 마무리 지점 | 시간대와 혼잡도를 보고 조정 |

{topic.keyword}를 처음 볼 때는 지도에서 가장 유명한 지점 하나를 먼저 찍고, 그 주변의 연관 장소를 2~3개만 더하는 편이 좋습니다. 동선을 너무 길게 잡으면 이동 시간이 늘어나고, 실제로는 카페나 식사 대기 때문에 뒤 일정이 밀리기 쉽습니다.

## TourAPI에서 본 주변 포인트

{summary_text or "TourAPI 응답은 있었지만 요약 가능한 항목이 제한적입니다. 공식 데이터는 연관 장소 확인용으로만 활용하세요."}

## 이렇게 움직이면 편합니다

1. 출발지는 대중교통역이나 주차 가능한 대표 지점으로 잡습니다.
2. 첫 장소에서 바로 오래 머물기보다 주변 골목과 상권을 먼저 훑습니다.
3. 카페나 식사는 동선 중간에 넣어 체력을 아낍니다.
4. 국문 관광정보에 주소, 운영시간, 휴무, 주차가 있으면 동선표의 판단 기준으로 씁니다.
5. 영문 관광정보가 있으면 외국인 독자가 검색할 수 있는 영문 장소명이나 주소를 함께 적습니다.
6. 관광지 집중률 데이터가 있으면 혼잡 가능성을 보는 보조 지표로만 참고합니다.
7. 의료관광 정보가 포함된 경우 예약, 진료 가능 여부, 통역, 비용은 기관에 직접 확인합니다.
8. 반려동물 동반 정보가 포함된 경우 목줄·이동장, 실내외 가능 구역, 무게·견종 제한, 추가요금은 업체에 다시 확인합니다.
9. 운영시간과 팝업 여부처럼 바뀌는 정보는 방문 당일 지도 앱에서 다시 확인합니다.

## 참고한 곳

{source_lines}
"""
        return Draft(
            topic=topic,
            title=f"{topic.keyword}, 처음 가면 이 동선",
            slug=self._slug(topic.keyword),
            excerpt=f"{topic.keyword} 방문 전 TourAPI 연관 관광지 데이터를 바탕으로 동선을 잡았습니다.",
            body_markdown=body,
            tags=self._tags(topic),
        )

    @staticmethod
    def _extract(text: str, label: str, default: str) -> str:
        pattern = (
            rf"(?im)^[ \t]*(?:\*\*)?{re.escape(label)}:(?:\*\*)?[ \t]*"
            rf"(.*?)(?=^[ \t]*(?:\*\*)?(?:TITLE|EXCERPT|BODY):(?:\*\*)?[ \t]*|\Z)"
        )
        match = re.search(pattern, text, flags=re.S)
        value = match.group(1).strip() if match else default
        return re.sub(r"^\*\*|\*\*$", "", value).strip()

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
    def _has_tourapi_source(topic: Topic) -> bool:
        return any("TourAPI" in source.title for source in topic.sources)

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
