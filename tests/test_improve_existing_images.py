from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from blog_agent.config import Settings
from blog_agent.images import ImageAgent
from scripts.improve_existing_images import improve_post


class ImproveExistingImagesTest(unittest.TestCase):
    def test_public_license_badge_is_removed_when_stock_image_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "post.md"
            path.write_text(
                "---\n"
                'title: "테스트"\n'
                'date: "2026-09-20"\n'
                'category: "정책"\n'
                'cover_image: "https://example.go.kr/images/openright_00.png"\n'
                'cover_image_alt: "공공누리 공공저작물 자유이용허락"\n'
                "---\n\n본문\n",
                encoding="utf-8",
            )
            agent = ImageAgent(Settings())

            changed, reason = improve_post(path, agent, public_license_only=True)

            raw = path.read_text(encoding="utf-8")
            self.assertTrue(changed)
            self.assertEqual(reason, "removed:public-license-badge")
            self.assertNotIn("openright_00", raw)
            self.assertNotIn("cover_image_alt", raw)


if __name__ == "__main__":
    unittest.main()
