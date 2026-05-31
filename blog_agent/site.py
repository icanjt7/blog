from __future__ import annotations

import html
import re
import shutil
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
    cover_image: str = ""
    cover_image_alt: str = ""


class StaticSiteBuilder:
    def __init__(
        self,
        posts_dir: Path,
        public_dir: Path,
        site_title: str,
        custom_domain: str | None = None,
        ga_measurement_id: str | None = None,
        adsense_publisher_id: str | None = None,
    ) -> None:
        self.posts_dir = posts_dir
        self.public_dir = public_dir
        self.site_title = site_title
        self.custom_domain = custom_domain
        self.ga_measurement_id = ga_measurement_id
        self.adsense_publisher_id = adsense_publisher_id

    def build(self) -> None:
        self.public_dir.mkdir(parents=True, exist_ok=True)
        posts = self._load_posts()
        for post in posts:
            self._write_post(post)
        self._write_index(posts)
        self._write_dashboard(posts)
        self._write_feed(posts)
        self._write_css()
        self._copy_assets()
        self._write_cname()

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
            cover_image=str(meta.get("cover_image") or ""),
            cover_image_alt=str(meta.get("cover_image_alt") or title),
        )

    def _write_post(self, post: Post) -> None:
        cover_html = ""
        if post.cover_image:
            cover_html = f'<img class="cover" src="{html.escape(post.cover_image)}" alt="{html.escape(post.cover_image_alt)}" loading="lazy">'
        ad_slot = self._ad_slot()
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">전체 글</a>
          {cover_html}
          <header>
            <p class="meta">{html.escape(post.category)} · {post.date:%Y-%m-%d}</p>
            <h1>{html.escape(post.title)}</h1>
            <div class="tags">{self._tag_html(post.tags)}</div>
          </header>
          {ad_slot}
          <div class="content">{post.body_html}</div>
          {ad_slot}
        </article>
        """
        self._write_html(f"{post.slug}.html", post.title, content)

    def _ad_slot(self) -> str:
        pub = html.escape(self.adsense_publisher_id or "ca-pub-3870943054399059")
        return f"""<div class="ad-slot">
          <ins class="adsbygoogle" style="display:block" data-ad-client="{pub}"
               data-ad-format="auto" data-full-width-responsive="true"></ins>
          <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
        </div>"""

    def _write_index(self, posts: list[Post]) -> None:
        if posts:
            cards = "\n".join(
                f"""
                <article class="card">
                  {f'<a href="./{post.slug}.html"><img class="card-img" src="{html.escape(post.cover_image)}" alt="{html.escape(post.cover_image_alt)}" loading="lazy"></a>' if post.cover_image else ''}
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
          <p class="meta">오늘의 생활·기술·정책 브리핑</p>
          <h1>{html.escape(self.site_title)}</h1>
          <p><a href="./dashboard.html">운영 현황</a></p>
        </section>
        <section class="grid">{cards}</section>
        """
        self._write_html("index.html", self.site_title, content)

    def _write_dashboard(self, posts: list[Post]) -> None:
        category_counts: dict[str, int] = {}
        for post in posts:
            category_counts[post.category] = category_counts.get(post.category, 0) + 1
        category_rows = "\n".join(
            f"<tr><td>{html.escape(category)}</td><td>{count}</td></tr>"
            for category, count in sorted(category_counts.items())
        )
        recent_rows = "\n".join(
            f"""
            <tr>
              <td><a href="./{post.slug}.html">{html.escape(post.title)}</a></td>
              <td>{html.escape(post.category)}</td>
              <td>{post.date:%Y-%m-%d}</td>
            </tr>
            """
            for post in posts[:20]
        )
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">블로그 홈</a>
          <header>
            <p class="meta">브리핑웨이브 운영 현황</p>
            <h1>채널 대시보드</h1>
          </header>
          <section class="stats">
            <div><strong>{len(posts)}</strong><span>발행 글</span></div>
            <div><strong>{len(category_counts)}</strong><span>카테고리</span></div>
          </section>
          <h2>카테고리</h2>
          <table>
            <thead><tr><th>카테고리</th><th>글 수</th></tr></thead>
            <tbody>{category_rows or '<tr><td colspan="2">아직 글이 없습니다.</td></tr>'}</tbody>
          </table>
          <h2>최근 글</h2>
          <table>
            <thead><tr><th>제목</th><th>카테고리</th><th>날짜</th></tr></thead>
            <tbody>{recent_rows or '<tr><td colspan="3">아직 글이 없습니다.</td></tr>'}</tbody>
          </table>
        </article>
        """
        self._write_html("dashboard.html", f"{self.site_title} 운영 현황", content)

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
    <description>오늘 꼭 확인할 생활·기술·정책 소식을 정리합니다.</description>
    <link>./</link>
    {items}
  </channel>
</rss>
"""
        (self.public_dir / "feed.xml").write_text(feed, encoding="utf-8")

    def _write_html(self, filename: str, title: str, content: str) -> None:
        ga_script = ""
        if self.ga_measurement_id:
            mid = html.escape(self.ga_measurement_id)
            ga_script = f"""
  <script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{mid}');
  </script>"""

        pub = html.escape(self.adsense_publisher_id or "ca-pub-3870943054399059")
        adsense_script = (
            f'\n  <meta name="google-adsense-account" content="{pub}">'
            f'\n  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        )

        page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(self.site_title)}">
  <link rel="stylesheet" href="./style.css">
  <link rel="alternate" type="application/rss+xml" href="./feed.xml">{ga_script}{adsense_script}
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
.cover { width: 100%; max-height: 420px; object-fit: cover; border-radius: 6px; margin-bottom: 20px; display: block; }
.ad-slot { margin: 24px 0; min-height: 90px; }
.card-img { width: 100%; height: 180px; object-fit: cover; border-radius: 6px 6px 0 0; display: block; margin: -20px -20px 14px; width: calc(100% + 40px); }
.empty { padding: 24px 0; color: var(--muted); }
.stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 24px 0; }
.stats div { border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: #faf7ef; }
.stats strong { display: block; font-size: 2rem; line-height: 1; }
.stats span { color: var(--muted); font-size: 0.9rem; }
@media (max-width: 640px) {
  main { width: min(100% - 20px, 1040px); padding-top: 20px; }
  .post { padding: 18px; }
  .stats { grid-template-columns: 1fr; }
}
"""
        (self.public_dir / "style.css").write_text(css.strip() + "\n", encoding="utf-8")

    def _write_cname(self) -> None:
        if self.custom_domain:
            (self.public_dir / "CNAME").write_text(self.custom_domain.strip() + "\n", encoding="utf-8")

    def _copy_assets(self) -> None:
        assets_dir = self.posts_dir.parent / "assets"
        if not assets_dir.exists():
            return
        target_dir = self.public_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in assets_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, target_dir / path.name)

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
