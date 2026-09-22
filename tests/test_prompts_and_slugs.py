from __future__ import annotations

import unittest

from blog_agent.prompts import classify_press_template, press_template_instruction
from blog_agent.slugs import slugify_words


class PressTemplateTest(unittest.TestCase):
    def test_mou_is_informational_even_when_body_mentions_support(self) -> None:
        kind = classify_press_template(
            "국가유산진흥원, WTC Seoul과 업무협약 체결",
            "양 기관은 국가유산 홍보와 콘텐츠 지원에 협력한다.",
        )

        self.assertEqual(kind, "informational")
        instruction = press_template_instruction(kind)
        self.assertIn("협약/행사의 목적과 의의", instruction)
        self.assertIn("지원 대상·금액·신청 방법을 만들지 않는다", instruction)

    def test_grant_is_actionable(self) -> None:
        kind = classify_press_template(
            "소상공인 경영안정 지원금 신청",
            "대상자는 온라인으로 접수하고 필수 서류를 제출한다.",
        )

        self.assertEqual(kind, "actionable")
        instruction = press_template_instruction(kind)
        self.assertIn("핵심 수혜 대상과 금액", instruction)
        self.assertIn("신청 방법과 필수 서류", instruction)

    def test_slug_truncates_only_at_word_boundary(self) -> None:
        title = "국가유산진흥원 (주)WTC Seoul 국가유산 가치 확산을 위한 업무협약 체결 (260922)"
        slug = slugify_words(title, max_length=48)

        self.assertLessEqual(len(slug), 48)
        self.assertFalse(slug.endswith("26092"))
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(slug.startswith("국가유산진흥원-주-wtc-seoul"))


if __name__ == "__main__":
    unittest.main()
