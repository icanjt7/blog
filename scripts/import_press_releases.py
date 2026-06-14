"""정부부처 보도자료 일괄 가져오기

지원 기관:
  - 행정안전부   (mois)
  - 과학기술정보통신부 (msit)
  - 재정경제부   (mofe)
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
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blog_agent.config import load_settings
from blog_agent.hwpx import extract_hwpx_text_bytes
from blog_agent.images import ImageAgent
from blog_agent.models import Draft, Topic
from blog_agent.writer import WriterAgent


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "output" / "posts"
USER_AGENT = "Mozilla/5.0 (compatible; BriefWavePressImporter/1.0)"
TIMEOUT = 20
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

INSTITUTION_LOGOS: dict[str, str] = {
    "행정안전부":        "assets/logos/mois.jpg",
    "과학기술정보통신부": "assets/logos/msit.jpg",
    "재정경제부":        "https://www.mofe.go.kr/images/common/og-image.jpg",
    "문화체육관광부":    "assets/logos/mcst.gif",
    "국가유산청":        "https://www.khs.go.kr/images/layout/cha_card.jpg",
    "국가유산진흥원":    "assets/logos/kh.png",
}

PRESS_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "정치",
        (
            "선거",
            "투표",
            "당선",
            "후보자",
            "공약",
            "정당",
            "국회",
            "의원",
            "정치",
        ),
    ),
    (
        "기술",
        (
            "ai",
            "인공지능",
            "데이터",
            "디지털",
            "클라우드",
            "보안",
            "사이버",
            "반도체",
            "배터리",
            "전기차",
            "자율주행",
            "로봇",
            "드론",
            "우주",
            "위성",
            "발사체",
            "항공",
            "r&d",
            "연구개발",
            "기술개발",
            "소프트웨어",
            "플랫폼",
            "통신",
            "5g",
            "6g",
            "양자",
            "스타트업",
            "벤처",
            "특허",
        ),
    ),
    (
        "핫이슈",
        (
            "관광",
            "여행",
            "축제",
            "행사",
            "공연",
            "전시",
            "박람회",
            "문화",
            "콘텐츠",
            "한류",
            "k-",
            "케이",
            "국가유산",
            "문화유산",
            "무형유산",
            "궁",
            "박물관",
            "미술관",
            "지역",
            "방문",
            "캠페인",
        ),
    ),
    (
        "생활",
        (
            "지원",
            "신청",
            "혜택",
            "복지",
            "돌봄",
            "청년",
            "교육",
            "학교",
            "유학생",
            "취업",
            "채용",
            "일자리",
            "노동",
            "근로",
            "임금",
            "안전",
            "폭염",
            "집중호우",
            "재난",
            "질병",
            "감염",
            "예방",
            "의료",
            "건강",
            "식품",
            "화장품",
            "주거",
            "교통",
            "철도",
            "생활",
            "소비자",
            "민원",
            "서류",
            "요금",
        ),
    ),
    (
        "정책",
        (
            "예산",
            "재정",
            "경제",
            "금융",
            "물가",
            "세금",
            "세제",
            "규제",
            "법",
            "시행령",
            "입법",
            "제도",
            "계획",
            "전략",
            "위원회",
            "회의",
            "협의회",
            "협약",
            "수출",
            "무역",
            "투자",
            "공공기관",
            "조달",
        ),
    ),
)

INSTITUTION_CATEGORY_HINTS: dict[str, str] = {
    "과학기술정보통신부": "기술",
    "우주항공청": "기술",
    "방송미디어통신위원회": "기술",
    "개인정보보호위원회": "기술",
    "문화체육관광부": "핫이슈",
    "국가유산청": "핫이슈",
    "국가유산진흥원": "핫이슈",
    "식품의약품안전처": "생활",
    "보건복지부": "생활",
    "질병관리청": "생활",
    "교육부": "생활",
    "고용노동부": "생활",
    "병무청": "생활",
    "경찰청": "생활",
    "소방청": "생활",
    "행정안전부": "생활",
    "국토교통부": "생활",
    "기획예산처": "정책",
    "재정경제부": "정책",
    "금융위원회": "정책",
    "공정거래위원회": "정책",
}

AGENCIES = {
    "mois": "행정안전부",
    "msit": "과학기술정보통신부",
    "mofe": "재정경제부",
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
    article_ready: bool = False


# ──────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────

def fetch(url: str) -> str:
    resp = request_with_retry("GET", url)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.text


def request_with_retry(method: str, url: str, attempts: int = 3, **kwargs: object) -> requests.Response:
    last_error: Exception | None = None
    for index in range(attempts):
        try:
            return SESSION.request(method, url, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            SESSION.close()
            if index < attempts - 1:
                time.sleep(1.5 * (index + 1))
    if last_error:
        raise last_error
    raise RuntimeError(f"request failed: {url}")


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


def fetch_bytes(url: str, *, data: dict[str, str] | None = None, referer: str = "") -> bytes:
    headers = {"Referer": referer} if referer else None
    if data is None:
        resp = request_with_retry("GET", url, headers=headers)
    else:
        resp = request_with_retry("POST", url, data=data, headers=headers)
    resp.raise_for_status()
    return resp.content


def extract_hwpx_text(download_url: str, *, data: dict[str, str] | None = None, referer: str = "") -> str:
    """HWPX 첨부파일을 다운로드해서 본문 텍스트를 반환한다."""
    try:
        payload = fetch_bytes(download_url, data=data, referer=referer)
        if payload[:2] != b"PK":
            return ""
        return extract_hwpx_text_bytes(payload)
    except Exception:
        return ""


def _js_args(call_args: str) -> list[str]:
    return [html.unescape(item) for item in re.findall(r"""['"]([^'"]*)['"]""", call_args)]


def extract_first_hwpx_attachment(page: str, page_url: str, institution: str = "") -> str:
    """Find the first HWPX attachment on a press-release page and return text."""
    # 과학기술정보통신부: fn_download('atchFileNo', 'fileOrd', 'hwpx') posts a form.
    for match in re.finditer(r"fn_download\(([^)]*hwpx[^)]*)\)", page, flags=re.IGNORECASE):
        args = _js_args(match.group(1))
        if len(args) >= 2:
            text = extract_hwpx_text(
                "https://www.msit.go.kr/ssm/file/fileDown.do",
                data={"atchFileNo": args[0], "fileOrd": args[1], "fileBtn": "A"},
                referer=page_url,
            )
            if text:
                return text

    # 문화체육관광부: file_download(fileName, savedName, path)
    for match in re.finditer(r"file_download\(([^)]*?\.hwpx[^)]*)\)", page, flags=re.IGNORECASE):
        args = _js_args(match.group(1))
        if len(args) >= 3:
            url = (
                "https://www.mcst.go.kr/servlets/eduport/front/upload/UplDownloadFile"
                f"?pFileName={args[0]}&pRealName={args[1]}&pPath={args[2]}&pFlag="
            )
            text = extract_hwpx_text(url, referer=page_url)
            if text:
                return text

    # 국가유산청 등: adjacent title says .hwpx and href points to FileDown.do.
    for match in re.finditer(
        r"""(?is)<li[^>]*>.*?\.hwpx.*?<a[^>]+href=["']([^"']*FileDown\.do[^"']+)["']""",
        page,
    ):
        url = urljoin(page_url, html.unescape(match.group(1)))
        text = extract_hwpx_text(url, referer=page_url)
        if text:
            return text

    # Generic direct .hwpx links.
    for match in re.finditer(r"""(?i)href=["']([^"']+\.hwpx(?:\?[^"']*)?)["']""", page):
        url = urljoin(page_url, html.unescape(match.group(1)))
        text = extract_hwpx_text(url, referer=page_url)
        if text:
            return text

    return ""


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w가-힣]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:48].strip("-") or "press"


def unique_slug(prefix: str, title: str, url: str) -> str:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    return f"{prefix}-{slugify(title)}-{digest}"


def post_path_for_release(prefix: str, title: str, url: str, overwrite: bool = False) -> Path:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    if overwrite:
        existing = sorted(POSTS_DIR.glob(f"{prefix}-*-{digest}.md"))
        if existing:
            return existing[0]
    return POSTS_DIR / f"{prefix}-{slugify(title)}-{digest}.md"


def existing_post_for_url(prefix: str, url: str) -> Path | None:
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    existing = sorted(POSTS_DIR.glob(f"{prefix}-*-{digest}.md"))
    return existing[0] if existing else None


def max_pages_for(per_source: int) -> int:
    return max(5, min(15, (per_source // 10) + 3))


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def existing_frontmatter_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return ""
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return ""
    match = re.search(rf"^{re.escape(key)}:\s*\"?([^\"\n]+)\"?", parts[1], flags=re.MULTILINE)
    return clean_text(match.group(1)) if match else ""


def shorten(value: str, limit: int = 220) -> str:
    value = clean_text(value)
    value = re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※\*\s]+", "", value)
    value = re.sub(r"\s+\*\s+", " / ", value)
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;·") + "..."


def extract_sentences(text: str, limit: int = 6) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?다요함임됨])\s+", normalized)
    out = []
    for p in parts:
        p = clean_text(p)
        p = re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※\s]+", "", p)
        if len(p) < 25:
            continue
        if any(skip in p for skip in ["문의", "연락처", "첨부", "다운로드", "☎"]):
            continue
        if "관련 보도자료 내용입니다" in p:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def extract_detail_lines(text: str, limit: int = 4) -> list[str]:
    """Return usable detail lines even when the source is a list/table, not prose."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = clean_text(raw)
        line = re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※\*\s]+", "", line)
        line = re.sub(r"\s+\*\s+", " / ", line)
        if len(line) < 18:
            continue
        if any(skip in line for skip in ["문의", "연락처", "첨부", "다운로드", "미리보기", "보도자료"]):
            continue
        normalized = re.sub(r"\s+", "", line)
        if normalized in seen:
            continue
        seen.add(normalized)
        lines.append(shorten(line, 260))
        if len(lines) >= limit:
            break
    return lines


def _llm_outputs(
    writer: "WriterAgent",
    prompt: str,
    temperature: float = 0.8,
    max_tokens: int = 512,
) -> list[str]:
    """Return provider responses in priority order so weak drafts can be rejected."""
    providers = getattr(writer, "_providers", [])
    if not providers and not writer._client:
        return []
    if not providers:
        providers = [(writer._client, writer._model)]
    outputs: list[str] = []
    last_error = ""
    for client, model in providers:
        if not client:
            continue
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                outputs.append(text)
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}"
            continue
    if last_error:
        print(f"  ! LLM 전체 실패: {last_error}")
    return outputs


def _call_llm(writer: "WriterAgent", prompt: str,
              temperature: float = 0.8, max_tokens: int = 512) -> str:
    """writer의 LLM 클라이언트로 프롬프트를 보내고 텍스트를 반환한다."""
    outputs = _llm_outputs(writer, prompt, temperature=temperature, max_tokens=max_tokens)
    return outputs[0] if outputs else ""


WEAK_ARTICLE_MARKERS = (
    "이번 보도자료의 핵심은",
    "발표 배경과 주요 일정, 현장에서 확인할 내용을 중심으로 정리했습니다",
    "원문 보도자료에는 일정, 참여 대상, 추진 배경 등 세부 정보가 함께 안내되어 있습니다",
)


def needs_llm_enrichment(text: str) -> bool:
    cleaned = clean_text(text)
    if len(cleaned) < 900:
        return True
    return any(marker in cleaned for marker in WEAK_ARTICLE_MARKERS)


def _similar_text(a: str, b: str) -> bool:
    a_tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", clean_text(a).lower()))
    b_tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", clean_text(b).lower()))
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / min(len(a_tokens), len(b_tokens))
    return overlap >= 0.72


def _already_used(candidate: str, used: set[str]) -> bool:
    return any(candidate == item or _similar_text(candidate, item) for item in used)


def generate_article_from_source(release: "PressRelease", writer: "WriterAgent") -> str:
    """HWPX에서 추출한 원문 텍스트를 LLM으로 기사화한다."""
    if not release.body_text:
        return ""
    prompt = f"""다음은 [{release.institution}]에서 발표한 보도자료 원문입니다.
이 내용을 독자 친화적인 블로그 기사로 작성해주세요.

[보도자료 원문]
{release.body_text[:3000]}

[작성 규칙]
- 본문 1,500~2,100자 (한국어)
- 첫 문단에 반드시 발표 기관({release.institution}), 발표일({release.date}), 발표 주제를 넣기
- 독자에게 중요한 수치·날짜·대상·장소·참여기관·지원내용·시행방식을 구체적으로 포함
- 원문에 있는 고유명사, 사업명, 제도명, 금액, 기간은 가능한 한 그대로 살리기
- 마크다운 헤딩(##)으로 4~5개 섹션 구성
- 표 1개 포함: 구분 / 확인할 내용
- '~입니다', '~합니다' 정중체 사용
- 제목을 반복하는 "이번 보도자료의 핵심은..." 문장 금지
- "원문 보도자료에는 세부 정보가 있습니다"처럼 뭉뚱그린 문장 금지
- 원문에서 확인한 장소, 참여 기관, 대상, 일정, 수치가 있으면 반드시 반영
- 마지막 섹션은 '## 확인할 점'으로 두고, 이 발표를 보고 독자가 확인할 구체 항목 3개를 적기
- 자료 출처 기관: {release.institution}
- 원문 URL: {release.url}

BODY: 로 시작해서 본문만 작성하세요."""
    for text in _llm_outputs(writer, prompt, temperature=0.75, max_tokens=2048):
        if text.startswith("BODY:"):
            text = text[5:].strip()
        if article_is_specific(text, release):
            return text
    return ""


def article_is_specific(text: str, release: PressRelease) -> bool:
    cleaned = clean_text(text)
    if len(cleaned) < 850:
        return False
    if release.institution not in cleaned:
        return False
    if sum(1 for marker in WEAK_ARTICLE_MARKERS if marker in cleaned) > 0:
        return False
    has_sections = len(re.findall(r"^##\s+", text, flags=re.M)) >= 3
    has_fact = bool(re.search(r"\d|대상|기간|장소|기관|신청|참여|시행|지원|발표일|원문", cleaned))
    return has_sections and has_fact


def rewrite_title(original: str, body_text: str, writer: "WriterAgent") -> str:
    prompt = f"""다음은 정부 보도자료 제목입니다. 일반 독자가 클릭하고 싶어지도록 제목을 한 줄로 바꿔줘.

규칙:
- 30자 이내
- 공무원 말투 금지 (예: "~를 추진", "~를 실시", "~에 따르면")
- 숫자/혜택/변화 포인트를 넣으면 좋음
- '핵심 정리', '총정리', '알아보기' 같은 진부한 표현 금지
- 원문 제목: {original}
- 본문 요약: {body_text[:200]}

새 제목만 한 줄로 답해. 다른 설명 없이."""
    new_title = _call_llm(writer, prompt, temperature=0.8, max_tokens=60).strip('"').strip("'")
    return new_title if 4 < len(new_title) <= 50 else original


def make_article_body(release: PressRelease) -> str:
    clean_title = re.sub(r"\(\d{6}\)\s*$", "", release.title).strip()
    clean_title = re.sub(r"^\[(?:보도자료|보도참고|참고|설명자료)\]\s*", "", clean_title).strip()
    sentences = [
        shorten(re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※>\s]+", "", s), 300)
        for s in extract_sentences(release.body_text)
    ]
    sentences = [
        s
        for s in sentences
        if len(clean_text(s)) > 24
        and "자세한 내용은" not in s
        and "자료제공" not in s
        and not s.startswith("문의")
    ]
    detail_lines = extract_detail_lines(release.body_text)
    lead = sentences[0] if sentences else f"{release.institution}이 {release.date} '{clean_title}' 관련 보도자료를 공개했습니다."
    points = sentences[1:5] or sentences[:4]
    used_sentences = {lead, *points}
    details = [s for s in sentences[5:12] if not _already_used(s, used_sentences)][:3]

    fact_candidates = re.findall(
        r"[^.\n]*(?:\d+(?:\.\d+)?\s*(?:개|건|명|곳|회|억|조|%|원|년|월|일)|"
        r"\d{1,2}\.\d{1,2}\.|"
        r"전국|대구|서울|부산|전북|전주|벨기에|유럽연합|EU|IMEC|AI|반도체|양자)[^.\n]*",
        release.body_text,
        flags=re.I,
    )
    facts = []
    for item in fact_candidates:
        value = shorten(re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※>\s]+", "", clean_text(item)), 220)
        if (
            len(value) > 20
            and value not in facts
            and not _already_used(value, used_sentences)
            and "자료제공" not in value
        ):
            facts.append(value)
        if len(facts) >= 5:
            break

    bullets = "\n".join(f"- {s}" for s in points)
    if not bullets and detail_lines:
        bullets = "\n".join(f"- {s}" for s in detail_lines[:3])
    if not bullets:
        bullets = f"- 발표 기관: {release.institution}\n- 발표일: {release.date}\n- 핵심 주제: {clean_title}"

    detail = "\n\n".join(details)
    if not detail and detail_lines:
        detail = "\n\n".join(detail_lines[:2])
    if not detail:
        paragraphs = [
            shorten(re.sub(r"^[\-–—ㆍ·•○ㅇ◇□■▪▶※\s]+", "", line), 260)
            for line in release.body_text.splitlines()
            if len(clean_text(line)) > 25
        ]
        detail = "\n\n".join(paragraphs[2:4] or paragraphs[:2])
    fact_block = "\n".join(f"- {fact}" for fact in facts)
    if not fact_block:
        fact_block = (
            f"- 발표 기관: {release.institution}\n"
            f"- 발표일: {release.date}\n"
            f"- 확인할 원문: {clean_title}"
        )

    sections = [
        (
            f"{with_particle(release.institution, '이', '가')} {release.date} 공개한 자료를 바탕으로 "
            f"{clean_title}의 주요 내용을 독자가 바로 확인할 수 있게 정리했습니다."
        ),
        "## 무엇을 발표했나",
        lead,
        "## 핵심 내용",
        bullets,
        "## 숫자와 현장 정보",
        fact_block,
        "## 배경과 의미",
        detail,
        "## 독자가 확인할 점",
        concrete_reader_checks(release, facts, detail_lines),
        "## 원문",
        f"- [{release.institution} 보도자료]({release.url})",
    ]
    return "\n\n".join(sections).strip() + "\n"


def concrete_reader_checks(release: PressRelease, facts: list[str], detail_lines: list[str]) -> str:
    source = "\n".join([release.title, release.body_text])
    checks: list[str] = []
    if re.search(r"신청|접수|공모|모집|예약|참여", source):
        checks.append("신청·접수형 사안이면 원문에서 접수 기간, 제출 서류, 담당 부서 안내를 먼저 확인합니다.")
    if re.search(r"지원|보조|예산|금액|원|억|조|감면|혜택|쿠폰|바우처", source):
        checks.append("지원·예산 관련 내용은 대상 조건, 금액 기준, 중복 수혜 가능 여부를 원문 표기대로 확인합니다.")
    if re.search(r"시행|개정|적용|일부터|월부터|년부터|기간", source):
        checks.append("시행일이나 적용 기간이 있는 발표이므로 실제 적용 시작일과 유예기간을 따로 확인합니다.")
    if re.search(r"지역|전국|서울|부산|대구|광주|인천|대전|울산|세종|제주|현장|장소", source):
        checks.append("지역·현장 관련 내용은 내가 이용할 지역이 포함되는지와 방문 가능 시간을 확인합니다.")
    if re.search(r"기업|기관|학교|대학|청년|아동|가족|어르신|장애|소상공인|농가", source):
        checks.append("대상자가 특정되어 있으므로 개인, 기업, 기관 중 누구에게 적용되는 발표인지 구분해서 봅니다.")
    for fact in [*facts, *detail_lines]:
        if len(checks) >= 3:
            break
        if fact and not _already_used(fact, set(checks)):
            checks.append(f"원문 핵심 문장으로는 '{shorten(fact, 110)}' 부분을 함께 확인합니다.")
    if not checks:
        checks = [
            f"{release.institution} 발표 원문에서 후속 공지나 첨부자료가 있는지 확인합니다.",
            f"발표일 {release.date} 이후 내용이 바뀌었을 수 있으므로 최신 공지 기준으로 다시 봅니다.",
            "신청, 참여, 방문이 필요한 사안이면 담당 기관 안내와 연락처를 확인합니다.",
        ]
    return "\n".join(f"- {item}" for item in checks[:3])


def finalize_article_body(release: PressRelease) -> str:
    if release.article_ready and article_is_specific(release.body_text, release):
        body = release.body_text.strip()
        if "## 원문" not in body:
            body += f"\n\n## 원문\n\n- [{release.institution} 보도자료]({release.url})"
        return body + "\n"
    return make_article_body(release)


def estimate_article_quality(body: str) -> float:
    cleaned = clean_text(body)
    score = 70.0
    if len(cleaned) >= 900:
        score += 8
    if len(cleaned) >= 1300:
        score += 5
    if len(re.findall(r"^##\s+", body, flags=re.M)) >= 4:
        score += 5
    if re.search(r"\d", cleaned):
        score += 5
    if re.search(r"대상|시행|기간|장소|기관|신청|참여|확인", cleaned):
        score += 4
    score -= 8 * sum(1 for marker in WEAK_ARTICLE_MARKERS if marker in cleaned)
    return max(50.0, min(96.0, score))


def _excerpt(text: str, limit: int = 180) -> str:
    text = " ".join(clean_text(text).split())
    return text[:limit].rstrip()


def with_particle(text: str, consonant_particle: str, vowel_particle: str) -> str:
    if not text:
        return text
    code = ord(text[-1])
    has_final = 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0
    return text + (consonant_particle if has_final else vowel_particle)


def classify_press_category(release: PressRelease) -> str:
    """보도자료 소재를 사이트 주요 카테고리로 분류한다."""
    text = f"{release.title}\n{release.institution}\n{release.body_text[:2500]}".lower()
    scores = {category: 0 for category, _ in PRESS_CATEGORY_RULES}
    for category, keywords in PRESS_CATEGORY_RULES:
        for keyword in keywords:
            key = keyword.lower()
            if key in text:
                scores[category] += 3 if key in release.title.lower() else 1

    hint = INSTITUTION_CATEGORY_HINTS.get(release.institution)
    if hint:
        scores[hint] = scores.get(hint, 0) + 1

    political_markers = ("선거", "투표", "당선", "공약", "정당", "후보자", "정치")
    if scores["정치"] >= 3 and any(marker in text for marker in political_markers):
        return "정치"
    if scores["기술"] >= 3:
        return "기술"
    if scores["핫이슈"] >= 3:
        return "핫이슈"
    if scores["생활"] >= 3:
        return "생활"
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "정책"


def search_cover_image(
    release: PressRelease,
    prefix: str,
    image_agent: ImageAgent | None,
    category: str,
) -> tuple[str, str]:
    if release.image_url:
        return release.image_url, release.image_alt or f"{release.title} 관련 보도자료 이미지"
    if not image_agent:
        return "", ""

    slug = unique_slug(prefix, release.title, release.url)
    draft = Draft(
        topic=Topic(
            keyword=release.title,
            title_hint=release.title,
            category=category,  # type: ignore[arg-type]
        ),
        title=release.title,
        slug=slug,
        excerpt=_excerpt(release.body_text),
        body_markdown=release.body_text,
        tags=["보도기사", release.institution],
    )
    updated = image_agent.attach_cover(draft)
    return updated.cover_image_path or "", updated.cover_image_alt or ""


def is_placeholder_cover(url: str) -> bool:
    if not url:
        return False
    weak_markers = (
        "picsum.photos",
        "loremflickr.com",
        "placehold.co",
        "placeholder",
        "assets/logos/",
        "/assets/logos/",
    )
    return url in set(INSTITUTION_LOGOS.values()) or any(marker in url for marker in weak_markers)


def write_post(
    release: PressRelease,
    prefix: str,
    sequence: int,
    overwrite: bool = False,
    image_agent: ImageAgent | None = None,
) -> Path:
    path = post_path_for_release(prefix, release.title, release.url, overwrite=overwrite)
    if path.exists() and not overwrite:
        return path
    title = existing_frontmatter_value(path, "title") if overwrite else ""
    if not title:
        title = release.title
    existing_cover = existing_frontmatter_value(path, "cover_image") if overwrite else ""
    existing_alt = existing_frontmatter_value(path, "cover_image_alt") if overwrite else ""
    preserved_cover = existing_cover if existing_cover and not is_placeholder_cover(existing_cover) else ""
    preserved_alt = existing_alt if preserved_cover else ""
    try:
        base_dt = datetime.fromisoformat(release.date)
    except ValueError:
        base_dt = datetime.now()
    post_dt = base_dt + timedelta(minutes=sequence)
    category = classify_press_category(release)
    tags = ["보도기사", release.institution, category]
    searched_cover = ""
    searched_alt = ""
    if not preserved_cover and not release.image_url:
        searched_cover, searched_alt = search_cover_image(release, prefix, image_agent, category)
    img = (
        preserved_cover
        or release.image_url
        or searched_cover
        or INSTITUTION_LOGOS.get(release.institution, "")
    )
    cover_line = f"cover_image: {yaml_quote(img)}\n" if img else ""
    alt = preserved_alt or release.image_alt or searched_alt or f"{release.title} 관련 보도자료 이미지"
    article_body = finalize_article_body(release)
    quality_score = estimate_article_quality(article_body)
    frontmatter = (
        "---\n"
        f"title: {yaml_quote(title)}\n"
        f"date: {yaml_quote(post_dt.isoformat(timespec='minutes'))}\n"
        f"category: {yaml_quote(category)}\n"
        "tags:\n"
        + "".join(f"  - {yaml_quote(t)}\n" for t in tags)
        + f"quality_score: {quality_score:.1f}\n"
        + cover_line
        + f"cover_image_alt: {yaml_quote(alt)}\n"
        + f"author: {yaml_quote(release.institution)}\n"
        + "---\n\n"
    )
    path.write_text(frontmatter + article_body, encoding="utf-8")
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
    while len(links) < per_source and page <= max_pages_for(per_source):
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
    while len(links) < per_source and page <= max_pages_for(per_source):
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
    html_body = html_to_text(body_fragment)
    hwpx_text = extract_first_hwpx_attachment(page, url, "과학기술정보통신부")
    if len(hwpx_text) > len(html_body):
        html_body = hwpx_text
    return PressRelease(
        institution="과학기술정보통신부",
        title=title,
        date=date,
        url=url,
        body_text=html_body,
        image_url=img_url,
        image_alt=img_alt or title,
    )


# ──────────────────────────────────────────────
# 재정경제부 (mofe)
# ──────────────────────────────────────────────

def mofe_links(per_source: int) -> list[str]:
    list_url  = "https://www.mofe.go.kr/nw/nes/nesdta.do?bbsId=MOSFBBS_000000000028&menuNo=4010100"
    view_base = "https://www.mofe.go.kr/nw/nes/detailNesDtaView.do?searchBbsId1=MOSFBBS_000000000028&menuNo=4010100&searchNttId1="
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= max_pages_for(per_source):
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
    title = clean_text(re.sub(r"<[^>]+>", " ", title_m.group(1))) if title_m else "재정경제부 보도자료"
    raw_date = re.sub(r"<[^>]+>", "", date_m.group(1) if date_m else "").strip()
    date = re.sub(r"\.", "-", raw_date.replace(" ", ""))[:10] or datetime.now().strftime("%Y-%m-%d")
    fragment = body_m.group(2) if body_m and body_m.lastindex and body_m.lastindex >= 2 else ""
    img_url, img_alt = first_image(fragment or page, url)
    hwpx_text = extract_first_hwpx_attachment(page, url, "재정경제부")
    body_text = hwpx_text or html_to_text(fragment or page)
    return PressRelease(
        institution="재정경제부",
        title=title,
        date=date,
        url=url,
        body_text=body_text,
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
    while len(links) < per_source and page <= max_pages_for(per_source):
        html_src = fetch(f"{list_url}?pCurrentPage={page}")
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
    hwpx_text = extract_first_hwpx_attachment(page, url, "문화체육관광부")
    if len(hwpx_text) > len(body_text):
        body_text = hwpx_text
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
    while len(links) < per_source and page <= max_pages_for(per_source):
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
    hwpx_text = extract_first_hwpx_attachment(page, url, "국가유산진흥원")
    body_text = hwpx_text or html_to_text(fragment)
    return PressRelease(
        institution="국가유산진흥원",
        title=title,
        date=date,
        url=url,
        body_text=body_text,
        image_url=img_url,
        image_alt=img_alt,
    )


def khs_links(per_source: int) -> list[str]:
    seen: set[str] = set()
    links: list[str] = []
    page = 1
    while len(links) < per_source and page <= max_pages_for(per_source):
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
    hwpx_text = extract_first_hwpx_attachment(page, url, "국가유산청")
    body_text = hwpx_text or html_to_text(fragment)
    return PressRelease(
        institution="국가유산청",
        title=title,
        date=date,
        url=url,
        body_text=body_text,
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


def _init_writer(enabled: bool) -> "WriterAgent | None":
    if not enabled:
        return None
    try:
        w = WriterAgent(load_settings())
        if w._client:
            print(f"LLM 활성화 (모델: {w._model})")
            return w
        print("LLM 키 없음 — LLM 기능 건너뜀")
    except Exception as e:
        print(f"LLM 초기화 실패: {e}")
    return None


def _init_image_agent(enabled: bool) -> ImageAgent | None:
    if not enabled:
        return None
    try:
        settings = load_settings()
        settings.enable_image_generation = False
        agent = ImageAgent(settings)
        providers = []
        if settings.unsplash_access_key:
            providers.append("Unsplash")
        if settings.pexels_api_key:
            providers.append("Pexels")
        if settings.pixabay_api_key:
            providers.append("Pixabay")
        provider_text = " → ".join(providers) if providers else "picsum fallback"
        print(f"이미지 검색 활성화 ({provider_text})")
        return agent
    except Exception as e:
        print(f"이미지 검색 초기화 실패: {e}")
    return None


def _enrich_release(release: PressRelease, writer: "WriterAgent") -> None:
    """LLM으로 본문 보강 + 제목 재작성 (in-place)."""
    if needs_llm_enrichment(release.body_text):
        generated = generate_article_from_source(release, writer)
        if generated:
            release.body_text = generated
            release.article_ready = True
    release.title = rewrite_title(release.title, release.body_text, writer)


def _import_source(
    prefix: str,
    list_fn: object,
    release_fn: object,
    per_source: int,
    writer: "WriterAgent | None",
    seq_start: int,
    overwrite: bool,
    new_only: bool = False,
    image_agent: ImageAgent | None = None,
) -> tuple[list[Path], list[str], int]:
    name = AGENCIES[prefix]
    print(f"\n[{name}] 링크 수집 중...")
    written: list[Path] = []
    errors: list[str] = []
    seq = seq_start
    target = per_source
    list_limit = per_source
    if new_only and not overwrite:
        list_limit = max(per_source * 4, per_source + 40)
    try:
        links = list_fn(list_limit)  # type: ignore[call-arg]
    except Exception as e:
        errors.append(f"{name} 목록 수집 실패: {e}")
        print(f"  ✗ 목록 실패: {e}")
        return written, errors, seq
    print(f"  {len(links)}건 발견")
    for url in links:
        try:
            if new_only and not overwrite and existing_post_for_url(prefix, url):
                print(f"  = 기존 글 건너뜀: {url[:70]}")
                continue
            release = release_fn(url)  # type: ignore[call-arg]
            if writer:
                _enrich_release(release, writer)
            path = write_post(release, prefix, seq, overwrite=overwrite, image_agent=image_agent)
            written.append(path)
            seq += 1
            print(f"  + {release.title[:50]}")
            if new_only and len(written) >= target:
                break
        except Exception as e:
            errors.append(f"{url}: {e}")
            print(f"  ✗ {url[:60]}: {e}")
    return written, errors, seq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=12,
                        help="기관별 수집 상한 (기본값: 12)")
    parser.add_argument("--agencies", nargs="*", default=None,
                        help="특정 기관만 수집 (예: --agencies mois msit)")
    parser.add_argument("--rewrite-titles", action="store_true",
                        help="LLM으로 본문 보강 + 제목 재작성")
    parser.add_argument("--overwrite-existing", action="store_true",
                        help="기존 보도자료 글도 다시 생성해 본문을 갱신")
    parser.add_argument("--new-only", action="store_true",
                        help="이미 작성한 URL은 건너뛰고 기관별 신규 글만 지정 수만큼 생성")
    parser.add_argument("--no-search-images", action="store_true",
                        help="원문 이미지가 없는 보도자료에 검색 기반 대표 이미지를 붙이지 않음")
    args = parser.parse_args()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    writer = _init_writer(args.rewrite_titles)
    image_agent = _init_image_agent(not args.no_search_images)

    all_written: list[Path] = []
    all_errors: list[str] = []
    seq = 0

    for prefix, list_fn, release_fn in SOURCES:
        if args.agencies and prefix not in args.agencies:
            continue
        written, errors, seq = _import_source(
            prefix,
            list_fn,
            release_fn,
            args.per_source,
            writer,
            seq,
            args.overwrite_existing,
            args.new_only,
            image_agent,
        )
        all_written.extend(written)
        all_errors.extend(errors)

    print(f"\n총 {len(all_written)}건 저장 완료")
    if all_errors:
        print(f"오류 {len(all_errors)}건:")
        for e in all_errors:
            print(f"  - {e}")
    for p in all_written:
        print(p.relative_to(ROOT))


if __name__ == "__main__":
    main()
