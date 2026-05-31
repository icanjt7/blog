from __future__ import annotations

import re

from openai import OpenAI

from .config import Settings
from .models import Draft


AI_CLICHES = [
    "이번 포스팅에서는",
    "알아보겠습니다",
    "결론적으로",
    "매우 중요합니다",
    "다양한",
]


class SeoEditorAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings and settings.openai_api_key and settings.enable_llm_edit
            else None
        )

    def improve(self, draft: Draft) -> Draft:
        if not self.client:
            return self.review(draft)
        reviewed = self.review(draft)
        sources = "\n".join(
            f"- {source.title}: {source.url} ({source.summary[:180]})"
            for source in reviewed.topic.sources
        )
        prompt = f"""
아래 한국어 블로그 초안을 편집해 주세요.

목표:
- 사실은 유지하고, 출처에 없는 구체 수치나 경험담은 추가하지 않는다.
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
        response = self.client.responses.create(
            model=self.settings.openai_model if self.settings else "gpt-4.1-mini",
            input=prompt,
        )
        text = response.output_text
        reviewed.title = self._extract(text, "TITLE", reviewed.title)
        reviewed.excerpt = self._extract(text, "EXCERPT", reviewed.excerpt)
        reviewed.body_markdown = self._extract(text, "BODY", reviewed.body_markdown).strip()
        reviewed.review_notes.append("LLM 편집 보완 완료")
        return self.review(reviewed)

    def review(self, draft: Draft) -> Draft:
        notes: list[str] = []
        score = 100.0
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
        if draft.topic.category == "local" and re.search(r"다녀왔|방문했|먹어봤", draft.body_markdown):
            score -= 30
            notes.append("직접 방문한 것처럼 보이는 표현이 있습니다.")
        draft.quality_score = max(0, score)
        draft.review_notes = notes
        return draft

    @staticmethod
    def _extract(text: str, label: str, default: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z]+:|\Z)"
        match = re.search(pattern, text, flags=re.S)
        return match.group(1).strip() if match else default
