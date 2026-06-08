from __future__ import annotations

import unittest

from blog_agent.config import Settings
from blog_agent.models import Source, Topic
from blog_agent.writer import WriterAgent


class WriterAgentTest(unittest.TestCase):
    def test_extract_accepts_markdown_bold_labels(self) -> None:
        response = """**TITLE:**
Steam Machine, 여름 구매 전 5가지

**EXCERPT:**
구매 전에 볼 내용을 정리했습니다.

**BODY:**
## 실제 사용감

| 항목 | 장점 | 단점 |
|------|------|------|
| 설정 | 간단함 | 확인 필요 |
"""

        self.assertEqual(
            WriterAgent._extract(response, "TITLE", "기본 제목"),
            "Steam Machine, 여름 구매 전 5가지",
        )
        self.assertEqual(
            WriterAgent._extract(response, "EXCERPT", "기본 요약"),
            "구매 전에 볼 내용을 정리했습니다.",
        )
        self.assertTrue(
            WriterAgent._extract(response, "BODY", "기본 본문").startswith("## 실제 사용감")
        )

    def test_tech_fallback_uses_article_context(self) -> None:
        topic = Topic(
            keyword="Notion restores access",
            title_hint="Notion restores access to Anthropic after service disruption",
            category="기술",
            sources=[
                Source(
                    title="Notion restores access to Anthropic after service disruption",
                    url="https://techcrunch.com/example",
                    summary=(
                        "Notion disabled Anthropic models after degraded performance caused "
                        "failures for Notion AI users, then restored access roughly 12 hours later."
                    ),
                )
            ],
        )
        draft = WriterAgent(Settings())._write_fallback(topic)

        self.assertIn("Notion AI", draft.body_markdown)
        self.assertIn("Claude", draft.body_markdown)
        self.assertIn("외부 LLM API", draft.body_markdown)
        self.assertNotIn("데이터센터, 클라우드, AI 서비스는 모두 전력과 냉각", draft.body_markdown)

    def test_tech_fallback_explains_space_garment(self) -> None:
        topic = Topic(
            keyword="NASA will wear",
            title_hint="NASA will wear high-tech Prada long johns to the Moon",
            category="기술",
            sources=[
                Source(
                    title="NASA will wear high-tech Prada long johns to the Moon",
                    url="https://www.theverge.com/example",
                    summary="Axiom Space and Prada revealed the LCVG layer for the AxEMU spacesuit.",
                )
            ],
        )
        draft = WriterAgent(Settings())._write_fallback(topic)

        self.assertIn("Liquid Cooling and Ventilation Garment", draft.body_markdown)
        self.assertIn("우주복", draft.body_markdown)
        self.assertIn("냉각·환기", draft.body_markdown)


if __name__ == "__main__":
    unittest.main()
