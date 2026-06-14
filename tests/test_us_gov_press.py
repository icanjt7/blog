from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_us_gov_press.py"
SPEC = importlib.util.spec_from_file_location("import_us_gov_press", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class USGovernmentPressImportTest(unittest.TestCase):
    def test_fallback_body_contains_specific_source_context(self) -> None:
        source = MODULE.SOURCES[1]
        entry = MODULE.USEntry(
            source=source,
            title="NASA Announces New Mission",
            date="2026-06-12",
            url="https://www.nasa.gov/example",
            summary="NASA announced a new mission with a launch window and science goals.",
        )

        body = MODULE.fallback_body(entry, entry.summary)

        self.assertIn("미 항공우주국", body)
        self.assertIn("NASA", body)
        self.assertIn("| 항목 | 내용 |", body)
        self.assertIn("https://www.nasa.gov/example", body)
        self.assertIn("원문 제목", body)
        self.assertNotIn("한국 기업, 연구기관, 소비자, 정책 담당자가 직접 적용할 내용인지", body)

    def test_fetch_feed_skips_items_without_links(self) -> None:
        rss = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Linked release</title>
            <link>https://agency.gov/release</link>
            <pubDate>Fri, 12 Jun 2026 10:00:00 GMT</pubDate>
            <description>Useful official summary.</description>
          </item>
          <item>
            <title>No link release</title>
            <description>This item should be skipped.</description>
          </item>
        </channel></rss>
        """
        source = MODULE.USSource(
            code="sample",
            agency="Sample Agency",
            agency_ko="샘플 기관",
            feed_url="https://agency.gov/rss.xml",
            category_hint="정책",
            tags=("미국정부",),
        )

        with patch.object(MODULE.feedparser, "parse", return_value=MODULE.feedparser.parse(rss)):
            entries = MODULE.fetch_feed(source, 5)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].url, "https://agency.gov/release")

    def test_normalize_title_removes_body_label_and_markdown(self) -> None:
        source = MODULE.SOURCES[2]
        entry = MODULE.USEntry(
            source=source,
            title="Paramount Skydance Warner Bros Transaction",
            date="2026-06-12",
            url="https://www.justice.gov/example",
            summary="",
        )

        title = MODULE.normalize_title('**\\nBODY: broken article body', entry)

        self.assertIn("미 법무부", title)
        self.assertNotIn("BODY", title)

    def test_us_article_specific_rejects_generic_body(self) -> None:
        source = MODULE.SOURCES[0]
        entry = MODULE.USEntry(
            source=source,
            title="Executive action",
            date="2026-06-12",
            url="https://www.whitehouse.gov/example",
            summary="",
        )
        body = """미국 백악관이 발표했습니다.

## 내용
이 발표는 미국 내 정책 흐름을 보여주는 자료입니다.
## 의미
한국 기업, 연구기관, 소비자, 정책 담당자가 직접 적용할 내용인지 판단하려면 발표 기관, 대상, 시행 시점, 후속 문서를 함께 확인해야 합니다.
## 표
| 항목 | 내용 |
|---|---|
| 기관 | 미국 백악관 |
## 원문
- 링크
"""

        self.assertFalse(MODULE.us_article_is_specific(body, entry))


if __name__ == "__main__":
    unittest.main()
