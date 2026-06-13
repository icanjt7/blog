"""Import U.S. government press/news releases into BriefWave posts.

The LOC and MOLEG pages are useful directories, but not live press feeds.
This importer uses official agency RSS feeds that can be checked daily.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from import_press_releases import (  # noqa: E402
    POSTS_DIR,
    PressRelease,
    clean_text,
    estimate_article_quality,
    first_image,
    get_og_image,
    html_to_text,
    write_post,
    yaml_quote,
)
from blog_agent.config import load_settings  # noqa: E402
from blog_agent.images import ImageAgent  # noqa: E402
from blog_agent.writer import WriterAgent  # noqa: E402


TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; BriefWaveUSGovImporter/1.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


@dataclass(frozen=True)
class USSource:
    code: str
    agency: str
    agency_ko: str
    feed_url: str
    category_hint: str
    tags: tuple[str, ...]


@dataclass
class USEntry:
    source: USSource
    title: str
    date: str
    url: str
    summary: str
    image_url: str = ""
    image_alt: str = ""


SOURCES: tuple[USSource, ...] = (
    USSource(
        code="whitehouse",
        agency="The White House",
        agency_ko="미국 백악관",
        feed_url="https://www.whitehouse.gov/releases/feed/",
        category_hint="정치",
        tags=("미국정부", "백악관", "미국정치", "releases"),
    ),
    USSource(
        code="nasa",
        agency="NASA",
        agency_ko="미 항공우주국",
        feed_url="https://www.nasa.gov/news-release/feed/",
        category_hint="기술",
        tags=("미국정부", "NASA", "우주"),
    ),
    USSource(
        code="doj",
        agency="U.S. Department of Justice",
        agency_ko="미 법무부",
        feed_url="https://www.justice.gov/news/rss?type=press_release",
        category_hint="정책",
        tags=("미국정부", "법무부", "사법"),
    ),
    USSource(
        code="ftc_competition",
        agency="Federal Trade Commission",
        agency_ko="미 연방거래위원회",
        feed_url="https://www.ftc.gov/feeds/press-release-competition.xml",
        category_hint="정책",
        tags=("미국정부", "FTC", "경쟁정책"),
    ),
    USSource(
        code="education",
        agency="U.S. Department of Education",
        agency_ko="미 교육부",
        feed_url="https://www.ed.gov/rss.xml",
        category_hint="생활",
        tags=("미국정부", "교육부", "교육"),
    ),
    USSource(
        code="bls",
        agency="U.S. Bureau of Labor Statistics",
        agency_ko="미 노동통계국",
        feed_url="https://www.bls.gov/feed/empsit.rss",
        category_hint="정책",
        tags=("미국정부", "노동통계국", "고용지표"),
    ),
    USSource(
        code="whitehouse_briefings",
        agency="The White House",
        agency_ko="미국 백악관",
        feed_url="https://www.whitehouse.gov/briefings-statements/feed/",
        category_hint="정치",
        tags=("미국정부", "백악관", "브리핑"),
    ),
    USSource(
        code="ftc_consumer",
        agency="Federal Trade Commission",
        agency_ko="미 연방거래위원회",
        feed_url="https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
        category_hint="생활",
        tags=("미국정부", "FTC", "소비자보호"),
    ),
    USSource(
        code="bls_cpi",
        agency="U.S. Bureau of Labor Statistics",
        agency_ko="미 노동통계국",
        feed_url="https://www.bls.gov/feed/cpi.rss",
        category_hint="정책",
        tags=("미국정부", "노동통계국", "소비자물가"),
    ),
    USSource(
        code="whitehouse_fact_sheets",
        agency="The White House",
        agency_ko="미국 백악관",
        feed_url="https://www.whitehouse.gov/fact-sheets/feed/",
        category_hint="정책",
        tags=("미국정부", "백악관", "팩트시트"),
    ),
    USSource(
        code="bls_ppi",
        agency="U.S. Bureau of Labor Statistics",
        agency_ko="미 노동통계국",
        feed_url="https://www.bls.gov/feed/ppi.rss",
        category_hint="정책",
        tags=("미국정부", "노동통계국", "생산자물가"),
    ),
    USSource(
        code="whitehouse_presidential_actions",
        agency="The White House",
        agency_ko="미국 백악관",
        feed_url="https://www.whitehouse.gov/presidential-actions/feed/",
        category_hint="정치",
        tags=("미국정부", "백악관", "대통령조치"),
    ),
)


CATEGORY_MARKERS = {
    "정치": "대통령 백악관 의회 행정부 외교 안보 선거 정치",
    "기술": "기술 AI 우주 에너지 연구개발 데이터 인프라 산업 혁신",
    "생활": "생활 소비자 교육 학생 노동 안전 건강 피해 예방 신청 대상",
    "정책": "정책 법 집행 규제 제도 예산 기관 발표",
    "핫이슈": "국제 이슈 문화 행사 현장 발표 관심",
}


def request_text(url: str) -> str:
    resp = SESSION.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def parse_date(entry: object) -> str:
    for key in ("published", "updated", "created"):
        raw = getattr(entry, "get", lambda _k, _d=None: _d)(key, "")
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw).date().isoformat()
        except (TypeError, ValueError, IndexError, AttributeError):
            pass
        match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", str(raw))
        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return datetime.now().date().isoformat()


def entry_html(entry: object) -> str:
    parts: list[str] = []
    for key in ("summary", "description"):
        value = getattr(entry, "get", lambda _k, _d=None: _d)(key, "")
        if value:
            parts.append(str(value))
    for content in getattr(entry, "get", lambda _k, _d=None: _d)("content", []) or []:
        value = content.get("value", "") if isinstance(content, dict) else ""
        if value:
            parts.append(value)
    return "\n".join(parts)


def entry_image(entry: object, fragment: str, url: str) -> tuple[str, str]:
    media = getattr(entry, "get", lambda _k, _d=None: _d)("media_content", []) or []
    for item in media:
        src = item.get("url", "") if isinstance(item, dict) else ""
        if src and not src.endswith(".svg"):
            return src, getattr(entry, "get", lambda _k, _d=None: _d)("title", "")
    img, alt = first_image(fragment, url)
    return img, alt


def fetch_feed(source: USSource, limit: int) -> list[USEntry]:
    parsed = feedparser.parse(source.feed_url, request_headers={"User-Agent": USER_AGENT})
    entries: list[USEntry] = []
    for entry in parsed.entries[: max(limit, 1) * 8]:
        title = clean_text(html.unescape(entry.get("title", "")))
        url = clean_text(entry.get("link", ""))
        if not title or not url:
            continue
        fragment = entry_html(entry)
        summary = html_to_text(fragment)
        image_url, image_alt = entry_image(entry, fragment, url)
        if len(summary) < 120:
            summary = f"{source.agency} published a new release titled {title}."
        entries.append(
            USEntry(
                source=source,
                title=title,
                date=parse_date(entry),
                url=url,
                summary=summary,
                image_url=image_url,
                image_alt=image_alt or title,
            )
        )
        if len(entries) >= limit:
            break
    return entries


def fetch_page_context(entry: USEntry) -> tuple[str, str, str]:
    try:
        page = request_text(entry.url)
    except Exception:
        return entry.summary, entry.image_url, entry.image_alt
    image_url = entry.image_url or get_og_image(page, entry.url)
    image_alt = entry.image_alt or entry.title
    if not image_url:
        image_url, image_alt = first_image(page, entry.url)

    candidates = []
    for pattern in (
        r"(?is)<article\b[^>]*>(.*?)</article>",
        r"(?is)<main\b[^>]*>(.*?)</main>",
        r"(?is)<div[^>]+class=[\"'][^\"']*(?:field--name-body|article-body|release-body|body-content|entry-content|node__content)[^\"']*[\"'][^>]*>(.*?)</div>",
    ):
        match = re.search(pattern, page)
        if match:
            candidates.append(html_to_text(match.group(1)))
    candidates.append(entry.summary)
    text = max(candidates, key=len)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:6000], image_url, image_alt


def existing_post_for_url_anywhere(url: str) -> Path | None:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    matches = sorted(POSTS_DIR.glob(f"*-{digest}.md"))
    return matches[0] if matches else None


def _call_llm(writer: WriterAgent | None, prompt: str, *, temperature: float = 0.65, max_tokens: int = 2200) -> str:
    if not writer or not writer._providers:
        return ""
    last_error = ""
    for client, model in writer._providers:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}"
            continue
    if last_error:
        print(f"  ! LLM 전체 실패: {last_error}")
    return ""


def korean_article(entry: USEntry, source_text: str, writer: WriterAgent | None) -> tuple[str, str]:
    prompt = f"""다음은 미국 정부 공식 기관의 보도자료 또는 뉴스 릴리스입니다.
한국 독자가 이해할 수 있도록 한국어 블로그 기사로 재작성하세요.

[기관]
영문: {entry.source.agency}
국문 표기: {entry.source.agency_ko}

[원문 제목]
{entry.title}

[발표일]
{entry.date}

[원문 URL]
{entry.url}

[원문 내용]
{source_text[:4200]}

[작성 규칙]
- 제목은 한국어 34자 이내, 기관명이나 변화 포인트를 포함
- 본문은 1,300~1,800자
- 원문에 없는 수치, 인명, 결론을 만들지 않기
- 첫 단락에서 어떤 기관의 어떤 발표인지 명확히 설명
- '미국 이야기라 한국과 무관하다'처럼 단정하지 말고, 한국 독자가 볼 연결점을 설명
- 최소 4개 섹션을 ## 헤딩으로 구성
- 표 1개 포함: 항목 / 내용
- 마지막에는 원문 확인 링크를 안내
- 반복형 체크리스트나 범용 문장 금지

응답 형식:
TITLE:
BODY:
"""
    generated = _call_llm(writer, prompt)
    title = extract_label(generated, "TITLE") or fallback_title(entry)
    body = extract_label(generated, "BODY") or ""
    if len(clean_text(body)) < 700:
        body = fallback_body(entry, source_text)
    return title, body


def extract_label(text: str, label: str) -> str:
    if not text:
        return ""
    pattern = rf"(?is){label}\s*:\s*(.*?)(?=\n[A-Z가-힣_ ]{{2,20}}\s*:|\Z)"
    match = re.search(pattern, text)
    if not match:
        return ""
    value = match.group(1).strip()
    return re.sub(r"^```(?:markdown)?|```$", "", value).strip()


def fallback_title(entry: USEntry) -> str:
    title = re.sub(r"\s+", " ", entry.title).strip()
    return f"{entry.source.agency_ko}, {title[:24]}".rstrip()


def fallback_body(entry: USEntry, source_text: str) -> str:
    summary = clean_text(source_text or entry.summary)
    sentences = [
        clean_text(item)
        for item in re.split(r"(?<=[.!?])\s+", summary)
        if len(clean_text(item)) > 35
    ][:8]
    if not sentences:
        sentences = [f"{entry.source.agency}가 '{entry.title}' 관련 발표를 공개했습니다."]
    marker = CATEGORY_MARKERS.get(entry.source.category_hint, CATEGORY_MARKERS["정책"])
    points = "\n".join(f"- {line}" for line in sentences[1:5]) or f"- 원문 제목: {entry.title}\n- 발표 기관: {entry.source.agency}"
    table = (
        "| 항목 | 내용 |\n"
        "|---|---|\n"
        f"| 발표 기관 | {entry.source.agency_ko} ({entry.source.agency}) |\n"
        f"| 발표일 | {entry.date} |\n"
        f"| 분류 기준 | {entry.source.category_hint} / {marker} |\n"
        f"| 원문 | [{entry.source.agency} release]({entry.url}) |\n"
    )
    return (
        f"{entry.source.agency_ko}가 {entry.date} 공개한 공식 발표를 바탕으로, 한국 독자가 확인할 핵심 맥락을 정리했습니다.\n\n"
        "## 어떤 발표인가\n\n"
        f"{sentences[0]}\n\n"
        "## 핵심 내용\n\n"
        f"{points}\n\n"
        "## 한눈에 보는 기준\n\n"
        f"{table}\n"
        "## 한국 독자가 볼 부분\n\n"
        f"이 발표는 미국 내 {entry.source.category_hint} 흐름을 보여주는 자료입니다. "
        "한국 기업, 연구기관, 소비자, 정책 담당자가 직접 적용할 내용인지 판단하려면 발표 기관, 대상, 시행 시점, 후속 문서를 함께 확인해야 합니다.\n\n"
        "## 원문 확인\n\n"
        f"- [{entry.source.agency} 공식 자료]({entry.url})\n"
    )


def write_us_post(
    entry: USEntry,
    title: str,
    body: str,
    sequence: int,
    image_agent: ImageAgent | None,
    overwrite: bool = False,
) -> Path:
    release = PressRelease(
        institution=entry.source.agency_ko,
        title=title,
        date=entry.date,
        url=entry.url,
        body_text=f"{CATEGORY_MARKERS.get(entry.source.category_hint, '')}\n\n{body}",
        image_url=entry.image_url,
        image_alt=entry.image_alt or title,
    )
    path = write_post(release, f"usgov-{entry.source.code}", sequence, overwrite=overwrite, image_agent=image_agent)

    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return path
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return path
    frontmatter = parts[1]
    category = entry.source.category_hint
    tags = ["보도기사", "미국정부", entry.source.agency_ko, category, *entry.source.tags]
    tag_block = "tags:\n" + "".join(f"  - {yaml_quote(tag)}\n" for tag in dict.fromkeys(tags))
    frontmatter = re.sub(r'^category:\s*.*$', f"category: {yaml_quote(category)}", frontmatter, flags=re.M)
    frontmatter = re.sub(r"(?ms)^tags:\n(?:  - .*\n)+", tag_block, frontmatter)
    frontmatter = re.sub(r'^author:\s*.*$', f"author: {yaml_quote(entry.source.agency_ko)}", frontmatter, flags=re.M)
    final_body = body.strip() + "\n"
    score = estimate_article_quality(final_body)
    frontmatter = re.sub(r"^quality_score:\s*.*$", f"quality_score: {score:.1f}", frontmatter, flags=re.M)
    path.write_text(f"---{frontmatter}---\n\n{final_body}", encoding="utf-8")
    return path


def init_writer(enabled: bool) -> WriterAgent | None:
    if not enabled:
        return None
    try:
        writer = WriterAgent(load_settings())
        if writer._client:
            print(f"LLM 활성화 (모델: {writer._model})")
            return writer
        print("LLM 키 없음 - 규칙 기반 기사로 진행합니다.")
    except Exception as exc:
        print(f"LLM 초기화 실패: {exc}")
    return None


def init_image_agent() -> ImageAgent | None:
    try:
        settings = load_settings()
        settings.enable_image_generation = False
        return ImageAgent(settings)
    except Exception as exc:
        print(f"이미지 검색 초기화 실패: {exc}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=1)
    parser.add_argument("--max-total-posts", type=int, default=6)
    parser.add_argument("--sources", nargs="*", help="Optional source codes, e.g. nasa doj ftc")
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    selected = list(SOURCES)
    if args.sources:
        wanted = {item.lower() for item in args.sources}
        selected = [source for source in selected if source.code in wanted or source.agency.lower() in wanted]

    writer = init_writer(not args.no_llm)
    image_agent = init_image_agent()
    written: list[Path] = []
    errors: list[str] = []
    max_total = max(0, args.max_total_posts)
    seq = 0

    print(f"대상 미국 기관: {len(selected)}개 / 기관당 {args.per_source}건 / 전체 최대 {max_total or '제한 없음'}건")
    for source in selected:
        if max_total and len(written) >= max_total:
            break
        print(f"\n[{source.agency_ko}] {source.feed_url}")
        try:
            entries = fetch_feed(source, max(args.per_source * 6, args.per_source + 8))
        except Exception as exc:
            errors.append(f"{source.agency_ko} 피드 실패: {exc}")
            print(f"  x 피드 실패: {exc}")
            continue
        count = 0
        for entry in entries:
            if args.new_only and existing_post_for_url_anywhere(entry.url):
                print(f"  = 기존 글 건너뜀: {entry.title[:60]}")
                continue
            try:
                source_text, image_url, image_alt = fetch_page_context(entry)
                entry.image_url = image_url
                entry.image_alt = image_alt
                title, body = korean_article(entry, source_text, writer)
                if args.dry_run:
                    print(f"  ? {entry.date} {title[:60]}")
                else:
                    path = write_us_post(entry, title, body, seq, image_agent=image_agent)
                    written.append(path)
                    print(f"  + {entry.date} {title[:60]}")
                seq += 1
                count += 1
                if max_total and len(written) >= max_total:
                    break
                if count >= args.per_source:
                    break
            except Exception as exc:
                errors.append(f"{source.agency_ko} {entry.url}: {exc}")
                print(f"  x {entry.title[:50]}: {exc}")
        if count < args.per_source:
            errors.append(f"{source.agency_ko}: {count}/{args.per_source}건만 처리")
            print(f"  ! {count}/{args.per_source}건")

    print(f"\n저장 완료: {len(written)}건")
    if errors:
        print(f"오류/부족: {len(errors)}건")
        for error in errors[:60]:
            print(f"  - {error}")
    for path in written:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
