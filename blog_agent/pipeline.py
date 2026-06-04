from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .editor import SeoEditorAgent
from .images import ImageAgent
from .models import Draft, PublishResult
from .publishers import build_publisher
from .reports import ReportWriter
from .retrieval import FactRetriever
from .storage import RunStore
from .trends import TrendScout
from .writer import WriterAgent


@dataclass
class PipelineResult:
    run_id: str
    drafts: list[Draft]
    publish_results: list[PublishResult]
    manifest_path: str | None = None
    report_path: str | None = None


class BlogPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scout = TrendScout(settings.state_dir)
        self.retriever = FactRetriever(settings)
        self.writer = WriterAgent(settings)
        self.editor = SeoEditorAgent(settings)
        self.images = ImageAgent(settings)
        self.publisher = build_publisher(settings)
        self.store = RunStore(settings.state_dir)
        self.reports = ReportWriter(settings.output_dir)

    def run(self, count: int = 5, dry_run: bool = False, min_quality: float = 65) -> PipelineResult:
        run_id = self.store.new_run(count=count, dry_run=dry_run, publisher=self.settings.publisher)
        # 여유분 포함해서 스카우트 — 품질 미달 시 다음 주제로 넘어가기 위해
        candidate_limit = count * 3
        topics = self.scout.scout(limit=candidate_limit)
        self.store.add_event(
            run_id,
            "trend_scout",
            "ok",
            {"topic_count": len(topics), "keywords": [topic.keyword for topic in topics]},
        )
        drafts: list[Draft] = []
        results: list[PublishResult] = []
        published_topics = []
        published_count = 0

        try:
            for topic in topics:
                if not dry_run and published_count >= count:
                    break
                self.store.add_event(run_id, "topic_started", "ok", {"keyword": topic.keyword})
                enriched = self.retriever.enrich(topic)
                draft = self.editor.improve(self.writer.write(enriched))
                draft = self.images.attach_cover(draft)
                drafts.append(draft)
                if dry_run:
                    self.store.add_draft(run_id, draft)
                    continue
                if draft.quality_score < min_quality:
                    result = PublishResult(
                        ok=False,
                        destination=self.settings.publisher,
                        message=f"quality score too low: {draft.quality_score:.1f}",
                    )
                    results.append(result)
                    self.store.add_draft(run_id, draft, result)
                    # 다음 주제로 넘어감
                    continue
                result = self.publisher.publish(draft)
                results.append(result)
                self.store.add_draft(run_id, draft, result)
                if result.ok:
                    published_topics.append(topic)
                    published_count += 1

            if published_topics:
                self.scout.remember(published_topics)
            manifest_path = self.store.write_manifest(run_id, topics, drafts, results)
            report_path = self.reports.write_quality_report(run_id, drafts)
            self.store.finish_run(run_id, "completed")
            return PipelineResult(
                run_id=run_id,
                drafts=drafts,
                publish_results=results,
                manifest_path=str(manifest_path),
                report_path=str(report_path),
            )
        except Exception as exc:
            self.store.add_event(run_id, "pipeline", "failed", {"error": str(exc)})
            self.store.finish_run(run_id, "failed", error=str(exc))
            raise
