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
        body = self._body_with_cover(draft)
        path = self.output_dir / f"{draft.slug}.md"
        cover_lines = []
        if draft.cover_image_path:
            cover_lines = [f'cover_image: "{draft.cover_image_path}"']
            if draft.cover_image_alt:
                cover_lines.append(f'cover_image_alt: "{draft.cover_image_alt}"')
        frontmatter = "\n".join(
            [
                "---",
                f'title: "{draft.title}"',
                f'date: "{draft.created_at.isoformat()}"',
                f'category: "{draft.topic.category}"',
                "tags:",
                *[f"  - {tag}" for tag in draft.tags],
                f'quality_score: {draft.quality_score:.1f}',
                *cover_lines,
                "---",
                "",
            ]
        )
        path.write_text(frontmatter + body + "\n", encoding="utf-8")
        return PublishResult(ok=True, destination="markdown", url=str(path), message="draft saved")

    @staticmethod
    def _body_with_cover(draft: Draft) -> str:
        if not draft.cover_image_path:
            return draft.body_markdown
        p = draft.cover_image_path
        alt = draft.cover_image_alt or draft.title
        # Unsplash/remote URL vs local file
        image_ref = p if p.startswith("http") else f"assets/{Path(p).name}"
        return f"![{alt}]({image_ref})\n\n{draft.body_markdown}"


class WordPressPublisher(Publisher):
    def __init__(self, settings: Settings) -> None:
        if not all([settings.wordpress_url, settings.wordpress_username, settings.wordpress_app_password]):
            raise ValueError("WordPress 환경변수가 필요합니다.")
        self.url = settings.wordpress_url.rstrip("/")
        self.auth = (settings.wordpress_username, settings.wordpress_app_password)
        self.status = settings.wordpress_status

    def publish(self, draft: Draft) -> PublishResult:
        media = self._upload_media(draft)
        body = draft.body_markdown
        if media:
            _, media_url = media
            alt = draft.cover_image_alt or draft.title
            body = f"![{alt}]({media_url})\n\n{draft.body_markdown}"
        elif draft.cover_image_path:
            body = MarkdownPublisher._body_with_cover(draft)
        payload = {
            "title": draft.title,
            "content": markdown.markdown(
                body,
                extensions=["tables", "fenced_code"],
                output_format="html5",
            ),
            "excerpt": draft.excerpt,
            "status": self.status,
        }
        if media:
            payload["featured_media"] = media[0]
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

    def _upload_media(self, draft: Draft) -> tuple[int, str] | None:
        if not draft.cover_image_path:
            return None
        path = Path(draft.cover_image_path)
        if not path.exists():
            return None
        headers = {
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "Content-Type": "image/png",
        }
        response = requests.post(
            f"{self.url}/wp-json/wp/v2/media",
            data=path.read_bytes(),
            headers=headers,
            auth=self.auth,
            timeout=60,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
        return int(data["id"]), data.get("source_url", "")


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
