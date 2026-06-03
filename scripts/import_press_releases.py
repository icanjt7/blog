"""정부부처 보도자료 일괄 가져오기

지원 기관:
  - 행정안전부   (mois)
  - 과학기술정보통신부 (msit)
  - 기획재정부   (mofe)
  - 문화체육관광부 (mcst)
  - 국가유산청   (khs)
  - 국가유산진흥원 (kh)
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blog_agent.config import load_settings
from blog_agent.writer import WriterAgent


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "output" / "posts"
USER_AGENT = "Mozilla/5.0 (compatible; BriefWavePressImporter/1.0)"
TIMEOUT = 20

INSTITUTION_LOGOS: dict[str, str] = {
    "행정안전부":        "assets/logos/mois.png",
    "과학기술정보통신부": "https://loremflickr.com/1200/630/science,technology,research?lock=5927",
    "기획재정부":        "https://www.mofe.go.kr/images/common/og-image.jpg",
    "문화체육관광부":    "assets/logos/mcst.gif",
    "국가유산청":        "https://www.khs.go.kr/images/layout/cha_card.jpg",
    "국가유산진흥원":    "assets/logos/kh.png",
}

AGENCIES = {
    "mois": "행정안전부",
    "msit": "과학기술정보통신부",
    "mofe": "기획재정부",
    "mcst": "문화체육관광부",
    "khs":  "국가유산청",
    "kh":   "국가유산진흥원",
}


@dataclass
class PressRelease:
    institution: str
    title: str
    date: str
    url: str
    body_text: str
    image_url: str = ""
    image_alt: str = ""


# ──────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────

def fetch(url: str) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\r", "\n", value)
    value = re.sub(r" |&nbsp;", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def html_to_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style|iframe|figure).*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?i)</?(p|div|li|tr|h[1-6])[^>]*>", "\n", fragment)
    fragment = re.sub(r"(?is)<[^>]+>", " ", fragment)
    text = clean_text(fragment)
    lines = []
    for line in text.splitlines():
        line = clean_text(line)
        if line and not line.startswith(("다운로드", "미리보기", "첨부파일")):
            lines.append(line)
    return "\n".join(lines)


_IMG_SKIP = re.compile(
    r"(spacer|blank|arrow|btn_|\.gif|/ico|/icon|icon_|/bg|_bg\.|/mark|mark\.|/bullet|/dot\b)",
    re.IGNORECASE,
)


def first_image(fragment: str, base_url: str) -> tuple[str, str]:
    for m in re.finditer(r"(?is)<img\b([^>]+)>", fragment):
        attrs = m.group(1)
        src_m = re.search(r"""(?i)\bsrc=["']([^"']+)["']""", attrs)
        if not src_m:
            continue
        src = html.unescape(src_m.group(1)).strip()
        if not src or src.startswith("data:") or src.endswith(".svg"):
            continue
        if _IMG_SKIP.search(src):
            continue
        # skip suspiciously small images via width/height attrs
        w_m = re.search(r"""(?i)\bwidth=["']?(\d+)""", attrs)
        h_m = re.search(r"""(?i)\bheight=["']?(\d+)""", attrs)
        if w_m and int(w_m.group(1)) < 60:
            continue
        if h_m and int(h_m.group(1)) < 60:
            continue
        alt_m = re.search(r"""(?i)\b(?:alt|title)=["']([^"']*)["']""", attrs)
        alt = clean_text(alt_m.group(1)) if alt_m else ""
        return urljoin(base_url, src), alt
    return "", ""


def get_og_image(html_src: str, base_url: str) -> str:
    """og:image 메타 태그에서 이미지 URL을 추출한다."""
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
        r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        html_src,
    )
    if not m:
        return ""
    raw = (m.group(1) or m.group(2) or "").strip()
    if not raw or not raw.startswith("http"):
        raw = urljoin(base_url, raw)
    # skip tiny icon-like images
    if any(x in raw.lower() for x in ["logo.gif", "logo.png", "icon", "favicon", "mark"]):
        return ""
    return raw


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w가-힣]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:48].strip("-") or "press"


def unique_slug(prefix: str, title: str, url: str) -> str:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{prefix}-{slugify(title)}-{digest}"


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def shorten(value: str, limit: int = 220) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;·") + "..."


def extract_sentences(text: str, limit: int = 6) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?다요함임됨])\s+", normalized)
    out = []
    for p in parts:
        p = clean_text(p)
        if len(p) < 25:
            continue
        if any(skip in p for skip in ["문의", "연락처", "첨부", "다운로드", "☎", "▶", "○"]):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def rewrite_title(original: str, body_text: str, writer: "WriterAgent") -> str:
    if not writer._client:
        return original
    prompt = f"""다음은 정부 보도자료 제목입니다. 일반 독자가 클릭하고 싶어지도록 제목을 한 줄로 바꿔줘.

규칙:
- 30자 이내
- 공무원 말투 금지 (예: "~를 추진", "~를 실시", "~에 따르면")
- 숫자/혜택/변화 포인트를 넣으면 좋음
- '핵심 정리', '총정리', '알아보기' 같은 진부한 표현 금지
- 원문 제목: {original}
- 본문 요약: {body_text[:200]}

새 제목만 한 줄로 답해. 다른 설명 없이."""
    try:
        resp = writer._client.chat.completions.create(
            model=writer._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=60,
        )
        new_title = (resp.choices[0].message.content or "").strip().strip('"').strip("'")
        return new_title if 4 < len(new_title) <= 50 else original
    except Exception:
        return original


def make_article_body(release: PressRelease) -> str:
    clean_title = re.sub(r"\(\d{6}\)\s*$", "", release.title).strip()
    sentences = [shorten(s) for s in extract_sentences(release.body_text)]
    summary = f"이번 보도자료의 핵심은 '{clean_title}'입니다. 발표 배경과 주요 일정, 현장에서 확인할 내용을 중심으로 정리했습니다."
    points = sentences[1:4] or sentences[:3]
    details = sentences[4:6]

    bullets = "\n".join(f"- {s}" for s in points)
    if not bullets:
        bullets = f"- 발표 기관: {release.institution}\n- 발표일: {release.date}\n- 핵심 주제: {clean_title}"

    detail = "\n\n".join(details) or (
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


def write_post(release: PressRelease, prefix: str, sequence: int) -> Path:
    slug = unique_slug(prefix, release.title, release.url)
    path = POSTS_DIR / f"{slug}.md"
    if path.exists():
        return path
    try:
        base_dt = datetime.fromisoformat(release.date)
    except ValueError:
        base_dt = datetime.now()
    post_dt = base_dt + timedelta(minutes=sequence)
    tags = ["보도기사", release.institution]
    img = release.image_url or INSTITUTION_LOGOS.get(release.institution, "")
    cover_line = f"cover_image: {yaml_quote(img)}\n" if img else ""
    alt = release.image_alt or f"{release.title} 관련 보도자료 이미지"
    frontmatter = (
        "---\n"
        f"title: {yaml_quote(release.title)}\n"
        f"date: {yaml_quote(post_dt.isoformat(timespec='minutes'))}\n"
        "category: \"정책\"\n"
        "tags:\n"
        + "".join(f"  - {yaml_quote(t)}\n" for t in tags)
        + "quality_score: 90.0\n"
        + cover_line
        + f"cover_image_alt: {yaml_quote(alt)}\n"
        + f"author: {yaml_quote(release.institution)}\n"
        + "---\n\n"
    )
    path.write_text(frontmatter + make_article_body(release), encoding="utf-8")
    return path


def strip_jsessionid(url: str) -> str:
    return re.sub(r";jsessionid=[^?&]+", "", url)


# ──────────────────────────────────────────────
# 행정안전부 (mois)
# ──────────────────────────────────────────────

def mois_links(per_source: int) -> list[str]:
    base = "https://www.mois.go.kr"
    list_url = f"{base}/frt/bbs/type010/commonSelectBoardList.do?bbsId=BBSMSTR_000000000008"
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        html_src = fetch(f"{list_url}&pageIndex={page}")
        for m in re.finditer(r'href="([^"]*commonSelectBoardArticle[^"]*nttId=(\d+)[^"]*)"', html_src):
            url = strip_jsessionid(urljoin(base, html.unescape(m.group(1))))
            ntt = m.group(2)
            if ntt not in seen:
                seen.add(ntt)
                links.append(url)
        page += 1
    return links[:per_source]


def mois_release(url: str) -> PressRelease:
    page = fetch(url)
    # title: class="subject" h4, strip sub_desc span
    title_m = re.search(r'class="subject"[^>]*>(.*?)</h4>', page, re.DOTALL)
    if not title_m:
        title_m = re.search(r'class="subject"[^>]*>(.*?)(?=</(?:div|p|td))', page, re.DOTALL)
    # date: inside class="table_info"
    date_m = re.search(r'등록일\s*</span>\s*:\s*([\d.]+)', page)
    if not date_m:
        date_m = re.search(r"등록일\s*</dt>\s*<dd[^>]*>(.*?)</dd>", page, re.DOTALL)
    # body: id="desc_pc" (actual article HTML, stops before prev/next nav)
    body_m = re.search(r'id="desc_pc"[^>]*>(.*?)(?=class="(prev_next|list_wrap|view_nav|btn_area|pagingArea)"|이전\s*글)', page, re.DOTALL)
    if not body_m:
        body_m = re.search(r'id="desc_pc"[^>]*>(.*?)(?=</div>\s*</div>\s*</div>)', page, re.DOTALL)
    if title_m:
        raw = re.sub(r'<span class="sub_desc">.*?</span>', '', title_m.group(1), flags=re.DOTALL)
        raw = re.sub(r'<br\s*/?>', ' ', raw)
        title = clean_text(re.sub(r"<[^>]+>", " ", raw))
    else:
        title = "행정안전부 보도자료"
    raw_date = re.sub(r"<[^>]+>", "", date_m.group(1) if date_m else "").strip()
    date = re.sub(r"\.", "-", raw_date.replace(" ", ""))[:10] or datetime.now().strftime("%Y-%m-%d")
    fragment = body_m.group(1) if body_m else ""
    img_url, img_alt = first_image(fragment, url)
    if not img_url:
        img_url = get_og_image(page, url)
    return PressRelease(
        institution="행정안전부",
        title=title,
        date=date,
        url=url,
        body_text=html_to_text(fragment),
        image_url=img_url,
        image_alt=img_alt or title,
    )


# ──────────────────────────────────────────────
# 과학기술정보통신부 (msit)
# ──────────────────────────────────────────────

def msit_links(per_source: int) -> list[str]:
    base_view = "https://www.msit.go.kr/bbs/view.do?sCode=user&mPid=208&mId=307&bbsSeqNo=94&nttSeqNo="
    list_url  = "https://www.msit.go.kr/bbs/list.do?sCode=user&mPid=208&mId=307"
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        html_src = fetch(f"{list_url}&pageIndex={page}")
        for ntt in re.findall(r"fn_detail\((\d+)\)", html_src):
            if ntt not in seen:
                seen.add(ntt)
                links.append(base_view + ntt)
        page += 1
    return links[:per_source]


def msit_release(url: str) -> PressRelease:
    page = fetch(url)
    bv_m = re.search(r'class="board_view"(.*?)(?=class="(view_nav|view_bottom|btn_list|paging_wrap)")', page, re.DOTALL)
    if not bv_m:
        bv_m = re.search(r'class="board_view"(.*?)(?=이전\s*글|다음\s*글)', page, re.DOTALL)
    fragment = bv_m.group(1) if bv_m else page
    # title: h2 inside view_head
    title_m = re.search(r'class="view_head".*?<h2[^>]*>(.*?)</h2>', fragment, re.DOTALL)
    if not title_m:
        title_m = re.search(r"<h2[^>]*>(.*?)</h2>", fragment, re.DOTALL)
    # date: span.date inside meta
    date_m = re.search(r'class="date"[^>]*>([^<]+)<', fragment)
    if not date_m:
        date_m = re.search(r"(\d{4}\.\d{2}\.\d{2})", fragment)
    # body: content after view_head section
    body_fragment = fragment
    vh_end = re.search(r'</div>\s*(?=<div class="(?!view_head|meta|tit_con))', fragment, re.DOTALL)
    if vh_end:
        body_fragment = fragment[vh_end.end():]
    title = clean_text(re.sub(r"<[^>]+>", " ", title_m.group(1))) if title_m else "과학기술정보통신부 보도자료"
    raw_date = (date_m.group(1) if date_m else "").strip()
    date = raw_date.replace(".", "-")[:10] or datetime.now().strftime("%Y-%m-%d")
    img_url, img_alt = first_image(body_fragment, url)
    if not img_url:
        img_url = get_og_image(page, url)
    return PressRelease(
        institution="과학기술정보통신부",
        title=title,
        date=date,
        url=url,
        body_text=html_to_text(body_fragment),
        image_url=img_url,
        image_alt=img_alt or title,
    )


# ──────────────────────────────────────────────
# 기획재정부 (mofe)
# ──────────────────────────────────────────────

def mofe_links(per_source: int) -> list[str]:
    list_url  = "https://www.mofe.go.kr/nw/nes/nesdta.do?bbsId=MOSFBBS_000000000028&menuNo=4010100"
    view_base = "https://www.mofe.go.kr/nw/nes/detailNesDtaView.do?searchBbsId1=MOSFBBS_000000000028&menuNo=4010100&searchNttId1="
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        html_src = fetch(f"{list_url}&pageIndex={page}")
        for ntt_id in re.findall(r"fn_egov_select\(['\"]([^'\"]+)['\"]", html_src):
            if ntt_id not in seen:
                seen.add(ntt_id)
                links.append(view_base + ntt_id)
        page += 1
    return links[:per_source]


def mofe_release(url: str) -> PressRelease:
    page = fetch(url)
    title_m = re.search(r"<h3[^>]*>(.*?)</h3>", page, re.DOTALL)
    date_m  = re.search(r'class="date"[^>]*>(.*?)</', page, re.DOTALL)
    if not date_m:
        date_m = re.search(r"(20\d\d\.\d{2}\.\d{2})", page)
    body_m = re.search(
        r'class="(cont_area|view_cont|board_cont|bbs_view|article_cont)"[^>]*>(.*?)(?=<div\s+(?:id|class)="(file|foot|btn|attach))',
        page, re.DOTALL,
    )
    if not body_m:
        body_m = re.search(r'class="boardInfo"(.*?)(?=class="(file|foot|btn)")', page, re.DOTALL)
    title = clean_text(re.sub(r"<[^>]+>", " ", title_m.group(1))) if title_m else "기획재정부 보도자료"
    raw_date = re.sub(r"<[^>]+>", "", date_m.group(1) if date_m else "").strip()
    date = re.sub(r"\.", "-", raw_date.replace(" ", ""))[:10] or datetime.now().strftime("%Y-%m-%d")
    fragment = body_m.group(2) if body_m and body_m.lastindex and body_m.lastindex >= 2 else ""
    img_url, img_alt = first_image(fragment or page, url)
    return PressRelease(
        institution="기획재정부",
        title=title,
        date=date,
        url=url,
        body_text=html_to_text(fragment or page),
        image_url=img_url,
        image_alt=img_alt,
    )


# ──────────────────────────────────────────────
# 문화체육관광부 (mcst)
# ──────────────────────────────────────────────

def mcst_links(per_source: int) -> list[str]:
    base = "https://www.mcst.go.kr"
    list_url = f"{base}/site/s_notice/press/pressList.jsp"
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        html_src = fetch(f"{list_url}?pageIndex={page}")
        for m in re.finditer(r"pressView\.jsp\?pSeq=(\d+)", html_src):
            pseq = m.group(1)
            if pseq not in seen:
                seen.add(pseq)
                links.append(f"{base}/site/s_notice/press/pressView.jsp?pSeq={pseq}")
        page += 1
    return links[:per_source]


def mcst_release(url: str) -> PressRelease:
    page = fetch(url)
    # title: find the h3 that isn't a nav item (longer than 8 chars)
    titles = [
        clean_text(re.sub(r"<[^>]+>", " ", m.group(1)))
        for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", page, re.DOTALL)
    ]
    title = next((t for t in titles if len(t) > 8 and "정보공개" not in t and "보도" not in t[:5]), None)
    if not title:
        title = titles[0] if titles else "문화체육관광부 보도자료"
    date_m = re.search(r"(20\d\d\.\d{2}\.\d{2})", page)
    raw_date = date_m.group(1) if date_m else ""
    date = re.sub(r"\.", "-", raw_date)[:10] or datetime.now().strftime("%Y-%m-%d")
    # body: visible text around the title area (minimal — content is in HWP/PDF)
    # Extract the region around the main content table
    body_m = re.search(
        r'class="(view_cont|board_view|press_view|cont_box|news_view|article)[^>]*>(.*?)(?=<div\s+class="(file|btn|foot))',
        page, re.DOTALL,
    )
    fragment = body_m.group(2) if body_m else ""
    if not fragment.strip():
        # fallback: use the area between title and attachment section
        body_m2 = re.search(
            r"<h3[^>]*>" + re.escape(html.escape(title[:20])) + r".*?(?=첨부파일|다운로드|HWP|PDF)",
            page, re.DOTALL | re.IGNORECASE,
        )
        fragment = body_m2.group(0) if body_m2 else ""
    img_url, img_alt = first_image(page, url)
    body_text = html_to_text(fragment).strip()
    if not body_text:
        body_text = f"{title}. 원문 보도자료(HWP/PDF)는 문화체육관광부 공식 누리집에서 내려받을 수 있습니다."
    return PressRelease(
        institution="문화체육관광부",
        title=title,
        date=date,
        url=url,
        body_text=body_text,
        image_url=img_url,
        image_alt=img_alt,
    )


# ──────────────────────────────────────────────
# 국가유산청 (khs) / 국가유산진흥원 (kh)
# ──────────────────────────────────────────────

def kh_links(per_source: int) -> list[str]:
    base = "https://www.kh.or.kr/brd/board/715/L/menu/373"
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        html_src = fetch(f"{base}?brdType=L&thisPage={page}&searchField=&searchText=")
        for m in re.finditer(r"""href=["']([^"']*brdType=R[^"']*bbIdx=\d+[^"']*)["']""", html_src):
            full = strip_jsessionid(urljoin(base, html.unescape(m.group(1))))
            if full not in seen:
                seen.add(full)
                links.append(full)
        page += 1
    return links[:per_source]


def kh_release(url: str) -> PressRelease:
    page = fetch(url)
    title_m = re.search(r'(?is)<div class="tbl_tit">\s*<span>(.*?)</span>', page)
    date_m  = re.search(r'(?is)<span class="tit">\s*<em>작성일</em>\s*:\s*([^<]+)</span>', page)
    body_m  = re.search(r'(?is)<div class="view_con">(.*?)</div>\s*<div class="tbl_file">', page)
    if not body_m:
        body_m = re.search(r'(?is)<div class="view_con">(.*?)</div>\s*</div>\s*<div class="btn_wrap">', page)
    title = clean_text(re.sub(r"<[^>]+>", " ", title_m.group(1))) if title_m else "국가유산진흥원 보도자료"
    date  = clean_text(date_m.group(1)) if date_m else datetime.now().strftime("%Y-%m-%d")
    fragment = body_m.group(1) if body_m else ""
    img_url, img_alt = first_image(fragment, url)
    return PressRelease(
        institution="국가유산진흥원",
        title=title,
        date=date,
        url=url,
        body_text=html_to_text(fragment),
        image_url=img_url,
        image_alt=img_alt,
    )


def khs_links(per_source: int) -> list[str]:
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= 5:
        url = (
            "https://www.khs.go.kr/newsBbz/selectNewsBbzList.do"
            f"?pageIndex={page}&mn=NS_01_02&pageUnit=10&sectionId=b_sec_1"
            "&sdate=&edate=&strWhere=&searchWrd=&strValue="
        )
        html_src = fetch(url)
        for m in re.finditer(
            r"""href=["']([^"']*selectNewsBbzView\.do[^"']*newsItemId=\d+[^"']*)["']""",
            html_src,
        ):
            href = re.sub(r";jsessionid=[^?]+", "", html.unescape(m.group(1)))
            full = urljoin("https://www.khs.go.kr", href)
            if full not in seen:
                seen.add(full)
                links.append(full)
        page += 1
    return links[:per_source]


def khs_release(url: str) -> PressRelease:
    page = fetch(url)
    title_m = re.search(r'(?is)<strong class="board-view-title">(.*?)</strong>', page)
    date_m  = re.search(r"(?is)<th[^>]*>\s*등록일\s*</th>\s*<td>\s*([^<]+)</td>", page)
    body_m  = re.search(
        r'(?is)<div class="board-view-content">(.*?)</div>\s*(?:<figure|<div class="btn-wrap")',
        page,
    )
    title = clean_text(re.sub(r"<[^>]+>", " ", title_m.group(1))) if title_m else "국가유산청 보도자료"
    date  = clean_text(date_m.group(1)) if date_m else datetime.now().strftime("%Y-%m-%d")
    fragment = body_m.group(1) if body_m else ""
    img_url, img_alt = first_image(fragment, url)
    if img_url.startswith("http://www.khs.go.kr"):
        img_url = img_url.replace("http://www.khs.go.kr", "https://www.khs.go.kr", 1)
    return PressRelease(
        institution="국가유산청",
        title=title,
        date=date,
        url=url,
        body_text=html_to_text(fragment),
        image_url=img_url,
        image_alt=img_alt,
    )


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────

SOURCES = [
    ("mois", mois_links, mois_release),
    ("msit", msit_links, msit_release),
    ("mofe", mofe_links, mofe_release),
    ("mcst", mcst_links, mcst_release),
    ("khs",  khs_links,  khs_release),
    ("kh",   kh_links,   kh_release),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=12,
                        help="기관별 수집 상한 (기본값: 12)")
    parser.add_argument("--agencies", nargs="*", default=None,
                        help="특정 기관만 수집 (예: --agencies mois msit)")
    parser.add_argument("--rewrite-titles", action="store_true",
                        help="LLM으로 제목을 독자 친화적으로 재작성")
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    writer = None
    if args.rewrite_titles:
        try:
            writer = WriterAgent(load_settings())
            if writer._client:
                print(f"제목 재작성 활성화 (모델: {writer._model})")
            else:
                print("LLM 키 없음 — 제목 재작성 건너뜀")
                writer = None
        except Exception as e:
            print(f"LLM 초기화 실패: {e}")

    written: list[Path] = []
    errors: list[str] = []
    seq = 0

    for prefix, list_fn, release_fn in SOURCES:
        if args.agencies and prefix not in args.agencies:
            continue
        name = AGENCIES[prefix]
        print(f"\n[{name}] 링크 수집 중...")
        try:
            links = list_fn(args.per_source)
        except Exception as e:
            errors.append(f"{name} 목록 수집 실패: {e}")
            print(f"  ✗ 목록 실패: {e}")
            continue

        print(f"  {len(links)}건 발견")
        for url in links:
            try:
                release = release_fn(url)
                if writer:
                    release.title = rewrite_title(release.title, release.body_text, writer)
                path = write_post(release, prefix, seq)
                written.append(path)
                seq += 1
                print(f"  + {release.title[:50]}")
            except Exception as e:
                errors.append(f"{url}: {e}")
                print(f"  ✗ {url[:60]}: {e}")

    print(f"\n총 {len(written)}건 저장 완료")
    if errors:
        print(f"오류 {len(errors)}건:")
        for e in errors:
            print(f"  - {e}")
    for p in written:
        print(p.relative_to(ROOT))


if __name__ == "__main__":
    main()
