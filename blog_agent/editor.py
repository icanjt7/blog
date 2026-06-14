from __future__ import annotations

import os
import re

from openai import OpenAI

from .config import Settings
from .models import Draft


PLACEHOLDER_PATTERNS = [
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
    "검색 전에 기준을 세워두면 시간을 꽤 줄일 수 있습니다",
    "가장 흔한 실수는 제목만 보고 바로 결론을 내리는 것입니다",
    "같은 표현이 반복돼도 실제 의미가 다를 수 있습니다",
    "헷갈리는 조건 3가지",
    "월드컵 일정, 명단, 공식 기록 확인용 포털",
    "대표팀, 선수, 대회, 리그 중 무엇을 보는지",
    "06월 월드컵",
    "06월 축구 대표팀",
    "원문 안내의 시행일과 적용 대상을 먼저 봅니다",
    "신청, 예약, 방문, 자동 적용 중 어떤 방식인지 구분합니다",
    "비용, 포인트, 캐시백, 준비물처럼 숫자로 확인할 항목",
    "지역이나 세대, 계정, 사용량처럼 예외 조건",
    "이용 직전에는 운영 주체의 최신 안내를 다시 확인합니다",
    "생활 정보는 '가능하다'는 말보다 '누가 어떤 조건에서 가능한가'",
    "혜택이 있는가\"와 \"내가 바로 이용할 수 있는가",
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
                    base_url="https://models.inference.ai.azure.com",
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
            if self.client is None:
                self.client = client
                self._model = model

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
- "원문 안내의 시행일과 적용 대상을 먼저 봅니다", "신청, 예약, 방문, 자동 적용 중 어떤 방식인지 구분합니다"처럼 어느 글에나 붙는 범용 체크리스트는 제거한다.
- 체크리스트와 표에는 참고 출처의 고유 숫자, 기간, 대상, 기관명, 절차를 최소 5개 이상 반영한다.
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
        text, last_error = self._complete(prompt, temperature=0.7, max_tokens=2048)
        if not text:
            suffix = f": {type(last_error).__name__}" if last_error else ""
            reviewed.review_notes.append(f"LLM 편집 실패로 규칙 기반 검수만 적용{suffix}")
            return reviewed
        reviewed.title = self._extract(text, "TITLE", reviewed.title)
        reviewed.excerpt = self._extract(text, "EXCERPT", reviewed.excerpt)
        reviewed.body_markdown = self._extract(text, "BODY", reviewed.body_markdown).strip()
        reviewed = self.review(reviewed)
        reviewed.review_notes.append("LLM 편집 보완 완료")
        if self._needs_second_pass(reviewed):
            repaired = self._second_pass(reviewed, sources)
            if repaired:
                return repaired
        return reviewed

    def _complete(self, prompt: str, *, temperature: float, max_tokens: int) -> tuple[str, Exception | None]:
        last_error: Exception | None = None
        for client, model in self._providers:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = response.choices[0].message.content or ""
                if text.strip():
                    return text, None
            except Exception as exc:
                last_error = exc
                continue
        return "", last_error

    def _needs_second_pass(self, draft: Draft) -> bool:
        threshold = self._env_float("BLOG_EDITOR_REWRITE_THRESHOLD", 90.0)
        if draft.quality_score >= threshold:
            return False
        severe_markers = (
            "일반 fallback 템플릿",
            "범용",
            "구체성이 부족",
            "본문 길이가 짧",
            "기술 글이",
            "원문 제목의 핵심 대상",
        )
        return any(any(marker in note for marker in severe_markers) for note in draft.review_notes)

    def _second_pass(self, draft: Draft, sources: str) -> Draft | None:
        prompt = f"""
아래 글은 1차 편집 후 검수에서 아직 품질 기준을 통과하지 못했습니다.
검수 메모를 모두 해결하도록 제목, 요약, 본문을 다시 작성하세요.

절대 조건:
- 출처에 없는 사실, 수치, 경험담은 만들지 않는다.
- 본문은 1,300자 이상, ## 헤딩 5개 이상, 표 1개 이상으로 작성한다.
- 검수 메모에 나온 범용 문장과 AI식 반복 표현은 제거한다.
- 출처의 고유명사, 수치, 기간, 기관명, 절차를 본문과 표에 반영한다.
- 제목은 30자 이내 한국어로, 원문 핵심 대상을 드러낸다.

검수 메모:
{chr(10).join(draft.review_notes) if draft.review_notes else "품질 점수가 낮음"}

참고 출처:
{sources}

현재 제목:
{draft.title}

현재 요약:
{draft.excerpt}

현재 본문:
{draft.body_markdown}

응답 형식:
TITLE:
EXCERPT:
BODY:
"""
        text, last_error = self._complete(prompt, temperature=0.55, max_tokens=2600)
        if not text:
            suffix = f": {type(last_error).__name__}" if last_error else ""
            draft.review_notes.append(f"LLM 2차 보완 실패{suffix}")
            return None
        candidate = draft.model_copy(deep=True)
        candidate.title = self._extract(text, "TITLE", candidate.title)
        candidate.excerpt = self._extract(text, "EXCERPT", candidate.excerpt)
        candidate.body_markdown = self._extract(text, "BODY", candidate.body_markdown).strip()
        candidate = self.review(candidate)
        candidate.review_notes.append("LLM 2차 검수 보완 완료")
        return candidate

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
        keyword_covered_by_tokens = self._keyword_tokens_covered(
            draft.topic.keyword,
            draft.title + "\n" + draft.body_markdown,
        )
        if keyword_count < 2:
            if not keyword_covered_by_tokens:
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
    def _keyword_tokens_covered(keyword: str, text: str) -> bool:
        tokens = [
            token
            for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", keyword.lower())
            if token not in {"관련", "핵심", "정리"}
        ]
        if len(tokens) < 2:
            return False
        lowered = text.lower()
        hits = sum(1 for token in tokens if token in lowered)
        return hits >= min(len(tokens), 3)

    @staticmethod
    def _extract(text: str, label: str, default: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z]+:|\Z)"
        match = re.search(pattern, text, flags=re.S)
        return match.group(1).strip() if match else default

    @staticmethod
    def _provider_order() -> list[str]:
        raw = os.getenv(
            "BLOG_LLM_PROVIDER_ORDER",
            os.getenv("REFINE_LLM_PROVIDER_ORDER", "motif,groq,gemini,openrouter,openai,github"),
        )
        return [item.strip().lower() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return max(0, int(os.getenv(name, str(default))))
        except ValueError:
            return max(0, default)

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return max(0.0, float(os.getenv(name, str(default))))
        except ValueError:
            return max(0.0, default)
