from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from blog_agent.models import Draft, Topic
from blog_agent.publishers import MarkdownPublisher


class MarkdownPublisherTest(unittest.TestCase):
    def test_publish_escapes_multiline_frontmatter_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            publisher = MarkdownPublisher(Path(tmp))
            topic = Topic(keyword="Benchmark raises its", title_hint="벤치마크", category="기술")
            draft = Draft(
                topic=topic,
                title='**\nBenchmark, "성장펀드" 출시\n**',
                slug="benchmark-test",
                excerpt="",
                body_markdown="본문",
                tags=["기술", "Benchmark"],
                cover_image_path="https://example.com/image.jpg",
                cover_image_alt='alt\nwith "quote"',
                quality_score=93.27,
            )

            publisher.publish(draft)
            raw = (Path(tmp) / "benchmark-test.md").read_text(encoding="utf-8")
            _, fm, body = raw.split("---", 2)
            meta = yaml.safe_load(fm)

        self.assertEqual(meta["title"], '** Benchmark, "성장펀드" 출시 **')
        self.assertEqual(meta["cover_image_alt"], 'alt with "quote"')
        self.assertIn('![alt with "quote"]', body)


if __name__ == "__main__":
    unittest.main()
