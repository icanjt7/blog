from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blog_agent.site import StaticSiteBuilder


class StaticSiteBuilderTest(unittest.TestCase):
    def test_frontmatter_split_ignores_markdown_rule_inside_quoted_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            post_path = root / "posts" / "table-title.md"
            post_path.parent.mkdir()
            post_path.write_text(
                """---
title: '제목에 표가 포함됨 | 항목 | 값 | |------|------|'
date: '2026-06-05T00:00:00'
category: 기술
tags:
- 기술
---

## 본문

정상적으로 읽혀야 합니다.
""",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(
                posts_dir=post_path.parent,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트",
            )

            post = builder._parse_post(post_path)

        self.assertEqual(post.title, "제목에 표가 포함됨 | 항목 | 값 | |------|------|")
        self.assertIn("정상적으로 읽혀야 합니다.", post.body_html)

    def test_build_writes_optimized_rss_feeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            for idx in range(2):
                (posts_dir / f"post-{idx}.md").write_text(
                    f"""---
title: 'RSS 테스트 {idx}'
date: '2026-06-0{idx + 1}T09:30:00'
category: 기술
tags:
- RSS
- 테스트
cover_image: 'https://example.com/image-{idx}.jpg'
cover_image_alt: '테스트 이미지 {idx}'
---

## 본문

RSS 본문 {idx}입니다.
""",
                    encoding="utf-8",
                )
            builder = StaticSiteBuilder(
                posts_dir=posts_dir,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트 설명",
                custom_domain="example.com",
            )

            builder.build()

            feed = root / "public" / "feed.xml"
            rss = root / "public" / "rss.xml"
            self.assertTrue(feed.exists())
            self.assertTrue(rss.exists())
            for path in (feed, rss):
                tree = ET.parse(path)
                root_el = tree.getroot()
                self.assertEqual(root_el.tag, "rss")
                text = path.read_text(encoding="utf-8")
                self.assertIn("xmlns:atom", text)
                self.assertIn("xmlns:content", text)
                self.assertIn("xmlns:media", text)
                self.assertIn("<media:thumbnail", text)
                self.assertIn("<content:encoded><![CDATA[", text)
                self.assertIn("<dc:creator>", text)
                self.assertEqual(text.count("<item>"), 2)
            self.assertIn('href="https://example.com/feed.xml"', feed.read_text(encoding="utf-8"))
            self.assertIn('href="https://example.com/rss.xml"', rss.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
