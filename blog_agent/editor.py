from __future__ import annotations

import re

from openai import OpenAI

from .config import Settings
from .models import Draft


PLACEHOLDER_PATTERNS = [
    r"[가-힣]+\d+",          # 영화1, 감독1, 인물1 등
    r"\[[가-힣a-zA-Z]+명?\]", # [감독명], [영화명], [이름], [회사명]
    r"XXX|OOO|___",
    r"제목\s*[:：]\s*미정",
    r"(감독|배우|주연|감독명)\s*[:：]\s*(미정|미상|불명)",
    r"(영화|작품|도서)\s*\d+\b",  # 영화 1, 작품 2
]

AI_CLICHES = [
    "이번 포스팅에서는",
    "알아보겠습니다",
    "결론적으로",
    "매우 중요합니다",
    "다양한",
    "함께 알아보",
    "살펴보겠습니다",
    "정리해 보겠습니다",
    "소개해 드리겠습니다",
    "어떠셨나요",
    "도움이 되셨으면",
    "궁금하셨던",
    "지금 바로",
    "놓치지 마세요",
]

GENERIC_FALLBACK_PATTERNS = [
    "최근 검색 수요가 꾸준히 생기는 주제입니다",
    "공개된 자료를 기준으로 핵심만 정리한 정보성 콘텐츠입니다",
    "조건, 비용, 일정, 공식 안내 변경 여부",
    "지역명, 연도, 모델명 같은 보조 키워드",
    "공식 자료 중심으로 간단히 정리했습니다",
    "지금 확인할 포인트",
    "여러 출처의 공통 내용을 먼저 봅니다",
    "제품명, 회사명, 기능 변화가 함께 묶인 기술 뉴스입니다",
    "발표 문구보다 사용자가 오늘 바꿔야 할 설정",
    "신기능인지 장애인지 가격 변화인지",
    "AI·클라우드 기능은 한 회사의 앱 안에서도",
]


class SeoEditorAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self.client: OpenAI | None = None
        self._model: str = ""
        self._providers: list[tuple[OpenAI, str]] = []
        if settings and settings.enable_llm_edit:
            self._init_client(settings)

    def _init_client(self, s: Settings) -> None:
        timeout = s.llm_timeout_seconds
        def add(client: OpenAI, model: str) -> None:
            self._providers.append((client, model))
            if self.client is None:
                self.client = client
                self._model = model

        if s.motif_api_key:
            add(
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
                OpenAI(
                    api_key=s.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.groq_model,
            )
        if s.gemini_api_key:
            add(
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
                OpenAI(
                    api_key=s.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.openrouter_model,
            )
        if s.openai_api_key:
            add(OpenAI(api_key=s.openai_api_key, timeout=timeout, max_retries=0), s.openai_model)
        if s.github_token:
            add(
                OpenAI(
                    api_key=s.github_token,
                    base_url="https://models.inference.ai.azure.com",
                    timeout=timeout,
                    max_retries=0,
                ),
                s.github_model,
            )

    def improve(self, draft: Draft) -> Draft:
        if not self._providers:
            return self.review(draft)
        reviewed = self.review(draft)
        sources = "\n".join(
            f"- {source.title}: {source.url} ({source.summary[:180]})"
            for source in reviewed.topic.sources
        )
        prompt = f"""
아래 한국어 블로그 초안을 편집해 주세요.

목표:
- 제목이 클릭하고 싶어지는지 먼저 확인한다. 아래 기준으로 더 좋은 제목으로 바꿔도 된다:
  · 숫자, 반전, 궁금증, 독자 공감 상황, 구체적 혜택 중 하나를 활용
  · '핵심 정리', '알아보자', '총정리' 같은 진부한 표현은 교체
  · 30자 이내
- 사실은 유지하고, 출처에 없는 구체 수치나 경험담은 추가하지 않는다.
- 글에 등장하는 인물·작품·기업·제도 중 설명이 부족한 것이 있으면 한 줄씩 보완한다.
- AI가 쓴 것처럼 보이는 반복 표현을 줄인다.
- 문단을 짧게 나누고, 표/체크리스트의 가독성을 높인다.
- 핵심 키워드 "{reviewed.topic.keyword}"는 자연스럽게 유지하되 과하게 반복하지 않는다.
- 지역/맛집 글이라도 직접 방문한 척하지 않는다.
- 제목, 2문장 요약, Markdown 본문을 반환한다.

현재 검수 메모:
{chr(10).join(reviewed.review_notes) if reviewed.review_notes else "특이사항 없음"}

참고 출처:
{sources}

초안 제목:
{reviewed.title}

초안 요약:
{reviewed.excerpt}

초안 본문:
{reviewed.body_markdown}

응답 형식:
TITLE:
EXCERPT:
BODY:
"""
        text = ""
        last_error: Exception | None = None
        for client, model in self._providers:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=2048,
                )
                text = response.choices[0].message.content or ""
                break
            except Exception as exc:
                last_error = exc
                continue
        if not text:
            suffix = f": {type(last_error).__name__}" if last_error else ""
            reviewed.review_notes.append(f"LLM 편집 실패로 규칙 기반 검수만 적용{suffix}")
            return reviewed
        reviewed.title = self._extract(text, "TITLE", reviewed.title)
        reviewed.excerpt = self._extract(text, "EXCERPT", reviewed.excerpt)
        reviewed.body_markdown = self._extract(text, "BODY", reviewed.body_markdown).strip()
        reviewed.review_notes.append("LLM 편집 보완 완료")
        return self.review(reviewed)

    BLAND_TITLE_PATTERNS = [
        "핵심 정리",
        "알아보자",
        "총정리",
        "완벽 정리",
        "알아보겠",
        "정리해",
        "소개합니다",
        "지금 확인할 포인트",
        "무엇이 바뀌나",
        "사용자가 볼 변화",
    ]

    @staticmethod
    def has_placeholders(text: str) -> bool:
        return any(re.search(p, text) for p in PLACEHOLDER_PATTERNS)

    def review(self, draft: Draft) -> Draft:
        notes: list[str] = []
        score = 100.0
        combined = draft.title + "\n" + draft.body_markdown
        if self.has_placeholders(combined):
            score -= 60
            notes.append("플레이스홀더 감지: 실제 데이터 없이 가짜 내용이 포함돼 있습니다.")
        for pattern in self.BLAND_TITLE_PATTERNS:
            if pattern in draft.title:
                score -= 8
                notes.append(f"제목이 클릭을 유도하지 않습니다: '{pattern}' 포함")
                break
        keyword_count = draft.body_markdown.count(draft.topic.keyword)
        if keyword_count < 2:
            score -= 12
            notes.append("핵심 키워드 노출이 적습니다.")
        if keyword_count > 8:
            score -= 15
            notes.append("핵심 키워드 반복이 과합니다.")
        if len(draft.body_markdown) < 800:
            score -= 15
            notes.append("본문 길이가 짧습니다.")
        if not re.search(r"\|.+\|", draft.body_markdown):
            score -= 6
            notes.append("표가 없어 스캔성이 약합니다.")
        for cliche in AI_CLICHES:
            if cliche in draft.body_markdown:
                score -= 4
                notes.append(f"AI 문체로 보일 수 있는 표현: {cliche}")
        generic_hits = [pattern for pattern in GENERIC_FALLBACK_PATTERNS if pattern in combined]
        if generic_hits:
            score -= 45
            notes.append("일반 fallback 템플릿 문장이 남아 있어 주제별 구체성이 부족합니다.")
        if draft.topic.category == "핫이슈" and re.search(r"다녀왔|방문했|먹어봤", draft.body_markdown):
            score -= 30
            notes.append("직접 방문한 것처럼 보이는 표현이 있습니다.")
        if draft.topic.category == "핫이슈" and re.search(r"여행|코스|카페|맛집|해수욕장|동선", draft.topic.keyword):
            has_tourapi = any("TourAPI" in source.title for source in draft.topic.sources)
            has_specific_place = re.search(r"주변 포인트|추천 동선|해수욕장|동백섬|시장|카페|관광지", draft.body_markdown)
            if not has_tourapi and not has_specific_place:
                score -= 35
                notes.append("여행 글인데 관광 API나 구체 장소 동선이 부족합니다.")
        if draft.topic.category == "기술":
            if self._looks_like_raw_english_title(draft.title):
                score -= 45
                notes.append("영문 원문 제목이 한국어 기사 제목으로 재해석되지 않았습니다.")
            title_words = [word for word in re.split(r"\W+", draft.topic.title_hint) if len(word) >= 5]
            if title_words and not any(word in draft.body_markdown for word in title_words[:5]):
                score -= 25
                notes.append("기술 글이 원문 제목의 핵심 대상을 충분히 설명하지 않습니다.")
            if re.search(r"최근 검색 수요가 꾸준히|공식 안내와 최신 공지|지역명, 연도, 모델명", draft.body_markdown):
                score -= 35
                notes.append("기술 글이 범용 확인 템플릿에 머물러 기사별 차이가 부족합니다.")
            if re.search(r"제품명, 회사명, 기능 변화|이번 글에서 봐야 할 내용|해당 제품 사용자, 도입을 검토하는 기업", draft.body_markdown):
                score -= 45
                notes.append("기술 글이 범용 기술 뉴스 템플릿에 머물러 기사별 차이가 부족합니다.")
            if self._has_low_information_tech_body(draft.body_markdown):
                score -= 30
                notes.append("기술 글의 고유명사·수치·구체 행동 정보가 부족합니다.")
            source_blob = " ".join(
                f"{source.title} {source.summary}" for source in draft.topic.sources
            ).lower()
            draft_blob = f"{draft.title}\n{draft.body_markdown}".lower()
            if "rivian" in source_blob and re.search(r"\b(carvana|slate auto)\b", draft_blob):
                score -= 70
                notes.append("기술 글의 원문은 Rivian인데 Carvana/Slate Auto 내용이 섞였습니다.")
            if "apple" in source_blob and "privacy" in source_blob and re.search(
                r"보안 사고|침해사고|해커|노출 데이터|비밀번호.*재설정",
                draft.body_markdown,
            ):
                score -= 45
                notes.append("Apple AI 개인정보 이슈를 해킹/침해사고 템플릿으로 잘못 해석했습니다.")
            if re.search(r"will live or die by its|is too much fun to let", draft.title, flags=re.I):
                score -= 20
                notes.append("영문 원문 제목이 잘린 채 제목에 남아 있습니다.")
        draft.quality_score = max(0, score)
        draft.review_notes = notes
        return draft

    @staticmethod
    def _looks_like_raw_english_title(title: str) -> bool:
        tokens = re.findall(r"[A-Za-z]{2,}", title)
        if len(tokens) >= 4:
            return True
        return bool(re.search(r"\b(is|are|was|were|to|for|with|ordered|built|disabling|host)\b", title, flags=re.I))

    @staticmethod
    def _has_low_information_tech_body(body: str) -> bool:
        headings = len(re.findall(r"^##\s+", body, flags=re.M))
        numbers = len(re.findall(r"\d", body))
        english_entities = len(set(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", body)))
        if len(body) < 1300:
            return True
        return headings < 5 or (numbers < 2 and english_entities < 4)

    @staticmethod
    def _extract(text: str, label: str, default: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z]+:|\Z)"
        match = re.search(pattern, text, flags=re.S)
        return match.group(1).strip() if match else default
