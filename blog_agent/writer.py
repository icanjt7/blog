from __future__ import annotations

import hashlib
import re
from datetime import datetime

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
        self._init_client()

    def _init_client(self) -> None:
        s = self.settings
        if s.groq_api_key:
            self._client = OpenAI(
                api_key=s.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=45,
                max_retries=1,
            )
            self._model = s.groq_model
        elif s.gemini_api_key:
            self._client = OpenAI(
                api_key=s.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=45,
                max_retries=1,
            )
            self._model = s.gemini_model
        elif s.openrouter_api_key:
            self._client = OpenAI(
                api_key=s.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=60,
                max_retries=1,
            )
            self._model = s.openrouter_model
        elif s.openai_api_key:
            self._client = OpenAI(api_key=s.openai_api_key, timeout=45, max_retries=1)
            self._model = s.openai_model
        elif s.github_token:
            self._client = OpenAI(
                api_key=s.github_token,
                base_url="https://models.inference.ai.azure.com",
                timeout=45,
                max_retries=1,
            )
            self._model = s.github_model

    def write(self, topic: Topic) -> Draft:
        if self._client:
            try:
                return self._write_with_llm(topic)
            except Exception:
                return self._write_fallback(topic)
        return self._write_fallback(topic)

    def _write_with_llm(self, topic: Topic) -> Draft:
        sources = "\n".join(
            f"- {source.title}: {source.url}\n  내용: {source.summary[:400]}"
            for source in topic.sources
        )
        tourism_instruction = ""
        if self._has_tourapi_source(topic):
            tourism_instruction = f"""
[TourAPI 관광 글 작성 지침]
- 참고 출처에 한국관광공사 TourAPI 데이터가 있으면 본문에 반드시 반영한다.
- 연관 관광지 정보는 '함께 묶을 곳', '동선 순서', '주변에서 볼 것'으로 풀어 쓴다.
- 관광지 집중률 정보는 혼잡 가능성을 보는 보조 지표로만 설명하고, 실제 방문자 수처럼 단정하지 않는다.
- 의료관광 정보는 주소, 문의, 운영정보, 주차, 예약 전 확인할 점 중심으로 안내한다.
- 치료 효과, 안전성, 가격, 진료 가능 여부는 출처에 있어도 단정하지 말고 기관 확인이 필요하다고 쓴다.
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
- 도입부: {hook_style}
- 문장 길이를 의도적으로 섞는다. 짧은 문장(5~10자)과 긴 문장(40~60자)을 번갈아 쓴다.
- '이번 포스팅에서는', '알아보겠습니다', '결론적으로', '매우 중요합니다', '다양한' 금지.
- 직접 경험하지 않은 일을 경험한 것처럼 쓰지 않는다.
- 출처에 없는 구체 수치는 추가하지 않는다.
- 핵심 키워드 "{topic.keyword}"는 4~7회만 자연스럽게 쓴다.
- 본문 1,400~1,800자. 표 1개 이상 포함.
- 마지막 문단은 독자에게 하나의 행동 권고나 확인 경로로 마무리.
{tourism_instruction}

[맥락 심화 — 반드시 포함]
글에 등장하는 인물·작품·기업·제도가 있다면 독자가 처음 듣는 사람이라고 가정하고 아래를 설명한다:
- 인물: 이름 + 어떤 사람인지(직업·경력·배경) + 왜 지금 주목받는지
- 작품(영화·책·앱 등): 장르·줄거리 한 줄 + 주요 관계자(감독·저자 등)
- 기업/브랜드: 어떤 회사인지 + 이번 소식과의 연결점
- 제도/정책: 대상이 누구인지 + 이전과 무엇이 달라졌는지
독자가 "그게 뭐야?"라고 물을 만한 모든 용어에 한 줄 설명을 붙인다.

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
        response = self._client.chat.completions.create(
            model=self._model,
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
            title=f"{topic.keyword}: 지금 확인할 포인트",
            slug=self._slug(topic.keyword),
            excerpt=f"{topic.keyword} 관련 정보를 공식 자료 중심으로 간단히 정리했습니다.",
            body_markdown=body,
            tags=self._tags(topic),
        )

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
| 2 | 연관 관광지·골목·상권 | TourAPI에서 함께 언급되는 주변 지점 확인 |
| 3 | 카페·식사·휴식 지점 | 오래 머물 곳은 중간에 배치 |
| 4 | 산책·야경·시장 등 마무리 지점 | 시간대와 혼잡도를 보고 조정 |

{topic.keyword}를 처음 볼 때는 지도에서 가장 유명한 지점 하나를 먼저 찍고, 그 주변의 연관 장소를 2~3개만 더하는 편이 좋습니다. 동선을 너무 길게 잡으면 이동 시간이 늘어나고, 실제로는 카페나 식사 대기 때문에 뒤 일정이 밀리기 쉽습니다.

## TourAPI에서 본 주변 포인트

{summary_text or "TourAPI 응답은 있었지만 요약 가능한 항목이 제한적입니다. 공식 데이터는 연관 장소 확인용으로만 활용하세요."}

## 이렇게 움직이면 편합니다

1. 출발지는 대중교통역이나 주차 가능한 대표 지점으로 잡습니다.
2. 첫 장소에서 바로 오래 머물기보다 주변 골목과 상권을 먼저 훑습니다.
3. 카페나 식사는 동선 중간에 넣어 체력을 아낍니다.
4. 관광지 집중률 데이터가 있으면 혼잡 가능성을 보는 보조 지표로만 참고합니다.
5. 의료관광 정보가 포함된 경우 예약, 진료 가능 여부, 통역, 비용은 기관에 직접 확인합니다.
6. 운영시간과 팝업 여부처럼 바뀌는 정보는 방문 당일 지도 앱에서 다시 확인합니다.

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
