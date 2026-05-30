from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import markdown
import yaml


@dataclass
class Post:
    title: str
    date: datetime
    category: str
    tags: list[str]
    slug: str
    excerpt: str
    body_html: str


class StaticSiteBuilder:
    def __init__(self, posts_dir: Path, public_dir: Path, site_title: str) -> None:
        self.posts_dir = posts_dir
        self.public_dir = public_dir
        self.site_title = site_title

    def build(self) -> None:
        self.public_dir.mkdir(parents=True, exist_ok=True)
        posts = self._load_posts()
        for post in posts:
            self._write_post(post)
        self._write_index(posts)
        self._write_feed(posts)
        self._write_css()

    def _load_posts(self) -> list[Post]:
        if not self.posts_dir.exists():
            return []
        posts = [self._parse_post(path) for path in sorted(self.posts_dir.glob("*.md"))]
        return sorted(posts, key=lambda post: post.date, reverse=True)

    def _parse_post(self, path: Path) -> Post:
        raw = path.read_text(encoding="utf-8")
        meta: dict = {}
        body = raw
        if raw.startswith("---"):
            _, frontmatter, body = raw.split("---", 2)
            meta = yaml.safe_load(frontmatter) or {}
        title = str(meta.get("title") or path.stem)
        date = self._parse_date(str(meta.get("date") or datetime.now().isoformat()))
        category = str(meta.get("category") or "blog")
        tags = [str(tag) for tag in meta.get("tags", [])]
        body_html = markdown.markdown(
            body,
            extensions=["tables", "fenced_code", "toc"],
            output_format="html5",
        )
        excerpt = self._excerpt(body)
        return Post(
            title=title,
            date=date,
            category=category,
            tags=tags,
            slug=path.stem,
            excerpt=excerpt,
            body_html=body_html,
        )

    def _write_post(self, post: Post) -> None:
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">전체 글</a>
          <header>
            <p class="meta">{html.escape(post.category)} · {post.date:%Y-%m-%d}</p>
            <h1>{html.escape(post.title)}</h1>
            <div class="tags">{self._tag_html(post.tags)}</div>
          </header>
          <div class="content">{post.body_html}</div>
        </article>
        """
        self._write_html(f"{post.slug}.html", post.title, content)

    def _write_index(self, posts: list[Post]) -> None:
        if posts:
            cards = "\n".join(
                f"""
                <article class="card">
                  <p class="meta">{html.escape(post.category)} · {post.date:%Y-%m-%d}</p>
                  <h2><a href="./{post.slug}.html">{html.escape(post.title)}</a></h2>
                  <p>{html.escape(post.excerpt)}</p>
                  <div class="tags">{self._tag_html(post.tags[:5])}</div>
                </article>
                """
                for post in posts
            )
        else:
            cards = '<p class="empty">아직 발행된 글이 없습니다.</p>'
        content = f"""
        <section class="hero">
          <p class="meta">자동화 정보 블로그</p>
          <h1>{html.escape(self.site_title)}</h1>
        </section>
        <section class="grid">{cards}</section>
        """
        self._write_html("index.html", self.site_title, content)

    def _write_feed(self, posts: list[Post]) -> None:
        items = "\n".join(
            f"""
            <item>
              <title>{html.escape(post.title)}</title>
              <link>{post.slug}.html</link>
              <description>{html.escape(post.excerpt)}</description>
              <pubDate>{post.date:%a, %d %b %Y 00:00:00 +0900}</pubDate>
            </item>
            """
            for post in posts[:20]
        )
        feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>{html.escape(self.site_title)}</title>
    <description>Daily automated blog posts</description>
    <link>./</link>
    {items}
  </channel>
</rss>
"""
        (self.public_dir / "feed.xml").write_text(feed, encoding="utf-8")

    def _write_html(self, filename: str, title: str, content: str) -> None:
        page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(self.site_title)}">
  <link rel="stylesheet" href="./style.css">
  <link rel="alternate" type="application/rss+xml" href="./feed.xml">
</head>
<body>
  <main>{content}</main>
</body>
</html>
"""
        (self.public_dir / filename).write_text(page, encoding="utf-8")

    def _write_css(self) -> None:
        css = """
:root {
  color-scheme: light;
  --bg: #f7f5ef;
  --ink: #232323;
  --muted: #6b675e;
  --line: #ded8ca;
  --accent: #0f766e;
  --paper: #fffdf8;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.7;
}
main {
  width: min(1040px, calc(100% - 32px));
  margin: 0 auto;
  padding: 40px 0 64px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.hero { padding: 32px 0 28px; border-bottom: 1px solid var(--line); }
.hero h1 { margin: 0; font-size: clamp(2rem, 4vw, 4.5rem); line-height: 1.05; }
.meta { margin: 0 0 8px; color: var(--muted); font-size: 0.9rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding-top: 24px; }
.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 20px;
}
.card h2 { margin: 0 0 10px; font-size: 1.18rem; line-height: 1.35; }
.card p { margin: 0 0 14px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--muted);
  font-size: 0.78rem;
}
.post {
  max-width: 760px;
  margin: 0 auto;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 28px;
}
.post h1 { margin: 8px 0 14px; font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.15; }
.back { display: inline-block; margin-bottom: 24px; color: var(--muted); }
.content { margin-top: 28px; }
.content h2 { margin-top: 32px; line-height: 1.3; }
.content table { width: 100%; border-collapse: collapse; margin: 18px 0; font-size: 0.95rem; }
.content th, .content td { border: 1px solid var(--line); padding: 9px; text-align: left; }
.content th { background: #ece7da; }
.empty { padding: 24px 0; color: var(--muted); }
@media (max-width: 640px) {
  main { width: min(100% - 20px, 1040px); padding-top: 20px; }
  .post { padding: 18px; }
}
"""
        (self.public_dir / "style.css").write_text(css.strip() + "\n", encoding="utf-8")

    @staticmethod
    def _parse_date(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()

    @staticmethod
    def _excerpt(markdown_text: str) -> str:
        text = re.sub(r"```.*?```", "", markdown_text, flags=re.S)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[\n#>*_|`-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:160] + ("..." if len(text) > 160 else "")

    @staticmethod
    def _tag_html(tags: list[str]) -> str:
        return "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in tags)
