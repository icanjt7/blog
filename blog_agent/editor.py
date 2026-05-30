from __future__ import annotations

import re

from .models import Draft


AI_CLICHES = [
    "이번 포스팅에서는",
    "알아보겠습니다",
    "결론적으로",
    "매우 중요합니다",
    "다양한",
]


class SeoEditorAgent:
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
