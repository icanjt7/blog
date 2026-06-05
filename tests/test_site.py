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

    def test_build_creates_press_release_navigation_and_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            (posts_dir / "press-post.md").write_text(
                """---
title: "새 보도자료"
date: "2026-06-05T00:00:00"
category: "정책"
tags:
  - "보도기사"
  - "행정안전부"
---

보도자료 본문입니다.
""",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(
                posts_dir=posts_dir,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트",
                categories=["정책"],
            )

            builder.build()

            index = (root / "public" / "index.html").read_text(encoding="utf-8")
            press_page = (root / "public" / "press-releases.html").read_text(encoding="utf-8")

        self.assertIn('href="./press-releases.html"', index)
        self.assertIn("새 보도자료", press_page)
        self.assertIn('class="active">보도자료</a>', press_page)


if __name__ == "__main__":
    unittest.main()
