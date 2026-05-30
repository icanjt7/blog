from __future__ import annotations

import json
from pathlib import Path

from .models import Draft


class ReportWriter:
    def __init__(self, output_dir: Path) -> None:
        self.report_dir = output_dir.parent / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def write_quality_report(self, run_id: str, drafts: list[Draft]) -> Path:
        path = self.report_dir / f"{run_id}-quality.json"
        payload = {
            "run_id": run_id,
            "average_quality": self._average_quality(drafts),
            "drafts": [
                {
                    "slug": draft.slug,
                    "title": draft.title,
                    "keyword": draft.topic.keyword,
                    "category": draft.topic.category,
                    "quality_score": draft.quality_score,
                    "review_notes": draft.review_notes,
                    "source_count": len(draft.topic.sources),
                    "source_authority_avg": self._source_authority_avg(draft),
                }
                for draft in drafts
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _average_quality(drafts: list[Draft]) -> float:
        if not drafts:
            return 0.0
        return round(sum(draft.quality_score for draft in drafts) / len(drafts), 1)

    @staticmethod
    def _source_authority_avg(draft: Draft) -> float:
        if not draft.topic.sources:
            return 0.0
        return round(sum(source.authority for source in draft.topic.sources) / len(draft.topic.sources), 1)
