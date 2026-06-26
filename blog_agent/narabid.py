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


def write_bid_digest(path: Path, notices: list[BidNotice], *, generated_at: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_bid_digest(notices, generated_at=generated_at), encoding="utf-8")
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
