from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import requests


DEFAULT_ENDPOINT = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
DATASET_URL = "https://www.data.go.kr/data/15129394/openapi.do"

OPERATIONS: dict[str, tuple[str, str]] = {
    "goods": ("물품", "getBidPblancListInfoThngPPSSrch"),
    "service": ("용역", "getBidPblancListInfoServcPPSSrch"),
    "construction": ("공사", "getBidPblancListInfoCnstwkPPSSrch"),
    "foreign": ("외자", "getBidPblancListInfoFrgcptPPSSrch"),
}


@dataclass(frozen=True)
class BidNotice:
    work_type: str
    bid_no: str
    bid_ord: str
    title: str
    notice_inst: str = ""
    demand_inst: str = ""
    contract_method: str = ""
    posted_at: str = ""
    bid_begin_at: str = ""
    bid_close_at: str = ""
    open_at: str = ""
    budget_amount: str = ""
    detail_url: str = ""

    @property
    def key(self) -> str:
        return f"{self.bid_no}-{self.bid_ord or '0'}"


class NaraBidClient:
    def __init__(
        self,
        service_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 12,
    ) -> None:
        self.service_key = unquote(service_key)
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def fetch_recent(
        self,
        work_types: list[str] | None = None,
        *,
        limit: int = 50,
        days: int = 1,
        keywords: list[str] | None = None,
    ) -> list[BidNotice]:
        selected = work_types or ["goods", "service", "construction"]
        # 업무구분별 1회 호출로 충분히 후보를 모은 뒤 중복 제거한다.
        per_operation = max(limit, 20)
        notices: list[BidNotice] = []
        for work_type in selected:
            notices.extend(self.fetch_by_work_type(work_type, num_rows=per_operation, days=days))

        if keywords:
            lowered = [keyword.lower() for keyword in keywords if keyword]
            notices = [notice for notice in notices if any(keyword in notice.title.lower() for keyword in lowered)]

        unique: dict[str, BidNotice] = {}
        for notice in notices:
            unique.setdefault(notice.key, notice)

        return sorted(
            unique.values(),
            key=lambda notice: (_sort_date(notice.bid_close_at), _sort_date(notice.posted_at)),
        )[:limit]

    def fetch_by_work_type(self, work_type: str, *, num_rows: int = 50, days: int = 1) -> list[BidNotice]:
        if work_type not in OPERATIONS:
            supported = ", ".join(sorted(OPERATIONS))
            raise ValueError(f"Unsupported work type: {work_type}. Supported: {supported}")
        label, operation = OPERATIONS[work_type]
        end = datetime.now()
        begin = end - timedelta(days=max(1, days))
        params = {
            "serviceKey": self.service_key,
            "pageNo": "1",
            "numOfRows": str(num_rows),
            "type": "json",
            "inqryDiv": "1",
            "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
            "inqryEndDt": end.strftime("%Y%m%d%H%M"),
        }
        items = self._get_items(f"{self.endpoint}/{operation}", params)
        if not items:
            fallback = dict(params)
            fallback.pop("inqryBgnDt", None)
            fallback.pop("inqryEndDt", None)
            fallback["bidNtceBgnDt"] = begin.strftime("%Y%m%d%H%M")
            fallback["bidNtceEndDt"] = end.strftime("%Y%m%d%H%M")
            items = self._get_items(f"{self.endpoint}/{operation}", fallback)
        return [_notice_from_item(label, item) for item in items]

    def _get_items(self, url: str, params: dict[str, str]) -> list[dict]:
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "unknown")
            raise RuntimeError(f"Nara Bid API request failed with status {status}") from exc
        body = data.get("response", {}).get("body", {})
        items = body.get("items", {})
        if isinstance(items, list):
            return [value for value in items if isinstance(value, dict)]
        if not isinstance(items, dict):
            return []
        item = items.get("item", [])
        if isinstance(item, dict):
            return [item]
        if isinstance(item, list):
            return [value for value in item if isinstance(value, dict)]
        return []


def render_bid_digest(notices: list[BidNotice], *, generated_at: datetime | None = None) -> str:
    now = generated_at or datetime.now()
    title = f"{now:%Y-%m-%d} 나라장터 입찰공고 {len(notices)}건"
    rows = "\n".join(_table_row(index, notice) for index, notice in enumerate(notices, start=1))
    if not rows:
        rows = "| - | - | 조회된 공고가 없습니다. | - | - | - | - |\n"

    return f"""---
title: "{title}"
date: "{now:%Y-%m-%dT%H:%M}"
category: "정책"
tags:
  - "나라장터"
  - "입찰공고"
  - "공공조달"
  - "조달청"
author: "조달청"
---

조달청 나라장터 입찰공고정보서비스 공개 데이터를 기준으로 최근 입찰공고를 모았습니다. 실제 참가 여부, 제출서류, 입찰참가자격, 기초금액은 반드시 나라장터 원문 공고에서 다시 확인해야 합니다.

## 오늘 확인할 공고

| 번호 | 구분 | 공고명 | 공고기관 | 수요기관 | 마감일시 | 계약방법 |
|---:|---|---|---|---|---|---|
{rows}

## 확인할 점

- 마감일시가 가까운 공고부터 원문 공고서와 첨부파일을 확인합니다.
- 지역 제한, 면허 제한, 공동수급 여부는 공고별 조건이 다를 수 있습니다.
- 기초금액과 추정가격은 변경될 수 있으므로 투찰 전 나라장터 최신 공고를 기준으로 봅니다.

## 출처

- [조달청 나라장터 입찰공고정보서비스]({DATASET_URL})
"""


def render_service_digest(notices: list[BidNotice], *, generated_at: datetime | None = None) -> str:
    now = generated_at or datetime.now()
    title = f"{now:%Y-%m-%d} 나라장터 용역 입찰공고 {len(notices)}건"
    sections = "\n\n".join(_service_section(index, notice) for index, notice in enumerate(notices, start=1))
    if not sections:
        sections = "조회된 용역 공고가 없습니다."

    return f"""---
title: "{title}"
date: "{now:%Y-%m-%dT%H:%M}"
category: "정책"
tags:
  - "나라장터"
  - "용역입찰"
  - "입찰공고"
  - "공공조달"
  - "조달청"
author: "조달청"
---

조달청 나라장터 입찰공고정보서비스 공개 데이터를 기준으로 최근 용역 입찰공고를 정리했습니다. 아래 요약은 공고 목록에 공개된 공고명, 공고기관, 수요기관, 마감일시, 계약방법을 바탕으로 작성한 안내입니다. 실제 과업 범위, 참가자격, 제출서류, 배점 기준은 반드시 나라장터 원문 공고와 첨부파일에서 다시 확인해야 합니다.

## 용역 공고 요약

{sections}

## 공통 확인사항

- 과업지시서와 제안요청서에서 실제 수행 범위와 산출물을 확인합니다.
- 참가자격, 면허·실적 제한, 공동수급 허용 여부를 공고별로 확인합니다.
- 제출 마감일시와 전자입찰 방식은 나라장터 원문 공고 기준으로 다시 확인합니다.

## 출처

- [조달청 나라장터 입찰공고정보서비스]({DATASET_URL})
"""


def write_bid_digest(path: Path, notices: list[BidNotice], *, generated_at: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_bid_digest(notices, generated_at=generated_at), encoding="utf-8")
    return path


def write_service_digest(path: Path, notices: list[BidNotice], *, generated_at: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_service_digest(notices, generated_at=generated_at), encoding="utf-8")
    return path


def _notice_from_item(work_type: str, item: dict) -> BidNotice:
    return BidNotice(
        work_type=work_type,
        bid_no=_pick(item, "bidNtceNo"),
        bid_ord=_pick(item, "bidNtceOrd"),
        title=_pick(item, "bidNtceNm"),
        notice_inst=_pick(item, "ntceInsttNm"),
        demand_inst=_pick(item, "dminsttNm"),
        contract_method=_pick(item, "cntrctCnclsMthdNm", "cntrctMthdNm"),
        posted_at=_pick(item, "bidNtceDt", "bidNtceDate"),
        bid_begin_at=_pick(item, "bidBeginDt"),
        bid_close_at=_pick(item, "bidClseDt"),
        open_at=_pick(item, "opengDt"),
        budget_amount=_pick(item, "asignBdgtAmt", "presmptPrce", "rsrvtnPrceRngBgnRate"),
        detail_url=_pick(item, "bidNtceUrl", "ntceSpecDocUrl1"),
    )


def _pick(item: dict, *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value is not None and str(value).strip():
            return re.sub(r"\s+", " ", str(value)).strip()
    return ""


def _sort_date(value: str) -> str:
    return value or "9999"


def _table_row(index: int, notice: BidNotice) -> str:
    title = _escape_cell(notice.title or "(공고명 없음)")
    if notice.detail_url:
        title = f"[{title}]({notice.detail_url})"
    return (
        f"| {index} | {_escape_cell(notice.work_type)} | {title} | "
        f"{_escape_cell(notice.notice_inst or '-')} | {_escape_cell(notice.demand_inst or '-')} | "
        f"{_escape_cell(notice.bid_close_at or '-')} | {_escape_cell(notice.contract_method or '-')} |"
    )


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _service_section(index: int, notice: BidNotice) -> str:
    title = notice.title or "(공고명 없음)"
    original = f"\n- 원문: [나라장터 공고]({notice.detail_url})" if notice.detail_url else ""
    return f"""### {index}. {_escape_heading(title)}

- 공고기관: {notice.notice_inst or '-'}
- 수요기관: {notice.demand_inst or '-'}
- 마감일시: {notice.bid_close_at or '-'}
- 계약방법: {notice.contract_method or '-'}{original}

요약: {_service_summary(notice)}

확인할 점: {_service_checkpoints(notice)}"""


def _service_summary(notice: BidNotice) -> str:
    title = notice.title or "공고명 미상"
    owner = notice.demand_inst or notice.notice_inst or "수요기관"
    topic = _service_topic(title)
    return (
        f"{owner}에서 추진하는 {title}입니다. "
        f"공고명 기준으로는 {topic} 관련 업무를 맡을 수행업체를 찾는 공고로 볼 수 있습니다."
    )


def _service_topic(title: str) -> str:
    rules: tuple[tuple[str, str], ...] = (
        ("폐기물", "건설폐기물 또는 사업장 폐기물 처리"),
        ("쓰레기", "폐기물 수거·운반·처리"),
        ("처리용역", "처리 대상 물량의 운반·처리"),
        ("유지관리", "시설·장비·시스템 유지관리"),
        ("정비", "시설 정비 또는 개선"),
        ("수리", "장비·시설 수리"),
        ("임차", "차량·장비·공간 임차"),
        ("임대", "차량·장비·공간 임차"),
        ("전송서비스", "메시지 전송 서비스 운영"),
        ("데이터", "데이터 구축·분석"),
        ("운영", "사업 운영 또는 현장 운영 지원"),
        ("행사", "행사 기획·운영"),
        ("축전", "행사 기획·운영"),
        ("홍보", "홍보·마케팅"),
        ("연구", "조사·분석·연구"),
        ("조사", "현황 조사와 자료 분석"),
        ("설계", "설계와 기술 검토"),
        ("감리", "공사·사업 감리"),
        ("청소", "청소·환경관리"),
        ("교육", "교육 운영 또는 역량 강화"),
        ("위탁", "업무 위탁 운영"),
        ("시스템", "정보시스템 구축·운영"),
        ("정보화", "정보화 사업"),
        ("진단", "안전·품질 진단"),
    )
    for keyword, topic in rules:
        if keyword in title:
            return topic
    return "해당 기관이 공고명에 제시한 과업"


def _service_checkpoints(notice: BidNotice) -> str:
    title = notice.title
    checks = ["과업 범위", "수행 기간", "제출서류", "참가자격"]
    if "폐기물" in title:
        checks.extend(["폐기물 종류", "처리 물량", "운반·처리 허가 기준"])
    elif "쓰레기" in title or "처리용역" in title:
        checks.extend(["처리 대상", "예상 물량", "운반·처리 기준"])
    elif "유지관리" in title or "시스템" in title:
        checks.extend(["장애 대응 시간", "투입 인력", "유지보수 대상"])
    elif "수리" in title or "정비" in title:
        checks.extend(["수리 범위", "부품·장비 기준", "검수 조건"])
    elif "임차" in title or "임대" in title:
        checks.extend(["임차 기간", "제공 장비·차량 규격", "유지관리 책임"])
    elif "행사" in title or "축전" in title or "홍보" in title:
        checks.extend(["행사 일정", "대행 범위", "성과물 기준"])
    elif "연구" in title or "조사" in title:
        checks.extend(["연구 범위", "보고서 산출물", "전문인력 기준"])
    elif "설계" in title or "감리" in title:
        checks.extend(["기술자격", "설계·감리 범위", "현장 조건"])
    return ", ".join(dict.fromkeys(checks))


def _escape_heading(value: str) -> str:
    return value.replace("\n", " ").strip()
