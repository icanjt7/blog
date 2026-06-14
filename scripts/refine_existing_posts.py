"""Refine existing posts with an LLM without padding their length.

The goal is not to make posts longer. It rewrites weak or low-score posts into
more concrete blog articles while staying close to the original body length and
preserving frontmatter, links, images, and source-grounded facts.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import yaml
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "output" / "posts"

WEAK_MARKERS = (
    "최근 검색 수요가 꾸준히 생기는 주제입니다",
    "공개된 자료를 기준으로 핵심만 정리한 정보성 콘텐츠입니다",
    "원문 안내의 시행일과 적용 대상을 먼저 봅니다",
    "신청, 예약, 방문, 자동 적용 중 어떤 방식인지 구분합니다",
    "비용, 포인트, 캐시백, 준비물처럼 숫자로 확인할 항목",
    "지역이나 세대, 계정, 사용량처럼 예외 조건",
    "한국 기업, 연구기관, 소비자, 정책 담당자가 직접 적용할 내용인지 판단하려면",
    "발표 기관, 대상, 시행 시점, 후속 문서를 함께 확인해야 합니다",
    "제품명, 회사명, 기능 변화가 함께 묶인 기술 뉴스입니다",
    "이번 글에서 봐야 할 내용",
    "해당 제품 사용자, 도입을 검토하는 기업",
    "TourAPI에서 본 주변 포인트",
)

AI_CLICHES = (
    "이번 포스팅에서는",
    "알아보겠습니다",
    "살펴보겠습니다",
    "정리해 보겠습니다",
    "도움이 되셨으면",
    "놓치지 마세요",
    "이제 준비가 끝났으니",
    "확인해 보시기 바랍니다",
)


@dataclass(frozen=True)
class LlmProvider:
    name: str
    client: OpenAI
    model: str


class ProviderTimeoutError(TimeoutError):
    pass


@contextmanager
def hard_timeout(seconds: int):
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _raise_timeout(_signum, _frame):
        raise ProviderTimeoutError(f"LLM provider exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def init_providers() -> list[LlmProvider]:
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    providers: list[LlmProvider] = []
    if key := os.getenv("MOTIF_API") or os.getenv("MOTIF_API_KEY"):
        providers.append(
            LlmProvider(
                "motif",
                OpenAI(
                    api_key=key,
                    base_url=os.getenv("MOTIF_BASE_URL", "https://chat.motiftech.io/openapi/v1"),
                    timeout=timeout,
                    max_retries=0,
                ),
                os.getenv("MOTIF_MODEL", "motif-12.7b-reasoning"),
            )
        )
    if key := os.getenv("GROQ_API_KEY"):
        providers.append(
            LlmProvider(
                "groq",
                OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=timeout, max_retries=0),
                os.getenv("GROQ_MODEL", "groq/compound"),
            )
        )
    if key := os.getenv("GEMINI_API_KEY"):
        providers.append(
            LlmProvider(
                "gemini",
                OpenAI(
                    api_key=key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=timeout,
                    max_retries=0,
                ),
                os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            )
        )
    if key := os.getenv("OPENROUTER_API_KEY"):
        providers.append(
            LlmProvider(
                "openrouter",
                OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", timeout=timeout, max_retries=0),
                os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
            )
        )
    if key := os.getenv("OPENAI_API_KEY"):
        providers.append(
            LlmProvider("openai", OpenAI(api_key=key, timeout=timeout, max_retries=0), os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        )
    if key := os.getenv("GITHUB_TOKEN"):
        providers.append(
            LlmProvider(
                "github",
                OpenAI(api_key=key, base_url="https://models.inference.ai.azure.com", timeout=timeout, max_retries=0),
                os.getenv("GITHUB_MODEL", "Llama-3.3-70B-Instruct"),
            )
        )
    order = [name.strip() for name in os.getenv("REFINE_LLM_PROVIDER_ORDER", "motif,groq,gemini,openrouter,openai,github").split(",")]
    rank = {name: index for index, name in enumerate(order)}
    return sorted(providers, key=lambda provider: rank.get(provider.name, len(rank)))


def split_post(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) != 3:
        return None
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def join_post(meta: dict, body: str) -> str:
    raw_meta = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{raw_meta}\n---\n\n{body.strip()}\n"


def visible_length(markdown_body: str) -> int:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", markdown_body)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"[#>*_`|\\-]", " ", text)
    return len(re.sub(r"\s+", " ", text).strip())


def quality_score(body: str) -> float:
    cleaned = re.sub(r"\s+", " ", body).strip()
    score = 72.0
    if visible_length(body) >= 800:
        score += 8
    if len(re.findall(r"^##\s+", body, flags=re.M)) >= 4:
        score += 6
    if re.search(r"\|.+\|", body):
        score += 4
    if re.search(r"\d", cleaned):
        score += 4
    score -= 10 * sum(1 for marker in WEAK_MARKERS if marker in cleaned)
    score -= 4 * sum(1 for marker in AI_CLICHES if marker in cleaned)
    return max(45.0, min(96.0, score))


def normalize_body(text: str) -> str:
    text = re.sub(r"^\s*BODY\s*:\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())
    text = text.replace("TourAPI에서 본 주변 포인트", "주변 포인트")
    return text.strip()


def preserve_images(original: str, refined: str) -> str:
    images = re.findall(r"!\[[^\]]*\]\([^)]+\)", original)
    missing = [image for image in images if image not in refined]
    if not missing:
        return refined
    image_block = "\n".join(missing)
    first_heading = re.match(r"^(##\s+.+)$", refined, flags=re.M)
    if not first_heading:
        return f"{image_block}\n\n{refined}".strip()
    insert_at = first_heading.end()
    return f"{refined[:insert_at]}\n{image_block}{refined[insert_at:]}".strip()


def should_refine(meta: dict, body: str, *, min_quality: float, include_all: bool) -> bool:
    if include_all:
        return True
    score = float(meta.get("quality_score") or 0)
    if not score or score < min_quality:
        return True
    combined = f"{meta.get('title', '')}\n{body}"
    if any(marker in combined for marker in WEAK_MARKERS):
        return True
    if any(marker in combined for marker in AI_CLICHES):
        return True
    return False


def body_links(body: str) -> set[str]:
    return set(re.findall(r"https?://[^)\s]+", body))


def acceptable(original: str, refined: str, *, max_growth: float, min_ratio: float) -> tuple[bool, str]:
    old_len = max(visible_length(original), 1)
    new_len = visible_length(refined)
    if new_len < max(350, int(old_len * min_ratio)):
        return False, f"too short {new_len}/{old_len}"
    if new_len > int(old_len * max_growth) + 250:
        return False, f"too long {new_len}/{old_len}"
    if len(re.findall(r"^##\s+", refined, flags=re.M)) < 3:
        return False, "too few sections"
    if any(marker in refined for marker in WEAK_MARKERS):
        return False, "weak marker remains"
    if any(marker in refined for marker in AI_CLICHES):
        return False, "ai cliche remains"
    lost_links = body_links(original) - body_links(refined)
    if lost_links:
        return False, "source links removed"
    return True, "ok"


def prompt_for(meta: dict, body: str, max_growth: float, min_ratio: float) -> str:
    title = str(meta.get("title") or "")
    category = str(meta.get("category") or "")
    tags = ", ".join(str(tag) for tag in meta.get("tags") or [])
    length = visible_length(body)
    min_len = int(length * min_ratio)
    max_len = int(length * max_growth)
    return f"""
아래 기존 블로그 글을 독자가 읽기 좋은 한국어 블로그 글로 다시 작성하세요.

중요한 목표:
- 글을 임의로 길게 늘리지 않는다.
- 현재 본문 길이 기준 약 {min_len}~{max_len}자 안에서 밀도를 높인다.
- 없는 사실, 수치, 방문 경험, 가격, 일정은 추가하지 않는다.
- 기존 글에 있는 링크, 출처, 이미지 마크다운은 보존한다.
- 범용 체크리스트와 AI식 문장을 제거하고, 글의 주제에 맞는 구체 문장으로 바꾼다.
- 제목을 본문 첫 문장에 반복하지 말고, 첫 단락에서 독자가 알 핵심을 바로 설명한다.
- ## 헤딩을 3~5개 사용하고, 기존 표가 있으면 유지하거나 더 읽기 좋게 정리한다.
- 직접 방문한 척하지 않는다.
- Markdown 본문만 반환한다. frontmatter, TITLE, EXCERPT, 설명문은 반환하지 않는다.

제목: {title}
카테고리: {category}
태그: {tags}

현재 본문:
{body[:9000]}
"""


def refine_with_llm(
    providers: list[LlmProvider],
    meta: dict,
    body: str,
    *,
    max_growth: float,
    min_ratio: float,
) -> tuple[str, str]:
    if not providers:
        return body, "no llm providers"
    max_providers = max(1, int(os.getenv("REFINE_MAX_PROVIDERS_PER_POST", "2")))
    timeout = int(float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) + 10
    prompt = prompt_for(meta, body, max_growth, min_ratio)
    errors: list[str] = []
    for provider in providers[:max_providers]:
        try:
            with hard_timeout(timeout):
                response = provider.client.chat.completions.create(
                    model=provider.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=2600,
                )
            refined = normalize_body(response.choices[0].message.content or "")
            refined = preserve_images(body, refined)
            ok, reason = acceptable(body, refined, max_growth=max_growth, min_ratio=min_ratio)
            if ok:
                return refined, f"llm refined via {provider.name}"
            errors.append(f"{provider.name}: rejected {reason}")
        except Exception as exc:
            errors.append(f"{provider.name}: {type(exc).__name__}")
    return body, "all llm providers failed or rejected: " + " | ".join(errors[:4])


def refine_file(
    path: Path,
    providers: list[LlmProvider],
    *,
    min_quality: float,
    include_all: bool,
    max_growth: float,
    min_ratio: float,
    dry_run: bool,
) -> tuple[bool, str]:
    raw = path.read_text(encoding="utf-8")
    split = split_post(raw)
    if not split:
        return False, "skip:no frontmatter"
    meta, body = split
    if not should_refine(meta, body, min_quality=min_quality, include_all=include_all):
        return False, "skip:not weak"
    refined, reason = refine_with_llm(providers, meta, body, max_growth=max_growth, min_ratio=min_ratio)
    if refined == body:
        return False, reason
    new_score = quality_score(refined)
    if new_score < max(78.0, min_quality - 8):
        return False, f"rejected low score {new_score:.1f}"
    meta["quality_score"] = max(float(meta.get("quality_score") or 0), new_score)
    meta["refined_by_llm"] = True
    new_text = join_post(meta, refined)
    if new_text == raw:
        return False, "unchanged"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True, f"{reason}; score {new_score:.1f}; len {visible_length(body)}->{visible_length(refined)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="output/posts/*.md")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-quality", type=float, default=90)
    parser.add_argument("--include-all", action="store_true", help="Refine even posts that do not look weak")
    parser.add_argument("--category", nargs="*", default=[], help="Optional category filter")
    parser.add_argument("--tag", nargs="*", default=[], help="Optional tag filter")
    parser.add_argument("--max-growth", type=float, default=1.12, help="Maximum visible length growth ratio")
    parser.add_argument("--min-ratio", type=float, default=0.72, help="Minimum visible length ratio")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    providers = init_providers()
    provider_names = ", ".join(provider.name for provider in providers) or "none"
    print(f"loaded llm providers: {provider_names}", flush=True)
    if not providers and os.getenv("REFINE_REQUIRE_LLM", "").lower() in {"1", "true", "yes"}:
        raise SystemExit("REFINE_REQUIRE_LLM is true, but no LLM providers are configured")
    paths = sorted(ROOT.glob(args.glob), key=lambda path: path.stat().st_mtime)
    changed = 0
    scanned = 0
    reported_failures = 0
    wanted_categories = set(args.category)
    wanted_tags = set(args.tag)
    for path in paths:
        if changed >= args.limit:
            break
        raw = path.read_text(encoding="utf-8")
        split = split_post(raw)
        if not split:
            continue
        meta, _body = split
        if wanted_categories and str(meta.get("category") or "") not in wanted_categories:
            continue
        tags = {str(tag) for tag in meta.get("tags") or []}
        if wanted_tags and not (tags & wanted_tags):
            continue
        scanned += 1
        print(f"checking: {path.relative_to(ROOT)}", flush=True)
        ok, reason = refine_file(
            path,
            providers,
            min_quality=args.min_quality,
            include_all=args.include_all,
            max_growth=args.max_growth,
            min_ratio=args.min_ratio,
            dry_run=args.dry_run,
        )
        if ok:
            changed += 1
            mode = "would refine" if args.dry_run else "refined"
            print(f"{mode}: {path.relative_to(ROOT)} ({reason})")
        elif not reason.startswith("skip:") and reported_failures < 30:
            reported_failures += 1
            print(f"not refined: {path.relative_to(ROOT)} ({reason})", flush=True)
    print(f"\nscanned {scanned} posts, refined {changed} posts")


if __name__ == "__main__":
    main()
