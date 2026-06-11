from __future__ import annotations

import os
from dataclasses import dataclass

from .config import Settings
from .editor import SeoEditorAgent
from .images import ImageAgent
from .models import Draft, PublishResult, Topic
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
        # 여유분 포함해서 스카우트. 예약 실행에서는 외부 API/LLM 지연이 누적되지 않도록
        # 환경변수로 후보 수를 제한한다.
        multiplier = self._env_int("BLOG_CANDIDATE_MULTIPLIER", 3, minimum=1)
        max_candidates = max(count, self._env_int("BLOG_MAX_CANDIDATES", count * multiplier, minimum=count))
        candidate_limit = min(count * multiplier, max_candidates)
        topics = self.scout.scout(limit=candidate_limit)
        topics = self._prioritize_api_topic(topics, count)
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

    def _prioritize_api_topic(self, topics: list[Topic], count: int) -> list[Topic]:
        if count <= 0 or not self.retriever.tourapi or not self._has_tourapi_key():
            return topics
        publish_window = min(count, len(topics))
        if any(self._is_tourapi_topic(topic) for topic in topics[:publish_window]):
            return topics
        for index, topic in enumerate(topics[publish_window:], start=publish_window):
            if self._is_tourapi_topic(topic):
                reordered = list(topics)
                api_topic = reordered.pop(index)
                reordered.insert(max(0, publish_window - 1), api_topic)
                return reordered
        return topics

    def _has_tourapi_key(self) -> bool:
        return any(
            [
                self.settings.tourapi_guide_key,
                self.settings.tourapi_rate_key,
                self.settings.tourapi_mdc_key,
                self.settings.tourapi_pet_key,
                self.settings.tourapi_tour_key,
                self.settings.tourapi_tour_en_key,
            ]
        )

    def _is_tourapi_topic(self, topic: Topic) -> bool:
        tourapi = self.retriever.tourapi
        return bool(
            tourapi
            and (
                tourapi.is_tourism_topic(topic)
                or tourapi.is_medical_tourism_topic(topic)
                or tourapi.is_pet_tourism_topic(topic)
            )
        )

    @staticmethod
    def _env_int(name: str, default: int, minimum: int = 0) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(default))))
        except ValueError:
            return max(minimum, default)
