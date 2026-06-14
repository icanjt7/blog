from __future__ import annotations

import unittest

from blog_agent.config import Settings
from blog_agent.editor import SeoEditorAgent
from blog_agent.models import Draft, Topic


class SeoEditorAgentTest(unittest.TestCase):
    def test_low_specificity_review_requires_second_pass(self) -> None:
        editor = SeoEditorAgent(Settings(enable_llm_edit=False))
        draft = Draft(
            topic=Topic(keyword="AI 뉴스", title_hint="AI 뉴스", category="기술"),
            title="AI 뉴스 핵심 정리",
            slug="ai-news",
            excerpt="AI 뉴스 요약",
            body_markdown=(
                "제품명, 회사명, 기능 변화가 함께 묶인 기술 뉴스입니다.\n\n"
                "## 이번 글에서 봐야 할 내용\n\n"
                "해당 제품 사용자, 도입을 검토하는 기업, 비용 구조를 확인합니다."
            ),
            tags=["기술"],
        )

        reviewed = editor.review(draft)

        self.assertLess(reviewed.quality_score, 90)
        self.assertTrue(editor._needs_second_pass(reviewed))


if __name__ == "__main__":
    unittest.main()
