from __future__ import annotations

import unittest

from scripts.import_press_releases import PressRelease, make_article_body, slugify


class PressReleaseTemplateTest(unittest.TestCase):
    def test_mou_fallback_uses_informational_headings(self) -> None:
        release = PressRelease(
            institution="국가유산진흥원",
            title="국가유산진흥원, WTC Seoul과 국가유산 홍보 업무협약 체결(260922)",
            date="2026-09-22",
            url="https://example.com/mou",
            body_text=(
                "국가유산진흥원과 WTC Seoul은 국가유산 가치 확산을 위한 업무협약을 체결했다. "
                "코엑스 전광판을 활용한 공동 홍보와 전통공연, 전승공예품 전시에 협력한다. "
                "양 기관은 향후 기념일 연계 행사를 추진할 예정이다."
            ),
        )

        body = make_article_body(release)

        self.assertIn("**[목적·의의]**", body)
        self.assertIn("**[주요 협력·행사 내용]**", body)
        self.assertIn("**[향후 계획]**", body)
        self.assertIn("코엑스", body)
        self.assertNotIn("**[핵심 수혜 대상·금액]**", body)
        self.assertNotIn("신청 전에 준비할 서류", body)

    def test_support_fallback_uses_actionable_headings(self) -> None:
        release = PressRelease(
            institution="중소벤처기업부",
            title="소상공인 경영안정 지원금 신청 접수",
            date="2026-09-22",
            url="https://example.com/support",
            body_text=(
                "중소벤처기업부는 소상공인을 대상으로 경영안정 지원금 신청을 받는다. "
                "신청자는 온라인 접수 기간에 사업자등록증 등 필수 서류를 제출해야 한다."
            ),
        )

        body = make_article_body(release)

        self.assertIn("**[핵심 수혜 대상·금액]**", body)
        self.assertIn("**[주요 지원 내용]**", body)
        self.assertIn("**[신청 방법·필수 서류]**", body)
        self.assertIn("소상공인 경영안정 지원금 신청 접수 FAQ", body)

    def test_press_slug_keeps_complete_date_token(self) -> None:
        slug = slugify("국가유산진흥원 (주)WTC Seoul 국가유산 가치 확산을 위한 업무협약 체결 (260922)")

        self.assertTrue(slug.endswith("260922"))
        self.assertNotIn("26092-", slug)


if __name__ == "__main__":
    unittest.main()
