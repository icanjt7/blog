from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from blog_agent.prompts import parse_press_json, press_json_system_prompt
from blog_agent.quality_filters import InvalidContentData, evaluate_source_content, require_source_content
from blog_agent.site import StaticSiteBuilder
from blog_agent.slugs import UnsafeSlugError, build_seo_slug
from blog_agent.writer import WriterAgent


class JunkContentGuardTest(unittest.TestCase):
    def test_monthly_attachment_shell_is_rejected_and_logged(self) -> None:
        title = "09월 탄소중립"
        body = "<p>탄소중립 월간 소식지가 발간되었습니다.</p><a href='file.pdf'>첨부파일</a>"

        decision = evaluate_source_content(title, body)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "Skip: Insufficient body length (월간 동향)")
        with self.assertLogs("junk-test", level="WARNING") as captured:
            import logging
            with self.assertRaises(InvalidContentData):
                require_source_content(title, body, logger=logging.getLogger("junk-test"))
        self.assertIn("Skip: Insufficient body length (월간 동향)", captured.output[0])

    def test_invalid_data_contract_is_accepted_as_skip_signal(self) -> None:
        payload = parse_press_json('{"post_type":"INVALID_DATA","reason":"구체적 원문 부족"}')
        self.assertEqual(payload["post_type"], "INVALID_DATA")
        self.assertIn("'post_type'을 'INVALID_DATA'", press_json_system_prompt())

    def test_slug_has_no_opaque_hash_and_short_title_uses_integer_fallback(self) -> None:
        slug = WriterAgent._slug("09월 탄소중립", "환경")
        self.assertTrue(slug.startswith("september-carbon-neutral-"))
        self.assertIsNone(re.search(r"-[0-9a-f]{8}$", slug))
        self.assertEqual(build_seo_slug("공지", category="정책", source_id=102), "policy-issue-102")
        with self.assertRaises(UnsafeSlugError):
            build_seo_slug("공지")

    def test_ssg_does_not_create_html_for_injected_legacy_junk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts = root / "posts"
            public = root / "public"
            posts.mkdir()
            junk = posts / "09월-탄소중립-3542f3be.md"
            junk.write_text(
                """---
title: 09월 탄소중립, 동선부터 잡는 법
date: 2026-09-23
category: 환경
---

월별 반복 검색 수요가 있는 evergreen 키워드 공식 포털

## 원문에서 확인할 내용

공식 포털 원문에서 확인할 내용입니다.
""",
                encoding="utf-8",
            )

            builder = StaticSiteBuilder(posts, public, "브리핑웨이브", "설명", "briefwave.kr")
            builder.build()

            self.assertFalse((public / "09월-탄소중립-3542f3be.html").exists())
            self.assertNotIn("09월 탄소중립", (public / "search.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
