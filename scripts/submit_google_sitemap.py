from __future__ import annotations

import base64
import json
import os
import sys
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account


SCOPE = "https://www.googleapis.com/auth/webmasters"
DEFAULT_SITE_URL = "https://briefwave.kr/"
DEFAULT_SITEMAP_URL = "https://briefwave.kr/sitemap.xml"
DEFAULT_EXTRA_SITEMAP_URLS = "https://briefwave.kr/sitemap-posts-priority.xml"


def _load_service_account_info() -> dict | None:
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    raw_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
    if raw_json:
        return json.loads(raw_json)
    if raw_b64:
        return json.loads(base64.b64decode(raw_b64).decode("utf-8"))
    return None


def _endpoint(site_url: str, sitemap_url: str) -> str:
    encoded_site = quote(site_url, safe="")
    encoded_sitemap = quote(sitemap_url, safe="")
    return f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps/{encoded_sitemap}"


def submit_sitemap(site_url: str, sitemap_url: str, service_account_info: dict) -> tuple[bool, str]:
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[SCOPE],
    )
    session = AuthorizedSession(credentials)
    response = session.put(_endpoint(site_url, sitemap_url), timeout=30)
    if response.status_code in {200, 204}:
        return True, f"Submitted {sitemap_url} for {site_url}"
    return False, f"Google Search Console API returned {response.status_code}: {response.text[:500]}"


def main() -> int:
    site_url = os.getenv("GOOGLE_SEARCH_CONSOLE_SITE_URL", DEFAULT_SITE_URL).strip() or DEFAULT_SITE_URL
    sitemap_url = os.getenv("GOOGLE_SITEMAP_URL", DEFAULT_SITEMAP_URL).strip() or DEFAULT_SITEMAP_URL
    extra_raw = os.getenv("GOOGLE_EXTRA_SITEMAP_URLS", DEFAULT_EXTRA_SITEMAP_URLS).strip()
    if not site_url.endswith("/") and not site_url.startswith("sc-domain:"):
        site_url += "/"

    service_account_info = _load_service_account_info()
    if not service_account_info:
        print(
            "Google Search Console sitemap submit skipped: "
            "GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is not set."
        )
        return 0

    sitemap_urls = [sitemap_url]
    sitemap_urls.extend(item.strip() for item in extra_raw.replace("\n", ",").split(",") if item.strip())
    sitemap_urls = list(dict.fromkeys(sitemap_urls))

    failed = False
    for url in sitemap_urls:
        ok, message = submit_sitemap(site_url, url, service_account_info)
        print(message)
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
