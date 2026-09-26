from __future__ import annotations

import re
import importlib.util
import tempfile
import unittest
from pathlib import Path

from blog_agent.prompts import parse_press_json, press_json_system_prompt
from blog_agent.quality_filters import (
    InvalidContentData,
    evaluate_source_content,
    is_legacy_junk_post,
    is_safe_legacy_garbage_slug,
    require_source_content,
    should_drop_post,
)
from blog_agent.site import StaticSiteBuilder
from blog_agent.slugs import UnsafeSlugError, build_seo_slug
from blog_agent.writer import WriterAgent


_CLEANUP_SPEC = importlib.util.spec_from_file_location(
    "cleanup_safe", Path(__file__).resolve().parents[1] / "cleanup_safe.py"
)
assert _CLEANUP_SPEC and _CLEANUP_SPEC.loader
_CLEANUP_MODULE = importlib.util.module_from_spec(_CLEANUP_SPEC)
_CLEANUP_SPEC.loader.exec_module(_CLEANUP_MODULE)
cleanup_build = _CLEANUP_MODULE.cleanup_build
is_safe_garbage_candidate = _CLEANUP_MODULE.is_safe_garbage_candidate


class JunkContentGuardTest(unittest.TestCase):
    def test_safe_cleanup_requires_all_three_conditions(self) -> None:
        self.assertTrue(is_safe_garbage_candidate(Path("07월-신청방법-f2149aa3.html")))
        self.assertTrue(is_safe_garbage_candidate(Path("9월-결과발표-a1b2c3d4.html")))
        self.assertFalse(is_safe_garbage_candidate(Path("ftc-guidelines-f2149aa3.html")))
        self.assertFalse(
            is_safe_garbage_candidate(
                Path("미-연방거래위원회-ftc-seeks-public-comment-c0516c46.html")
            )
        )
        self.assertFalse(
            is_safe_garbage_candidate(Path("07월-신청방법-상세-자격-서류-f2149aa3.html"))
        )
        self.assertFalse(is_safe_garbage_candidate(Path("07월-신청방법.html")))
        self.assertTrue(is_safe_legacy_garbage_slug("07월-ai-b73636a4"))
        self.assertFalse(
            is_safe_legacy_garbage_slug(
                "미-연방거래위원회-ftc-seeks-public-comment-c0516c46"
            )
        )

    def test_cleanup_is_dry_run_by_default_and_deletes_only_safe_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            junk = root / "07월-신청방법-f2149aa3.html"
            protected = root / "미-연방거래위원회-ftc-seeks-public-comment-c0516c46.html"
            junk.write_text("junk", encoding="utf-8")
            protected.write_text("article", encoding="utf-8")

            self.assertEqual(cleanup_build(root), [junk.resolve()])
            self.assertTrue(junk.exists())
            self.assertEqual(cleanup_build(root, execute=True), [junk.resolve()])
            self.assertFalse(junk.exists())
            self.assertTrue(protected.exists())

    def test_new_admin_shell_keywords_are_rejected(self) -> None:
        for keyword in ("신청방법", "모집안내", "결과발표"):
            dropped, reason = should_drop_post(
                {
                    "title": f"07월 {keyword}",
                    "slug": f"07월-{keyword}-f2149aa3",
                    "body": "구체적인 사실이 부족한 안내입니다. " * 15,
                }
            )
            self.assertTrue(dropped)
            self.assertIn("단답형 스팸 제목", reason)

    def test_structured_drop_rule_rejects_thin_monthly_and_unsafe_slug_records(self) -> None:
        good_post = {
            "title": "문화체육관광부 2026년 하반기 문화예술 지원 정책 안내",
            "slug": "culture-ministry-culture-2026-09-25-156783181",
            "body": "<p>문화예술 지원 대상과 신청 절차를 구체적으로 안내합니다.</p>" * 20,
        }
        thin_monthly = {
            "title": "07월 생활비",
            "slug": "07월-생활비-f8224f14",
            "body": "<p>첨부파일을 확인하세요.</p>",
        }
        generated_shell = {
            "title": "07월 제철음식, 꼭 챙겨야 할 5가지 정보",
            "slug": "07월-제철음식-facfb66b",
            "body": "<p>공식 포털에서 대상과 기간을 확인하세요.</p>" * 40,
        }

        self.assertEqual(should_drop_post(good_post), (False, "Pass: 정상적인 고품질 데이터"))
        dropped, thin_reason = should_drop_post(thin_monthly)
        self.assertTrue(dropped)
        self.assertIn("본문 텍스트 부족", thin_reason)
        dropped, slug_reason = should_drop_post(generated_shell)
        self.assertTrue(dropped)
        self.assertIn("비정상 헥사 해시값", slug_reason)

    def test_legacy_hash_guard_is_scoped_to_monthly_shell_titles(self) -> None:
        filler = "구체적인 정책 사실과 일정이 포함된 충분한 본문입니다. " * 40
        self.assertTrue(
            is_legacy_junk_post(
                "07월 생활비, 달라진 지원 조건 한눈에 확인",
                "07월-생활비-f8224f14",
                filler,
            )
        )
        self.assertFalse(
            is_legacy_junk_post(
                "주민자치회 활성화를 위한 워크숍 개최",
                "mois-행정안전부-주민자치회-활성화-0cefae3f",
                filler,
            )
        )

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
