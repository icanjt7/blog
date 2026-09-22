from __future__ import annotations

import json
import unittest

from blog_agent.prompts import (
    classify_press_template,
    parse_press_json,
    press_json_system_prompt,
    press_template_instruction,
    render_press_json,
)
from blog_agent.slugs import slugify_words


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
            "sections": [
                {"heading": "선정 결과", "body_markdown": "당선작 설명"},
                {"heading": "사업 규모", "body_markdown": "시설 설명"},
                {"heading": "추진 계획", "body_markdown": "후속 절차"},
            ],
        }

        self.assertIsNone(parse_press_json(json.dumps(payload, ensure_ascii=False), "ANNOUNCEMENT"))
        self.assertIn('"post_type"', press_json_system_prompt())

        payload["summary_box"][2] = {"label": "심사 평가", "value": "효율적인 동선과 높은 시공성을 평가"}
        parsed = parse_press_json(json.dumps(payload, ensure_ascii=False), "ANNOUNCEMENT")
        self.assertIsNotNone(parsed)
        self.assertIn("## 선정 결과", render_press_json(parsed))

    def test_slug_truncates_only_at_word_boundary(self) -> None:
        title = "국가유산진흥원 (주)WTC Seoul 국가유산 가치 확산을 위한 업무협약 체결 (260922)"
        slug = slugify_words(title, max_length=48)

        self.assertLessEqual(len(slug), 48)
        self.assertFalse(slug.endswith("26092"))
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(slug.startswith("국가유산진흥원-주-wtc-seoul"))


if __name__ == "__main__":
    unittest.main()
