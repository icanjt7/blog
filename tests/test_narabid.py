from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from blog_agent.narabid import BidNotice, NaraBidClient, render_bid_digest, render_service_digest


class FakeResponse:
    def __init__(self, items: list[dict] | dict | None) -> None:
        self.items = items

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"response": {"body": {"items": {"item": self.items}}}}


class FakeListResponse(FakeResponse):
    def json(self) -> dict:
        return {"response": {"body": {"items": self.items}}}


class NaraBidTest(unittest.TestCase):
    @patch("blog_agent.narabid.requests.get")
    def test_fetch_goods_uses_public_search_operation_and_secret_param(self, mock_get) -> None:
        mock_get.return_value = FakeResponse(
            [
                {
                    "bidNtceNo": "20260626001",
                    "bidNtceOrd": "0",
                    "bidNtceNm": "테스트 물품 구매",
                    "ntceInsttNm": "조달청",
                    "dminsttNm": "수요기관",
                    "bidClseDt": "2026-06-27 10:00",
                }
            ]
        )

        client = NaraBidClient("encoded%2Bkey")
        notices = client.fetch_by_work_type("goods", num_rows=5, days=2)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].work_type, "물품")
        url = mock_get.call_args.args[0]
        params = mock_get.call_args.kwargs["params"]
        self.assertTrue(url.endswith("/getBidPblancListInfoThngPPSSrch"))
        self.assertEqual(params["serviceKey"], "encoded+key")
        self.assertEqual(params["numOfRows"], "5")
        self.assertEqual(params["type"], "json")
        self.assertIn("inqryBgnDt", params)
        self.assertIn("inqryEndDt", params)

    @patch("blog_agent.narabid.requests.get")
    def test_fetch_accepts_body_items_list_shape(self, mock_get) -> None:
        mock_get.return_value = FakeListResponse(
            [
                {
                    "bidNtceNo": "20260626002",
                    "bidNtceOrd": "0",
                    "bidNtceNm": "리스트 형태 응답",
                    "bidClseDt": "2026-06-27 10:00",
                }
            ]
        )

        notices = NaraBidClient("secret").fetch_by_work_type("service", num_rows=5, days=2)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].title, "리스트 형태 응답")

    @patch("blog_agent.narabid.requests.get")
    def test_fetch_recent_deduplicates_and_limits(self, mock_get) -> None:
        mock_get.side_effect = [
            FakeResponse(
                [
                    {"bidNtceNo": "A", "bidNtceOrd": "0", "bidNtceNm": "첫 번째", "bidClseDt": "2026-06-28 10:00"},
                    {"bidNtceNo": "B", "bidNtceOrd": "0", "bidNtceNm": "두 번째", "bidClseDt": "2026-06-27 10:00"},
                ]
            ),
            FakeResponse(
                [
                    {"bidNtceNo": "B", "bidNtceOrd": "0", "bidNtceNm": "두 번째 중복", "bidClseDt": "2026-06-27 10:00"},
                    {"bidNtceNo": "C", "bidNtceOrd": "0", "bidNtceNm": "세 번째", "bidClseDt": "2026-06-29 10:00"},
                ]
            ),
        ]

        client = NaraBidClient("secret")
        notices = client.fetch_recent(["goods", "service"], limit=2, days=1)

        self.assertEqual([notice.key for notice in notices], ["B-0", "A-0"])

    def test_render_bid_digest_is_source_oriented(self) -> None:
        body = render_bid_digest(
            [
                BidNotice(
                    work_type="물품",
                    bid_no="20260626001",
                    bid_ord="0",
                    title="테스트 물품 구매",
                    notice_inst="조달청",
                    demand_inst="수요기관",
                    bid_close_at="2026-06-27 10:00",
                    contract_method="일반경쟁",
                    detail_url="https://example.go.kr/notice",
                )
            ],
            generated_at=datetime(2026, 6, 26, 9, 0),
        )

        self.assertIn('title: "2026-06-26 나라장터 입찰공고 1건"', body)
        self.assertIn("| 1 | 물품 | [테스트 물품 구매](https://example.go.kr/notice) | 조달청 | 수요기관 |", body)
        self.assertIn("조달청 나라장터 입찰공고정보서비스 공개 데이터", body)
        self.assertNotIn("어디로", body)
        self.assertNotIn("단독", body)

    def test_render_service_digest_summarizes_each_notice(self) -> None:
        body = render_service_digest(
            [
                BidNotice(
                    work_type="용역",
                    bid_no="20260626003",
                    bid_ord="0",
                    title="2026년 정보시스템 유지관리 용역",
                    notice_inst="조달청",
                    demand_inst="수요기관",
                    bid_close_at="2026-07-01 10:00",
                    contract_method="제한경쟁",
                    detail_url="https://example.go.kr/service",
                )
            ],
            generated_at=datetime(2026, 6, 26, 9, 0),
        )

        self.assertIn('title: "나라장터 용역 입찰 1건 정리: 유지관리·정비 중심"', body)
        self.assertIn("## 오늘의 흐름", body)
        self.assertIn("## 주목할 공고", body)
        self.assertIn("## 유형별 현황", body)
        self.assertIn("## 전체 20건", body)
        self.assertIn("### 1. 2026년 정보시스템 유지관리 용역", body)
        self.assertIn("시설·장비·시스템 유지관리", body)
        self.assertIn("나라장터 원문 공고와 첨부파일", body)
        self.assertNotIn("단독", body)


if __name__ == "__main__":
    unittest.main()
