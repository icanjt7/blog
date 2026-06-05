from __future__ import annotations

import tempfile
import unittest
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

if __name__ == "__main__":
    unittest.main()
