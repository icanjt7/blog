"""Improve duplicate titles and short posts in bounded LLM-backed batches."""
from __future__ import annotations

import argparse
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.refine_existing_posts import (
        LlmProvider,
        body_links,
        hard_timeout,
        init_providers,
        join_post,
        normalize_body,
        preserve_images,
        quality_score,
        split_post,
        visible_length,
    )
except ModuleNotFoundError:
    from refine_existing_posts import (
        LlmProvider,
        body_links,
        hard_timeout,
        init_providers,
        join_post,
        normalize_body,
        preserve_images,
        quality_score,
        split_post,
        visible_length,
    )


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class PostRecord:
    path: Path
    meta: dict
    body: str

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.path.stem).strip()


def normalize_title(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", title.casefold())


def load_records(glob: str) -> list[PostRecord]:
    records: list[PostRecord] = []
    for path in sorted(ROOT.glob(glob)):
        split = split_post(path.read_text(encoding="utf-8"))
        if split:
            meta, body = split
            records.append(PostRecord(path, meta, body))
    return records


def duplicate_title_paths(records: list[PostRecord]) -> set[Path]:
    groups: dict[str, list[PostRecord]] = defaultdict(list)
    for record in records:
        groups[normalize_title(record.title)].append(record)
    duplicates: set[Path] = set()
    for key, group in groups.items():
        if not key or len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda record: (str(record.meta.get("date") or ""), record.path.name),
            reverse=True,
        )
        duplicates.update(record.path for record in ordered[1:])
    return duplicates


def clean_title_response(value: str) -> str:
    value = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", value.strip(), flags=re.I)
    value = re.sub(r"^(?:TITLE|제목)\s*:\s*", "", value.strip(), flags=re.I)
    return value.strip().strip('"').strip("'").strip()


def call_provider(provider: LlmProvider, prompt: str, *, max_tokens: int, temperature: float) -> str:
    timeout = int(float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) + 10
    with hard_timeout(timeout):
        response = provider.client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return response.choices[0].message.content or ""


def title_prompt(record: PostRecord) -> str:
    return f"""
다음 글은 다른 글과 제목이 중복됩니다. 본문의 고유한 사실을 반영해 제목을 한 줄로 다시 작성하세요.

규칙:
- 한국어 18~55자를 권장하고 70자를 넘지 않는다.
- 본문에 없는 수치, 혜택, 일정, 결론을 추가하지 않는다.
- '핵심 정리', '총정리', '알아보기', '완벽 가이드'를 쓰지 않는다.
- 제목만 반환한다.

현재 제목: {record.title}
카테고리: {record.meta.get('category', '')}
날짜: {record.meta.get('date', '')}
본문:
{record.body[:5000]}
"""


def improve_title(
    providers: list[LlmProvider], record: PostRecord, used_titles: set[str]
) -> tuple[str, str]:
    max_providers = max(1, int(os.getenv("INDEX_IMPROVE_MAX_PROVIDERS_PER_POST", "3")))
    errors: list[str] = []
    for provider in providers[:max_providers]:
        try:
            title = clean_title_response(
                call_provider(provider, title_prompt(record), max_tokens=100, temperature=0.7)
            )
            normalized = normalize_title(title)
            if len(title) < 8 or len(title) > 70:
                errors.append(f"{provider.name}: invalid length")
            elif not normalized or normalized in used_titles or normalized == normalize_title(record.title):
                errors.append(f"{provider.name}: still duplicate")
            elif "\n" in title or title.startswith(("#", "-")):
                errors.append(f"{provider.name}: invalid format")
            else:
                return title, f"title via {provider.name}"
        except Exception as exc:
            errors.append(f"{provider.name}: {type(exc).__name__}")
    return record.title, "title providers failed: " + " | ".join(errors)


def short_body_prompt(record: PostRecord, min_length: int, target_length: int) -> str:
    return f"""
다음 기존 글을 검색 독자가 주제를 충분히 이해할 수 있는 한국어 글로 보강하세요.

규칙:
- 본문에서 확인되는 사실만 사용하고 수치, 일정, 인용, 혜택, 경험을 만들지 않는다.
- 기존 URL, 출처 링크, 이미지 마크다운을 모두 보존한다.
- 가시 문자 수를 최소 {min_length}자, 목표 {target_length}~{target_length + 400}자로 작성한다.
- ## 헤딩을 3~5개 사용한다.
- 정보가 부족하면 추측으로 채우지 말고 기존 사실의 맥락, 영향, 확인할 점을 설명한다.
- '이번 포스팅에서는', '알아보겠습니다', '총정리', '놓치지 마세요'를 쓰지 않는다.
- Markdown 본문만 반환한다.

제목: {record.title}
카테고리: {record.meta.get('category', '')}
태그: {', '.join(str(tag) for tag in record.meta.get('tags') or [])}
현재 본문:
{record.body[:9000]}
"""


def acceptable_expansion(original: str, expanded: str, min_length: int) -> tuple[bool, str]:
    new_length = visible_length(expanded)
    if new_length < min_length:
        return False, f"too short {new_length}"
    if new_length > max(2400, visible_length(original) * 4):
        return False, f"too long {new_length}"
    if len(re.findall(r"^##\s+", expanded, flags=re.M)) < 3:
        return False, "too few sections"
    if body_links(original) - body_links(expanded):
        return False, "source links removed"
    original_images = set(re.findall(r"!\[[^\]]*\]\([^)]+\)", original))
    expanded_images = set(re.findall(r"!\[[^\]]*\]\([^)]+\)", expanded))
    if original_images - expanded_images:
        return False, "images removed"
    return True, "ok"


def expand_body(
    providers: list[LlmProvider], record: PostRecord, min_length: int, target_length: int
) -> tuple[str, str]:
    max_providers = max(1, int(os.getenv("INDEX_IMPROVE_MAX_PROVIDERS_PER_POST", "3")))
    errors: list[str] = []
    prompt = short_body_prompt(record, min_length, target_length)
    for provider in providers[:max_providers]:
        try:
            expanded = normalize_body(
                call_provider(provider, prompt, max_tokens=3200, temperature=0.45)
            )
            expanded = preserve_images(record.body, expanded)
            ok, reason = acceptable_expansion(record.body, expanded, min_length)
            if ok:
                return expanded, f"body via {provider.name}"
            errors.append(f"{provider.name}: {reason}")
        except Exception as exc:
            errors.append(f"{provider.name}: {type(exc).__name__}")
    return record.body, "body providers failed: " + " | ".join(errors)


def candidate_records(
    records: list[PostRecord], duplicate_paths: set[Path], mode: str, min_length: int
) -> list[PostRecord]:
    candidates = [
        record
        for record in records
        if record.path in duplicate_paths
        or (mode in {"both", "short"} and visible_length(record.body) < min_length)
    ]
    return sorted(
        candidates,
        key=lambda record: (
            0 if record.path in duplicate_paths else 1,
            visible_length(record.body),
            str(record.meta.get("date") or ""),
            record.path.name,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="output/posts/*.md")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--mode", choices=("both", "titles", "short"), default="both")
    parser.add_argument("--min-length", type=int, default=800)
    parser.add_argument("--target-length", type=int, default=1100)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    providers = init_providers()
    print("loaded llm providers: " + (", ".join(p.name for p in providers) or "none"), flush=True)
    if not providers:
        raise SystemExit("No LLM providers are configured")

    records = load_records(args.glob)
    duplicate_paths = duplicate_title_paths(records) if args.mode in {"both", "titles"} else set()
    used_titles = {normalize_title(record.title) for record in records}
    candidates = candidate_records(records, duplicate_paths, args.mode, args.min_length)
    max_candidates = args.max_candidates or max(args.limit * 4, args.limit)

    changed = 0
    attempted = 0
    for record in candidates[:max_candidates]:
        if changed >= args.limit:
            break
        attempted += 1
        original_title = record.title
        original_body = record.body
        reasons: list[str] = []

        if record.path in duplicate_paths and args.mode in {"both", "titles"}:
            new_title, reason = improve_title(providers, record, used_titles)
            reasons.append(reason)
            if new_title != original_title:
                used_titles.add(normalize_title(new_title))
                record.meta["title"] = new_title
                record.meta["title_improved_by_llm"] = True

        if visible_length(record.body) < args.min_length and args.mode in {"both", "short"}:
            new_body, reason = expand_body(providers, record, args.min_length, args.target_length)
            reasons.append(reason)
            if new_body != record.body:
                record.body = new_body
                record.meta["quality_score"] = max(
                    float(record.meta.get("quality_score") or 0), quality_score(new_body)
                )
                record.meta["expanded_by_llm"] = True

        if record.title == original_title and record.body == original_body:
            print(f"not improved: {record.path.relative_to(ROOT)} ({'; '.join(reasons)})", flush=True)
            continue

        record.meta["search_index_improved"] = True
        if not args.dry_run:
            record.path.write_text(join_post(record.meta, record.body), encoding="utf-8")
        changed += 1
        action = "would improve" if args.dry_run else "improved"
        print(
            f"{action}: {record.path.relative_to(ROOT)} "
            f"(title={original_title != record.title}; "
            f"len={visible_length(original_body)}->{visible_length(record.body)}; {'; '.join(reasons)})",
            flush=True,
        )

    short_count = sum(visible_length(record.body) < args.min_length for record in records)
    print(
        f"\nrecords {len(records)}, duplicate title candidates {len(duplicate_paths)}, "
        f"short candidates {short_count}, attempted {attempted}, improved {changed}"
    )


if __name__ == "__main__":
    main()
