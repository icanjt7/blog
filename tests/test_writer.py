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

    def test_living_fallback_uses_source_specific_details(self) -> None:
        topic = Topic(
            keyword="에너지캐시백 전기 혜택",
            title_hint="전기 1%만 덜 써도 혜택",
            category="생활",
            sources=[
                Source(
                    title="전기 1%만 덜 써도 혜택…올 하반기 에너지캐시백 확대 시행",
                    url="https://www.korea.kr/news/example",
                    summary=(
                        "주택용 에너지캐시백 제도가 7월부터 12월까지 확대 시행된다. "
                        "기존에는 전기 사용량을 3% 이상 줄여야 했지만, 올 하반기에는 "
                        "1% 이상으로 완화된다. 절감률 구간에 따라 1kWh당 20~30원의 "
                        "추가 지원금을 더해 최대 120원까지 캐시백을 받을 수 있다. "
                        "기후에너지환경부는 국민의 자발적인 에너지 절약 참여를 유도한다고 밝혔다."
                    ),
                )
            ],
        )

        draft = WriterAgent(Settings())._write_fallback(topic)

        self.assertIn("1%", draft.body_markdown)
        self.assertIn("3%", draft.body_markdown)
        self.assertIn("120원", draft.body_markdown)
        self.assertIn("주택용", draft.body_markdown)
        self.assertIn("기후에너지환경부", draft.body_markdown)
        self.assertNotIn("원문 안내의 시행일과 적용 대상을 먼저 봅니다", draft.body_markdown)
        self.assertNotIn("신청, 예약, 방문, 자동 적용 중 어떤 방식인지 구분합니다", draft.body_markdown)

    def test_living_fallback_handles_non_benefit_public_notice(self) -> None:
        topic = Topic(
            keyword="노인학대 신고의무자 보호",
            title_hint="노인학대 신고의무자 확대",
            category="생활",
            sources=[
                Source(
                    title="'노인학대' 작년보다 16.8% 증가…신고의무자 확대",
                    url="https://www.korea.kr/news/example2",
                    summary=(
                        "지난해 노인학대 신고는 2만 6578건으로 전년 대비 16.8% 증가했다. "
                        "노인학대로 판정된 건수는 7973건으로 전년보다 11.2% 늘었다. "
                        "보건복지부는 신고 활성화와 재학대 예방, 피해 노인 보호를 강화할 계획이다."
                    ),
                )
            ],
        )

        draft = WriterAgent(Settings())._write_fallback(topic)

        self.assertIn("2만 6578건", draft.body_markdown)
        self.assertIn("7973건", draft.body_markdown)
        self.assertIn("보건복지부", draft.body_markdown)
        self.assertIn("신고", draft.body_markdown)
        self.assertNotIn("비용, 포인트, 캐시백, 준비물처럼 숫자로 확인할 항목", draft.body_markdown)


if __name__ == "__main__":
    unittest.main()
