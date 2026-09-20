"""Fetch public Toss Shopping aggregate ratings and buyer review excerpts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blog_agent.product_links import PRODUCT_LINKS  # noqa: E402


class JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._active = False
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._active = tag == "script" and dict(attrs).get("type") == "application/ld+json"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._active = False

    def handle_data(self, data: str) -> None:
        if self._active:
            self.documents.append(data)


def product_schema(raw_html: str) -> dict:
    parser = JsonLdParser()
    parser.feed(raw_html)
    for document in parser.documents:
        try:
            value = json.loads(document)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("@type") == "Product":
            return value
    return {}


def fetch_review_data(url: str, timeout: float = 15) -> dict:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 BriefWave/1.0"})
    response.raise_for_status()
    schema = product_schema(response.text)
    aggregate = schema.get("aggregateRating") or {}
    reviews = []
    for review in schema.get("review") or []:
        if not isinstance(review, dict):
            continue
        body = " ".join(str(review.get("reviewBody") or "").split())[:300]
        if not body:
            continue
        reviews.append(
            {
                "author": str((review.get("author") or {}).get("name") or "구매자"),
                "rating": int((review.get("reviewRating") or {}).get("ratingValue") or 0),
                "text": body,
            }
        )
    return {
        "source_url": response.url.split("?", 1)[0],
        "fetched_at": date.today().isoformat(),
        "rating": float(aggregate.get("ratingValue") or 0),
        "review_count": int(aggregate.get("reviewCount") or 0),
        "reviews": reviews[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "blog_agent" / "product_reviews.json")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    result: dict[str, dict] = {}
    for item in PRODUCT_LINKS:
        code = item.url.rsplit("/", 1)[-1]
        try:
            result[code] = fetch_review_data(item.url, timeout=args.timeout)
            print(f"synced {code}: {result[code]['review_count']} reviews")
        except Exception as exc:
            print(f"warning: {code}: {type(exc).__name__}: {exc}", file=sys.stderr)
            result[code] = {
                "source_url": item.url,
                "fetched_at": date.today().isoformat(),
                "rating": 0,
                "review_count": 0,
                "reviews": [],
            }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(result)} products to {args.output}")


if __name__ == "__main__":
    main()
