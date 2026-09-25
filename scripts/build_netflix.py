"""Multiprocess SSG builder for the Korean Netflix JustWatch catalog.

Input is streamed from a top-level JSON array, grouped into bounded 1,000-item
chunks, and submitted to ``ProcessPoolExecutor``.  Each worker renders its own
chunk and writes the matching child sitemap; the parent only keeps a bounded
number of in-flight chunks and finally writes the sitemap index.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blog_agent.netflix_pipeline import NETFLIX_RUNTIME_JS, chunked_records
from blog_agent.site import Post, StaticSiteBuilder

DEFAULT_INPUT = ROOT / "data" / "netflix_raw_data.json"
DEFAULT_DIST = ROOT / "dist"
TEMPLATE_PATH = ROOT / "blog_agent" / "templates" / "netflix-catalog-post.html"
GENRE_SLUGS = {
    "action", "animation", "comedy", "crime", "documentary", "drama", "family",
    "fantasy", "history", "horror", "music", "reality", "romance",
    "science-fiction", "sports", "thriller", "war", "western", "other",
}
CATALOG_PAGE_SIZE = 100
DISCOVERY_STYLE_MARKER = "/* Netflix discovery */"


def _required(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"Netflix raw field '{key}' is required")
    return value


def _slug(raw: dict[str, Any]) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9]+", "-", _required(raw, "id")).strip("-").lower()
    ascii_title = unicodedata.normalize("NFKD", _required(raw, "title")).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_title).strip("-").lower()[:52].strip("-")
    if len(re.sub(r"[^a-z]", "", words)) < 3:
        words = ""
    content_type = "movie" if raw.get("content_type") == "movie" else "series"
    return f"{words}-{identifier}" if words else f"netflix-{content_type}-{identifier}"


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    content_type = _required(raw, "content_type").lower()
    if content_type not in {"movie", "tv"}:
        raise ValueError("content_type must be movie or tv")
    year = int(raw.get("release_year") or 0)
    if year < 1888 or year > datetime.now().year + 2:
        raise ValueError(f"invalid release year: {year}")
    genres = [str(value).strip() for value in raw.get("genres", []) if str(value).strip()]
    genre_slugs = [str(value).strip().lower() for value in raw.get("genre_slugs", []) if str(value).strip()]
    genre_slug = next((value for value in genre_slugs if value in GENRE_SLUGS), "other")
    collected_at = _required(raw, "collected_at")
    datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    return {
        **raw,
        "id": _required(raw, "id"),
        "title": _required(raw, "title"),
        "synopsis": _required(raw, "synopsis"),
        "poster_url": _required(raw, "poster_url"),
        "source_url": _required(raw, "source_url"),
        "content_type": content_type,
        "release_year": year,
        "genres": genres or ["기타"],
        "genre_slug": genre_slug,
        "slug": _slug(raw),
        "collected_at": collected_at,
    }


def _runtime(record: dict[str, Any]) -> str:
    if record["content_type"] == "movie" and int(record.get("runtime_minutes") or 0):
        return f"{int(record['runtime_minutes'])}분"
    pieces = []
    if int(record.get("season_count") or 0):
        pieces.append(f"{int(record['season_count'])}시즌")
    if int(record.get("episode_count") or 0):
        pieces.append(f"{int(record['episode_count'])}화")
    if int(record.get("runtime_minutes") or 0):
        pieces.append(f"회당 {int(record['runtime_minutes'])}분")
    return " · ".join(pieces) or "회차 정보 없음"


def _sitemap_xml(entries: list[tuple[str, str]]) -> str:
    rows = "".join(
        f"  <url><loc>{xml_escape(url)}</loc><lastmod>{xml_escape(lastmod[:10])}</lastmod></url>\n"
        for url, lastmod in entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{rows}</urlset>\n"
    )


def _render_record(builder: StaticSiteBuilder, template_text: str, raw: dict[str, Any]) -> tuple[str, str]:
    record = normalize_record(raw)
    filename = f"netflix/{record['genre_slug']}/{record['release_year']}/{record['slug']}.html"
    asset_prefix = "../../../"
    page_url = builder._page_url(filename)
    genres = ", ".join(record["genres"])
    runtime = _runtime(record)
    collected_date = record["collected_at"][:10]
    content_label = "영화" if record["content_type"] == "movie" else "시리즈"
    facts = [
        f"콘텐츠 유형: {content_label}",
        f"공개 연도: {record['release_year']}년",
        f"장르: {genres}",
        f"러닝타임/회차: {runtime}",
    ]
    scoring = record.get("scoring") or {}
    if scoring.get("imdb_score") is not None:
        facts.append(f"IMDb 평점: {scoring['imdb_score']}")

    post_date = datetime.fromisoformat(record["collected_at"].replace("Z", "+00:00"))
    product_post = Post(
        title=f"{record['title']} 넷플릭스 정주행",
        date=post_date,
        category="영화",
        tags=[*record["genres"], "넷플릭스", "정주행", "홈시네마"],
        slug=f"netflix-{record['slug']}",
        excerpt=record["synopsis"][:160],
        body_html=f"<p>{html.escape(record['synopsis'])}</p>",
    )
    breadcrumb = builder._breadcrumb_html([
        ("홈", asset_prefix),
        ("넷플릭스", f"{asset_prefix}search.html?q=넷플릭스"),
        (record["genres"][0], f"{asset_prefix}search.html?q={html.escape(record['genres'][0])}"),
        (record["title"], page_url),
    ])
    content = Template(template_text).substitute(
        breadcrumb=breadcrumb,
        poster_url=html.escape(record["poster_url"], quote=True),
        poster_alt=html.escape(f"{record['title']} 포스터", quote=True),
        year=record["release_year"],
        title=html.escape(record["title"]),
        genres=html.escape(genres),
        age_rating=html.escape(str(record.get("age_certification") or "등급 정보 없음")),
        runtime=html.escape(runtime),
        key_facts="".join(f"<li>{html.escape(item)}</li>" for item in facts),
        synopsis=html.escape(record["synopsis"]),
        collected_at=html.escape(record["collected_at"], quote=True),
        collected_date=html.escape(collected_date),
        source_url=html.escape(record["source_url"], quote=True),
        product_widget=builder._product_link_html(
            product_post,
            asset_prefix=asset_prefix,
            bridge_heading="📺 [정주행 필수템] 넷플릭스 몰아보기를 위한 실속 가성비 핫딜",
            bridge_description="밤샘 정주행의 몰입감을 높여줄 간식 특가와 편안한 시청 환경을 만들어줄 홈시네마 추천 아이템을 확인해 보세요.",
        ),
    )
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Movie" if record["content_type"] == "movie" else "TVSeries",
        "name": record["title"],
        "description": record["synopsis"],
        "image": record["poster_url"],
        "dateCreated": str(record["release_year"]),
        "genre": record["genres"],
        "inLanguage": "ko-KR",
        "sameAs": record["source_url"],
    }
    if scoring.get("imdb_score") is not None and scoring.get("imdb_votes"):
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": scoring["imdb_score"],
            "bestRating": 10,
            "ratingCount": scoring["imdb_votes"],
        }
    faq = builder._faq_schema([(
        f"{record['title']}은 현재 한국 넷플릭스에서 볼 수 있나요?",
        f"{collected_date} 수집 시점에 JustWatch의 한국 넷플릭스 제공 목록에서 확인됐습니다. 편성은 변경될 수 있습니다.",
    )])
    builder._write_html(
        filename,
        f"{record['title']} 넷플릭스 시놉시스·작품 정보",
        content,
        active="영화",
        page_url=page_url,
        description=record["synopsis"][:160],
        og_image=record["poster_url"],
        og_type="video.movie" if record["content_type"] == "movie" else "video.tv_show",
        robots="index,follow,max-image-preview:large",
        structured_data=[schema, faq],
        alternate_urls={"ko": page_url, "x-default": page_url},
        asset_prefix=asset_prefix,
        monetize=True,
        og_image_width=500,
        og_image_height=750,
        compact_runtime=True,
    )
    rendered = (builder.public_dir / filename).read_text(encoding="utf-8")
    for marker in ('class="toss-shopping-card product-recommendation"', 'application/ld+json', 'loading="lazy"'):
        if marker not in rendered:
            raise RuntimeError(f"mandatory markup missing ({marker}): {filename}")
    return page_url, record["collected_at"]


def _render_chunk(task: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point: render one bounded chunk and its own sitemap."""
    public_dir = Path(task["public_dir"])
    builder = StaticSiteBuilder(
        posts_dir=Path(task["posts_dir"]),
        public_dir=public_dir,
        site_title=task["site_title"],
        site_description=task["site_description"],
        custom_domain=task["custom_domain"],
        categories=["영화"],
    )
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    entries = [_render_record(builder, template_text, raw) for raw in task["records"]]
    sitemap_name = f"sitemap-netflix-{task['chunk_index']}.xml"
    (public_dir / sitemap_name).write_text(_sitemap_xml(entries), encoding="utf-8")
    return {
        "chunk_index": task["chunk_index"],
        "sitemap": sitemap_name,
        "records": len(entries),
    }


def _prepare_assets(public_dir: Path, posts_dir: Path, custom_domain: str) -> None:
    builder = StaticSiteBuilder(
        posts_dir=posts_dir,
        public_dir=public_dir,
        site_title="브리핑웨이브",
        site_description="한국 넷플릭스 작품 정보",
        custom_domain=custom_domain,
        categories=["영화"],
    )
    public_dir.mkdir(parents=True, exist_ok=True)
    builder._write_css()
    builder._write_product_catalog()
    runtime = NETFLIX_RUNTIME_JS.replace("__GA_ID__", json.dumps(os.getenv("GA_MEASUREMENT_ID", "")))
    runtime = runtime.replace("__ADSENSE_ID__", json.dumps(os.getenv("ADSENSE_PUBLISHER_ID", "ca-pub-3870943054399059")))
    (public_dir / "netflix-runtime.js").write_text(runtime, encoding="utf-8")


def _catalog_card(record: dict[str, Any], *, href_prefix: str = "./") -> str:
    filename = f"{record['genre_slug']}/{record['release_year']}/{record['slug']}.html"
    genres = ", ".join(record["genres"][:2])
    return (
        f'<article class="netflix-catalog-card">'
        f'<a href="{href_prefix}{html.escape(filename, quote=True)}">'
        f'<img src="{html.escape(record["poster_url"], quote=True)}" '
        f'alt="{html.escape(record["title"], quote=True)} 포스터" width="300" height="450" loading="lazy" decoding="async">'
        f'<span class="netflix-card-body"><span class="netflix-card-badge">넷플릭스 · {html.escape(genres)}</span>'
        f'<strong>{html.escape(record["title"])}</strong>'
        f'<small>{record["release_year"]}년 · {"영화" if record["content_type"] == "movie" else "시리즈"}</small>'
        f'</span></a></article>'
    )


def _write_discovery_css(public_dir: Path) -> None:
    path = public_dir / "style.css"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if DISCOVERY_STYLE_MARKER in current:
        return
    css = """
/* Netflix discovery */
.netflix-discovery{margin:2rem 0;padding:1.5rem;border-radius:20px;background:linear-gradient(135deg,#111827,#1f2937);color:#fff}
.netflix-discovery-head{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin-bottom:1rem}.netflix-discovery h2{margin:0;color:#fff}.netflix-discovery p{margin:.45rem 0 0;color:#d1d5db}.netflix-view-all{flex:none;color:#fff;font-weight:800;text-decoration:none;border:1px solid #6b7280;border-radius:999px;padding:.55rem .9rem}
.netflix-catalog-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1rem}.netflix-catalog-card{min-width:0;background:#fff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;box-shadow:0 5px 18px rgba(15,23,42,.09)}.netflix-catalog-card a{display:block;color:#111827;text-decoration:none}.netflix-catalog-card img{display:block;width:100%;aspect-ratio:2/3;object-fit:cover;transition:transform .2s ease}.netflix-catalog-card a:hover img{transform:scale(1.025)}.netflix-card-body{display:grid;gap:.35rem;padding:.8rem}.netflix-card-badge{color:#dc2626;font-size:.75rem;font-weight:800}.netflix-card-body strong{font-size:.98rem;line-height:1.4}.netflix-card-body small{color:#6b7280}.netflix-catalog-page h1{margin-bottom:.35rem}.netflix-catalog-lead{color:#4b5563;margin-bottom:1.5rem}.netflix-pagination{display:flex;justify-content:center;gap:.75rem;align-items:center;margin:2rem 0}.netflix-pagination a{padding:.65rem 1rem;border:1px solid #d1d5db;border-radius:10px;text-decoration:none;font-weight:700}.netflix-pagination span{font-weight:700}
@media(max-width:760px){.netflix-discovery{padding:1.1rem;margin-inline:-.25rem}.netflix-discovery-head{align-items:start}.netflix-catalog-grid{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:.5rem}.netflix-catalog-card{flex:0 0 68%;scroll-snap-align:start}.netflix-catalog-page .netflix-catalog-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:visible}.netflix-catalog-page .netflix-catalog-card{min-width:0}.netflix-view-all{font-size:.82rem}}
"""
    path.write_text(current.rstrip() + "\n" + css, encoding="utf-8")


def _write_catalog_pages(args: argparse.Namespace, records: list[dict[str, Any]]) -> int:
    builder = StaticSiteBuilder(
        posts_dir=args.posts_dir,
        public_dir=args.dist_dir,
        site_title="브리핑웨이브",
        site_description="현재 한국 넷플릭스에서 시청 가능한 영화와 시리즈",
        custom_domain=args.domain,
        categories=["영화"],
    )
    total_pages = max(1, (len(records) + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
    for page_number in range(1, total_pages + 1):
        page_records = records[(page_number - 1) * CATALOG_PAGE_SIZE:page_number * CATALOG_PAGE_SIZE]
        cards = "".join(_catalog_card(record) for record in page_records)
        previous = "index.html" if page_number == 2 else f"page-{page_number - 1}.html"
        following = f"page-{page_number + 1}.html"
        nav = '<nav class="netflix-pagination" aria-label="넷플릭스 목록 페이지">'
        if page_number > 1:
            nav += f'<a href="./{previous}" rel="prev">← 이전</a>'
        nav += f'<span>{page_number} / {total_pages}</span>'
        if page_number < total_pages:
            nav += f'<a href="./{following}" rel="next">다음 →</a>'
        nav += "</nav>"
        content = (
            '<section class="netflix-catalog-page" aria-labelledby="netflix-catalog-title">'
            f'<h1 id="netflix-catalog-title">한국 넷플릭스 작품 전체 목록{f" — {page_number}페이지" if page_number > 1 else ""}</h1>'
            f'<p class="netflix-catalog-lead">수집 시점 기준 {len(records):,}편의 영화와 시리즈를 장르·연도별 상세 정보로 확인하세요.</p>'
            f'<div class="netflix-catalog-grid">{cards}</div>{nav}</section>'
        )
        filename = "netflix/index.html" if page_number == 1 else f"netflix/page-{page_number}.html"
        page_url = builder._page_url(filename)
        schema = {
            "@context": "https://schema.org", "@type": "CollectionPage",
            "name": "한국 넷플릭스 작품 전체 목록", "url": page_url,
            "numberOfItems": len(records),
        }
        builder._write_html(
            filename, f"한국 넷플릭스 작품 전체 목록{f' {page_number}페이지' if page_number > 1 else ''}", content,
            active="영화", page_url=page_url,
            description=f"현재 한국 넷플릭스에서 시청 가능한 영화와 시리즈 {len(records):,}편을 확인하세요.",
            robots="index,follow,max-image-preview:large", structured_data=[schema], asset_prefix="../", monetize=True,
        )
    return total_pages


def _inject_home_discovery(public_dir: Path, records: list[dict[str, Any]]) -> bool:
    path = public_dir / "index.html"
    if not path.exists() or not records:
        return False
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"\n?<!-- NETFLIX_DISCOVERY_START -->.*?<!-- NETFLIX_DISCOVERY_END -->\n?", "\n", source, flags=re.S)
    cards = "".join(_catalog_card(record, href_prefix="./netflix/") for record in records[:10])
    section = (
        '\n<!-- NETFLIX_DISCOVERY_START --><section class="netflix-discovery" aria-labelledby="home-netflix-title">'
        '<div class="netflix-discovery-head"><div><h2 id="home-netflix-title">🎬 지금 볼 수 있는 넷플릭스 작품</h2>'
        '<p>한국 넷플릭스 영화와 시리즈의 줄거리·장르·러닝타임을 한곳에서 확인하세요.</p></div>'
        '<a class="netflix-view-all" href="./netflix/index.html">전체 작품 보기 →</a></div>'
        f'<div class="netflix-catalog-grid">{cards}</div></section><!-- NETFLIX_DISCOVERY_END -->\n'
    )
    if "</main>" not in source:
        return False
    path.write_text(source.replace("</main>", section + "</main>", 1), encoding="utf-8")
    return True


def _extend_search_index(public_dir: Path, records: list[dict[str, Any]]) -> int:
    path = public_dir / "search.json"
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    items = [item for item in items if not str(item.get("url", "")).startswith("./netflix/")]
    for record in records:
        filename = f"netflix/{record['genre_slug']}/{record['release_year']}/{record['slug']}.html"
        items.append({
            "title": record["title"], "slug": record["slug"], "url": f"./{filename}",
            "excerpt": record["synopsis"][:160], "date": record["collected_at"][:10],
            "category": "영화", "tags": [*record["genres"], "넷플릭스"],
            "author": "브리핑웨이브 편집팀", "display_author": "브리핑웨이브 편집팀",
            "aliases": [record["title"], "넷플릭스", *record["genres"]],
        })
    path.write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(items)


def build(args: argparse.Namespace) -> dict[str, int | str]:
    if args.chunk_size < 1 or args.chunk_size > 1000:
        raise ValueError("--chunk-size must be between 1 and 1000")
    max_workers = max(1, args.workers or (os.cpu_count() or 1))
    _prepare_assets(args.dist_dir, args.posts_dir, args.domain)
    chunks = enumerate(chunked_records(args.input, chunk_size=args.chunk_size, limit=args.limit or None), 1)
    pending: set[Any] = set()
    results: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    exhausted = False
    common = {
        "public_dir": str(args.dist_dir),
        "posts_dir": str(args.posts_dir),
        "site_title": "브리핑웨이브",
        "site_description": "한국 넷플릭스 작품 정보",
        "custom_domain": args.domain,
    }

    # Only ``max_workers`` chunks are resident in child processes at once.
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        while pending or not exhausted:
            while len(pending) < max_workers and not exhausted:
                try:
                    chunk_index, records = next(chunks)
                except StopIteration:
                    exhausted = True
                    break
                for raw in records:
                    record = normalize_record(raw)
                    key = f"{record['genre_slug']}/{record['release_year']}/{record['slug']}"
                    if key in seen_paths:
                        raise ValueError(f"duplicate Netflix output path: {key}")
                    seen_paths.add(key)
                pending.add(executor.submit(_render_chunk, {**common, "chunk_index": chunk_index, "records": records}))
            if not pending:
                continue
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            results.extend(future.result() for future in done)

    site_url = f"https://{args.domain.strip().strip('/')}"
    updated = datetime.now(timezone.utc).date().isoformat()
    rows = "".join(
        "  <sitemap>"
        f"<loc>{xml_escape(site_url + '/' + result['sitemap'])}</loc>"
        f"<lastmod>{updated}</lastmod>"
        "</sitemap>\n"
        for result in sorted(results, key=lambda value: value["chunk_index"])
    )
    sitemap_index = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{rows}</sitemapindex>\n"
    )
    index_path = args.dist_dir / "sitemap-netflix-index.xml"
    index_path.write_text(sitemap_index, encoding="utf-8")
    # Compatibility alias for the site's existing deployment workflow.
    (args.dist_dir / "sitemap-netflix.xml").write_text(sitemap_index, encoding="utf-8")
    robots_path = args.dist_dir / "robots.txt"
    robots = robots_path.read_text(encoding="utf-8") if robots_path.exists() else "User-agent: *\nAllow: /\n"
    netflix_sitemap_line = f"Sitemap: {site_url}/sitemap-netflix-index.xml"
    if netflix_sitemap_line not in robots:
        robots_path.write_text(robots.rstrip() + "\n" + netflix_sitemap_line + "\n", encoding="utf-8")
    discovery_records: list[dict[str, Any]] = []
    for raw_chunk in chunked_records(args.input, chunk_size=args.chunk_size, limit=args.limit or None):
        discovery_records.extend(normalize_record(raw) for raw in raw_chunk)
    catalog_pages = _write_catalog_pages(args, discovery_records)
    home_injected = _inject_home_discovery(args.dist_dir, discovery_records)
    search_records = _extend_search_index(args.dist_dir, discovery_records)
    _write_discovery_css(args.dist_dir)
    report: dict[str, int | str] = {
        "input": str(args.input),
        "dist_dir": str(args.dist_dir),
        "workers": max_workers,
        "chunk_size": args.chunk_size,
        "chunks": len(results),
        "records": sum(int(result["records"]) for result in results),
        "catalog_pages": catalog_pages,
        "home_discovery": int(home_injected),
        "search_records": search_records,
        "sitemap_index": str(index_path),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="JSON/JSONL input, optionally gzip-compressed")
    command.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    command.add_argument("--posts-dir", type=Path, default=ROOT / "output" / "posts")
    command.add_argument("--chunk-size", type=int, default=1000)
    command.add_argument("--workers", type=int, default=0, help="0 uses all logical CPU cores")
    command.add_argument("--limit", type=int, default=0, help="0 builds every input record")
    command.add_argument("--domain", default="briefwave.kr")
    return command


def main() -> None:
    args = parser().parse_args()
    if not args.input.exists():
        raise SystemExit(f"input does not exist: {args.input}")
    build(args)


if __name__ == "__main__":
    main()
