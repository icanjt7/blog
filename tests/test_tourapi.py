from __future__ import annotations

import unittest
from unittest.mock import patch

from blog_agent.config import Settings
from blog_agent.models import Topic
from blog_agent.tourapi import TourApiClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class TourApiClientTest(unittest.TestCase):
    def test_enrich_adds_related_and_rate_sources_for_tourism_topic(self) -> None:
        settings = Settings(tourapi_guide_key="guide-key", tourapi_rate_key="rate-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="서울 성수 카페 동선", title_hint="처음 가면 이 동선", category="핫이슈")

        payloads = [
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "tAtsNm": "성수동",
                                    "rlteTatsNm": "서울숲",
                                    "rlteCtgryLclsNm": "관광지",
                                    "areaNm": "서울",
                                    "rlteRank": "1",
                                }
                            ]
                        }
                    }
                }
            },
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "tAtsNm": "서울숲",
                                    "baseYmd": "20260604",
                                    "cnctrRate": "62",
                                    "areaNm": "서울",
                                }
                            ]
                        }
                    }
                }
            },
        ]

        with patch("blog_agent.tourapi.requests.get", side_effect=[_FakeResponse(p) for p in payloads]) as get:
            result = client.enrich(topic)

        self.assertEqual(result.related_count, 1)
        self.assertEqual(result.rate_count, 1)
        self.assertEqual(len(result.sources), 2)
        self.assertIn("서울숲", result.sources[0].summary)
        self.assertIn("집중률", result.sources[1].summary)
        self.assertEqual(get.call_args_list[0].args[0], "https://apis.data.go.kr/B551011/TarRlteTarService1/searchKeyword1")
        self.assertIn("baseYm", get.call_args_list[0].kwargs["params"])

    def test_non_tourism_topic_is_ignored(self) -> None:
        settings = Settings(tourapi_guide_key="guide-key", tourapi_rate_key="rate-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="아이폰 배터리", title_hint="오래 쓰는 법", category="기술")

        with patch("blog_agent.tourapi.requests.get") as get:
            result = client.enrich(topic)

        self.assertEqual(result.sources, [])
        get.assert_not_called()

    def test_enrich_adds_medical_tourism_source(self) -> None:
        settings = Settings(tourapi_mdc_key="mdc-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="서울 의료관광 병원", title_hint="예약 전 확인", category="핫이슈")

        payloads = [
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "contentid": "100",
                                    "contenttypeid": "12",
                                    "title": "서울메디컬센터",
                                    "addr1": "서울특별시 성동구",
                                }
                            ]
                        }
                    }
                }
            },
            {"response": {"body": {"items": {"item": [{"overview": "외국인 의료관광 안내 가능"}]}}}},
            {"response": {"body": {"items": {"item": [{"parking": "주차 가능", "restdate": "일요일"}]}}}},
            {"response": {"body": {"items": {"item": [{"treatitem": "검진 상담"}]}}}},
        ]

        with patch("blog_agent.tourapi.requests.get", side_effect=[_FakeResponse(p) for p in payloads]) as get:
            result = client.enrich(topic)

        self.assertEqual(result.medical_count, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertIn("의료관광", result.sources[0].title)
        self.assertIn("서울메디컬센터", result.sources[0].summary)
        self.assertIn("주차 가능", result.sources[0].summary)
        self.assertIn("검진 상담", result.sources[0].summary)
        self.assertEqual(get.call_args_list[0].args[0], "https://apis.data.go.kr/B551011/KorService2/searchKeyword2")


if __name__ == "__main__":
    unittest.main()
