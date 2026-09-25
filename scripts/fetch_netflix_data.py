"""Collect titles currently offered by Netflix in South Korea via JustWatch.

The maintained ``simple-justwatch-python-api`` client uses the JustWatch
GraphQL endpoint.  JustWatch caps one result window at 1,999 entries, so this
collector partitions requests by release year and object type (movie/show),
then de-duplicates the stable entry IDs while streaming a JSON array to disk.

JustWatch and this Python package are independent services.  Review their
terms and robots/rate-limit policies before running a large collection job.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import random
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "netflix_raw_data.json"
COUNTRY = "KR"
LANGUAGE = "ko"
LOCALE = "ko_KR"
PROVIDER = "nfx"
MAX_RESULT_WINDOW = 1999
LOGGER = logging.getLogger("briefwave.justwatch")

GENRES: dict[str, tuple[str, str]] = {
    "act": ("액션", "action"),
    "ani": ("애니메이션", "animation"),
    "cmy": ("코미디", "comedy"),
    "crm": ("범죄", "crime"),
    "doc": ("다큐멘터리", "documentary"),
    "drm": ("드라마", "drama"),
    "fml": ("가족", "family"),
    "fnt": ("판타지", "fantasy"),
    "hst": ("역사", "history"),
    "hrr": ("공포", "horror"),
    "msc": ("음악", "music"),
    "msm": ("음악", "music"),
    "rly": ("리얼리티", "reality"),
    "rma": ("로맨스", "romance"),
    "scf": ("SF", "science-fiction"),
    "spt": ("스포츠", "sports"),
    "trl": ("스릴러", "thriller"),
    "war": ("전쟁", "war"),
    "wst": ("서부", "western"),
}


def _value(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _absolute_justwatch_url(value: str | None) -> str:
    url = str(value or "").strip()
    if not url:
        return "https://www.justwatch.com/kr"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://www.justwatch.com{url if url.startswith('/') else '/' + url}"


def _scoring(value: object | None) -> dict[str, float | int | bool | None]:
    if not value:
        return {}
    names = ("imdb_score", "imdb_votes", "tmdb_popularity", "tmdb_score", "tomatometer", "jw_rating")
    return {name: _value(value, name) for name in names if _value(value, name) is not None}


def normalize_entry(entry: object, *, collected_at: str) -> dict[str, Any]:
    """Convert a package MediaEntry into the stable raw-data contract."""
    genre_ids = [str(code).strip().lower() for code in (_value(entry, "genres", []) or []) if str(code).strip()]
    genres = [GENRES.get(code, (code.upper(), code))[0] for code in genre_ids]
    genre_slugs = [GENRES.get(code, (code.upper(), code))[1] for code in genre_ids]
    object_type = str(_value(entry, "object_type", "")).upper()
    if object_type not in {"MOVIE", "SHOW"}:
        raise ValueError(f"unsupported JustWatch object type: {object_type or 'missing'}")
    entry_id = str(_value(entry, "entry_id") or _value(entry, "id") or "").strip()
    title = str(_value(entry, "title") or "").strip()
    year = int(_value(entry, "release_year") or 0)
    synopsis = str(_value(entry, "short_description") or "").strip()
    poster_url = str(_value(entry, "poster") or "").strip()
    if not entry_id or not title or year < 1888 or not synopsis or not poster_url:
        raise ValueError("entry id, Korean title, release year, synopsis and poster are required")
    return {
        "id": entry_id,
        "object_id": int(_value(entry, "object_id") or 0),
        "title": title,
        "release_year": year,
        "release_date": str(_value(entry, "release_date") or ""),
        "genre_ids": genre_ids,
        "genres": genres or ["기타"],
        "genre_slugs": genre_slugs or ["other"],
        "synopsis": synopsis,
        "poster_url": poster_url,
        "backdrop_urls": list(_value(entry, "backdrops", []) or []),
        "content_type": "movie" if object_type == "MOVIE" else "tv",
        "runtime_minutes": int(_value(entry, "runtime_minutes") or 0),
        "season_count": int(_value(entry, "total_season_count") or 0),
        "episode_count": int(_value(entry, "total_episode_count") or 0),
        "age_certification": str(_value(entry, "age_certification") or "").strip(),
        "imdb_id": str(_value(entry, "imdb_id") or "").strip(),
        "tmdb_id": str(_value(entry, "tmdb_id") or "").strip(),
        "scoring": _scoring(_value(entry, "scoring")),
        "source_url": _absolute_justwatch_url(_value(entry, "url")),
        "provider": PROVIDER,
        "locale": LOCALE,
        "collected_at": collected_at,
    }


def _load_api() -> tuple[Any, Any, Any, str]:
    try:
        from simplejustwatchapi import popular
        from simplejustwatchapi.justwatch import _GRAPHQL_API_URL
        from simplejustwatchapi.query import parse_popular_response, prepare_popular_request
    except ImportError as exc:  # pragma: no cover - exercised by CLI environment
        raise SystemExit("Install dependencies first: pip install -e .") from exc
    return popular, prepare_popular_request, parse_popular_response, _GRAPHQL_API_URL


def _fetch_page_sync(*, year: int, object_type: str, offset: int, count: int) -> list[object]:
    """Call the public API, with a compatibility path for package 0.19.

    Release-year/type filters landed after the 0.19 public signature.  The
    compatibility path still delegates query creation and response parsing to
    the package, adding only the two documented TitleFilter fields.
    """
    popular, prepare_request, parse_response, endpoint = _load_api()
    signature = inspect.signature(popular)
    if "min_release_year" in signature.parameters:
        return popular(
            country=COUNTRY,
            language=LANGUAGE,
            count=count,
            best_only=True,
            offset=offset,
            providers=[PROVIDER],
            min_release_year=year,
            max_release_year=year,
            object_types=[object_type],
        )

    import httpx

    request = prepare_request(COUNTRY, LANGUAGE, count, True, offset, [PROVIDER])
    title_filter = request["variables"].setdefault("popularTitlesFilter", {})
    title_filter.update({"releaseYear": {"min": year, "max": year}, "objectTypes": [object_type]})
    response = httpx.post(endpoint, json=request, timeout=45.0)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"JustWatch GraphQL error: {payload['errors']}")
    return parse_response(payload)


def _status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


async def fetch_page_with_backoff(
    *, year: int, object_type: str, offset: int, count: int, delay: float, retries: int
) -> list[object]:
    for attempt in range(retries + 1):
        try:
            # The package is synchronous; isolate it from the asyncio event loop.
            result = await asyncio.to_thread(
                _fetch_page_sync, year=year, object_type=object_type, offset=offset, count=count
            )
            # Deliberate inter-page pause protects the public endpoint from bursts.
            await asyncio.sleep(delay + random.uniform(0, max(0.05, delay * 0.2)))
            return result
        except Exception as exc:
            status = _status_code(exc)
            if attempt >= retries or (status is not None and status not in {429, 500, 502, 503, 504}):
                raise
            wait_seconds = max(delay, 1.0) * (2 ** attempt) + random.uniform(0, 0.5)
            LOGGER.warning("JustWatch %s; retry %s/%s in %.1fs", status or type(exc).__name__, attempt + 1, retries, wait_seconds)
            await asyncio.sleep(wait_seconds)
    return []


def _partitions(min_year: int, max_year: int, _sort_by: str) -> Iterable[tuple[int, str]]:
    # Each API page is sorted by POPULAR.  Year partitions are traversed newest
    # first so both supported modes have deterministic, release-aware output.
    years = range(max_year, min_year - 1, -1)
    for year in years:
        yield year, "MOVIE"
        yield year, "SHOW"


async def collect(args: argparse.Namespace) -> dict[str, int | str]:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    seen: set[str] = set()
    written = pages = rejected = 0
    collected_at = datetime.now(timezone.utc).isoformat()

    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write("[\n")
            first = True
            stop = False
            for year, object_type in _partitions(args.min_year, args.max_year, args.sort_by):
                offset = 0
                while offset < MAX_RESULT_WINDOW:
                    page_size = min(args.page_size, MAX_RESULT_WINDOW - offset)
                    entries = await fetch_page_with_backoff(
                        year=year,
                        object_type=object_type,
                        offset=offset,
                        count=page_size,
                        delay=args.delay,
                        retries=args.retries,
                    )
                    pages += 1
                    if not entries:
                        break
                    for entry in entries:
                        try:
                            record = normalize_entry(entry, collected_at=collected_at)
                        except (TypeError, ValueError) as exc:
                            rejected += 1
                            LOGGER.warning("Skip invalid JustWatch entry: %s", exc)
                            continue
                        if record["id"] in seen:
                            continue
                        seen.add(record["id"])
                        if not first:
                            handle.write(",\n")
                        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                        first = False
                        written += 1
                        if args.limit and written >= args.limit:
                            stop = True
                            break
                    handle.flush()
                    if stop or len(entries) < page_size:
                        break
                    offset += page_size
                LOGGER.info("year=%s type=%s collected=%s", year, object_type, written)
                if stop:
                    break
            handle.write("\n]\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(args.output)
    except BaseException:
        with suppress(FileNotFoundError):
            temporary.unlink()
        raise

    report: dict[str, int | str] = {
        "output": str(args.output),
        "records": written,
        "pages": pages,
        "rejected": rejected,
        "provider": PROVIDER,
        "locale": LOCALE,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.limit and written < args.limit:
        LOGGER.warning("Requested %s records, but the current KR Netflix catalog returned %s unique records", args.limit, written)
    return report


def parser() -> argparse.ArgumentParser:
    current_year = datetime.now().year
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    command.add_argument("--limit", type=int, default=20_000, help="0 collects every available result")
    command.add_argument("--page-size", type=int, default=99)
    command.add_argument("--delay", type=float, default=0.75, help="minimum delay between requests")
    command.add_argument("--retries", type=int, default=5)
    command.add_argument("--min-year", type=int, default=1900)
    command.add_argument("--max-year", type=int, default=current_year + 1)
    command.add_argument("--sort-by", choices=("popularity", "release_year"), default="popularity")
    command.add_argument("--verbose", action="store_true")
    return command


def main() -> None:
    args = parser().parse_args()
    if not 1 <= args.page_size <= 99:
        raise SystemExit("--page-size must be between 1 and 99")
    if args.min_year > args.max_year or args.delay < 0 or args.limit < 0:
        raise SystemExit("invalid year range, delay, or limit")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()
