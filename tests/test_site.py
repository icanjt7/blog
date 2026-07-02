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

    def test_parse_post_unwraps_body_wrapped_in_markdown_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            post_path = root / "posts" / "wrapped.md"
            post_path.parent.mkdir()
            post_path.write_text(
                """---
title: '김구 탄생 150주년 공식 로고'
date: '2026-06-28T23:22:13'
category: 생활
tags:
- 생활
---

![대표 이미지](https://example.com/cover.jpg)

```markdown
## 공식 로고 사용 기준

| 항목 | 내용 |
| --- | --- |
| 대상 | 공공 목적 |

본문이 코드블록이 아니라 일반 본문으로 보여야 합니다.
```
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

        self.assertIn("<h2", post.body_html)
        self.assertIn("<table>", post.body_html)
        self.assertIn("공식 로고 사용 기준", post.excerpt)
        self.assertNotIn("<pre>", post.body_html)
        self.assertNotIn("language-markdown", post.body_html)

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
                self.assertIn("<width>144</width>", text)
                self.assertIn("<height>144</height>", text)
            self.assertIn('href="https://example.com/feed.xml"', feed.read_text(encoding="utf-8"))
            self.assertIn('href="https://example.com/rss.xml"', rss.read_text(encoding="utf-8"))

    def test_build_uses_consistent_canonical_and_indexing_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            for idx in range(10):
                (posts_dir / f"한글-글-{idx}.md").write_text(
                    f"""---
title: '색인 테스트 {idx}'
date: '2026-06-{idx + 1:02d}T09:30:00'
category: 기술
tags:
- 테스트
quality_score: 95.0
---

## 본문

""" + " ".join(["색인 규칙과 독자 탐색 기준을 검증하는 충분한 본문입니다."] * 80) + """
""",
                    encoding="utf-8",
                )
            builder = StaticSiteBuilder(
                posts_dir=posts_dir,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트 설명",
                custom_domain="example.com",
                categories=["기술"],
            )

            builder.build()

            first_post = (root / "public" / "한글-글-0.html").read_text(encoding="utf-8")
            self.assertIn("<title>색인 테스트 0 - 테스트</title>", first_post)
            self.assertIn(
                '<link rel="canonical" href="https://example.com/%ED%95%9C%EA%B8%80-%EA%B8%80-0.html">',
                first_post,
            )
            self.assertNotIn('href="./index.html"', first_post)
            self.assertIn(
                '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
                first_post,
            )
            self.assertIn('<nav class="breadcrumb" aria-label="탐색 경로">', first_post)
            self.assertIn('"@type": "BreadcrumbList"', first_post)
            self.assertIn('"item": "https://example.com/category-%EA%B8%B0%EC%88%A0.html"', first_post)

            page_two = (root / "public" / "page2.html").read_text(encoding="utf-8")
            category_two = (root / "public" / "category-기술-2.html").read_text(encoding="utf-8")
            search = (root / "public" / "search.html").read_text(encoding="utf-8")
            self.assertIn('<meta name="robots" content="noindex,follow">', page_two)
            self.assertIn('<meta name="robots" content="noindex,follow">', category_two)
            self.assertIn('<meta name="robots" content="noindex,follow">', search)

            static_sitemap = (root / "public" / "sitemap-static.xml").read_text(encoding="utf-8")
            post_sitemap = (root / "public" / "sitemap-posts-priority.xml").read_text(encoding="utf-8")
            robots = (root / "public" / "robots.txt").read_text(encoding="utf-8")
            self.assertNotIn("search.html", static_sitemap)
            self.assertNotIn("page2.html", static_sitemap)
            self.assertNotIn("category-%EA%B8%B0%EC%88%A0-2.html", static_sitemap)
            self.assertIn("category-%EA%B8%B0%EC%88%A0.html", static_sitemap)
            self.assertIn("%ED%95%9C%EA%B8%80-%EA%B8%80-0.html", post_sitemap)
            self.assertIn("Allow: /", robots)
            self.assertIn("Sitemap: https://example.com/sitemap-static.xml", robots)

    def test_build_adds_adsense_quality_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            (posts_dir / "source-post.md").write_text(
                """---
title: '출처 글'
date: '2026-06-01T09:30:00'
category: 기술
tags:
- 기술
quality_score: 95.0
---

## 핵심

공식 발표를 독자 관점으로 풀어 쓴 본문입니다.

## 판단 기준

""" + " ".join(["지원 조건과 실제 이용 절차를 독자가 직접 확인할 수 있게 설명합니다."] * 70) + """

## 참고한 곳

- [공식 원문](https://example.com/source)
""",
                encoding="utf-8",
            )
            (posts_dir / "related-post.md").write_text(
                """---
title: '관련 글'
date: '2026-06-02T09:30:00'
category: 기술
tags:
- 기술
quality_score: 95.0
---

## 본문

""" + " ".join(["관련 글입니다."] * 180) + """
""",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(
                posts_dir=posts_dir,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트 설명",
                custom_domain="example.com",
                categories=["기술"],
            )

            builder.build()

            html = (root / "public" / "source-post.html").read_text(encoding="utf-8")
            self.assertNotIn("읽는 기준", html)
            self.assertIn("맥락 짚기", html)
            self.assertIn("지원 기기", html)
            self.assertIn("참고 자료", html)
            self.assertIn("공식 원문", html)
            self.assertIn("Google Search Central", html)
            self.assertIn("편집 기준", html)
            self.assertIn("함께 보면 좋은 글", html)
            self.assertIn("관련 글", html)
            self.assertIn('aria-label="광고 영역"', html)
            self.assertIn('<div class="ad-label">광고</div>', html)
            self.assertLess(html.index('<div class="content">'), html.index('<div class="ad-slot"'))

            for filename in ("about.html", "editorial-policy.html", "privacy.html", "contact.html"):
                self.assertTrue((root / "public" / filename).exists())
            footer_html = (root / "public" / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="./privacy.html"', footer_html)
            self.assertIn('class="footer-category-links"', footer_html)
            self.assertIn('href="./category-기술.html"', footer_html)
            contact_html = (root / "public" / "contact.html").read_text(encoding="utf-8")
            self.assertIn('href="mailto:jungteck@gmail.com"', contact_html)
            self.assertIn(">jungteck@gmail.com<", contact_html)
            self.assertNotIn("icanjt7@gmail.com", contact_html)
            privacy_html = (root / "public" / "privacy.html").read_text(encoding="utf-8")
            self.assertIn("Google 광고 설정", privacy_html)
            editorial_html = (root / "public" / "editorial-policy.html").read_text(encoding="utf-8")
            self.assertIn("광고와 편집 분리", editorial_html)
            sitemap = (root / "public" / "sitemap-static.xml").read_text(encoding="utf-8")
            self.assertIn("privacy.html", sitemap)

    def test_adsense_review_mode_limits_low_value_auto_posts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            rich_body = " ".join(["실제 선택 기준과 확인 절차를 설명합니다."] * 80)
            (posts_dir / "useful-guide.md").write_text(
                f"""---
title: '실제로 확인할 수 있는 생활 가이드'
date: '2026-06-03T09:30:00'
category: 생활
tags:
- 생활
quality_score: 95.0
---

## 판단 기준

{rich_body}
""",
                encoding="utf-8",
            )
            (posts_dir / "krgov-auto-summary.md").write_text(
                """---
title: '자동 보도자료 요약'
date: '2026-06-04T09:30:00'
category: 정책
tags:
- 보도자료
quality_score: 96.0
---

## 요약

정부 발표를 짧게 옮긴 글입니다.
""",
                encoding="utf-8",
            )
            (posts_dir / "thin-guide.md").write_text(
                """---
title: '짧은 안내'
date: '2026-06-05T09:30:00'
category: 생활
tags:
- 생활
quality_score: 95.0
---

## 안내

아직 내용이 충분하지 않습니다.
""",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(
                posts_dir=posts_dir,
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트 설명",
                custom_domain="example.com",
                categories=["생활", "정책"],
            )

            builder.build()

            index_html = (root / "public" / "index.html").read_text(encoding="utf-8")
            search_json = (root / "public" / "search.json").read_text(encoding="utf-8")
            priority_sitemap = (root / "public" / "sitemap-posts-priority.xml").read_text(encoding="utf-8")
            auto_html = (root / "public" / "krgov-auto-summary.html").read_text(encoding="utf-8")
            thin_html = (root / "public" / "thin-guide.html").read_text(encoding="utf-8")
            useful_html = (root / "public" / "useful-guide.html").read_text(encoding="utf-8")

            self.assertIn("실제로 확인할 수 있는 생활 가이드", index_html)
            self.assertNotIn("자동 보도자료 요약", index_html)
            self.assertNotIn("짧은 안내", index_html)
            self.assertIn("useful-guide.html", priority_sitemap)
            self.assertNotIn("krgov-auto-summary.html", priority_sitemap)
            self.assertNotIn("thin-guide.html", priority_sitemap)
            self.assertIn("useful-guide", search_json)
            self.assertNotIn("krgov-auto-summary", search_json)
            self.assertIn('<meta name="robots" content="index,follow', useful_html)
            self.assertIn('<meta name="google-adsense-account"', useful_html)
            self.assertIn('<meta name="robots" content="noindex,follow">', auto_html)
            self.assertNotIn("google-adsense-account", auto_html)
            self.assertIn('<meta name="robots" content="noindex,follow">', thin_html)

if __name__ == "__main__":
    unittest.main()
