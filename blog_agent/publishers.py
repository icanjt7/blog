from __future__ import annotations

from pathlib import Path

import markdown
import requests

from .config import Settings
from .models import Draft, PublishResult


class Publisher:
    def publish(self, draft: Draft) -> PublishResult:
        raise NotImplementedError


class MarkdownPublisher(Publisher):
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, draft: Draft) -> PublishResult:
        path = self.output_dir / f"{draft.slug}.md"
        frontmatter = "\n".join(
            [
                "---",
                f'title: "{draft.title}"',
                f'date: "{draft.created_at.isoformat()}"',
                f'category: "{draft.topic.category}"',
                "tags:",
                *[f"  - {tag}" for tag in draft.tags],
                f'quality_score: {draft.quality_score:.1f}',
                "---",
                "",
            ]
        )
        path.write_text(frontmatter + draft.body_markdown + "\n", encoding="utf-8")
        return PublishResult(ok=True, destination="markdown", url=str(path), message="draft saved")


class WordPressPublisher(Publisher):
    def __init__(self, settings: Settings) -> None:
        if not all([settings.wordpress_url, settings.wordpress_username, settings.wordpress_app_password]):
            raise ValueError("WordPress 환경변수가 필요합니다.")
        self.url = settings.wordpress_url.rstrip("/")
        self.auth = (settings.wordpress_username, settings.wordpress_app_password)
        self.status = settings.wordpress_status

    def publish(self, draft: Draft) -> PublishResult:
        payload = {
            "title": draft.title,
            "content": markdown.markdown(
                draft.body_markdown,
                extensions=["tables", "fenced_code"],
                output_format="html5",
            ),
            "excerpt": draft.excerpt,
            "status": self.status,
        }
        response = requests.post(
            f"{self.url}/wp-json/wp/v2/posts",
            json=payload,
            auth=self.auth,
            timeout=30,
        )
        if response.status_code >= 400:
            return PublishResult(
                ok=False,
                destination="wordpress",
                message=f"{response.status_code}: {response.text[:300]}",
            )
        data = response.json()
        return PublishResult(ok=True, destination="wordpress", url=data.get("link"), message="published")


class CompositePublisher(Publisher):
    def __init__(self, publishers: list[Publisher]) -> None:
        self.publishers = publishers

    def publish(self, draft: Draft) -> PublishResult:
        results = [publisher.publish(draft) for publisher in self.publishers]
        failed = [result for result in results if not result.ok]
        destination = "+".join(result.destination for result in results)
        wordpress_url = next((result.url for result in results if result.destination == "wordpress"), None)
        message = " | ".join(f"{result.destination}: {result.message}" for result in results)
        return PublishResult(
            ok=not failed,
            destination=destination,
            url=wordpress_url or results[0].url,
            message=message,
        )


def build_publisher(settings: Settings) -> Publisher:
    if settings.publisher == "wordpress":
        return WordPressPublisher(settings)
    if settings.publisher == "both":
        return CompositePublisher([MarkdownPublisher(settings.output_dir), WordPressPublisher(settings)])
    return MarkdownPublisher(settings.output_dir)
