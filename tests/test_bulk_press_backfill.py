from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bulk_press_backfill as backfill
from bulk_press_backfill import append_drop_log, existing_source_urls, iter_jsonl_chunks, verify
from blog_agent.quality_filters import evaluate_source_content
from blog_agent.site import Post, StaticSiteBuilder
from blog_agent.slugs import build_seo_slug


class BulkPressBackfillTest(unittest.TestCase):
    def test_thin_source_is_logged_before_any_llm_call(self) -> None:
        record = {
            "institution": "테스트기관",
            "title": "09월 재난안전 월간",
            "date": "2026-09-25",
            "url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=12345",
            "body_text": "본문" * 50,
        }
        with patch.object(backfill.press, "generate_article_from_source") as llm_call:
            generated, reason = backfill._articleize_record(record)
        self.assertIsNone(generated)
        self.assertIn("Insufficient body length", reason)
        llm_call.assert_not_called()

        with tempfile.TemporaryDirectory() as tmp:
            drop_log = Path(tmp) / "drop_logs.txt"
            append_drop_log(drop_log, "12345", record["title"], reason)
            line = drop_log.read_text(encoding="utf-8")
        self.assertIn("12345\t09월 재난안전 월간\tLength < 500", line)

    def test_long_source_passes_pre_llm_filter(self) -> None:
        body = "<p>" + ("검증된 정책 본문입니다. " * 80) + "</p>"
        decision = evaluate_source_content("청년 지원 정책", body)
        self.assertTrue(decision.accepted)
        self.assertGreaterEqual(len(decision.raw_text), 500)

        record = {
            "agency_code": "test",
            "agency_section": "policy",
            "institution": "테스트기관",
            "title": "청년 지원 정책",
            "date": "2026-09-25",
            "url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=67890",
            "body_text": body,
        }
        article = "## 청년 지원 정책의 구체적 대상\n\n검증된 기사 본문입니다."
        with (
            patch.object(backfill, "_WORKER_WRITER", object()),
            patch.object(backfill.press, "generate_article_from_source", return_value=article) as llm_call,
            patch.object(backfill.press, "article_is_specific", return_value=True),
        ):
            generated, reason = backfill._articleize_record(record)
        self.assertEqual(reason, "")
        self.assertIsNotNone(generated)
        self.assertTrue(generated["article_ready"])
        llm_call.assert_called_once()

    def test_jsonl_is_streamed_in_requested_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jsonl"
            source.write_text(
                "".join(json.dumps({"id": value}) + "\n" for value in range(5)),
                encoding="utf-8",
            )
            chunks = list(iter_jsonl_chunks(source, 2))
            self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])

    def test_existing_source_url_frontmatter_is_a_deduplication_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp)
            (posts / "post.md").write_text(
                "---\nsource_url: \"https://www.korea.kr/briefing/pressReleaseView.do?newsId=1&amp;pageIndex=3\"\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(
                existing_source_urls(posts),
                {"https://www.korea.kr/briefing/pressReleaseView.do?newsId=1"},
            )

    def test_agency_keyword_date_slug_is_english_and_hash_free(self) -> None:
        slug = build_seo_slug(
            "청년 창업 지원사업 모집",
            agency="중소벤처기업부",
            source_id=102,
            published_date="2026-09-25",
        )
        self.assertEqual(
            slug,
            "sme-startup-ministry-youth-startup-support-recruitment-2026-09-25-102",
        )
        self.assertNotRegex(slug, r"-[0-9a-f]{8}$")

    def test_sitemap_is_split_and_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BLOG_SITEMAP_CHUNK_SIZE": "1"}):
            root = Path(tmp)
            posts = root / "posts"
            posts.mkdir()
            for index in range(3):
                (posts / f"policy-item-{index}.md").write_text(
                    f"---\ntitle: 정책 {index}\ndate: 2026-09-25\ncategory: 정책\n---\n\n## 정책 {index} 대상은 누구인가요?\n\n본문입니다.\n",
                    encoding="utf-8",
                )
            public = root / "public"
            StaticSiteBuilder(posts, public, "브리핑웨이브", "설명", "briefwave.kr").build()
            sitemap_index = (public / "sitemap-index.xml").read_text(encoding="utf-8")
            self.assertTrue((public / "sitemap-post-2.xml").exists())
            self.assertTrue((public / "sitemap-post-3.xml").exists())
            self.assertIn("sitemap-post-2.xml", sitemap_index)
            self.assertIn("sitemap-post-3.xml", sitemap_index)

    def test_2500_posts_create_three_well_formed_sitemaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / "public"
            public.mkdir()
            builder = StaticSiteBuilder(Path(tmp) / "posts", public, "브리핑웨이브", "설명", "briefwave.kr")
            posts = [
                Post(
                    title=f"정책 자료 {index}",
                    date=datetime(2026, 9, 25),
                    category="정책",
                    tags=["정책"],
                    slug=f"policy-item-{index}",
                    excerpt="정책 설명",
                    body_html="<p>본문</p>",
                )
                for index in range(2500)
            ]

            builder._write_sitemap(posts, posts)

            namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            expected_counts = (1000, 1000, 500)
            for index, expected in enumerate(expected_counts, 1):
                path = public / f"sitemap-post-{index}.xml"
                self.assertTrue(path.exists())
                root = ET.parse(path).getroot()
                self.assertEqual(len(root.findall("sm:url", namespace)), expected)
            sitemap_index = ET.parse(public / "sitemap-index.xml").getroot()
            locations = [item.text or "" for item in sitemap_index.findall("sm:sitemap/sm:loc", namespace)]
            post_locations = [location for location in locations if "sitemap-post-" in location]
            self.assertEqual(len(post_locations), 3)
            self.assertTrue(all(f"sitemap-post-{index}.xml" in post_locations[index - 1] for index in range(1, 4)))

    def test_canary_qa_requires_dynamic_headings_and_toss_widget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts = root / "posts"
            public = root / "public"
            posts.mkdir()
            public.mkdir()
            (posts / "labor-ministry-youth-jobs-2026-09-25-102.md").write_text(
                """---
title: 청년 일자리 사업
post_type: "ACTIONABLE"
---

> **[지원 대상]** 취업 준비 중인 만 19세 이상 청년
>
> **[핵심 혜택·금액]** 직무교육비와 취업 상담 지원
>
> **[신청 방법·기한]** 10월 20일까지 온라인 신청

## 청년 일자리 사업은 누가 신청할 수 있나요?

본문

## 직무교육비는 얼마나 지원되나요?

본문

## 10월 20일까지 어떤 서류를 제출하나요?

본문

## 청년 일자리 사업 신청자가 자주 묻는 질문은 무엇인가요?

본문
""",
                encoding="utf-8",
            )
            (public / "labor-ministry-youth-jobs-2026-09-25-102.html").write_text(
                '<aside class="toss-shopping-card product-recommendation">오늘 한정 특가 및 실구매자 후기 보기</aside>',
                encoding="utf-8",
            )
            result = verify(argparse.Namespace(posts_dir=posts, public_dir=public, expected=1, report=None))
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
