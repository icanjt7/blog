from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.improve_search_index_posts import (
    PostRecord,
    acceptable_expansion,
    duplicate_title_paths,
    normalize_title,
)


class ImproveSearchIndexPostsTest(unittest.TestCase):
    def test_normalize_title_ignores_spacing_and_punctuation(self) -> None:
        self.assertEqual(normalize_title("AI 정책, 변경!"), normalize_title("AI정책 변경"))

    def test_duplicate_title_paths_keeps_newest_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = PostRecord(root / "older.md", {"title": "같은 제목", "date": "2026-06-01"}, "본문")
            newer = PostRecord(root / "newer.md", {"title": "같은 제목", "date": "2026-06-10"}, "본문")

            duplicates = duplicate_title_paths([older, newer])

            self.assertEqual(duplicates, {older.path})

    def test_acceptable_expansion_requires_length_sections_and_links(self) -> None:
        original = "## 원문\n\nhttps://example.com/source"
        expanded = (
            "## 발표 내용\n\n" + "구체적인 설명입니다. " * 40
            + "\n\n## 의미\n\n" + "독자가 이해할 맥락입니다. " * 30
            + "\n\n## 원문\n\nhttps://example.com/source"
        )

        ok, reason = acceptable_expansion(original, expanded, 800)

        self.assertTrue(ok, reason)
        without_link = expanded.replace("https://example.com/source", "")
        self.assertFalse(acceptable_expansion(original, without_link, 800)[0])


if __name__ == "__main__":
    unittest.main()
