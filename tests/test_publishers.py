from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from blog_agent.models import Draft, Topic
from blog_agent.publishers import MarkdownPublisher
from blog_agent.slugs import UnsafeSlugError


class MarkdownPublisherTest(unittest.TestCase):
    def test_new_unsafe_slug_is_rejected_but_existing_legacy_path_is_grandfathered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            publisher = MarkdownPublisher(output)
            topic = Topic(keyword="생활비", title_hint="생활비", category="생활")
            draft = Draft(
                topic=topic,
                title="07월 생활비",
                slug="07월-생활비-f8224f14",
                excerpt="",
                body_markdown="본문",
                tags=["생활"],
            )

            with self.assertRaises(UnsafeSlugError):
                publisher.publish(draft)
            self.assertFalse((output / "07월-생활비-f8224f14.md").exists())

            legacy_path = output / "07월-생활비-f8224f14.md"
            legacy_path.write_text("legacy", encoding="utf-8")
            result = publisher.publish(draft)
            self.assertTrue(result.ok)
            self.assertTrue(legacy_path.exists())

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

    def test_publish_unwraps_body_wrapped_in_markdown_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            publisher = MarkdownPublisher(Path(tmp))
            topic = Topic(keyword="공식 로고", title_hint="김구 로고", category="생활")
            draft = Draft(
                topic=topic,
                title="김구 탄생 150주년 공식 로고",
                slug="logo-test",
                excerpt="",
                body_markdown="""```markdown
## 공식 로고 사용 기준

본문이 코드블록으로 저장되면 안 됩니다.
```""",
                tags=["생활"],
                cover_image_path="https://example.com/cover.jpg",
                cover_image_alt="대표 이미지",
            )

            publisher.publish(draft)
            raw = (Path(tmp) / "logo-test.md").read_text(encoding="utf-8")

        self.assertIn("![대표 이미지](https://example.com/cover.jpg)", raw)
        self.assertIn("## 공식 로고 사용 기준", raw)
        self.assertNotIn("```markdown", raw)


if __name__ == "__main__":
    unittest.main()
