"""Refine legacy TourAPI fallback travel posts with an LLM."""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from openai import OpenAI


TARGET_PHRASE = "TourAPI에서 본 주변 포인트"
NEW_PHRASE = "주변 포인트"


@dataclass(frozen=True)
class LlmProvider:
    name: str
    client: OpenAI
    model: str


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
                OpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/", timeout=timeout, max_retries=0),
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
        providers.append(LlmProvider("openai", OpenAI(api_key=key, timeout=timeout, max_retries=0), os.getenv("OPENAI_MODEL", "gpt-4.1-mini")))
    if key := os.getenv("GITHUB_TOKEN"):
        providers.append(
            LlmProvider(
                "github",
                OpenAI(api_key=key, base_url="https://models.inference.ai.azure.com", timeout=timeout, max_retries=0),
                os.getenv("GITHUB_MODEL", "Llama-3.3-70B-Instruct"),
            )
        )
    order = [name.strip() for name in os.getenv("REFINE_LLM_PROVIDER_ORDER", "motif,gemini,openrouter,openai,github,groq").split(",")]
    rank = {name: index for index, name in enumerate(order)}
    return sorted(providers, key=lambda provider: rank.get(provider.name, len(rank)))


def split_post(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, raw_meta, body = text.split("---", 2)
    return yaml.safe_load(raw_meta) or {}, body.strip()


def join_post(meta: dict, body: str) -> str:
    raw_meta = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{raw_meta}\n---\n\n{body.strip()}\n"


def extract_cover(body: str) -> tuple[str, str]:
    match = re.match(r"(!\[[^\]]*\]\([^)]+\)\s*)\n+", body)
    if not match:
        return "", body.strip()
    return match.group(1).strip(), body[match.end():].strip()


def rule_cleanup(body: str) -> str:
    cleaned = body.replace(TARGET_PHRASE, NEW_PHRASE)
    cleaned = re.sub(r"글에서는 [^.]+반영하세요\.\s*", "", cleaned)
    cleaned = cleaned.replace("TourAPI 응답은 있었지만", "공개 데이터 응답은 있었지만")
    return cleaned.strip()


def is_target_post(text: str) -> bool:
    return TARGET_PHRASE in text or ("## 주변 포인트" in text and "한국관광공사 TourAPI" in text)


def compact_body_for_prompt(body: str) -> str:
    return body[:7000]


def llm_refine(provider: LlmProvider, title: str, body: str) -> str:
    prompt = f"""
아래 한국어 여행/핫이슈 블로그 글의 본문만 자연스럽게 다시 다듬어 주세요.

목표:
- 섹션 제목은 반드시 "## 주변 포인트"를 사용하고, "TourAPI에서 본 주변 포인트"는 쓰지 않는다.
- "글에서는 반영하세요", "우선 사용하세요"처럼 작성자에게 지시하는 내부 문구를 독자용 문장으로 바꾼다.
- TourAPI라는 단어는 필요할 때만 "한국관광공사 공개 데이터" 정도로 자연스럽게 풀어 쓴다.
- 직접 방문한 척하지 않는다.
- 출처에 없는 장소, 영업시간, 가격, 경험담은 추가하지 않는다.
- 기존 표와 참고한 곳 섹션은 유지하되, raw 데이터 나열은 읽기 쉬운 문장이나 짧은 목록으로 정리한다.
- Markdown 본문만 반환한다. 프론트매터, 제목 레이블, 설명문은 반환하지 않는다.

글 제목:
{title}

현재 본문:
{compact_body_for_prompt(body)}
"""
    response = provider.client.chat.completions.create(
        model=provider.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.55,
        max_tokens=2200,
    )
    refined = response.choices[0].message.content or body
    refined = re.sub(r"^\s*BODY:\s*", "", refined.strip(), flags=re.I)
    return rule_cleanup(refined)


def refine_file(path: Path, providers: list[LlmProvider], dry_run: bool) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    if not is_target_post(text):
        return False, "not a TourAPI fallback post"

    meta, body = split_post(text)
    title = str(meta.get("title") or path.stem)
    cover, content = extract_cover(body)
    content = rule_cleanup(content)

    if providers:
        errors: list[str] = []
        for provider in providers:
            try:
                content = llm_refine(provider, title, content)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            reason = f"llm refined via {provider.name}"
            break
        else:
            content = rule_cleanup(content)
            reason = "all llm providers failed, rule cleanup only: " + " | ".join(errors[:3])
    else:
        reason = "no llm key, rule cleanup only"

    new_body = f"{cover}\n\n{content}" if cover else content
    meta["quality_score"] = max(float(meta.get("quality_score") or 0), 95.0)
    new_text = join_post(meta, new_body)
    if new_text == text:
        return False, "unchanged"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True, reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="output/posts/*.md")
    parser.add_argument("--max-count", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    providers = init_providers()
    paths = sorted(Path().glob(args.glob))
    changed = 0
    for path in paths:
        if changed >= args.max_count:
            break
        ok, reason = refine_file(path, providers, args.dry_run)
        if ok:
            changed += 1
            mode = "would refine" if args.dry_run else "refined"
            print(f"{mode}: {path} ({reason})")
    print(f"\nrefined {changed} TourAPI posts")


if __name__ == "__main__":
    main()
