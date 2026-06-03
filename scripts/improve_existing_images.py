"""Replace weak legacy post covers with topic-aware stock images.

The normal publishing pipeline already tries Unsplash -> Pexels -> Pixabay
before falling back to picsum. This script applies that same idea to older
posts whose current cover is missing, a generic picsum image, or an institution
logo placeholder.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from blog_agent.config import load_settings
from blog_agent.images import ImageAgent
from blog_agent.models import Draft, Topic


POSTS_DIR = Path(__file__).resolve().parents[1] / "output" / "posts"
VALID_CATEGORIES = {"핫이슈", "기술", "정책", "생활"}


def _quote_yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _split_post(raw: str) -> tuple[str, str] | None:
    if not raw.startswith("---"):
        return None
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _set_frontmatter_field(frontmatter: str, key: str, value: str) -> str:
    line = f"{key}: {_quote_yaml(value)}"
    pattern = rf"^{re.escape(key)}:\s*.*$"
    if re.search(pattern, frontmatter, flags=re.MULTILINE):
        return re.sub(pattern, line, frontmatter, flags=re.MULTILINE)
    return frontmatter.rstrip() + "\n" + line + "\n"


def _is_weak_cover(url: str | None) -> bool:
    if not url:
        return True
    weak_markers = (
        "picsum.photos",
        "loremflickr.com",
        "placehold.co",
        "placeholder",
        "assets/logos/",
        "/assets/logos/",
    )
    return any(marker in url for marker in weak_markers)


def _provider_name(url: str) -> str:
    if "images.unsplash.com" in url:
        return "unsplash"
    if "pexels.com" in url:
        return "pexels"
    if "pixabay.com" in url:
        return "pixabay"
    if "picsum.photos" in url:
        return "picsum"
    return "remote"


def _keyword(meta: dict, title: str) -> str:
    tags = meta.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    useful_tags = [
        str(tag)
        for tag in tags
        if str(tag).lower() not in {"tech", "finance", "living", "local", "보도기사"}
    ]
    return " ".join(useful_tags[:3]) or title


def _replace_leading_weak_image(body: str, old_url: str | None, new_url: str, alt: str) -> str:
    leading = re.match(r"(\s*)!\[([^\]]*)\]\(([^)]+)\)", body)
    if not leading:
        return body
    image_url = leading.group(3).strip()
    if not _is_weak_cover(image_url) and image_url != old_url:
        return body
    replacement = f"{leading.group(1)}![{alt}]({new_url})"
    return replacement + body[leading.end():]


def _build_draft(path: Path, meta: dict, body: str) -> Draft:
    title = str(meta.get("title") or path.stem)
    category = str(meta.get("category") or "핫이슈").strip('"')
    if category not in VALID_CATEGORIES:
        category = "핫이슈"
    topic = Topic(
        keyword=_keyword(meta, title),
        title_hint=title,
        category=category,  # type: ignore[arg-type]
    )
    return Draft(
        topic=topic,
        title=title,
        slug=path.stem,
        excerpt=str(meta.get("excerpt") or ""),
        body_markdown=body,
        tags=[str(tag) for tag in meta.get("tags") or []],
        cover_image_path=str(meta.get("cover_image") or "") or None,
        cover_image_alt=str(meta.get("cover_image_alt") or "") or None,
    )


def improve_post(path: Path, image_agent: ImageAgent, dry_run: bool = False) -> tuple[bool, str]:
    raw = path.read_text(encoding="utf-8")
    split = _split_post(raw)
    if not split:
        return False, "skip:no-frontmatter"
    frontmatter, body = split
    meta = yaml.safe_load(frontmatter) or {}
    old_cover = str(meta.get("cover_image") or "")
    if not _is_weak_cover(old_cover):
        return False, "skip:strong-cover"

    draft = _build_draft(path, meta, body)
    if dry_run:
        query = image_agent.visual_query(draft.topic.keyword, draft.topic.category, draft.title)
        return True, f"dry-run:{query}"

    updated = image_agent.attach_cover(draft)
    new_cover = updated.cover_image_path or ""
    if not new_cover or _is_weak_cover(new_cover):
        return False, "skip:no-better-image"

    alt = updated.cover_image_alt or f"{updated.title} 대표 이미지"
    frontmatter = _set_frontmatter_field(frontmatter, "cover_image", new_cover)
    frontmatter = _set_frontmatter_field(frontmatter, "cover_image_alt", alt)
    body = _replace_leading_weak_image(body, old_cover, new_cover, alt)
    path.write_text(f"---\n{frontmatter.strip()}\n---{body}", encoding="utf-8")
    return True, f"updated:{_provider_name(new_cover)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-dir", type=Path, default=POSTS_DIR)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    settings.enable_image_generation = False
    image_agent = ImageAgent(settings)

    changed = 0
    scanned = 0
    for path in sorted(args.posts_dir.glob("*.md")):
        if args.limit > 0 and changed >= args.limit:
            break
        ok, reason = improve_post(path, image_agent, dry_run=args.dry_run)
        scanned += 1
        if ok:
            changed += 1
            print(f"{reason} {path.relative_to(args.posts_dir.parent.parent)}")

    mode = "would improve" if args.dry_run else "improved"
    print(f"\n{mode} {changed} posts after scanning {scanned} files.")


if __name__ == "__main__":
    main()
