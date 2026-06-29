from __future__ import annotations

from pathlib import Path
import re

import markdown
import requests
import yaml

from .config import Settings
from .models import Draft, PublishResult
import time


class Publisher:
    def publish(self, draft: Draft) -> PublishResult:
        raise NotImplementedError


class MarkdownPublisher(Publisher):
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, draft: Draft) -> PublishResult:
        body = self._body_with_images(draft)
        path = self.output_dir / f"{draft.slug}.md"
        meta = {
            "title": self._clean_scalar(draft.title),
            "date": draft.created_at.isoformat(),
            "category": draft.topic.category,
            "tags": [self._clean_scalar(tag) for tag in draft.tags],
            "quality_score": round(draft.quality_score, 1),
        }
        if draft.cover_image_path:
            meta["cover_image"] = draft.cover_image_path
            if draft.cover_image_alt:
                meta["cover_image_alt"] = self._clean_scalar(draft.cover_image_alt)
        if draft.inline_image_path:
            meta["inline_image"] = draft.inline_image_path
            if draft.inline_image_alt:
                meta["inline_image_alt"] = self._clean_scalar(draft.inline_image_alt)
        frontmatter = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"
        path.write_text(frontmatter + body + "\n", encoding="utf-8")
        return PublishResult(ok=True, destination="markdown", url=str(path), message="draft saved")

    @staticmethod
    def _clean_scalar(value: str) -> str:
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _body_with_images(draft: Draft) -> str:
        body = MarkdownPublisher._normalize_body_markdown(draft.body_markdown)
        if draft.inline_image_path:
            body = MarkdownPublisher._insert_inline_image(
                body,
                MarkdownPublisher._image_ref(draft.inline_image_path),
                MarkdownPublisher._clean_scalar(draft.inline_image_alt or f"{draft.title} 본문 이미지"),
            )
        if draft.cover_image_path:
            alt = MarkdownPublisher._clean_scalar(draft.cover_image_alt or draft.title)
            body = f"![{alt}]({MarkdownPublisher._image_ref(draft.cover_image_path)})\n\n{body}"
        return body

    @staticmethod
    def _normalize_body_markdown(markdown_text: str) -> str:
        match = re.fullmatch(
            r"\s*```(?:markdown|md)?[ \t]*\r?\n(.*?)\r?\n```[ \t]*\s*",
            markdown_text,
            flags=re.S | re.I,
        )
        if match:
            return match.group(1).strip() + "\n"
        return markdown_text

    @staticmethod
    def _image_ref(path_or_url: str) -> str:
        return path_or_url if path_or_url.startswith("http") else f"assets/{Path(path_or_url).name}"

    @staticmethod
    def _insert_inline_image(body: str, image_ref: str, alt: str) -> str:
        if not image_ref or image_ref in body:
            return body
        image_md = f"\n\n![{alt}]({image_ref})\n\n"
        heading_matches = list(re.finditer(r"(?m)^#{2,4}\s+.+$", body))
        if len(heading_matches) >= 2:
            insert_at = heading_matches[1].start()
            return body[:insert_at].rstrip() + image_md + body[insert_at:].lstrip()
        paragraphs = list(re.finditer(r"\n\s*\n", body))
        if len(paragraphs) >= 2:
            insert_at = paragraphs[1].end()
            return body[:insert_at].rstrip() + image_md + body[insert_at:].lstrip()
        return body.rstrip() + image_md


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
        if draft.inline_image_path:
            body = MarkdownPublisher._insert_inline_image(
                body,
                MarkdownPublisher._image_ref(draft.inline_image_path),
                MarkdownPublisher._clean_scalar(draft.inline_image_alt or f"{draft.title} 본문 이미지"),
            )
        if media:
            _, media_url = media
            alt = draft.cover_image_alt or draft.title
            body = f"![{alt}]({media_url})\n\n{body}"
        elif draft.cover_image_path:
            body = MarkdownPublisher._body_with_images(draft)
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


class BloggerPublisher(Publisher):
    """Google Blogger API를 통해 포스팅"""

    def __init__(self, settings: Settings) -> None:
        if not settings.blogger_blog_id:
            raise ValueError("Blogger 블로그 ID가 필요합니다: BLOGGER_BLOG_ID")
        self.api_key = settings.blogger_api_key
        self.blog_id = settings.blogger_blog_id
        # Optional OAuth2 credentials for write access
        self.oauth_client_id = settings.blogger_oauth_client_id
        self.oauth_client_secret = settings.blogger_oauth_client_secret
        self.refresh_token = settings.blogger_refresh_token
        self.base_url = "https://www.googleapis.com/blogger/v3"

    def publish(self, draft: Draft) -> PublishResult:
        body = MarkdownPublisher._body_with_images(draft)
        
        content = markdown.markdown(
            body,
            extensions=["tables", "fenced_code"],
            output_format="html5",
        )

        payload = {
            "kind": "blogger#post",
            "title": draft.title,
            "content": content,
            "labels": draft.tags,
        }

        url = f"{self.base_url}/blogs/{self.blog_id}/posts"

        headers = {"Content-Type": "application/json"}
        params = {}

        # If refresh token is provided, exchange it for an access token and use Bearer auth
        if self.refresh_token and self.oauth_client_id and self.oauth_client_secret:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": self.oauth_client_id,
                "client_secret": self.oauth_client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
            try:
                tokresp = requests.post(token_url, data=data, timeout=10)
                tokresp.raise_for_status()
                access_token = tokresp.json().get("access_token")
                headers["Authorization"] = f"Bearer {access_token}"
            except Exception as exc:
                return PublishResult(ok=False, destination="blogger", message=f"OAuth token error: {str(exc)[:300]}")
        elif self.api_key:
            params["key"] = self.api_key

        response = requests.post(url, json=payload, params=params, headers=headers, timeout=30)

        if response.status_code >= 400:
            return PublishResult(
                ok=False,
                destination="blogger",
                message=f"{response.status_code}: {response.text[:300]}",
            )

        try:
            data = response.json()
            post_url = data.get("url", "")
            return PublishResult(
                ok=True,
                destination="blogger",
                url=post_url,
                message="published",
            )
        except Exception as e:
            return PublishResult(
                ok=False,
                destination="blogger",
                message=f"Error parsing response: {str(e)[:300]}",
            )


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
    if settings.publisher == "blogger":
        return BloggerPublisher(settings)
    if settings.publisher == "wordpress+blogger":
        return CompositePublisher([WordPressPublisher(settings), BloggerPublisher(settings)])
    if settings.publisher == "both":
        return CompositePublisher([MarkdownPublisher(settings.output_dir), WordPressPublisher(settings)])
    if settings.publisher == "all":
        return CompositePublisher([
            MarkdownPublisher(settings.output_dir),
            WordPressPublisher(settings),
            BloggerPublisher(settings),
        ])
    return MarkdownPublisher(settings.output_dir)
