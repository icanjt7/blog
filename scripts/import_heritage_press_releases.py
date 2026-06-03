from __future__ import annotations

import argparse
import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "output" / "posts"
USER_AGENT = "Mozilla/5.0 (compatible; BriefWavePressImporter/1.0)"


@dataclass
class PressRelease:
    institution: str
    title: str
    date: str
    url: str
    body_text: str
    image_url: str = ""
    image_alt: str = ""


def fetch(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\r", "\n", value)
    value = re.sub(r"\u00a0|&nbsp;", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def html_fragment_to_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style|iframe|figure).*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?i)</?(p|div|li|tr|h[1-6])[^>]*>", "\n", fragment)
    fragment = re.sub(r"(?is)<[^>]+>", " ", fragment)
    text = clean_text(fragment)
    lines = []
    for line in text.splitlines():
        line = clean_text(line)
        if line and not line.startswith(("다운로드", "미리보기")):
            lines.append(line)
    return "\n".join(lines)


def first_image(fragment: str, base_url: str) -> tuple[str, str]:
    for match in re.finditer(r"(?is)<img\b([^>]+)>", fragment):
        attrs = match.group(1)
        src_match = re.search(r"""(?i)\bsrc=["']([^"']+)["']""", attrs)
        if not src_match:
            continue
        src = html.unescape(src_match.group(1)).strip()
        if not src or src.startswith("data:") or "mark" in src.lower() or src.endswith(".svg"):
            continue
        alt_match = re.search(r"""(?i)\b(?:alt|title)=["']([^"']*)["']""", attrs)
        alt = clean_text(alt_match.group(1)) if alt_match else ""
        url = urljoin(base_url, src)
        if url.startswith("http://www.khs.go.kr"):
            url = url.replace("http://www.khs.go.kr", "https://www.khs.go.kr", 1)
        return url, alt
    return "", ""


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w가-힣]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:48].strip("-") or "press-release"


def unique_slug(prefix: str, title: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{slugify(title)}-{digest}"


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def extract_sentences(text: str, limit: int = 5) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?다요함임됨됨\.])\s+", normalized)
    sentences = []
    for part in parts:
        part = clean_text(part)
        if len(part) < 25:
            continue
        if any(skip in part for skip in ["문의", "연락", "첨부", "다운로드", "미리보기"]):
            continue
        sentences.append(part)
        if len(sentences) >= limit:
            break
    return sentences


def shorten(value: str, limit: int = 220) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;·") + "..."


def clean_bullet(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^\*\s*", "", value)
    value = value.replace(" * ", " / ")
    return value


def make_article_body(release: PressRelease) -> str:
    clean_title = re.sub(r"\(\d{6}\)\s*$", "", release.title).strip()
    sentences = [shorten(clean_bullet(sentence)) for sentence in extract_sentences(release.body_text, limit=6)]
    summary = f"이번 보도자료의 핵심은 '{clean_title}'입니다. 발표 배경과 주요 일정, 현장에서 확인할 내용을 중심으로 정리했습니다."
    point_sentences = sentences[1:4] or sentences[:3]
    detail_sentences = sentences[4:6]

    bullets = "\n".join(f"- {sentence}" for sentence in point_sentences)
    if not bullets:
        bullets = f"- 발표 기관: {release.institution}\n- 발표일: {release.date}\n- 핵심 주제: {clean_title}"

    detail = "\n\n".join(detail_sentences)
    if not detail:
        detail = (
            "원문 보도자료에는 일정, 참여 대상, 추진 배경 등 세부 정보가 함께 안내되어 있습니다. "
            "관심 있는 독자는 원문에서 최신 공지와 첨부 자료를 함께 확인하는 것이 좋습니다."
        )

    sections = [
        (
            f"{release.institution}이 {release.date} 공개한 보도자료를 바탕으로 핵심 내용을 정리했습니다. "
            "원문을 그대로 옮기기보다 일정, 대상, 의미를 빠르게 확인할 수 있도록 브리핑 형식으로 재구성했습니다."
        ),
        "## 한눈에 보기",
        summary,
        "## 핵심 포인트",
        bullets,
        "## 더 살펴볼 내용",
        detail,
        "## 확인 메모",
        f"- 발표 기관: {release.institution}\n- 발표일: {release.date}\n- 자료 성격: 기관 보도자료 기반 브리핑",
        "## 원문",
        f"- [{release.institution} 보도자료]({release.url})",
    ]
    return "\n\n".join(sections).strip() + "\n"


def kh_links(per_source: int) -> list[str]:
    base = "https://www.kh.or.kr/brd/board/715/L/menu/373"
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        url = f"{base}?brdType=L&thisPage={page}&searchField=&searchText="
        page_html = fetch(url)
        for match in re.finditer(r"""href=["']([^"']*brdType=R[^"']*bbIdx=\d+[^"']*)["']""", page_html):
            href = html.unescape(match.group(1))
            full = urljoin(base, href)
            if full not in links:
                links.append(full)
        page += 1
    return links[:per_source]


def kh_release(url: str) -> PressRelease:
    page_html = fetch(url)
    title_match = re.search(r'(?is)<div class="tbl_tit">\s*<span>(.*?)</span>', page_html)
    date_match = re.search(r'(?is)<span class="tit">\s*<em>작성일</em>\s*:\s*([^<]+)</span>', page_html)
    body_match = re.search(r'(?is)<div class="view_con">(.*?)</div>\s*<div class="tbl_file">', page_html)
    if not body_match:
        body_match = re.search(r'(?is)<div class="view_con">(.*?)</div>\s*</div>\s*<div class="btn_wrap">', page_html)

    title = clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else "국가유산진흥원 보도자료"
    date = clean_text(date_match.group(1)) if date_match else datetime.now().strftime("%Y-%m-%d")
    fragment = body_match.group(1) if body_match else ""
    image_url, image_alt = first_image(fragment, url)
    return PressRelease(
        institution="국가유산진흥원",
        title=title,
        date=date,
        url=url,
        body_text=html_fragment_to_text(fragment),
        image_url=image_url,
        image_alt=image_alt,
    )


def khs_links(per_source: int) -> list[str]:
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        url = (
            "https://www.khs.go.kr/newsBbz/selectNewsBbzList.do"
            f"?pageIndex={page}&mn=NS_01_02&pageUnit=10&sectionId=b_sec_1"
            "&sdate=&edate=&strWhere=&searchWrd=&strValue="
        )
        page_html = fetch(url)
        for match in re.finditer(r"""href=["']([^"']*selectNewsBbzView\.do[^"']*newsItemId=\d+[^"']*)["']""", page_html):
            href = html.unescape(match.group(1))
            href = re.sub(r";jsessionid=[^?]+", "", href)
            full = urljoin("https://www.khs.go.kr", href)
            if full not in links:
                links.append(full)
        page += 1
    return links[:per_source]


def khs_release(url: str) -> PressRelease:
    page_html = fetch(url)
    title_match = re.search(r'(?is)<strong class="board-view-title">(.*?)</strong>', page_html)
    date_match = re.search(r"(?is)<th[^>]*>\s*등록일\s*</th>\s*<td>\s*([^<]+)</td>", page_html)
    body_match = re.search(r'(?is)<div class="board-view-content">(.*?)</div>\s*(?:<figure|<div class="btn-wrap")', page_html)

    title = clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else "국가유산청 보도자료"
    date = clean_text(date_match.group(1)) if date_match else datetime.now().strftime("%Y-%m-%d")
    fragment = body_match.group(1) if body_match else ""
    image_url, image_alt = first_image(fragment, url)
    return PressRelease(
        institution="국가유산청",
        title=title,
        date=date,
        url=url,
        body_text=html_fragment_to_text(fragment),
        image_url=image_url,
        image_alt=image_alt,
    )


def write_post(release: PressRelease, sequence: int) -> Path:
    prefix = "kh" if release.institution == "국가유산진흥원" else "khs"
    slug = unique_slug(prefix, release.title, release.url)
    path = POSTS_DIR / f"{slug}.md"
    base_dt = datetime.fromisoformat(release.date)
    post_dt = base_dt + timedelta(minutes=sequence)
    tags = ["보도자료", "국가유산", release.institution]
    cover_line = f"cover_image: {yaml_quote(release.image_url)}\n" if release.image_url else ""
    alt = release.image_alt or f"{release.title} 관련 보도자료 이미지"
    frontmatter = (
        "---\n"
        f"title: {yaml_quote(release.title)}\n"
        f"date: {yaml_quote(post_dt.isoformat(timespec='minutes'))}\n"
        "category: \"정책\"\n"
        "tags:\n"
        + "".join(f"  - {yaml_quote(tag)}\n" for tag in tags)
        + "quality_score: 90.0\n"
        + cover_line
        + f"cover_image_alt: {yaml_quote(alt)}\n"
        + f"author: {yaml_quote(release.institution)}\n"
        + "---\n\n"
    )
    path.write_text(frontmatter + make_article_body(release), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=12)
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    releases: list[PressRelease] = []
    for link in kh_links(args.per_source):
        releases.append(kh_release(link))
    for link in khs_links(args.per_source):
        releases.append(khs_release(link))

    written = []
    for index, release in enumerate(releases):
        written.append(write_post(release, index))

    with_images = sum(1 for release in releases if release.image_url)
    print(f"wrote {len(written)} posts")
    print(f"source images found: {with_images}/{len(releases)}")
    for path in written:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
