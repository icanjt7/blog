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


if __name__ == "__main__":
    unittest.main()
