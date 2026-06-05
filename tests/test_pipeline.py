from __future__ import annotations

import unittest
from types import SimpleNamespace

from blog_agent.config import Settings
from blog_agent.models import Topic
from blog_agent.pipeline import BlogPipeline
from blog_agent.tourapi import TourApiClient


class BlogPipelineTourApiPriorityTest(unittest.TestCase):
    def test_prioritizes_tourapi_topic_inside_publish_window(self) -> None:
        settings = Settings(tourapi_tour_key="tour-key")
        pipeline = BlogPipeline.__new__(BlogPipeline)
        pipeline.settings = settings
        pipeline.retriever = SimpleNamespace(tourapi=TourApiClient(settings))
        topics = [
            Topic(keyword="청년 지원금", title_hint="청년 지원금", category="생활"),
            Topic(keyword="아이폰 배터리", title_hint="아이폰 배터리", category="기술"),
            Topic(keyword="금리 전망", title_hint="금리 전망", category="정책"),
            Topic(keyword="서울 성수 카페 동선", title_hint="처음 가면 이 동선", category="핫이슈"),
        ]

        reordered = pipeline._prioritize_api_topic(topics, count=3)

        self.assertIn("서울 성수 카페 동선", [topic.keyword for topic in reordered[:3]])
        self.assertEqual(reordered[2].keyword, "서울 성수 카페 동선")

    def test_does_not_reorder_without_tourapi_key(self) -> None:
        settings = Settings()
        pipeline = BlogPipeline.__new__(BlogPipeline)
        pipeline.settings = settings
        pipeline.retriever = SimpleNamespace(tourapi=TourApiClient(settings))
        topics = [
            Topic(keyword="청년 지원금", title_hint="청년 지원금", category="생활"),
            Topic(keyword="아이폰 배터리", title_hint="아이폰 배터리", category="기술"),
            Topic(keyword="서울 성수 카페 동선", title_hint="처음 가면 이 동선", category="핫이슈"),
        ]

        reordered = pipeline._prioritize_api_topic(topics, count=2)

        self.assertEqual([topic.keyword for topic in reordered], [topic.keyword for topic in topics])


if __name__ == "__main__":
    unittest.main()
