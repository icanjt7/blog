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

MEDICAL_TOURISM_KEYWORDS = (
    "의료관광",
    "의료 관광",
    "메디컬",
    "웰니스",
    "건강검진",
    "검진",
    "병원",
    "의원",
    "클리닉",
    "피부과",
    "치과",
    "한방",
    "한의원",
    "성형",
    "미용",
    "재활",
    "치료",
)

PET_TOURISM_KEYWORDS = (
    "반려동물",
    "반려견",
    "반려묘",
    "애견",
    "애묘",
    "강아지",
    "고양이",
    "펫",
    "펫캉스",
    "댕댕이",
    "동반여행",
    "동반 여행",
    "애견동반",
    "반려동물 동반",
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
    medical_count: int = 0
    pet_count: int = 0


class TourApiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.guide_endpoint = settings.tourapi_guide_endpoint.rstrip("/")
        self.rate_endpoint = settings.tourapi_rate_endpoint.rstrip("/")
        self.mdc_endpoint = settings.tourapi_mdc_endpoint.rstrip("/")
        self.pet_endpoint = settings.tourapi_pet_endpoint.rstrip("/")

    @staticmethod
    def is_tourism_topic(topic: Topic) -> bool:
        text = f"{topic.keyword} {topic.title_hint} {topic.rationale}"
        return topic.category == "핫이슈" and any(word in text for word in TOURISM_KEYWORDS)

    @staticmethod
    def is_medical_tourism_topic(topic: Topic) -> bool:
        text = f"{topic.keyword} {topic.title_hint} {topic.rationale}"
        return topic.category == "핫이슈" and any(word in text for word in MEDICAL_TOURISM_KEYWORDS)

    @staticmethod
    def is_pet_tourism_topic(topic: Topic) -> bool:
        text = f"{topic.keyword} {topic.title_hint} {topic.rationale}"
        return topic.category == "핫이슈" and any(word in text for word in PET_TOURISM_KEYWORDS)

    def enrich(self, topic: Topic) -> TourApiSummary:
        is_tourism = self.is_tourism_topic(topic)
        is_medical_tourism = self.is_medical_tourism_topic(topic)
        is_pet_tourism = self.is_pet_tourism_topic(topic)
        if not (is_tourism or is_medical_tourism or is_pet_tourism):
            return TourApiSummary([])

        sources: list[Source] = []
        related_items = self._fetch_related(topic) if is_tourism else []
        if related_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 관광지별 연관 관광지 정보",
                    url="https://www.data.go.kr/data/15128560/openapi.do",
                    summary=self._summarise_related(topic.keyword, related_items),
                    authority=5,
                )
            )

        rate_items = self._fetch_rate(topic) if is_tourism else []
        if rate_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 관광지 집중률 방문자 추이 예측 정보",
                    url="https://www.data.go.kr/data/15128555/openapi.do",
                    summary=self._summarise_rate(topic.keyword, rate_items),
                    authority=5,
                )
            )

        medical_items = self._fetch_medical_tourism(topic) if is_medical_tourism else []
        if medical_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 의료관광 정보",
                    url="https://www.data.go.kr/",
                    summary=self._summarise_medical_tourism(topic.keyword, medical_items),
                    authority=5,
                )
            )

        pet_items = self._fetch_pet_tourism(topic) if is_pet_tourism else []
        if pet_items:
            sources.append(
                Source(
                    title="한국관광공사 TourAPI 반려동물 동반여행 정보",
                    url="https://www.data.go.kr/data/15135102/openapi.do",
                    summary=self._summarise_pet_tourism(topic.keyword, pet_items),
                    authority=5,
                )
            )

        return TourApiSummary(
            sources=sources,
            related_count=len(related_items),
            rate_count=len(rate_items),
            medical_count=len(medical_items),
            pet_count=len(pet_items),
        )

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

    def _fetch_medical_tourism(self, topic: Topic) -> list[dict]:
        if not self.settings.tourapi_mdc_key:
            return []

        base_params = self._base_params(self.settings.tourapi_mdc_key) | {
            "numOfRows": "10",
            "pageNo": "1",
        }
        items = self._get_items_first(
            self._endpoint_candidates("searchKeyword"),
            base_params
            | {
                "keyword": self._clean_keyword(topic.keyword),
                "arrange": "Q",
            },
        )
        if not items:
            region = self._region_codes(topic.keyword)
            if region:
                area_cd, signgu_cd = region
                items = self._get_items_first(
                    self._endpoint_candidates("mdclTursmSyncList"),
                    base_params
                    | {
                        "areaCode": area_cd,
                        "sigunguCode": signgu_cd,
                        "showflag": "1",
                        "arrange": "Q",
                    },
                )
        if not items:
            return []

        enriched: list[dict] = []
        for item in items[:5]:
            merged = dict(item)
            content_id = self._pick(item, "contentid", "contentId")
            content_type_id = self._pick(item, "contenttypeid", "contentTypeId")
            if content_id:
                detail_params = self._base_params(self.settings.tourapi_mdc_key) | {
                    "contentId": content_id,
                    "contentid": content_id,
                    "defaultYN": "Y",
                    "addrinfoYN": "Y",
                    "mapinfoYN": "Y",
                    "overviewYN": "Y",
                    "_type": "json",
                }
                if content_type_id:
                    detail_params |= {"contentTypeId": content_type_id, "contenttypeid": content_type_id}
                merged |= self._first_item_from_candidates(self._endpoint_candidates("detailCommon"), detail_params)
                merged |= self._first_item_from_candidates(self._endpoint_candidates("detailIntro"), detail_params)
                merged |= self._first_item_from_candidates(self._endpoint_candidates("detailMdclTursm"), detail_params)
            enriched.append(merged)
        return enriched

    def _fetch_pet_tourism(self, topic: Topic) -> list[dict]:
        if not self.settings.tourapi_pet_key:
            return []

        base_params = self._base_params(self.settings.tourapi_pet_key) | {
            "numOfRows": "10",
            "pageNo": "1",
        }
        items = self._get_items_first(
            self._pet_endpoint_candidates("searchKeyword"),
            base_params
            | {
                "keyword": self._clean_keyword(topic.keyword),
                "arrange": "Q",
            },
        )
        if not items:
            region = self._region_codes(topic.keyword)
            if region:
                area_cd, signgu_cd = region
                items = self._get_items_first(
                    self._pet_endpoint_candidates("areaBasedList"),
                    base_params
                    | {
                        "areaCode": area_cd,
                        "sigunguCode": signgu_cd,
                        "arrange": "Q",
                        "listYN": "Y",
                    },
                )
        if not items:
            return []

        enriched: list[dict] = []
        for item in items[:5]:
            merged = dict(item)
            content_id = self._pick(item, "contentid", "contentId")
            content_type_id = self._pick(item, "contenttypeid", "contentTypeId")
            if content_id:
                detail_params = self._base_params(self.settings.tourapi_pet_key) | {
                    "contentId": content_id,
                    "contentid": content_id,
                    "defaultYN": "Y",
                    "addrinfoYN": "Y",
                    "mapinfoYN": "Y",
                    "overviewYN": "Y",
                    "imageYN": "Y",
                    "_type": "json",
                }
                if content_type_id:
                    detail_params |= {"contentTypeId": content_type_id, "contenttypeid": content_type_id}
                merged |= self._first_item_from_candidates(self._pet_endpoint_candidates("detailCommon"), detail_params)
                merged |= self._first_item_from_candidates(self._pet_endpoint_candidates("detailIntro"), detail_params)
                merged |= self._first_item_from_candidates(self._pet_endpoint_candidates("detailInfo"), detail_params)
                merged |= self._first_item_from_candidates(self._pet_endpoint_candidates("detailPetTour"), detail_params)
                merged |= self._first_item_from_candidates(self._pet_endpoint_candidates("detailImage"), detail_params)
            enriched.append(merged)
        return enriched

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

    def _get_items_first(self, urls: list[str], params: dict[str, str]) -> list[dict]:
        for url in urls:
            items = self._get_items(url, params)
            if items:
                return items
        return []

    def _first_item_from_candidates(self, urls: list[str], params: dict[str, str]) -> dict:
        items = self._get_items_first(urls, params)
        return items[0] if items else {}

    def _endpoint_candidates(self, operation: str) -> list[str]:
        return self._operation_candidates(self.mdc_endpoint, operation)

    def _pet_endpoint_candidates(self, operation: str) -> list[str]:
        return self._operation_candidates(self.pet_endpoint, operation)

    @staticmethod
    def _operation_candidates(base_endpoint: str, operation: str) -> list[str]:
        if operation.endswith("2"):
            names = [operation, operation[:-1]]
        else:
            names = [f"{operation}2", operation]
        return [f"{base_endpoint}/{name}" for name in dict.fromkeys(names)]

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

    def _summarise_medical_tourism(self, keyword: str, items: list[dict]) -> str:
        rows: list[str] = []
        for item in items[:8]:
            title = self._pick(item, "title", "facltNm", "yadmNm", "contentNm") or keyword
            addr = self._pick(item, "addr1", "addr2", "adres", "address")
            tel = self._pick(item, "tel", "telno", "infocenter", "medicaltourinfo")
            overview = self._pick(item, "overview", "treatitem", "mdclTursmInfo", "intro")
            medical_info = self._pick(item, "treatitem", "mdclTursmInfo", "medicaltourinfo", "medicalTourInfo")
            parking = self._pick(item, "parking", "parkingshopping", "parkingculture")
            rest = self._pick(item, "restdate", "restdatehealth", "restdateculture", "chkcreditcard")
            homepage = self._pick(item, "homepage", "firstimage")
            parts = [title]
            if addr:
                parts.append(f"주소 {addr}")
            if tel:
                parts.append(f"문의 {tel}")
            if overview:
                parts.append(f"개요 {overview[:120]}")
            if medical_info and medical_info != overview:
                parts.append(f"의료관광 정보 {medical_info[:120]}")
            if parking:
                parts.append(f"주차 {parking}")
            if rest:
                parts.append(f"휴무/이용 참고 {rest}")
            if homepage:
                parts.append("공식/이미지 정보 있음")
            rows.append(" · ".join(parts))
        joined = " / ".join(rows)
        return (
            "TourAPI 의료관광 정보에서 가져온 공개 데이터입니다. "
            "의료관광 글에서는 치료 효과나 안전성을 단정하지 말고, 주소·문의·운영정보·주차·공식 확인 경로를 중심으로 안내하세요. "
            "예약, 진료 가능 여부, 통역, 비용, 준비서류는 방문 전 기관에 직접 확인해야 합니다. "
            f"조회 키워드: {keyword}. 결과: {joined}"
        )

    def _summarise_pet_tourism(self, keyword: str, items: list[dict]) -> str:
        rows: list[str] = []
        for item in items[:8]:
            title = self._pick(item, "title", "facltNm", "contentNm") or keyword
            addr = self._pick(item, "addr1", "addr2", "adres", "address")
            tel = self._pick(item, "tel", "telno", "infocenter")
            overview = self._pick(item, "overview", "intro")
            pet_rules = self._pick(
                item,
                "acmpyNeedMtr",
                "acmpyPsblCpam",
                "acmpyTypeCd",
                "petTursmInfo",
                "petTourInfo",
                "petinfo",
                "chkpet",
            )
            pet_facilities = self._pick(
                item,
                "relaPosesFclty",
                "petfacility",
                "petFacility",
                "etcAcmpyInfo",
                "relaAcdntRiskMtr",
            )
            parking = self._pick(item, "parking", "parkingshopping", "parkingculture")
            hours = self._pick(item, "usetime", "opentime", "restdate", "restdateculture")
            image = self._pick(item, "originimgurl", "smallimageurl", "firstimage", "firstimage2")
            parts = [title]
            if addr:
                parts.append(f"주소 {addr}")
            if tel:
                parts.append(f"문의 {tel}")
            if overview:
                parts.append(f"개요 {overview[:120]}")
            if pet_rules:
                parts.append(f"동반 조건 {pet_rules[:120]}")
            if pet_facilities:
                parts.append(f"반려동물 시설/주의 {pet_facilities[:120]}")
            if parking:
                parts.append(f"주차 {parking}")
            if hours:
                parts.append(f"이용 참고 {hours}")
            if image:
                parts.append("이미지 정보 있음")
            rows.append(" · ".join(parts))
        joined = " / ".join(rows)
        return (
            "TourAPI 반려동물 동반여행 정보에서 가져온 공개 데이터입니다. "
            "반려동물 여행 글에서는 동반 가능 여부, 목줄·이동장, 실내외 가능 구역, 무게·견종 제한, 추가요금, 예약 필요 여부를 중심으로 안내하세요. "
            "운영 정책은 바뀔 수 있으므로 최종 동반 가능 여부와 세부 조건은 방문 당일 업체나 현장에 재확인해야 합니다. "
            f"조회 키워드: {keyword}. 결과: {joined}"
        )
