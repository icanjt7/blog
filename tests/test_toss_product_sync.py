from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blog_agent.product_links import ProductLink
from blog_agent.site import StaticSiteBuilder


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_toss_products.py"
SPEC = importlib.util.spec_from_file_location("sync_toss_products", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeClient:
    def __init__(self) -> None:
        self.issued: list[int] = []

    def health(self) -> dict:
        return {"status": "ok"}

    def best_selling(self, size: int) -> list[dict]:
        return [
            {
                "rank": 1,
                "tacaItemId": 101,
                "displayName": "테스트 오메가3",
                "thumbnailUrl": "https://shopping.toss.im/product.jpg",
                "productUrl": "https://toss.shopping/t/10",
                "displayPrice": 19900,
                "originalPrice": 25000,
                "discountRate": 20,
                "isSoldOut": False,
                "reviewScore": 4.8,
                "reviewCount": 123,
                "categoryIds": [1, 2],
            }
        ]

    def today_deals(self, size: int = 30) -> list[dict]:
        return []

    def issue_link(self, taca_item_id: int, publisher_id: str) -> dict:
        self.issued.append(taca_item_id)
        return {
            "shortUrl": "https://toss.im/_m/test",
            "originUrl": "https://toss.shopping/t/10?k=test&referrer=affiliate",
        }


class TossProductSyncTest(unittest.TestCase):
    def test_sync_writes_official_fields_and_sharelink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "products.json"
            client = FakeClient()

            MODULE.synchronize(
                client,
                publisher_id="publisher-id",
                output=output,
                size=30,
                include_today_deals=False,
                images_allowed=False,
            )
            product = json.loads(output.read_text(encoding="utf-8"))["products"][0]

        self.assertEqual(client.issued, [101])
        self.assertEqual(product["shortUrl"], "https://toss.im/_m/test")
        self.assertEqual(product["displayPrice"], 19900)
        self.assertFalse(product["imageAllowed"])

    def test_sync_reuses_cached_sharelink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "products.json"
            output.write_text(
                json.dumps(
                    {
                        "products": [
                            {
                                "tacaItemId": 101,
                                "shortUrl": "https://toss.im/_m/cached",
                                "originUrl": "https://toss.shopping/t/10?k=cached",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            client = FakeClient()

            MODULE.synchronize(
                client,
                publisher_id="publisher-id",
                output=output,
                size=30,
                include_today_deals=False,
                images_allowed=True,
            )
            product = json.loads(output.read_text(encoding="utf-8"))["products"][0]

        self.assertEqual(client.issued, [])
        self.assertEqual(product["shortUrl"], "https://toss.im/_m/cached")
        self.assertTrue(product["imageAllowed"])

    def test_home_product_strip_uses_tracking_links_and_respects_image_permission(self) -> None:
        products = (
            ProductLink(
                name="API 인기 상품",
                url="https://toss.im/_m/tracked",
                keywords=("생활",),
                taca_item_id=101,
                thumbnail_url="https://shopping.toss.im/product.jpg",
                image_allowed=False,
                display_price=19900,
                discount_rate=20,
                review_score=4.8,
                review_count=123,
                source="openapi",
            ),
            ProductLink(
                name="두 번째 상품",
                url="https://toss.im/_m/second",
                keywords=("식품",),
                taca_item_id=102,
                source="openapi",
            ),
        )
        builder = StaticSiteBuilder(Path("posts"), Path("public"), "테스트", "테스트")

        with patch("blog_agent.site.PRODUCT_LINKS", products):
            strip = builder._home_product_strip_html()

        self.assertEqual(strip.count('class="home-product-card"'), 2)
        self.assertIn("https://toss.im/_m/tracked", strip)
        self.assertIn("19,900원", strip)
        self.assertIn("★ 4.8 · 후기 123", strip)
        self.assertIn('rel="sponsored nofollow noopener"', strip)
        self.assertNotIn("product.jpg", strip)


if __name__ == "__main__":
    unittest.main()
