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
    extract_detail_lines,
    extract_sentences,
    first_image,
    get_og_image,
    html_to_text,
    with_particle,
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

WEAK_US_MARKERS = (
    "한국 기업, 연구기관, 소비자, 정책 담당자가 직접 적용할 내용인지 판단하려면",
    "발표 기관, 대상, 시행 시점, 후속 문서를 함께 확인해야 합니다",
    "공개한 공식 발표를 바탕으로, 한국 독자가 확인할 핵심 맥락을 정리했습니다",
)


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
    outputs = _llm_outputs(writer, prompt, temperature=temperature, max_tokens=max_tokens)
    return outputs[0] if outputs else ""


def _llm_outputs(
    writer: WriterAgent | None,
    prompt: str,
    *,
    temperature: float = 0.65,
    max_tokens: int = 2200,
) -> list[str]:
    if not writer or not writer._providers:
        return []
    outputs: list[str] = []
    last_error = ""
    for client, model in writer._providers:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                outputs.append(text)
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}"
            continue
    if last_error:
        print(f"  ! LLM 전체 실패: {last_error}")
    return outputs


def korean_article(entry: USEntry, source_text: str, writer: WriterAgent | None) -> tuple[str, str]:
    source_facts = source_fact_pack(entry, source_text)
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

[원문에서 추출한 확인 포인트]
{source_facts}

[작성 규칙]
- 제목은 한국어 34자 이내, 기관명이나 변화 포인트를 포함
- 본문은 1,500~2,100자
- 원문에 없는 수치, 인명, 결론을 만들지 않기
- 첫 단락에서 {entry.source.agency_ko}({entry.source.agency})가 {entry.date}에 어떤 발표를 했는지 명확히 설명
- 발표 대상, 조치 내용, 일정, 금액, 기관명, 수치가 원문에 있으면 구체적으로 반영
- '미국 이야기라 한국과 무관하다'처럼 단정하지 말고, 한국 독자가 볼 연결점을 설명
- 최소 5개 섹션을 ## 헤딩으로 구성: 발표 내용 / 세부 내용 / 숫자와 일정 / 한국 독자가 볼 부분 / 원문 확인
- 표 1개 포함: 항목 / 내용
- 마지막에는 원문 확인 링크를 안내
- 반복형 체크리스트나 "공식 발표를 확인해야 한다" 수준의 범용 문장 금지
- 원문이 짧으면 짧다고 말하지 말고, 확인 가능한 사실만 촘촘히 풀어 설명

응답 형식:
TITLE:
BODY:
"""
    fallback_title_value = fallback_title(entry)
    for generated in _llm_outputs(writer, prompt):
        title = normalize_title(extract_label(generated, "TITLE"), entry)
        body = extract_label(generated, "BODY") or ""
        if us_article_is_specific(body, entry):
            return title, body
        fallback_title_value = title or fallback_title_value
    return fallback_title_value, fallback_body(entry, source_text)


def us_article_is_specific(body: str, entry: USEntry) -> bool:
    cleaned = clean_text(body)
    if len(cleaned) < 900:
        return False
    if entry.source.agency_ko not in cleaned and entry.source.agency not in cleaned:
        return False
    if len(re.findall(r"^##\s+", body, flags=re.M)) < 4:
        return False
    generic_markers = (*WEAK_US_MARKERS, "이 발표는 미국 내")
    if any(marker in cleaned for marker in generic_markers):
        return False
    return bool(re.search(r"\d|대상|기관|조치|시행|일정|금액|규제|지원|소송|발표", cleaned))


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


def normalize_title(value: str, entry: USEntry) -> str:
    """Keep LLM titles safe for YAML/frontmatter and filenames."""
    value = clean_text(value.replace("\\n", "\n"))
    value = re.split(r"(?i)\b(?:BODY|EXCERPT)\s*:", value, maxsplit=1)[0]
    value = re.sub(r"(?i)^TITLE\s*:\s*", "", value).strip()
    value = value.splitlines()[0] if value.splitlines() else value
    value = value.strip(" \t\r\n\"'`*_#:-")
    value = re.sub(r"\s+", " ", value)
    if len(value) > 70:
        value = value[:70].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if len(value) < 4 or value in {"**", "---"}:
        return fallback_title(entry)
    return value


def fallback_body(entry: USEntry, source_text: str) -> str:
    summary = clean_text(source_text or entry.summary)
    sentences = extract_sentences(summary, limit=10)
    detail_lines = extract_detail_lines(source_text or entry.summary, limit=6)
    if not sentences:
        sentences = [f"{entry.source.agency}가 '{entry.title}' 관련 발표를 공개했습니다."]
    marker = CATEGORY_MARKERS.get(entry.source.category_hint, CATEGORY_MARKERS["정책"])
    points_source = sentences[1:6] or detail_lines[:5] or sentences[:4]
    points = "\n".join(f"- {line}" for line in points_source) or f"- 원문 제목: {entry.title}\n- 발표 기관: {entry.source.agency}"
    facts = extract_us_facts(summary, limit=5)
    fact_block = "\n".join(f"- {line}" for line in facts) or "\n".join(f"- {line}" for line in detail_lines[:4])
    if not fact_block:
        fact_block = f"- 발표 기관: {entry.source.agency_ko} ({entry.source.agency})\n- 발표일: {entry.date}\n- 원문 제목: {entry.title}"
    table = (
        "| 항목 | 내용 |\n"
        "|---|---|\n"
        f"| 발표 기관 | {entry.source.agency_ko} ({entry.source.agency}) |\n"
        f"| 발표일 | {entry.date} |\n"
        f"| 원문 제목 | {entry.title} |\n"
        f"| 분류 기준 | {entry.source.category_hint} / {marker} |\n"
        f"| 원문 | [{entry.source.agency} release]({entry.url}) |\n"
    )
    korea_angle = korean_reader_angle(entry, summary)
    return (
        f"{with_particle(entry.source.agency_ko, '이', '가')}({entry.source.agency}) {entry.date} 공개한 '{entry.title}' 발표를 바탕으로, 확인 가능한 사실을 중심으로 정리했습니다.\n\n"
        "## 어떤 발표인가\n\n"
        f"{sentences[0]}\n\n"
        "## 발표에서 확인되는 내용\n\n"
        f"{points}\n\n"
        "## 숫자와 고유명사\n\n"
        f"{fact_block}\n\n"
        "## 한눈에 보는 원문 기준\n\n"
        f"{table}\n"
        "## 한국 독자가 볼 부분\n\n"
        f"{korea_angle}\n\n"
        "## 원문 확인\n\n"
        f"- [{entry.source.agency} 공식 자료]({entry.url})\n"
    )


def source_fact_pack(entry: USEntry, source_text: str) -> str:
    facts = extract_us_facts(source_text or entry.summary, limit=6)
    details = extract_detail_lines(source_text or entry.summary, limit=4)
    lines = [
        f"- 발표 기관: {entry.source.agency_ko} ({entry.source.agency})",
        f"- 발표일: {entry.date}",
        f"- 원문 제목: {entry.title}",
    ]
    for item in [*facts, *details]:
        if item not in lines:
            lines.append(f"- {item}")
        if len(lines) >= 9:
            break
    return "\n".join(lines)


def extract_us_facts(text: str, limit: int = 5) -> list[str]:
    facts: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
        line = clean_text(raw)
        if len(line) < 28:
            continue
        if not re.search(
            r"\d|percent|million|billion|trillion|department|agency|commission|court|act|rule|program|grant|"
            r"lawsuit|settlement|NASA|FTC|DOJ|White House|Bureau|Labor|Education",
            line,
            flags=re.I,
        ):
            continue
        if line not in facts:
            facts.append(line[:260].rstrip(" ,.;"))
        if len(facts) >= limit:
            break
    return facts


def korean_reader_angle(entry: USEntry, text: str) -> str:
    lower = text.lower()
    if any(key in lower for key in ["consumer", "fraud", "scam", "privacy", "data", "payment"]):
        return "소비자 보호나 개인정보, 결제 관행과 관련된 발표라면 국내 서비스 이용자도 유사한 약관, 환불, 데이터 활용 방식을 비교해 볼 수 있습니다. 특히 플랫폼 기업이나 해외 서비스를 쓰는 경우에는 미국 규제기관이 문제 삼은 행위가 무엇인지 확인하는 것이 도움이 됩니다."
    if any(key in lower for key in ["nasa", "space", "mission", "launch", "galaxy", "artemis"]):
        return "우주·과학 분야 발표는 국내 연구기관, 대학, 항공우주 산업 종사자가 기술 협력 흐름을 살필 때 참고할 만합니다. 임무 일정, 관측 장비, 연구 목표처럼 원문에 적힌 고유 정보를 중심으로 보는 것이 좋습니다."
    if any(key in lower for key in ["employment", "payroll", "cpi", "ppi", "prices", "wages", "inflation"]):
        return "고용·물가 지표는 미국 경기 판단뿐 아니라 환율, 금리, 수출 기업의 비용 전망과도 연결됩니다. 다만 원문 지표의 기준월, 계절조정 여부, 전월 대비·전년 대비 구분을 함께 봐야 해석이 흔들리지 않습니다."
    if any(key in lower for key in ["court", "justice", "sentence", "indictment", "law enforcement"]):
        return "법 집행 발표는 특정 사건의 판결이나 수사 결과를 다루는 경우가 많습니다. 국내 독자는 혐의, 판결 단계, 관련 기관을 구분해 보고, 확정 판결인지 수사·기소 단계인지 원문에서 확인해야 합니다."
    return f"{entry.source.category_hint} 분야의 미국 공식 발표이므로 국내 독자는 발표 기관, 적용 대상, 시행 시점, 후속 문서가 실제 이해관계와 연결되는지 확인해 볼 수 있습니다."


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
    if re.search(r"(?ms)^tags:\n(?:  - .*\n)+", frontmatter):
        frontmatter = re.sub(r"(?ms)^tags:\n(?:  - .*\n)+", tag_block, frontmatter)
    else:
        frontmatter += tag_block
    final_body = body.strip() + "\n"
    score = estimate_article_quality(final_body)
    frontmatter = upsert_frontmatter(frontmatter, "author", yaml_quote(entry.source.agency_ko))
    frontmatter = upsert_frontmatter(frontmatter, "quality_score", f"{score:.1f}")
    path.write_text(f"---{frontmatter}---\n\n{final_body}", encoding="utf-8")
    return path


def upsert_frontmatter(frontmatter: str, key: str, value: str) -> str:
    line = f"{key}: {value}"
    if re.search(rf"^{re.escape(key)}\s*:", frontmatter, flags=re.M):
        return re.sub(rf"^{re.escape(key)}\s*:.*$", line, frontmatter, flags=re.M)
    if not frontmatter.endswith("\n"):
        frontmatter += "\n"
    return frontmatter + line + "\n"


def source_for_post(path: Path) -> USSource | None:
    name = path.name
    for source in sorted(SOURCES, key=lambda item: len(item.code), reverse=True):
        if name.startswith(f"usgov-{source.code}-"):
            return source
    return None


def frontmatter_value(raw: str, key: str) -> str:
    if not raw.startswith("---"):
        return ""
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return ""
    match = re.search(rf"^{re.escape(key)}:\s*\"?([^\"\n]+)\"?", parts[1], flags=re.M)
    return clean_text(match.group(1)) if match else ""


def markdown_url(body: str) -> str:
    matches = re.findall(r"\((https?://[^)\s]+)\)", body)
    for url in reversed(matches):
        if any(domain in url for domain in ("whitehouse.gov", "nasa.gov", "justice.gov", "ftc.gov", "bls.gov", "ed.gov")):
            return url
    return matches[-1] if matches else ""


def is_weak_us_post(raw: str) -> bool:
    if any(marker in raw for marker in WEAK_US_MARKERS):
        return True
    if not frontmatter_value(raw, "author") or not frontmatter_value(raw, "quality_score"):
        return True
    body = raw.split("---", 2)[2] if raw.startswith("---") and len(raw.split("---", 2)) == 3 else raw
    english_tokens = len(re.findall(r"\b[A-Za-z]{4,}\b", body))
    korean_tokens = len(re.findall(r"[가-힣]{2,}", body))
    return english_tokens > max(35, korean_tokens * 2)


def repair_weak_existing(limit: int, writer: WriterAgent | None, dry_run: bool = False) -> list[Path]:
    if limit <= 0:
        return []
    repaired: list[Path] = []
    for path in sorted(POSTS_DIR.glob("usgov-*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(repaired) >= limit:
            break
        raw = path.read_text(encoding="utf-8")
        if not is_weak_us_post(raw):
            continue
        source = source_for_post(path)
        if not source:
            continue
        parts = raw.split("---", 2)
        if len(parts) != 3:
            continue
        frontmatter, old_body = parts[1], parts[2]
        url = markdown_url(old_body)
        if not url:
            continue
        entry = USEntry(
            source=source,
            title=frontmatter_value(raw, "title") or path.stem,
            date=(frontmatter_value(raw, "date") or datetime.now().date().isoformat())[:10],
            url=url,
            summary=clean_text(old_body),
            image_url=frontmatter_value(raw, "cover_image"),
            image_alt=frontmatter_value(raw, "cover_image_alt"),
        )
        source_text, image_url, image_alt = fetch_page_context(entry)
        entry.image_url = image_url or entry.image_url
        entry.image_alt = image_alt or entry.image_alt
        title, body = korean_article(entry, source_text, writer)
        if not us_article_is_specific(body, entry):
            continue
        if dry_run:
            print(f"  ? 보강 대상: {path.name} -> {title[:60]}")
            repaired.append(path)
            continue
        category = source.category_hint
        tags = ["보도기사", "미국정부", source.agency_ko, category, *source.tags]
        tag_block = "tags:\n" + "".join(f"  - {yaml_quote(tag)}\n" for tag in dict.fromkeys(tags))
        frontmatter = upsert_frontmatter(frontmatter, "title", yaml_quote(title))
        frontmatter = upsert_frontmatter(frontmatter, "category", yaml_quote(category))
        frontmatter = re.sub(r"(?ms)^tags:\n(?:  - .*\n)+", tag_block, frontmatter)
        frontmatter = upsert_frontmatter(frontmatter, "author", yaml_quote(source.agency_ko))
        frontmatter = upsert_frontmatter(frontmatter, "quality_score", f"{estimate_article_quality(body):.1f}")
        if entry.image_url:
            frontmatter = upsert_frontmatter(frontmatter, "cover_image", yaml_quote(entry.image_url))
        if entry.image_alt:
            frontmatter = upsert_frontmatter(frontmatter, "cover_image_alt", yaml_quote(entry.image_alt))
        path.write_text(f"---{frontmatter}---\n\n{body.strip()}\n", encoding="utf-8")
        repaired.append(path)
        print(f"  ~ 보강: {path.name}")
    return repaired


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
    parser.add_argument("--repair-weak-existing", type=int, default=0, help="Rewrite weak existing U.S. posts before importing new ones")
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    selected = list(SOURCES)
    if args.sources:
        wanted = {item.lower() for item in args.sources}
        selected = [source for source in selected if source.code in wanted or source.agency.lower() in wanted]

    writer = init_writer(not args.no_llm)
    image_agent = init_image_agent()
    if args.repair_weak_existing:
        repaired = repair_weak_existing(args.repair_weak_existing, writer, dry_run=args.dry_run)
        print(f"기존 약한 미국 정부 글 보강: {len(repaired)}건")
        if args.dry_run:
            return
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
        if not written and not args.dry_run:
            sys.exit(1)
    for path in written:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
