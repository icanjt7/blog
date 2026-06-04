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
    def test_enrich_adds_korean_tourism_source(self) -> None:
        settings = Settings(tourapi_tour_key="tour-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="서울 성수 카페 동선", title_hint="처음 가면 이 동선", category="핫이슈")

        payloads = [
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "contentid": "300",
                                    "contenttypeid": "12",
                                    "title": "서울숲",
                                    "addr1": "서울특별시 성동구",
                                    "cat2": "자연관광지",
                                }
                            ]
                        }
                    }
                }
            },
            {"response": {"body": {"items": {"item": [{"overview": "성수와 함께 묶기 좋은 공원"}]}}}},
            {"response": {"body": {"items": {"item": [{"usetime": "상시", "parking": "공영주차장 이용"}]}}}},
            {"response": {"body": {"items": {"item": [{"infoname": "산책", "infotext": "서울숲 산책로"}]}}}},
            {"response": {"body": {"items": {"item": [{"originimgurl": "https://example.com/seoulforest.jpg"}]}}}},
        ]

        with patch("blog_agent.tourapi.requests.get", side_effect=[_FakeResponse(p) for p in payloads]) as get:
            result = client.enrich(topic)

        self.assertEqual(result.tour_count, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertIn("국문 관광정보", result.sources[0].title)
        self.assertIn("서울숲", result.sources[0].summary)
        self.assertIn("성수와 함께 묶기 좋은 공원", result.sources[0].summary)
        self.assertIn("공영주차장 이용", result.sources[0].summary)
        self.assertEqual(get.call_args_list[0].args[0], "https://apis.data.go.kr/B551011/KorService2/searchKeyword2")

    def test_enrich_adds_english_tourism_source(self) -> None:
        settings = Settings(tourapi_tour_en_key="tour-en-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="서울 성수 카페 동선", title_hint="처음 가면 이 동선", category="핫이슈")

        payloads = [
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "contentid": "400",
                                    "contenttypeid": "12",
                                    "title": "Seoul Forest",
                                    "addr1": "Seongsu-dong, Seongdong-gu, Seoul",
                                    "cat2": "Nature",
                                }
                            ]
                        }
                    }
                }
            },
            {"response": {"body": {"items": {"item": [{"overview": "A large park near Seongsu cafe streets."}]}}}},
            {"response": {"body": {"items": {"item": [{"usetime": "Open all year", "parking": "Public parking available"}]}}}},
            {"response": {"body": {"items": {"item": [{"infoname": "Walking", "infotext": "Forest walking trail"}]}}}},
            {"response": {"body": {"items": {"item": [{"originimgurl": "https://example.com/seoulforest-en.jpg"}]}}}},
        ]

        with patch("blog_agent.tourapi.requests.get", side_effect=[_FakeResponse(p) for p in payloads]) as get:
            result = client.enrich(topic)

        self.assertEqual(result.tour_en_count, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertIn("영문 관광정보", result.sources[0].title)
        self.assertIn("Seoul Forest", result.sources[0].summary)
        self.assertIn("A large park near Seongsu", result.sources[0].summary)
        self.assertIn("Public parking available", result.sources[0].summary)
        self.assertEqual(get.call_args_list[0].args[0], "https://apis.data.go.kr/B551011/EngService2/searchKeyword2")

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

    def test_enrich_adds_pet_tourism_source(self) -> None:
        settings = Settings(tourapi_pet_key="pet-key")
        client = TourApiClient(settings)
        topic = Topic(keyword="서울 반려동물 동반여행", title_hint="강아지와 가기 좋은 곳", category="핫이슈")

        payloads = [
            {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "contentid": "200",
                                    "contenttypeid": "12",
                                    "title": "서울펫파크",
                                    "addr1": "서울특별시 성동구",
                                }
                            ]
                        }
                    }
                }
            },
            {"response": {"body": {"items": {"item": [{"overview": "반려견 산책이 가능한 공원"}]}}}},
            {"response": {"body": {"items": {"item": [{"parking": "주차 가능", "restdate": "월요일"}]}}}},
            {"response": {"body": {"items": {"item": [{"relaPosesFclty": "반려견 놀이터"}]}}}},
            {"response": {"body": {"items": {"item": [{"acmpyNeedMtr": "목줄 착용"}]}}}},
            {"response": {"body": {"items": {"item": [{"originimgurl": "https://example.com/pet.jpg"}]}}}},
        ]

        with patch("blog_agent.tourapi.requests.get", side_effect=[_FakeResponse(p) for p in payloads]) as get:
            result = client.enrich(topic)

        self.assertEqual(result.pet_count, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertIn("반려동물", result.sources[0].title)
        self.assertIn("서울펫파크", result.sources[0].summary)
        self.assertIn("목줄 착용", result.sources[0].summary)
        self.assertIn("반려견 놀이터", result.sources[0].summary)
        self.assertEqual(get.call_args_list[0].args[0], "https://apis.data.go.kr/B551011/KorPetTourService2/searchKeyword2")


if __name__ == "__main__":
    unittest.main()
