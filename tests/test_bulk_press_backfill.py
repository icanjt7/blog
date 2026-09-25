from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bulk_press_backfill import existing_source_urls, iter_jsonl_chunks, verify
from blog_agent.site import StaticSiteBuilder
from blog_agent.slugs import build_seo_slug


class BulkPressBackfillTest(unittest.TestCase):
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
            self.assertTrue((public / "sitemap-2.xml").exists())
            self.assertTrue((public / "sitemap-3.xml").exists())
            self.assertIn("sitemap-2.xml", sitemap_index)
            self.assertIn("sitemap-3.xml", sitemap_index)

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
