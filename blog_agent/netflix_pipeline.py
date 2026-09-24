from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator


NETFLIX_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "post_type", "title", "summary_box", "synopsis", "characters",
        "viewing_points", "ending_analysis", "review_summary",
    ],
    "properties": {
        "post_type": {"const": "ENTERTAINMENT_NETFLIX"},
        "title": {"type": "string"},
        "summary_box": {
            "type": "object",
            "required": ["genre_rating", "episodes_runtime", "casting_direction"],
            "properties": {
                "genre_rating": {"type": "string"},
                "episodes_runtime": {"type": "string"},
                "casting_direction": {"type": "string"},
            },
        },
        "synopsis": {"type": "string"},
        "characters": {"type": "array", "items": {"type": "object"}},
        "viewing_points": {"type": "array", "minItems": 3, "maxItems": 3},
        "ending_analysis": {"type": "string"},
        "review_summary": {
            "type": "object",
            "required": ["strengths", "weaknesses"],
            "properties": {
                "strengths": {"type": "array", "minItems": 3, "maxItems": 3},
                "weaknesses": {"type": "array", "minItems": 2, "maxItems": 2},
            },
        },
    },
}

NETFLIX_CONTENT_SYSTEM_PROMPT = """당신은 OTT 콘텐츠 전문 에디터다. 입력으로 제공된 TMDB 메타데이터, 공식 발표, 관람객 리뷰만 사용한다.
출력 post_type은 반드시 ENTERTAINMENT_NETFLIX다. 입력에 없는 사건, 인물 관계, 복선, 시즌 계획, 평점은 창작하지 마라.
공식 후속 시즌 발표와 해석·예상은 명확히 구분하고, 근거가 없으면 '공식 발표 없음'이라고 간결하게 표시하라.
실제 관람평 문장 안에서만 장점 3개와 단점 2개를 추출하고 욕설·스포일러·도배 문장은 사용하지 마라.
'AI가 분석한 바에 따르면' 같은 기계적인 서두를 쓰지 말고 사람이 쓴 듯 자연스럽고 간결한 한국어 문체를 사용하라.
상단 요약은 장르 및 시청 등급, 총 회차/러닝타임, 주요 캐스팅 및 연출 순서로 작성한다.
본문은 제목을 포함한 다음 4단 구조로 작성한다: 시놉시스 및 주요 등장인물, 놓치면 안 될 핵심 관전 포인트 3가지, 결말 해석 및 시즌 후속작 떡밥, 국내외 관람객 호불호 평점 요약.
응답은 제공된 JSON Schema를 엄격하게 만족하는 JSON 객체만 출력하라.
"""

NETFLIX_RUNTIME_JS = r"""(function(){
  function idle(callback){if('requestIdleCallback' in window)requestIdleCallback(callback,{timeout:2500});else setTimeout(callback,1500);}
  idle(function(){
    var first=document.scripts[0],gtm=document.createElement('script');gtm.async=true;gtm.src='https://www.googletagmanager.com/gtm.js?id=GTM-PRH78BZK';first.parentNode.insertBefore(gtm,first);
    if(__GA_ID__){var ga=document.createElement('script');ga.async=true;ga.src='https://www.googletagmanager.com/gtag/js?id='+__GA_ID__;document.head.appendChild(ga);window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments);};gtag('js',new Date());gtag('config',__GA_ID__);}
    if(__ADSENSE_ID__){var ad=document.createElement('script');ad.async=true;ad.crossOrigin='anonymous';ad.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+__ADSENSE_ID__;document.head.appendChild(ad);}
  });
  var q=document.getElementById('header-q'),button=document.getElementById('header-search-btn');
  function prefix(){var host=document.querySelector('[data-product-catalog]');var value=host&&host.getAttribute('data-product-catalog');return value?value.replace('product-catalog.json',''):'../../../';}
  function go(){if(q&&q.value.trim())location.href=prefix()+'search.html?q='+encodeURIComponent(q.value.trim());}
  if(button)button.addEventListener('click',go);
  if(q)q.addEventListener('keydown',function(event){if(event.key==='Enter')go();});
  document.querySelectorAll('[data-product-rotation]').forEach(function(host){
    var catalogUrl=host.getAttribute('data-product-catalog');
    var data=host.querySelector('.product-rotation-candidates');
    if(!catalogUrl||!data)return;
    fetch(catalogUrl).then(function(response){return response.json();}).then(function(catalog){
      var candidates=[];try{candidates=JSON.parse(data.textContent||'[]');}catch(error){return;}
      candidates=candidates.filter(function(code){return catalog[code]&&catalog[code].html;});
      if(candidates.length<2)return;
      var selected=candidates[Math.floor(Math.random()*candidates.length)];
      var card=host.querySelector('.product-recommendation');
      if(card)card.outerHTML=catalog[selected].html;
    }).catch(function(){});
  });
})();
"""


@dataclass(frozen=True)
class NetflixRecord:
    content_id: str
    content_type: str
    title: str
    slug: str
    genre: str
    genre_slug: str
    year: int
    age_rating: str
    episodes_runtime: str
    director: str
    cast: tuple[str, ...]
    synopsis: str
    characters: tuple[tuple[str, str], ...]
    viewing_points: tuple[str, ...]
    ending_analysis: str
    review_strengths: tuple[str, ...]
    review_weaknesses: tuple[str, ...]
    poster_url: str
    poster_alt: str
    source_url: str
    reviews_source_url: str
    updated_at: str
    is_fixture: bool = False

    def output_path(self, *, dry_run: bool) -> str:
        base = "staging/netflix" if dry_run else "netflix"
        return f"{base}/{self.genre_slug}/{self.year}/{self.slug}.html"

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"netflix field '{key}' is required")
    return value


def parse_netflix_record(raw: dict[str, Any], *, dry_run: bool) -> NetflixRecord:
    if raw.get("post_type") != "ENTERTAINMENT_NETFLIX":
        raise ValueError("post_type must be ENTERTAINMENT_NETFLIX")
    content_type = _text(raw, "content_type").lower()
    if content_type not in {"movie", "tv"}:
        raise ValueError("content_type must be movie or tv")
    slug = _text(raw, "slug")
    genre_slug = _text(raw, "genre_slug")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if not slug or set(slug) - allowed or not genre_slug or set(genre_slug) - allowed:
        raise ValueError("slug and genre_slug must be lowercase ASCII words")
    year = int(raw.get("year") or 0)
    if year < 1900 or year > 2100:
        raise ValueError(f"invalid release year: {year}")
    summary = raw.get("summary_box") or {}
    characters_raw = raw.get("characters") or []
    characters = tuple(
        (_text(item, "name"), _text(item, "relationship"))
        for item in characters_raw if isinstance(item, dict)
    )
    points = tuple(str(item).strip() for item in raw.get("viewing_points", []) if str(item).strip())
    reviews = raw.get("review_summary") or {}
    strengths = tuple(str(item).strip() for item in reviews.get("strengths", []) if str(item).strip())
    weaknesses = tuple(str(item).strip() for item in reviews.get("weaknesses", []) if str(item).strip())
    if len(points) != 3 or len(strengths) != 3 or len(weaknesses) != 2:
        raise ValueError("viewing_points/strengths/weaknesses must contain exactly 3/3/2 items")
    if not characters:
        raise ValueError("at least one character relationship is required")
    is_fixture = bool(raw.get("is_fixture"))
    if is_fixture and not dry_run:
        raise ValueError("fixture Netflix data cannot be published")
    return NetflixRecord(
        content_id=_text(raw, "id"),
        content_type=content_type,
        title=_text(raw, "title"),
        slug=slug,
        genre=_text(raw, "genre"),
        genre_slug=genre_slug,
        year=year,
        age_rating=_text(summary, "genre_rating"),
        episodes_runtime=_text(summary, "episodes_runtime"),
        director=_text(raw, "director"),
        cast=tuple(str(item).strip() for item in raw.get("cast", []) if str(item).strip()),
        synopsis=_text(raw, "synopsis"),
        characters=characters,
        viewing_points=points,
        ending_analysis=_text(raw, "ending_analysis"),
        review_strengths=strengths,
        review_weaknesses=weaknesses,
        poster_url=_text(raw, "poster_url"),
        poster_alt=_text(raw, "poster_alt"),
        source_url=_text(raw, "source_url"),
        reviews_source_url=_text(raw, "reviews_source_url"),
        updated_at=_text(raw, "updated_at"),
        is_fixture=is_fixture,
    )


def stream_json_items(path: Path, *, read_size: int = 1024 * 1024) -> Iterator[dict[str, Any]]:
    """Yield objects from JSONL or a top-level JSON array without loading the file."""
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"line {line_number} must be a JSON object")
                yield value
        return

    decoder = json.JSONDecoder()
    buffer = ""
    started = False
    ended = False
    with path.open("r", encoding="utf-8") as handle:
        while not ended:
            chunk = handle.read(read_size)
            if chunk:
                buffer += chunk
            elif not buffer.strip():
                break
            while True:
                buffer = buffer.lstrip()
                if not started:
                    if not buffer:
                        break
                    if buffer[0] != "[":
                        raise ValueError("JSON input must be JSONL or a top-level array")
                    buffer = buffer[1:]
                    started = True
                    continue
                buffer = buffer.lstrip()
                if buffer.startswith("]"):
                    ended = True
                    buffer = buffer[1:]
                    break
                if buffer.startswith(","):
                    buffer = buffer[1:]
                    continue
                if not buffer:
                    break
                try:
                    value, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk:
                        raise
                    break
                if not isinstance(value, dict):
                    raise ValueError("each array item must be a JSON object")
                yield value
                buffer = buffer[end:]
            if not chunk and not ended:
                raise ValueError("unterminated JSON array")


def chunked_records(path: Path, *, chunk_size: int = 1000, limit: int | None = None) -> Iterator[list[dict[str, Any]]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    chunk: list[dict[str, Any]] = []
    emitted = 0
    for item in stream_json_items(path):
        if limit is not None and emitted >= limit:
            break
        chunk.append(item)
        emitted += 1
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _render_chunk(task: dict[str, Any]) -> dict[str, Any]:
    from .site import StaticSiteBuilder

    builder = StaticSiteBuilder(
        posts_dir=Path(task["posts_dir"]),
        public_dir=Path(task["public_dir"]),
        site_title=task["site_title"],
        site_description=task["site_description"],
        custom_domain=task["custom_domain"],
        categories=task["categories"],
        ga_measurement_id=task["ga_measurement_id"],
        adsense_publisher_id=task["adsense_publisher_id"],
    )
    cache_root = Path(task["cache_dir"]) / ("dry-run" if task["dry_run"] else "production")
    entries: list[tuple[str, str]] = []
    rendered = cached = 0
    for raw in task["records"]:
        record = parse_netflix_record(raw, dry_run=task["dry_run"])
        filename = record.output_path(dry_run=task["dry_run"])
        target = Path(task["public_dir"]) / filename
        cache_path = cache_root / filename
        digest_path = cache_path.with_suffix(".sha256")
        digest = hashlib.sha256(f"netflix-v1:{task['version']}:{record.fingerprint}".encode()).hexdigest()
        target.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and digest_path.exists() and digest_path.read_text().strip() == digest:
            shutil.copy2(cache_path, target)
            cached += 1
        else:
            builder._write_netflix_post(record, dry_run=task["dry_run"])
            source = target.read_text(encoding="utf-8")
            required = ("toss-shopping-card", "<details", "application/ld+json", "movie-poster")
            if any(marker not in source for marker in required):
                raise RuntimeError(f"mandatory Netflix markup missing: {filename}")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, cache_path)
            digest_path.write_text(digest + "\n", encoding="utf-8")
            rendered += 1
        entries.append((builder._page_url(filename), record.updated_at))
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        max_rss //= 1024
    return {
        "chunk_index": task["chunk_index"],
        "entries": entries,
        "rendered": rendered,
        "cached": cached,
        "max_rss_kb": max_rss,
    }


def _write_urlset(path: Path, entries: list[tuple[str, str]]) -> None:
    from xml.sax.saxutils import escape
    rows = "".join(
        f"  <url><loc>{escape(url)}</loc><lastmod>{escape(updated[:10])}</lastmod></url>\n"
        for url, updated in entries
    )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{rows}</urlset>\n",
        encoding="utf-8",
    )


def build_netflix_site(
    input_path: Path,
    *,
    public_dir: Path,
    posts_dir: Path,
    site_title: str,
    site_description: str,
    custom_domain: str | None,
    categories: list[str],
    ga_measurement_id: str | None,
    adsense_publisher_id: str | None,
    cache_dir: Path,
    chunk_size: int = 1000,
    limit: int | None = None,
    dry_run: bool = False,
    workers: int | None = None,
) -> dict[str, int]:
    from .product_links import PRODUCT_LINKS

    public_dir.mkdir(parents=True, exist_ok=True)
    runtime = NETFLIX_RUNTIME_JS.replace("__GA_ID__", json.dumps(ga_measurement_id or ""))
    runtime = runtime.replace("__ADSENSE_ID__", json.dumps(adsense_publisher_id or "ca-pub-3870943054399059"))
    (public_dir / "netflix-runtime.js").write_text(runtime, encoding="utf-8")

    template_path = Path(__file__).with_name("templates") / "netflix-post.html"
    version_material = (
        template_path.read_text(encoding="utf-8")
        + (Path(__file__).with_name("site.py").read_text(encoding="utf-8"))
        + "|".join(f"{item.name}:{item.url}" for item in PRODUCT_LINKS)
    )
    version = hashlib.sha256(version_material.encode("utf-8")).hexdigest()
    max_workers = workers or (os.cpu_count() or 1)
    max_workers = max(1, max_workers)
    stats = {"chunks": 0, "records": 0, "rendered": 0, "cached": 0, "max_worker_rss_kb": 0}
    sitemap_names: list[tuple[int, str]] = []

    common = {
        "posts_dir": str(posts_dir), "public_dir": str(public_dir),
        "site_title": site_title, "site_description": site_description,
        "custom_domain": custom_domain, "categories": categories,
        "ga_measurement_id": ga_measurement_id,
        "adsense_publisher_id": adsense_publisher_id,
        "cache_dir": str(cache_dir), "dry_run": dry_run, "version": version,
    }
    chunks = enumerate(chunked_records(input_path, chunk_size=chunk_size, limit=limit), 1)
    pending: set[Any] = set()
    seen_paths: set[str] = set()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        exhausted = False
        while pending or not exhausted:
            while len(pending) < max_workers and not exhausted:
                try:
                    chunk_index, records = next(chunks)
                except StopIteration:
                    exhausted = True
                    break
                for raw in records:
                    key = f"{raw.get('genre_slug')}/{raw.get('year')}/{raw.get('slug')}"
                    if key in seen_paths:
                        raise ValueError(f"duplicate Netflix output path: {key}")
                    seen_paths.add(key)
                pending.add(executor.submit(_render_chunk, {**common, "chunk_index": chunk_index, "records": records}))
            if not pending:
                continue
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                result = future.result()
                sitemap_prefix = "sitemap-netflix-canary" if dry_run else "sitemap-netflix"
                sitemap_name = f"{sitemap_prefix}-{result['chunk_index']}.xml"
                _write_urlset(public_dir / sitemap_name, result["entries"])
                sitemap_names.append((result["chunk_index"], sitemap_name))
                stats["chunks"] += 1
                stats["records"] += len(result["entries"])
                stats["rendered"] += result["rendered"]
                stats["cached"] += result["cached"]
                stats["max_worker_rss_kb"] = max(stats["max_worker_rss_kb"], result["max_rss_kb"])

    site_url = f"https://{custom_domain.strip()}" if custom_domain else "https://briefwave.kr"
    rows = "".join(
        f"  <sitemap><loc>{site_url}/{name}</loc></sitemap>\n"
        for _, name in sorted(sitemap_names)
    )
    sitemap_index_name = "sitemap-netflix-canary.xml" if dry_run else "sitemap-netflix.xml"
    (public_dir / sitemap_index_name).write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{rows}</sitemapindex>\n",
        encoding="utf-8",
    )
    if not dry_run:
        robots = public_dir / "robots.txt"
        sitemap_line = f"Sitemap: {site_url}/sitemap-netflix.xml"
        current = robots.read_text(encoding="utf-8") if robots.exists() else "User-agent: *\nAllow: /\n"
        if sitemap_line not in current:
            robots.write_text(current.rstrip() + "\n" + sitemap_line + "\n", encoding="utf-8")
    return stats
