from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
