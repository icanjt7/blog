"""Synchronize Toss Shopping products through the ShareLink Open API.

The API credentials must be supplied through environment variables. Access
tokens are intentionally kept in memory only; issued ShareLinks are persisted
and reused by ``tacaItemId`` to avoid consuming the API quota unnecessarily.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "blog_agent" / "toss_products.json"
TOKEN_URL = "https://oauth2.cert.toss.im/token"
API_BASE_URL = "https://sharelink.toss.im/openapi"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class TossApiError(RuntimeError):
    """Raised when Toss returns an HTTP or result-envelope failure."""


def _required_env(name: str, *aliases: str) -> str:
    for candidate in (name, *aliases):
        value = os.getenv(candidate, "").strip()
        if value:
            return value
    names = ", ".join((name, *aliases))
    raise TossApiError(f"Missing required environment variable: {names}")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _keywords(name: str) -> list[str]:
    tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", name)
    return list(dict.fromkeys([*tokens[:12], "쇼핑", "상품"]))


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    products = payload.get("products", []) if isinstance(payload, dict) else []
    return {
        str(item.get("tacaItemId")): item
        for item in products
        if isinstance(item, dict) and item.get("tacaItemId") is not None
    }


class TossShareLinkClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        timeout: float = 20,
        max_retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._access_token = ""

    def authenticate(self) -> str:
        response = self._request(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.access_key,
                "client_secret": self.secret_key,
                "scope": "sharelink:read sharelink:write",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            authenticated=False,
        )
        token = str(response.get("access_token") or "").strip()
        if not token:
            raise TossApiError("Token response did not contain access_token")
        self._access_token = token
        return token

    def health(self) -> dict[str, Any]:
        return self._api("GET", "/health")

    def best_selling(self, size: int) -> list[dict[str, Any]]:
        success = self._api("GET", "/products/best-selling", params={"size": size})
        items = success.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    def today_deals(self, size: int = 30) -> list[dict[str, Any]]:
        success = self._api("GET", "/products/today-deals", params={"size": min(size, 30)})
        items = success.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    def issue_link(self, taca_item_id: int, publisher_id: str) -> dict[str, Any]:
        return self._api(
            "POST",
            "/links",
            json={"tacaItemId": taca_item_id, "publisherId": publisher_id},
        )

    def _api(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self._access_token:
            self.authenticate()
        payload = self._request(method, f"{API_BASE_URL}{path}", **kwargs)
        if payload.get("resultType") != "SUCCESS":
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = payload.get("errorCode") or error.get("errorCode") or "UNKNOWN"
            reason = error.get("reason") or payload.get("reason") or "Toss API request failed"
            raise TossApiError(f"{code}: {reason}")
        success = payload.get("success")
        if not isinstance(success, dict):
            raise TossApiError("Toss API success response was not an object")
        return success

    def _request(self, method: str, url: str, *, authenticated: bool = True, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if authenticated:
            headers["Authorization"] = f"Bearer {self._access_token}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.isdigit() else 2**attempt
                    time.sleep(min(delay, 30))
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise TossApiError("Toss API response was not a JSON object")
                return payload
            except (requests.RequestException, ValueError, TossApiError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 30))
        raise TossApiError(f"Request failed after retries: {last_error}") from last_error


def normalize_product(
    item: dict[str, Any],
    link: dict[str, Any],
    *,
    source: str,
    images_allowed: bool,
) -> dict[str, Any]:
    taca_item_id = int(item["tacaItemId"])
    short_url = str(link.get("shortUrl") or "").strip()
    if not short_url:
        raise TossApiError(f"No shortUrl for tacaItemId={taca_item_id}")
    name = str(item.get("displayName") or "").strip()
    return {
        "tacaItemId": taca_item_id,
        "name": name,
        "shortUrl": short_url,
        "originUrl": str(link.get("originUrl") or "").strip(),
        "productUrl": str(item.get("productUrl") or "").strip(),
        "thumbnailUrl": str(item.get("thumbnailUrl") or "").strip(),
        "imageAllowed": images_allowed,
        "displayPrice": int(item.get("displayPrice") or 0),
        "originalPrice": int(item.get("originalPrice") or 0),
        "discountRate": int(item.get("discountRate") or 0),
        "isSoldOut": bool(item.get("isSoldOut")),
        "reviewScore": float(item.get("reviewScore") or 0),
        "reviewCount": int(item.get("reviewCount") or 0),
        "categoryIds": [int(value) for value in item.get("categoryIds", []) if str(value).isdigit()],
        "rank": int(item.get("rank") or 0),
        "endAt": item.get("endAt"),
        "source": source,
        "keywords": _keywords(name),
    }


def synchronize(
    client: TossShareLinkClient,
    *,
    publisher_id: str,
    output: Path,
    size: int,
    include_today_deals: bool,
    images_allowed: bool,
) -> dict[str, Any]:
    client.health()
    cached = _load_cache(output)
    candidates: list[tuple[str, dict[str, Any]]] = [
        ("best-selling", item) for item in client.best_selling(size)
    ]
    if include_today_deals:
        candidates.extend(("today-deals", item) for item in client.today_deals(min(size, 30)))

    products: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source, item in candidates:
        try:
            taca_item_id = int(item["tacaItemId"])
        except (KeyError, TypeError, ValueError):
            print("warning: skipped product without a valid tacaItemId")
            continue
        if taca_item_id in seen or bool(item.get("isSoldOut")):
            continue
        seen.add(taca_item_id)
        cached_item = cached.get(str(taca_item_id), {})
        if cached_item.get("shortUrl"):
            link = {
                "shortUrl": cached_item["shortUrl"],
                "originUrl": cached_item.get("originUrl", ""),
            }
        else:
            try:
                link = client.issue_link(taca_item_id, publisher_id)
            except TossApiError as exc:
                print(f"warning: link issuance failed for {taca_item_id}: {exc}")
                continue
        products.append(
            normalize_product(item, link, source=source, images_allowed=images_allowed)
        )

    if not products:
        raise TossApiError("No usable products returned; existing cache was left unchanged")
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Toss ShareLink Open API",
        "products": products,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=30)
    parser.add_argument("--include-today-deals", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--allow-images", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.size <= 100:
        parser.error("--size must be between 1 and 100")

    access_key = _required_env("TOSS_ACCESS_KEY", "Toss_Access_Key")
    secret_key = _required_env("TOSS_SECRET_KEY")
    publisher_id = _required_env("TOSS_ID", "TOSS_PUBLISHER_ID")
    images_allowed = args.allow_images or _truthy(os.getenv("TOSS_PRODUCT_IMAGES_ALLOWED"))
    client = TossShareLinkClient(access_key, secret_key, timeout=args.timeout)
    payload = synchronize(
        client,
        publisher_id=publisher_id,
        output=args.output,
        size=args.size,
        include_today_deals=args.include_today_deals,
        images_allowed=images_allowed,
    )
    print(f"wrote {len(payload['products'])} products to {args.output}")


if __name__ == "__main__":
    main()
