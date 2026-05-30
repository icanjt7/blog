from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .editor import SeoEditorAgent
from .models import Draft, PublishResult
from .publishers import build_publisher
from .retrieval import FactRetriever
from .trends import TrendScout
from .writer import WriterAgent


@dataclass
class PipelineResult:
    drafts: list[Draft]
    publish_results: list[PublishResult]


class BlogPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scout = TrendScout(settings.state_dir)
        self.retriever = FactRetriever()
        self.writer = WriterAgent(settings)
        self.editor = SeoEditorAgent()
        self.publisher = build_publisher(settings)

    def run(self, count: int = 5, dry_run: bool = False, min_quality: float = 65) -> PipelineResult:
        topics = self.scout.scout(limit=count)
        drafts: list[Draft] = []
        results: list[PublishResult] = []
        published_topics = []

        for topic in topics:
            enriched = self.retriever.enrich(topic)
            draft = self.editor.review(self.writer.write(enriched))
            drafts.append(draft)
            if dry_run:
                continue
            if draft.quality_score < min_quality:
                results.append(
                    PublishResult(
                        ok=False,
                        destination=self.settings.publisher,
                        message=f"quality score too low: {draft.quality_score:.1f}",
                    )
                )
                continue
            result = self.publisher.publish(draft)
            results.append(result)
            if result.ok:
                published_topics.append(topic)

        if published_topics:
            self.scout.remember(published_topics)
        return PipelineResult(drafts=drafts, publish_results=results)
