"""Import central-government press releases from korea.kr.

The agency-specific importer handles a handful of ministries directly. This
script uses Korea Policy Briefing's common press-release index so that all
central-government agencies exposed there can be imported with one parser.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from import_press_releases import (  # noqa: E402
    POSTS_DIR,
    PressRelease,
    clean_text,
    _enrich_release,
    _init_writer,
    extract_hwpx_text,
    first_image,
    get_og_image,
    html_to_text,
    write_post,
)
from blog_agent.config import load_settings  # noqa: E402
from blog_agent.images import ImageAgent  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.korea.kr"
LIST_URL = f"{BASE}/briefing/pressReleaseList.do"
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; BriefWaveKoreaPolicyImporter/1.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


CENTRAL_SECTIONS = ("부처", "청", "위원회", "대통령 소속 위원회")
GENERIC_KOREA_IMAGES = (
    "/images/event/korea_logo_2024.jpg",
    "korea_logo_2024.jpg",
    "/images/event/korea_logo",
)


@dataclass(frozen=True)
class Agency:
    code: str
    name: str
    section: str


FALLBACK_AGENCIES = (
    Agency("A00001", "고용노동부", "부처"),
    Agency("A00002", "교육부", "부처"),
    Agency("A00004", "국무조정실", "부처"),
    Agency("A00005", "국방부", "부처"),
    Agency("A00006", "국토교통부", "부처"),
    Agency("A00009", "문화체육관광부", "부처"),
    Agency("A00012", "보건복지부", "부처"),
    Agency("A00013", "성평등가족부", "부처"),
    Agency("A00033", "과학기술정보통신부", "부처"),
    Agency("A00038", "국가데이터처", "부처"),
    Agency("A00039", "지식재산처", "부처"),
    Agency("B00022", "소방청", "청"),
    Agency("B00023", "질병관리청", "청"),
    Agency("C00012", "원자력안전위원회", "위원회"),
)


@dataclass(frozen=True)
class ListItem:
    title: str
    date: str
    agency: str
    url: str
    lead: str


def request(url: str, *, params: dict[str, str] | None = None) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = SESSION.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}") from last_error


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w가-힣]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:24].strip("-") or "agency"


def prefix_for(agency: Agency) -> str:
    return f"krgov-{agency.code.lower()}-{slugify(agency.name)}"


def extract_agencies(page: str) -> list[Agency]:
    agencies: list[Agency] = []
    seen: set[str] = set()
    for section in CENTRAL_SECTIONS:
        marker = f"<button type=\"button\"><i></i>{section}</button>"
        start = page.find(marker)
        if start < 0:
            continue
        next_start = len(page)
        for other in CENTRAL_SECTIONS:
            other_marker = f"<button type=\"button\"><i></i>{other}</button>"
            idx = page.find(other_marker, start + len(marker))
            if idx > start:
                next_start = min(next_start, idx)
        block = page[start:next_start]
        for code, label in re.findall(
            r'<input name="chkRepCode" type="checkbox" value="([^"]+)" id="\1"[^>]*>\s*'
            r'<label for="\1"[^>]*>(.*?)</label>',
            block,
            flags=re.S,
        ):
            name = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(label)))
            if not name or code in seen:
                continue
            seen.add(code)
            agencies.append(Agency(code=code, name=name, section=section))
    return agencies


def list_agencies() -> list[Agency]:
    try:
        agencies = extract_agencies(request(LIST_URL))
    except Exception as exc:
        print(f"기관 목록 수집 실패, fallback 기관 목록으로 진행합니다: {exc}")
        return list(FALLBACK_AGENCIES)
    if not agencies:
        print("기관 목록을 찾지 못해 fallback 기관 목록으로 진행합니다.")
        return list(FALLBACK_AGENCIES)
    return agencies


def _extract_list_items(page: str, agency_name: str) -> list[ListItem]:
    items: list[ListItem] = []
    for block in re.findall(r"(?is)<li>\s*<a href=\"([^\"]*pressReleaseView\.do[^\"]*)\">(.*?)</a>\s*</li>", page):
        href, inner = block
        title_m = re.search(r"(?is)<strong>(.*?)</strong>", inner)
        lead_m = re.search(r'(?is)<span class="lead">\s*(.*?)\s*</span>', inner)
        source_m = re.search(
            r'(?is)<span class="source">\s*<span>([^<]+)</span>\s*<span>([^<]+)</span>',
            inner,
        )
        if not title_m or not source_m:
            continue
        date = clean_text(source_m.group(1))
        source = clean_text(source_m.group(2))
        if source != agency_name:
            continue
        title = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(title_m.group(1))))
        lead = html_to_text(lead_m.group(1)) if lead_m else ""
        url = urljoin(BASE, html.unescape(href)).split("&pageIndex=", 1)[0]
        items.append(ListItem(title=title, date=date, agency=source, url=url, lead=lead))
    return items


def agency_items(
    agency: Agency,
    limit: int,
    scan_pages: int = 20,
    start_date: str = "2025-01-01",
    end_date: str | None = None,
) -> list[ListItem]:
    items: list[ListItem] = []
    seen: set[str] = set()
    end_date = end_date or datetime.now().strftime("%Y-%m-%d")
    for page_no in range(1, max(1, scan_pages) + 1):
        page = request(
            LIST_URL,
            params={
                "pageIndex": str(page_no),
                "repCode": agency.code,
                "startDate": start_date,
                "endDate": end_date,
            },
        )
        for item in _extract_list_items(page, agency.name):
            if item.url in seen:
                continue
            seen.add(item.url)
            items.append(item)
            if len(items) >= limit:
                return items
        if "list_type" not in page:
            break
    return items


def _jsonld_value(page: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"])*)"', page)
    if not match:
        return ""
    value = match.group(1).replace('\\"', '"').replace("\\n", "\n")
    return clean_text(html.unescape(html.unescape(value)))


def _download_first_hwpx(page: str, page_url: str) -> str:
    for match in re.finditer(
        r'(?is)<a href="([^"]*/common/download\.do\?fileId=[^"]+tblKey=GMN[^"]*)">\s*'
        r'(?:<img[^>]+alt="한글파일"[^>]*>)?([^<]*?\.hwpx)',
        page,
    ):
        href = html.unescape(match.group(1))
        text = extract_hwpx_text(urljoin(BASE, href), referer=page_url)
        if text:
            return text
    return ""


def is_generic_korea_image(url: str) -> bool:
    lowered = (url or "").lower()
    return any(marker.lower() in lowered for marker in GENERIC_KOREA_IMAGES)


def release_from_item(item: ListItem) -> PressRelease:
    page = request(item.url)
    title = clean_text(_jsonld_value(page, "headline") or item.title)
    date_value = _jsonld_value(page, "datePublished")
    date = (date_value[:10] if date_value else item.date.replace(".", "-")[:10]) or datetime.now().strftime("%Y-%m-%d")
    body = _download_first_hwpx(page, item.url)
    if not body:
        desc = _jsonld_value(page, "description")
        view_m = re.search(r'(?is)<div class="view_cont">(.*?)</div>\s*</div>\s*<div class="article_footer">', page)
        body = html_to_text(view_m.group(1)) if view_m else ""
        if len(body) < 250:
            body = desc or item.lead
    if len(body) < 250:
        body = item.lead
    img_url = ""
    img_alt = ""
    view_m = re.search(r'(?is)<div class="view_cont">(.*?)</div>', page)
    if view_m:
        img_url, img_alt = first_image(view_m.group(1), item.url)
    if not img_url:
        img_url = get_og_image(page, item.url)
    if is_generic_korea_image(img_url):
        img_url = ""
        img_alt = ""
    return PressRelease(
        institution=item.agency,
        title=title,
        date=date,
        url=item.url,
        body_text=body,
        image_url=img_url,
        image_alt=img_alt or title,
    )


def existing_post_for_url_anywhere(url: str) -> Path | None:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    matches = sorted(POSTS_DIR.glob(f"*-{digest}.md"))
    return matches[0] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-agency", type=int, default=2)
    parser.add_argument("--agencies", nargs="*", help="기관명 또는 기관코드 일부 지정")
    parser.add_argument("--sections", nargs="*", help="섹션 지정: 부처 청 위원회 대통령 소속 위원회")
    parser.add_argument("--max-agencies", type=int, default=0)
    parser.add_argument("--scan-pages", type=int, default=20, help="기관별 목록을 훑을 최대 페이지 수")
    parser.add_argument("--start-date", default="2025-01-01", help="수집 시작일 YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="수집 종료일 YYYY-MM-DD, 기본값은 오늘")
    parser.add_argument("--max-total-posts", type=int, default=0, help="이번 실행에서 저장할 전체 최대 글 수, 0이면 제한 없음")
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rewrite-titles", action="store_true", help="LLM으로 제목과 본문 품질을 보강")
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    settings.enable_image_generation = False
    image_agent = ImageAgent(settings)
    writer = _init_writer(args.rewrite_titles)
    agencies = list_agencies()
    if args.sections:
        wanted_sections = {section.lower() for section in args.sections}
        agencies = [agency for agency in agencies if agency.section.lower() in wanted_sections]
    if args.agencies:
        wanted = {item.lower() for item in args.agencies}
        agencies = [
            agency
            for agency in agencies
            if agency.code.lower() in wanted
            or agency.name.lower() in wanted
            or any(token in agency.name.lower() for token in wanted)
        ]
    if args.max_agencies:
        agencies = agencies[: args.max_agencies]

    written: list[Path] = []
    errors: list[str] = []
    seq = 0
    end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
    max_total = max(0, args.max_total_posts)
    limit_label = f" / 전체 최대 {max_total}건" if max_total else ""
    print(f"대상 기관: {len(agencies)}개 / 기관당 {args.per_agency}건{limit_label} / 기간 {args.start_date}~{end_date}")

    for agency in agencies:
        if max_total and len(written) >= max_total:
            print(f"\n전체 최대 {max_total}건에 도달하여 수집을 종료합니다.")
            break
        print(f"\n[{agency.section}] {agency.name} ({agency.code})")
        try:
            item_limit = (
                max(args.per_agency * 30, args.per_agency + 80)
                if args.new_only
                else max(args.per_agency * 3, args.per_agency + 8)
            )
            items = agency_items(
                agency,
                item_limit,
                scan_pages=args.scan_pages,
                start_date=args.start_date,
                end_date=end_date,
            )
        except Exception as exc:
            errors.append(f"{agency.name} 목록 실패: {exc}")
            print(f"  x 목록 실패: {exc}")
            continue

        count = 0
        for item in items:
            if args.new_only and existing_post_for_url_anywhere(item.url):
                print(f"  = 기존 글 건너뜀: {item.title[:45]}")
                continue
            try:
                release = release_from_item(item)
                if writer:
                    _enrich_release(release, writer)
                prefix = prefix_for(agency)
                if args.dry_run:
                    print(f"  ? {release.date} {release.title[:60]}")
                else:
                    path = write_post(release, prefix, seq, image_agent=image_agent)
                    written.append(path)
                    print(f"  + {release.date} {release.title[:55]}")
                seq += 1
                count += 1
                if max_total and len(written) >= max_total:
                    print(f"  ! 전체 최대 {max_total}건 도달")
                    break
                if count >= args.per_agency:
                    break
            except Exception as exc:
                errors.append(f"{agency.name} {item.url}: {exc}")
                print(f"  x {item.title[:45]}: {exc}")
        if count < args.per_agency:
            errors.append(f"{agency.name}: {count}/{args.per_agency}건만 저장")
            print(f"  ! {count}/{args.per_agency}건")

    print(f"\n저장 완료: {len(written)}건")
    if errors:
        print(f"오류/부족: {len(errors)}건")
        for error in errors[:80]:
            print(f"  - {error}")
    for path in written:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
