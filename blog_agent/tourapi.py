from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

import requests

from .config import Settings
from .models import Source, Topic


TOURISM_KEYWORDS = (
    "여행",
    "관광",
    "코스",
    "동선",
    "카페",
    "먹거리",
    "시장",
    "산책",
    "야경",
    "당일치기",
    "거리",
    "마을",
    "해변",
    "바다",
    "숲",
    "공원",
    "한옥",
    "둘레길",
    "케이블카",
    "스카이워크",
    "포차",
)


REGION_HINTS: dict[str, tuple[str, str]] = {
    "서울": ("11", "11000"),
    "성수": ("11", "11200"),
    "서울숲": ("11", "11200"),
    "성동": ("11", "11200"),
    "북촌": ("11", "11110"),
    "익선동": ("11", "11110"),
    "잠실": ("11", "11710"),
    "망원": ("11", "11440"),
    "홍대": ("11", "11440"),
    "합정": ("11", "11440"),
    "부산": ("26", "26000"),
    "해운대": ("26", "26350"),
    "광안리": ("26", "26500"),
    "송정": ("26", "26350"),
    "흰여울": ("26", "26200"),
    "제주": ("50", "50000"),
    "애월": ("50", "50110"),
    "성산": ("50", "50130"),
    "서귀포": ("50", "50130"),
    "강릉": ("51", "51150"),
    "주문진": ("51", "51150"),
    "속초": ("51", "51210"),
    "양양": ("51", "51830"),
    "춘천": ("51", "51110"),
    "원주": ("51", "51130"),
    "대전": ("30", "30000"),
    "청주": ("43", "43110"),
    "수원": ("41", "41110"),
    "용인": ("41", "41460"),
    "파주": ("41", "41480"),
    "고양": ("41", "41280"),
    "인천": ("28", "28000"),
    "송도": ("28", "28185"),
    "월미도": ("28", "28110"),
    "경주": ("47", "47130"),
    "포항": ("47", "47110"),
    "안동": ("47", "47170"),
    "전주": ("52", "52110"),
    "군산": ("52", "52130"),
    "여수": ("46", "46130"),
    "순천": ("46", "46150"),
    "담양": ("46", "46710"),
    "통영": ("48", "48220"),
    "남해": ("48", "48840"),
    "울산": ("31", "31000"),
    "김해": ("48", "48250"),
    "창원": ("48", "48120"),
    "가평": ("41", "41820"),
    "제천": ("43", "43150"),
    "단양": ("43", "43800"),
}


@dataclass(frozen=True)
class TourApiSummary:
    sources: list[Source]
    related_count: int = 0
    rate_count: int = 0


class TourApiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.guide_endpoint = settings.tourapi_guide_endpoint.rstrip("/")
        self.rate_endpoint = settings.tourapi_rate_endpoint.rstrip("/")

    @staticmethod
    def is_tourism_topic(topic: Topic) -> bool:
        text = f"{topic.keyword} {topic.title_hint} {topic.rationale}"
        return topic.category == "핫이슈" and any(word in text for word in TOURISM_KEYWORDS)

    def enrich(self, topic: Topic) -> TourApiSummary:
        if not self.is_tourism_topic(topic):
            return TourApiSummary([])

        sources: list[Source] = []
        related_items = self._fetch_related(topic)
        if related_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 관광지별 연관 관광지 정보",
                    url="https://www.data.go.kr/data/15128560/openapi.do",
                    summary=self._summarise_related(topic.keyword, related_items),
                    authority=5,
                )
            )

        rate_items = self._fetch_rate(topic)
        if rate_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 관광지 집중률 방문자 추이 예측 정보",
                    url="https://www.data.go.kr/data/15128555/openapi.do",
                    summary=self._summarise_rate(topic.keyword, rate_items),
                    authority=5,
                )
            )

        return TourApiSummary(sources, len(related_items), len(rate_items))

    def _fetch_related(self, topic: Topic) -> list[dict]:
        if not self.settings.tourapi_guide_key:
            return []
        items = self._get_items(
            f"{self.guide_endpoint}/searchKeyword1",
            self._base_params(self.settings.tourapi_guide_key)
            | {
                "keyword": self._clean_keyword(topic.keyword),
                "baseYm": self.settings.tourapi_base_ym,
                "numOfRows": "10",
                "pageNo": "1",
            },
        )
        if items:
            return items

        region = self._region_codes(topic.keyword)
        if not region:
            return []
        area_cd, signgu_cd = region
        return self._get_items(
            f"{self.guide_endpoint}/areaBasedList1",
            self._base_params(self.settings.tourapi_guide_key)
            | {
                "areaCd": area_cd,
                "signguCd": signgu_cd,
                "baseYm": self.settings.tourapi_base_ym,
                "numOfRows": "10",
                "pageNo": "1",
            },
        )

    def _fetch_rate(self, topic: Topic) -> list[dict]:
        if not self.settings.tourapi_rate_key:
            return []
        region = self._region_codes(topic.keyword)
        if not region:
            return []
        area_cd, signgu_cd = region
        return self._get_items(
            f"{self.rate_endpoint}/tatsCnctrRatedList",
            self._base_params(self.settings.tourapi_rate_key)
            | {
                "areaCd": area_cd,
                "signguCd": signgu_cd,
                "tAtsNm": self._clean_keyword(topic.keyword),
                "numOfRows": "10",
                "pageNo": "1",
            },
        )

    @staticmethod
    def _base_params(service_key: str) -> dict[str, str]:
        return {
            "serviceKey": unquote(service_key),
            "MobileOS": "ETC",
            "MobileApp": "BriefWave",
            "_type": "json",
        }

    @staticmethod
    def _clean_keyword(keyword: str) -> str:
        cleaned = re.sub(r"\b(서울|부산|제주|대전|인천|울산|대구|광주)\b", "", keyword)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or keyword

    @staticmethod
    def _region_codes(text: str) -> tuple[str, str] | None:
        for hint, codes in REGION_HINTS.items():
            if hint in text:
                return codes
        return None

    @staticmethod
    def _get_items(url: str, params: dict[str, str]) -> list[dict]:
        try:
            resp = requests.get(url, params=params, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        body = data.get("response", {}).get("body", {})
        items = body.get("items", {}).get("item", [])
        if isinstance(items, dict):
            return [items]
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    @staticmethod
    def _pick(item: dict, *names: str) -> str:
        for name in names:
            value = item.get(name)
            if value not in (None, ""):
                return str(value)
        return ""

    def _summarise_related(self, keyword: str, items: list[dict]) -> str:
        rows: list[str] = []
        for item in items[:8]:
            base = self._pick(item, "tAtsNm", "tAtsName", "title", "hubTatsNm") or keyword
            related = self._pick(item, "rlteTatsNm", "rlteTatsName", "rlteNm", "rlteTitle")
            category = self._pick(item, "rlteCtgryLclsNm", "rlteCtgryMclsNm", "rlteCtgrySclsNm", "cat1", "cat2")
            area = self._pick(item, "areaNm", "signguNm", "rlteRegnNm", "addr1")
            rank = self._pick(item, "rlteRank", "rank", "rlteTatsRank")
            parts = [f"기준 관광지 {base}"]
            if related:
                parts.append(f"연관 관광지 {related}")
            if category:
                parts.append(f"분류 {category}")
            if area:
                parts.append(f"지역 {area}")
            if rank:
                parts.append(f"연관 순위 {rank}")
            rows.append(" · ".join(parts))
        joined = " / ".join(rows)
        return (
            "TourAPI 관광지별 연관 관광지 정보에서 가져온 공개 데이터입니다. "
            "글에서는 연관 관광지, 주변에서 함께 묶기 좋은 지점, 카테고리 흐름을 우선 반영하세요. "
            f"조회 키워드: {keyword}. 결과: {joined}"
        )

    def _summarise_rate(self, keyword: str, items: list[dict]) -> str:
        rows: list[str] = []
        for item in items[:8]:
            name = self._pick(item, "tAtsNm", "tatsNm", "title") or keyword
            date = self._pick(item, "baseYmd", "predictYmd", "etdYmd", "tm")
            rate = self._pick(item, "cnctrRate", "tatsCnctrRate", "cnctrRated", "rate")
            area = self._pick(item, "areaNm", "signguNm", "addr1")
            level = self._pick(item, "cnctrRateLevel", "level", "grade")
            parts = [name]
            if date:
                parts.append(f"기준일 {date}")
            if rate:
                parts.append(f"집중률 {rate}")
            if level:
                parts.append(f"단계 {level}")
            if area:
                parts.append(f"지역 {area}")
            rows.append(" · ".join(parts))
        joined = " / ".join(rows)
        return (
            "TourAPI 관광지 집중률 정보는 KT 이동통신 기반 방문자 추이 예측값입니다. "
            "가장 붐비는 시기를 100으로 본 상대 수치이므로, 혼잡 가능성을 설명할 때만 보조 지표로 쓰세요. "
            f"조회 키워드: {keyword}. 결과: {joined}"
        )
