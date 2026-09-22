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

        self.assertIn("**[참여 기관]**", body)
        self.assertIn("**[협약·행사 목적]**", body)
        self.assertIn("**[주요 협력·기대 효과]**", body)
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

        self.assertIn("**[지원 대상]**", body)
        self.assertIn("**[핵심 혜택·금액]**", body)
        self.assertIn("**[신청 방법·기한]**", body)
        self.assertIn("소상공인 경영안정 지원금 신청 접수 FAQ", body)

    def test_design_winner_fallback_uses_announcement_schema(self) -> None:
        release = PressRelease(
            institution="국가유산청",
            title="후백제역사문화센터 건립 설계공모 당선작 선정",
            date="2026-09-22",
            url="https://example.com/winner",
            body_text=(
                "국립완주문화유산연구소는 설계공모에서 '역사의 틈, 자연 사잇공간'을 최종 당선작으로 선정했다. "
                "전주시 완산구 교동 일원에 대지면적 19,903㎡, 연면적 약 5,005㎡ 규모로 조성된다. "
                "심사위원회는 주변 주거지와의 조화, 효율적인 동선, 높은 시공성을 평가했다."
            ),
        )

        body = make_article_body(release)

        self.assertIn("**[당선작·핵심 결과]**", body)
        self.assertIn("**[사업 규모·위치]**", body)
        self.assertIn("**[심사 평가·설계 콘셉트]**", body)
        self.assertIn("최종 선정 결과와 심사 평가", body)
        self.assertNotIn("신청 전에 준비할 서류", body)
        self.assertNotIn("공식 원문 확인", body)

    def test_press_slug_keeps_complete_date_token(self) -> None:
        slug = slugify("국가유산진흥원 (주)WTC Seoul 국가유산 가치 확산을 위한 업무협약 체결 (260922)")

        self.assertTrue(slug.endswith("260922"))
        self.assertNotIn("26092-", slug)


if __name__ == "__main__":
    unittest.main()
