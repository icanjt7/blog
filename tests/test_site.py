from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from blog_agent.product_links import PRODUCT_LINKS, ProductLink
from blog_agent.site import StaticSiteBuilder


class StaticSiteBuilderTest(unittest.TestCase):
    def test_source_links_handle_url_labels_and_ignore_malformed_urls(self) -> None:
        markdown_text = """## 출처

[https://inmun2026.kr](https://inmun2026.kr)
https://[잘못된-주소
"""

        links = StaticSiteBuilder._extract_source_links(markdown_text)

        self.assertEqual(links, [("https://inmun2026.kr", "https://inmun2026.kr")])
        self.assertIsNone(StaticSiteBuilder._source_label_for_url("https://[잘못된-주소"))

    def test_product_catalog_uses_sharelinks_and_only_approved_images(self) -> None:
        self.assertTrue(PRODUCT_LINKS)
        self.assertTrue(all(product.url.startswith("https://toss.im/") for product in PRODUCT_LINKS))
        self.assertTrue(
            all(
                not product.image_url or product.image_url.startswith("https://shopping.toss.im/")
                for product in PRODUCT_LINKS
            )
        )

    def test_product_review_data_is_structured(self) -> None:
        self.assertTrue(all(isinstance(product.review_data, dict) for product in PRODUCT_LINKS))

    def test_openapi_product_card_shows_price_without_unapproved_image(self) -> None:
        product = ProductLink(
            name="공식 API 상품",
            url="https://toss.im/_m/api",
            keywords=("상품",),
            thumbnail_url="https://shopping.toss.im/product.jpg",
            image_allowed=False,
            display_price=19900,
            original_price=25000,
            discount_rate=20,
            review_score=4.8,
            review_count=123,
            source="openapi",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder = StaticSiteBuilder(
                posts_dir=root / "posts",
                public_dir=root / "public",
                site_title="테스트",
                site_description="테스트",
            )

            card = builder._product_card_html(product, "추천 이유")

        self.assertIn("20% 할인", card)
        self.assertIn("19,900원", card)
        self.assertIn("평점 4.8점 · 후기 123개", card)
        self.assertIn('class="toss-shopping-card product-recommendation"', card)
        self.assertNotIn("product-bridge-copy", card)
        self.assertIn("[토스 인기 특가]", card)
        self.assertIn("[무료배송 대상]", card)
        self.assertIn("👉 [최저가 확인] 오늘 한정 특가 및 실구매자 후기 보기", card)
        self.assertIn("★ 4.8점 · 후기 123개", card)
        self.assertNotIn("product-recommendation-image", card)

    def test_parse_post_recovers_from_inline_llm_response_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            post_path = root / "posts" / "broken-generated-post.md"
            post_path.parent.mkdir()
            post_path.write_text(
                """---
title: '** 09월 지방선거 핵심 정보 총정리 **EXCERPT:** 선거 정보를 정리했습니다. **BODY:** 본문 전체가 잘못 합쳐졌습니다.'
date: '2026-09-19T18:16:28'
category: 정치
tags:
- 지방선거
cover_image: https://example.com/cover.jpg
---

**
투표일이 다가오면서 핵심 정보를 확인해야 합니다.
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

        self.assertEqual(post.title, "09월 지방선거 핵심 정보 총정리")
        self.assertNotIn("EXCERPT", post.title)
        self.assertNotIn("BODY", post.title)
        self.assertNotIn("<p>**", post.body_html)
        self.assertIn("투표일이 다가오면서", post.body_html)

    def test_product_matching_uses_article_content(self) -> None:
        omega = ProductLink(
            name="종근당건강 프로메가 알티지 오메가3",
            url="https://toss.im/_m/omega",
            keywords=("오메가3", "혈행", "영양제", "건강"),
        )
        cleaner = ProductLink(
            name="생활 청소기",
            url="https://toss.im/_m/cleaner",
            keywords=("청소", "가전", "생활"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            post_path = root / "posts" / "omega-health.md"
            post_path.parent.mkdir()
            post_path.write_text(
                """---
title: 오메가3로 혈행 건강을 관리하는 방법
category: 생활
tags:
- 오메가3
- 영양제
cover_image: https://example.com/cover.jpg
---

혈행과 면역 건강을 위한 오메가3 선택 기준을 알아봅니다.
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
            with patch("blog_agent.site.PRODUCT_LINKS", (cleaner, omega)):
                selected = builder._select_product(post)
                candidates = builder._select_products(post)

        self.assertEqual(selected.url, "https://toss.im/_m/omega")
        self.assertIn("오메가3", selected.name)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len({product.url for product in candidates}), 2)

    def test_product_widget_uses_hard_fallback_for_policy_and_unrelated_articles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            policy_path = posts_dir / "policy.md"
            policy_path.write_text(
                "---\ntitle: 저소득층 복지지원 신청\ncategory: 정책\ntags:\n- 복지지원\n---\n여성 의류와 무관한 지원 정책입니다.",
                encoding="utf-8",
            )
            unrelated_path = posts_dir / "unrelated.md"
            unrelated_path.write_text(
                "---\ntitle: 지역 도서관 운영시간\ncategory: 생활\ntags:\n- 도서관\n---\n도서관 휴관일 안내입니다.",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(posts_dir, root / "public", "테스트", "테스트")

            self.assertIn("toss-shopping-card", builder._product_link_html(builder._parse_post(policy_path)))
            self.assertIn("toss-shopping-card", builder._product_link_html(builder._parse_post(unrelated_path)))

    def test_product_bridge_copy_follows_article_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            support_path = posts_dir / "support.md"
            support_path.write_text(
                "---\ntitle: 소상공인 지원금 신청\ncategory: 정책\ntags:\n- 지원금\n---\n신청 대상과 금액 안내입니다.",
                encoding="utf-8",
            )
            mou_path = posts_dir / "mou.md"
            mou_path.write_text(
                "---\ntitle: 국가유산진흥원 WTC Seoul 업무협약\ncategory: 정책\ntags:\n- 문화\n- 협약\n---\n코엑스 전광판 홍보 협력 내용입니다.",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(posts_dir, root / "public", "테스트", "테스트")

            support_html = builder._product_link_html(builder._parse_post(support_path))
            mou_html = builder._product_link_html(builder._parse_post(mou_path))

        self.assertIn("🛒 [가계부 절약] 정책 혜택과 함께 챙기는 알뜰 실속 핫딜", support_html)
        self.assertIn("가계 부담을 덜어드리기 위해", support_html)
        self.assertIn("🎁 [브리핑웨이브 추천] 일상 속 가치를 더하는 실시간 핫딜", mou_html)
        self.assertIn("공공 소식과 함께", mou_html)

    def test_relevant_policy_and_public_bid_both_receive_product_widget(self) -> None:
        energy_product = ProductLink(
            name="가정용 에너지 절약 멀티탭",
            url="https://toss.im/_m/energy",
            keywords=("에너지", "절약", "전기", "멀티탭"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            posts_dir = root / "posts"
            posts_dir.mkdir()
            policy_path = posts_dir / "energy-policy.md"
            policy_path.write_text(
                "---\ntitle: 전기 에너지 절약 지원 혜택\ncategory: 정책\ntags:\n- 에너지\n- 전기\n- 절약\n---\n전기 절약 가구 지원 안내입니다.",
                encoding="utf-8",
            )
            bid_path = posts_dir / "bid.md"
            bid_path.write_text(
                "---\ntitle: 공공기관 멀티탭 구매 입찰\ncategory: 정책\ntags:\n- 공공입찰\n- 멀티탭\n---\n나라장터 구매 공고입니다.",
                encoding="utf-8",
            )
            builder = StaticSiteBuilder(posts_dir, root / "public", "테스트", "테스트")
            with patch("blog_agent.site.PRODUCT_LINKS", (energy_product,)):
                policy_html = builder._product_link_html(builder._parse_post(policy_path))
                bid_html = builder._product_link_html(builder._parse_post(bid_path))

        self.assertIn("오늘 한정 특가", policy_html)
        self.assertIn("toss-shopping-card", bid_html)

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
            for rendered_page in (page_two, category_two, search):
                self.assertIn('class="home-products toss-shopping-home"', rendered_page)
                self.assertIn('class="bottom-recommend-widget"', rendered_page)
                self.assertIn("window.renderTossProducts", rendered_page)
                self.assertIn("briefwave:content-updated", rendered_page)
            self.assertIn("document.dispatchEvent(new CustomEvent('briefwave:content-updated'))", search)

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

            generated_post_pages = [
                page
                for page in (root / "public").glob("*.html")
                if '<article class="post">' in page.read_text(encoding="utf-8")
            ]
            self.assertEqual(len(generated_post_pages), 2)
            self.assertTrue(
                all(
                    '<aside class="toss-shopping-card product-recommendation"'
                    in page.read_text(encoding="utf-8")
                    for page in generated_post_pages
                )
            )

            html = (root / "public" / "source-post.html").read_text(encoding="utf-8")
            self.assertNotIn("읽는 기준", html)
            self.assertIn("자주 묻는 질문", html)
            self.assertEqual(html.count("<dt>"), 2)
            self.assertIn("지원 기기", html)
            self.assertIn("공식 정보는 어디에서 확인하나요?", html)
            self.assertIn("공식 원문", html)
            self.assertIn("Google Search Central", html)
            self.assertIn("편집 기준", html)
            self.assertIn("함께 보면 좋은 글", html)
            self.assertIn("관련 글", html)
            self.assertIn('class="official-source-badge"', html)
            self.assertIn('target="_blank"', html)
            self.assertIn('noopener noreferrer', html)
            self.assertIn('class="toss-shopping-card product-recommendation"', html)
            self.assertIn('aria-label="광고 영역"', html)
            self.assertIn('<div class="ad-label">광고</div>', html)
            self.assertLess(html.index('<div class="content">'), html.index('<div class="ad-slot"'))
            product_catalog = json.loads((root / "public" / "product-catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(len(product_catalog), len(PRODUCT_LINKS))
            first_product = next(iter(product_catalog.values()))
            self.assertIn("name", first_product)
            self.assertIn("url", first_product)
            self.assertIn("keywords", first_product)
            search_html = (root / "public" / "search.html").read_text(encoding="utf-8")
            self.assertIn("기사·상품 검색", search_html)
            self.assertIn("product-catalog.json", search_html)
            self.assertIn('id="product-results"', search_html)
            self.assertIn("filterProducts", search_html)
            self.assertIn("기사 ${results.length}개 · 상품 ${products.length}개", search_html)

            for filename in ("about.html", "editorial-policy.html", "privacy.html", "contact.html"):
                self.assertTrue((root / "public" / filename).exists())
            footer_html = (root / "public" / "index.html").read_text(encoding="utf-8")
            self.assertIn("기사·상품 검색...", footer_html)
            self.assertIn('class="home-products toss-shopping-home"', footer_html)
            self.assertIn("🔥 실시간 특가 TOP 4", footer_html)
            self.assertIn('data-home-products', footer_html)
            self.assertIn("최저가·실시간 혜택 보기", footer_html)
            self.assertLess(footer_html.index("home-notices"), footer_html.index("toss-shopping-home"))
            self.assertIn('class="bottom-recommend-widget"', footer_html)
            self.assertIn("[최저가 확인] 혜택 및 후기 보기 →", footer_html)
            self.assertLess(footer_html.index('class="grid"'), footer_html.index('class="bottom-recommend-widget"'))
            self.assertLess(footer_html.index('class="bottom-recommend-widget"'), footer_html.index('<footer class="site-footer">'))
            self.assertIn('href="./privacy.html"', footer_html)
            self.assertIn('class="footer-category-links"', footer_html)
            self.assertIn('href="./category-기술.html"', footer_html)
            category_html = (root / "public" / "category-기술.html").read_text(encoding="utf-8")
            self.assertIn('class="home-products toss-shopping-home"', category_html)
            self.assertIn("🔥 실시간 특가 TOP 4", category_html)
            self.assertIn('data-home-products', category_html)
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

    def test_all_posts_remain_public_when_legacy_review_mode_is_set(self) -> None:
        env = patch.dict("os.environ", {"ADSENSE_REVIEW_MODE": "1", "ADSENSE_REVIEW_INDEX_LIMIT": "120"})
        env.start()
        self.addCleanup(env.stop)
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
            self.assertIn("자동 보도자료 요약", index_html)
            self.assertIn("짧은 안내", index_html)
            self.assertIn("useful-guide.html", priority_sitemap)
            self.assertIn("krgov-auto-summary.html", priority_sitemap)
            self.assertIn("thin-guide.html", priority_sitemap)
            self.assertIn("useful-guide", search_json)
            self.assertIn("krgov-auto-summary", search_json)
            self.assertIn("thin-guide", search_json)
            self.assertIn('<meta name="robots" content="index,follow', useful_html)
            self.assertIn('<meta name="google-adsense-account"', useful_html)
            self.assertIn('<meta name="robots" content="index,follow', auto_html)
            self.assertIn("google-adsense-account", auto_html)
            self.assertIn('<meta name="robots" content="index,follow', thin_html)

if __name__ == "__main__":
    unittest.main()
