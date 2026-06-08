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
        if topic.category == "기술" and topic.sources:
            return self._write_tech_news_fallback(topic)
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

## 핵심 정리

| 항목 | 이번 글에서 봐야 할 내용 |
| --- | --- |
| 직접 대상 | {context["target"]} |
| 기술 맥락 | {context["tech_context"]} |
| 사용자 영향 | {context["user_impact"]} |
| 다음 확인 | {context["next_check"]} |

## 독자가 이해해야 할 포인트

1. {context["point_1"]}
2. {context["point_2"]}
3. {context["point_3"]}
4. 원문 요약만으로 부족하면 회사 공지, 상태 페이지, 후속 보도까지 같이 확인하는 편이 안전합니다.

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
                ("carvana", "slate", "auto", "car", "vehicle", "ev"),
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
        ]
        for keywords, angle in angles:
            if any(keyword in blob for keyword in keywords):
                return angle
        return {
            "title_template": "{subject}, 사용자가 볼 변화",
            "excerpt_template": "{subject} 소식을 제품 변화와 실제 사용자 영향 중심으로 정리했습니다.",
            "summary_fallback": "{subject}는 제품 기능, 가격, 운영 안정성 중 무엇이 달라지는지 나눠 봐야 하는 기술 이슈입니다.",
            "background": "해외 기술 뉴스 제목은 회사명, 제품명, 별칭만 짧게 드러나는 경우가 많습니다. {subject}도 먼저 어떤 회사와 제품의 이야기인지, 변화가 기능 추가인지 가격 변화인지 장애 대응인지 구분해야 합니다.",
            "why_it_matters": "기술 이슈는 발표 문구보다 사용자 경험과 비용 구조로 이어질 때 중요해집니다. {subject}를 볼 때도 실제 사용자가 해야 할 행동, 기업이 부담할 운영 비용, 대체 서비스 가능성을 함께 확인해야 합니다.",
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
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) <= 280:
            return cleaned
        return cleaned[:280].rsplit(" ", 1)[0] + "..."

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
