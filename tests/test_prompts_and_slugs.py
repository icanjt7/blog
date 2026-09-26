from __future__ import annotations

import json
import unittest

import markdown

from blog_agent.prompts import (
    classify_press_template,
    parse_press_json,
    press_json_system_prompt,
    press_localization_instruction,
    press_template_instruction,
    render_press_json,
)
from blog_agent.slugs import build_seo_slug, ensure_clean_slug, romanize_korean, slugify_words


class PressTemplateTest(unittest.TestCase):
    def test_mou_is_informational_even_when_body_mentions_support(self) -> None:
        kind = classify_press_template(
            "국가유산진흥원, WTC Seoul과 업무협약 체결",
            "양 기관은 국가유산 홍보와 콘텐츠 지원에 협력한다.",
        )

        self.assertEqual(kind, "INFORMATIONAL")
        instruction = press_template_instruction(kind)
        self.assertIn("[참여 기관]", instruction)
        self.assertIn("[협약·행사 목적]", instruction)
        self.assertIn("H1 바로 아래", instruction)

    def test_grant_is_actionable(self) -> None:
        kind = classify_press_template(
            "소상공인 경영안정 지원금 신청",
            "대상자는 온라인으로 접수하고 필수 서류를 제출한다.",
        )

        self.assertEqual(kind, "ACTIONABLE")
        instruction = press_template_instruction(kind)
        self.assertIn("[지원 대상]", instruction)
        self.assertIn("[신청 방법·기한]", instruction)

    def test_design_competition_winner_is_announcement_not_actionable(self) -> None:
        kind = classify_press_template(
            "후백제역사문화센터 건립 설계공모 당선작 선정",
            "15개 팀의 작품을 심사해 최종 당선작 1건을 결정했다.",
        )

        self.assertEqual(kind, "ANNOUNCEMENT")
        instruction = press_template_instruction(kind)
        self.assertIn("[당선작·핵심 결과]", instruction)
        self.assertIn("[사업 규모·위치]", instruction)

    def test_json_contract_rejects_placeholder_values(self) -> None:
        payload = {
            "post_type": "ANNOUNCEMENT",
            "title": "후백제역사문화센터 당선작",
            "excerpt": "설계공모 결과입니다.",
            "lead": "국가유산청이 당선작을 발표했습니다.",
            "summary_box": [
                {"label": "당선작", "value": "역사의 틈, 자연 사잇공간"},
                {"label": "사업 규모", "value": "연면적 약 5,005㎡"},
                {"label": "완공 일정", "value": "미정"},
            ],
            "key_facts": [
                "설계공모 당선작 1건을 선정",
                "연면적 약 5,005㎡",
                "국가유산청이 결과를 발표",
            ],
            "sections": [
                {"heading": "선정 결과", "body_markdown": "당선작 설명"},
                {"heading": "사업 규모", "body_markdown": "시설 설명"},
                {"heading": "추진 계획", "body_markdown": "후속 절차"},
            ],
        }

        self.assertIsNone(parse_press_json(json.dumps(payload, ensure_ascii=False), "ANNOUNCEMENT"))
        self.assertIn('"post_type"', press_json_system_prompt())
        self.assertIn("종합해 보면", press_json_system_prompt())
        self.assertIn("H1 바로 아래", press_json_system_prompt())

        payload["summary_box"][2] = {"label": "심사 평가", "value": "효율적인 동선과 높은 시공성을 평가"}
        parsed = parse_press_json(json.dumps(payload, ensure_ascii=False), "ANNOUNCEMENT")
        self.assertIsNotNone(parsed)
        self.assertIn("## 선정 결과", render_press_json(parsed))
        self.assertIn("## 핵심 팩트 (Key Facts)", render_press_json(parsed))
        self.assertIn("- 연면적 약 5,005㎡", render_press_json(parsed))
        rendered = render_press_json(parsed)
        self.assertLess(rendered.index("> **[당선작]**"), rendered.index("국가유산청이 당선작을 발표했습니다."))

    def test_foreign_ftc_policy_renders_local_impact_glossary_and_takeaways(self) -> None:
        payload = {
            "post_type": "INFORMATIONAL",
            "source_scope": "FOREIGN",
            "title": "FTC 디지털 구독 규칙 변화",
            "excerpt": "FTC가 디지털 구독 서비스의 해지 절차와 소비자 고지를 다루는 규칙 제정 절차를 공개했습니다.",
            "lead": "미국 연방거래위원회(FTC)가 디지털 구독 서비스의 해지 절차와 소비자 고지 기준을 다루는 자료를 발표했습니다.",
            "summary_box": [
                {"label": "발표 기관", "value": "미국 연방거래위원회(FTC)"},
                {"label": "정책 대상", "value": "디지털 구독 서비스의 해지 절차와 소비자 고지"},
                {"label": "자료 성격", "value": "규칙 제정 절차 안내"},
            ],
            "key_facts": [
                "발표 기관은 미국 연방거래위원회(FTC)",
                "검토 대상은 디지털 구독 서비스의 해지 절차",
                "소비자 고지 기준이 주요 쟁점",
            ],
            "local_impact": "미국 시장에 디지털 구독 서비스를 제공하는 한국 기업은 해지 화면과 고지 절차를 다시 점검해야 할 가능성이 있습니다. 국내 소비자 정책에도 유사한 논의가 확산되는지 확인할 필요가 있습니다.",
            "glossary": [
                {"term": "FTC", "explanation": "미국의 소비자 보호와 경쟁 정책을 담당하는 연방거래위원회"},
                {"term": "Rulemaking", "explanation": "행정기관이 의견 수렴 등을 거쳐 구속력 있는 규칙을 만드는 절차"},
            ],
            "sections": [
                {"heading": "FTC가 검토하는 구독 해지 기준은 무엇인가요?", "body_markdown": "FTC 자료는 가입과 해지 과정에서 소비자가 받는 고지와 선택 절차를 다룹니다."},
                {"heading": "미국 사업자에게 요구될 수 있는 변화는 무엇인가요?", "body_markdown": "구체적인 의무와 시행 시점은 최종 규칙과 후속 발표를 확인해야 합니다."},
                {"heading": "한국 기업은 어떤 후속 발표를 확인해야 하나요?", "body_markdown": "미국 고객을 대상으로 운영하는 서비스라면 적용 범위와 최종 문구를 확인해야 합니다."},
            ],
            "takeaways": [
                "미국 고객 대상 구독 서비스의 해지 동선을 점검합니다.",
                "최종 규칙의 적용 대상과 시행일을 공식 발표에서 확인합니다.",
                "국내 소비자 보호 제도의 후속 논의를 함께 추적합니다.",
            ],
        }

        parsed = parse_press_json(json.dumps(payload, ensure_ascii=False), "INFORMATIONAL")
        self.assertIsNotNone(parsed)
        rendered = render_press_json(parsed or {})
        self.assertEqual(rendered.count("## 에디터의 시사점 (Key Takeaways)"), 1)
        self.assertLess(rendered.index("## 핵심 내용과 국내 파급력"), rendered.index("## 핵심 팩트 (Key Facts)"))
        self.assertIn("> 💡 **핵심 용어: FTC**", rendered)
        self.assertTrue(rendered.endswith("- 국내 소비자 보호 제도의 후속 논의를 함께 추적합니다."))

        html = markdown.markdown(rendered, extensions=["tables", "fenced_code", "toc"])
        self.assertRegex(html, r'<h2[^>]*>핵심 내용과 국내 파급력</h2>')
        self.assertIn("<blockquote>", html)
        self.assertIn("<strong>핵심 용어: FTC</strong>", html)
        self.assertRegex(html, r'<h2[^>]*>에디터의 시사점 \(Key Takeaways\)</h2>')
        self.assertIn("<ul>", html)
        self.assertIn("<li>미국 고객 대상 구독 서비스의 해지 동선을 점검합니다.</li>", html)

        instruction = press_localization_instruction("INFORMATIONAL")
        self.assertIn("핵심 내용과 국내 파급력", instruction)
        self.assertIn("합리적 추론", instruction)
        self.assertIn("정확히 '## 에디터의 시사점 (Key Takeaways)'", instruction)

    def test_slug_truncates_only_at_word_boundary(self) -> None:
        title = "국가유산진흥원 (주)WTC Seoul 국가유산 가치 확산을 위한 업무협약 체결 (260922)"
        slug = slugify_words(title, max_length=48)

        self.assertLessEqual(len(slug), 48)
        self.assertFalse(slug.endswith("26092"))
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(slug.startswith("국가유산진흥원-주-wtc-seoul"))

    def test_press_seo_slug_uses_agency_keyword_and_integer_id(self) -> None:
        slug = build_seo_slug(
            "탄소중립 월간 동향",
            category="환경",
            agency="me",
            source_id="https://example.go.kr/view?id=102",
        )
        self.assertEqual(slug, "me-carbon-neutral-monthly-trends-102")

    def test_future_korean_titles_use_clean_romanized_slugs(self) -> None:
        slug = build_seo_slug(
            "강릉시장 당선인 공약",
            category="정치",
            published_date="2026-09-26",
        )
        self.assertEqual(slug, "politics-gangreungsijang-dangseonin-gongyak-2026-09-26")
        self.assertNotRegex(slug, r"[가-힣]")
        self.assertNotRegex(slug, r"-[0-9a-f]{8}$")
        self.assertEqual(ensure_clean_slug(slug), slug)
        self.assertEqual(romanize_korean("나라장터 입찰공고"), "narajangteo-ipchalgonggo")

    def test_long_slug_keeps_date_and_integer_identifier(self) -> None:
        slug = build_seo_slug(
            "청년 창업 지원사업 모집 " * 12,
            category="정책",
            agency="중소벤처기업부",
            source_id=156783181,
            published_date="2026-09-26",
            max_length=80,
        )
        self.assertLessEqual(len(slug), 80)
        self.assertTrue(slug.endswith("-2026-09-26-156783181"))
        self.assertNotRegex(slug, r"[가-힣]")


if __name__ == "__main__":
    unittest.main()
