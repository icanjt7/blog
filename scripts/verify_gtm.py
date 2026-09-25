"""Fail the deployment when any generated HTML page misses the GTM install tags."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


HEAD_MARKER = "googletagmanager.com/gtm.js?id="
BODY_MARKER = "googletagmanager.com/ns.html?id=GTM-PRH78BZK"


def verify(public_dir: Path) -> dict[str, int | bool]:
    pages = list(public_dir.rglob("*.html"))
    failures: list[str] = []
    for path in pages:
        source = path.read_text(encoding="utf-8")
        head = source.find("<head>")
        head_tag = source.find("<!-- Google Tag Manager -->")
        charset = source.find('<meta charset="utf-8">')
        body = source.find("<body>")
        body_tag = source.find("<!-- Google Tag Manager (noscript) -->")
        valid = (
            source.count(HEAD_MARKER) == 1
            and source.count(BODY_MARKER) == 1
            and -1 < head < head_tag < charset
            and -1 < body < body_tag
        )
        if not valid:
            failures.append(str(path))
    if not pages:
        raise SystemExit(f"no HTML pages found under {public_dir}")
    if failures:
        raise SystemExit(f"GTM validation failed for {len(failures)} pages: {failures[:5]}")
    result: dict[str, int | bool] = {"ok": True, "html_pages": len(pages), "gtm_container": "GTM-PRH78BZK"}
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, default=Path("public"))
    args = parser.parse_args()
    verify(args.public_dir)


if __name__ == "__main__":
    main()
