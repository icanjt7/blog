"""Canary-first backfill pipeline for unpublished korea.kr press releases.

The pipeline is intentionally split into collection, LLM articleization and QA
so a 50-page staging build can gate a larger production run.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import random
import re
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import import_press_releases as press
from blog_agent.config import load_settings
from blog_agent.quality_filters import InvalidContentData, evaluate_source_content, require_source_content
from blog_agent.slugs import UnsafeSlugError
from blog_agent.writer import WriterAgent
from import_korea_policy_press import (
    Agency,
    ListItem,
    agency_items,
    list_agencies,
    prefix_for,
    release_from_item,
)


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("briefwave.bulk_press")
URL_RE = re.compile(r"https://www\.korea\.kr/briefing/pressReleaseView\.do[^\s)\]<>\"']+")
GENERIC_HEADINGS = {"개요", "지원 내용", "신청 방법", "주요 내용", "향후 계획", "faq"}
_WORKER_WRITER: WriterAgent | None = None


def _normalize_url(value: str) -> str:
    normalized = html.unescape(value).rstrip(".,")
    news_id = re.search(r"[?&]newsId=(\d+)", normalized)
    if news_id:
        return f"https://www.korea.kr/briefing/pressReleaseView.do?newsId={news_id.group(1)}"
    return normalized.split("&pageIndex=", 1)[0]


def existing_source_urls(posts_dir: Path) -> set[str]:
    urls: set[str] = set()
    for path in posts_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        source = re.search(r'^source_url:\s*["\']?([^"\'\n]+)', text, flags=re.M)
        if source:
            urls.add(_normalize_url(source.group(1).strip()))
        urls.update(_normalize_url(match.group(0)) for match in URL_RE.finditer(text))
    return urls


def _collect_agency_items(task: tuple[Agency, int, int, str, str]) -> tuple[Agency, list[ListItem], str]:
    agency, limit, scan_pages, start_date, end_date = task
    try:
        return agency, agency_items(agency, limit, scan_pages, start_date, end_date), ""
    except Exception as exc:
        return agency, [], f"{type(exc).__name__}: {exc}"


def _round_robin(groups: list[list[tuple[Agency, ListItem]]]) -> Iterator[tuple[Agency, ListItem]]:
    offset = 0
    while True:
        emitted = False
        for group in groups:
            if offset < len(group):
                emitted = True
                yield group[offset]
        if not emitted:
            return
        offset += 1


def _fetch_release(task: tuple[Agency, ListItem]) -> tuple[dict[str, str] | None, str]:
    agency, item = task
    try:
        release = release_from_item(item)
        decision = evaluate_source_content(release.title, release.body_text)
        if not decision.accepted:
            return None, decision.reason
        payload = asdict(release)
        payload["agency_code"] = agency.code
        payload["agency_section"] = agency.section
        payload["body_text"] = decision.raw_text
        return payload, ""
    except Exception as exc:
        return None, f"Skip: source fetch failed ({type(exc).__name__})"


def _write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect(args: argparse.Namespace) -> dict[str, object]:
    posted = existing_source_urls(args.posts_dir)
    agencies = list_agencies()
    per_agency = max(40, ((args.candidate_limit * 3) // max(1, len(agencies))) + 20)
    list_tasks = [
        (agency, per_agency, args.scan_pages, args.start_date, args.end_date)
        for agency in agencies
    ]
    groups: list[list[tuple[Agency, ListItem]]] = []
    list_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(args.fetch_workers, len(list_tasks))) as executor:
        for agency, items, error in executor.map(_collect_agency_items, list_tasks):
            if error:
                list_errors.append(f"{agency.name}: {error}")
            fresh = [(agency, item) for item in items if _normalize_url(item.url) not in posted]
            groups.append(fresh)

    candidates: list[tuple[Agency, ListItem]] = []
    seen = set(posted)
    for agency, item in _round_robin(groups):
        url = _normalize_url(item.url)
        if url in seen:
            continue
        seen.add(url)
        candidates.append((agency, item))
        if len(candidates) >= args.candidate_limit:
            break

    accepted: list[dict[str, str]] = []
    skipped: dict[str, int] = {}
    iterator = iter(candidates)
    with ThreadPoolExecutor(max_workers=args.fetch_workers) as executor:
        pending = set()
        for _ in range(min(len(candidates), args.fetch_workers * 2)):
            try:
                pending.add(executor.submit(_fetch_release, next(iterator)))
            except StopIteration:
                break
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                record, reason = future.result()
                if record:
                    accepted.append(record)
                else:
                    skipped[reason] = skipped.get(reason, 0) + 1
                    print(reason)
                try:
                    pending.add(executor.submit(_fetch_release, next(iterator)))
                except StopIteration:
                    pass

    _write_jsonl(args.output, accepted)
    report = {
        "unpublished_candidates": len(candidates),
        "qualified": len(accepted),
        "dropped": len(candidates) - len(accepted),
        "drop_reasons": skipped,
        "list_errors": list_errors,
        "output": str(args.output),
    }
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(candidates) < args.candidate_limit:
        raise RuntimeError(f"only {len(candidates)} unpublished candidates found; requested {args.candidate_limit}")
    return report


def iter_jsonl_chunks(path: Path, chunk_size: int) -> Iterator[list[dict[str, str]]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    chunk: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            chunk.append(json.loads(line))
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
    if chunk:
        yield chunk


def _worker_init() -> None:
    global _WORKER_WRITER
    _WORKER_WRITER = WriterAgent(load_settings())
    if not _WORKER_WRITER._client:
        raise RuntimeError("LLM credentials are required for bulk articleization")


def _articleize_record(record: dict[str, str]) -> tuple[dict[str, str] | None, str]:
    try:
        require_source_content(record["title"], record["body_text"])
        release = press.PressRelease(
            institution=record["institution"],
            title=record["title"],
            date=record["date"],
            url=record["url"],
            body_text=record["body_text"],
            image_url=record.get("image_url", ""),
            image_alt=record.get("image_alt", ""),
        )
        if _WORKER_WRITER is None:
            raise RuntimeError("worker LLM is not initialized")
        article = press.generate_article_from_source(release, _WORKER_WRITER)
        if not article or not press.article_is_specific(article, release):
            return None, "Skip: LLM did not return a specific valid article"
        record = dict(record)
        record["body_text"] = article
        record["article_ready"] = True
        return record, ""
    except InvalidContentData as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"Skip: articleization failed ({type(exc).__name__})"


def _record_to_release(record: dict[str, str]) -> press.PressRelease:
    return press.PressRelease(
        institution=record["institution"], title=record["title"], date=record["date"],
        url=record["url"], body_text=record["body_text"],
        image_url=record.get("image_url", ""), image_alt=record.get("image_alt", ""),
        article_ready=bool(record.get("article_ready")),
    )


def articleize(args: argparse.Namespace) -> dict[str, object]:
    args.posts_dir.mkdir(parents=True, exist_ok=True)
    press.POSTS_DIR = args.posts_dir
    max_workers = args.workers or max(1, os.cpu_count() or 1)
    randomizer = random.Random(args.seed)
    chunks: Iterator[list[dict[str, str]]] = iter_jsonl_chunks(args.input, args.chunk_size)
    if args.random_sample:
        reservoir: list[dict[str, str]] = []
        seen = 0
        for chunk in chunks:
            for record in chunk:
                seen += 1
                if len(reservoir) < args.random_sample:
                    reservoir.append(record)
                else:
                    index = randomizer.randrange(seen)
                    if index < args.random_sample:
                        reservoir[index] = record
        randomizer.shuffle(reservoir)
        chunks = iter([reservoir])

    written: list[str] = []
    skipped: dict[str, int] = {}
    sequence = 0
    chunk_count = 0
    with ProcessPoolExecutor(max_workers=max_workers, initializer=_worker_init) as executor:
        for chunk in chunks:
            chunk_count += 1
            for record, reason in executor.map(_articleize_record, chunk, chunksize=1):
                if record is None:
                    skipped[reason] = skipped.get(reason, 0) + 1
                    print(reason)
                    continue
                agency = Agency(record["agency_code"], record["institution"], record["agency_section"])
                try:
                    path = press.write_post(_record_to_release(record), prefix_for(agency), sequence)
                except (InvalidContentData, UnsafeSlugError) as exc:
                    reason = str(exc)
                    skipped[reason] = skipped.get(reason, 0) + 1
                    continue
                written.append(path.name)
                sequence += 1
                if args.target_success and len(written) >= args.target_success:
                    break
            if args.target_success and len(written) >= args.target_success:
                break

    report = {
        "chunks": chunk_count,
        "chunk_size": args.chunk_size,
        "workers": max_workers,
        "written": len(written),
        "skipped": sum(skipped.values()),
        "skip_reasons": skipped,
        "files": written,
    }
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.target_success and len(written) < args.target_success:
        raise RuntimeError(f"only {len(written)}/{args.target_success} valid articles were generated")
    return report


def verify(args: argparse.Namespace) -> dict[str, object]:
    paths = sorted(args.posts_dir.glob("*.md"))
    failures: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if re.search(r"-[0-9a-f]{8}\.md$", path.name, flags=re.I):
            failures.append(f"opaque hash slug: {path.name}")
        labels = re.findall(r"^> \*\*\[[^\]]+\]\*\*\s+(.+)$", text, flags=re.M)
        if len(labels) != 3 or any(len(value.strip()) < 8 for value in labels):
            failures.append(f"invalid summary box: {path.name}")
        headings = [heading.strip() for heading in re.findall(r"^##\s+(.+)$", text, flags=re.M)]
        meaningful = [h for h in headings if h.casefold() not in GENERIC_HEADINGS]
        required_headings = 4 if 'post_type: "ACTIONABLE"' in text else 3
        if len(meaningful) < required_headings:
            failures.append(f"non-dynamic H2 headings: {path.name}")
        if "post_type: \"INVALID_DATA\"" in text:
            failures.append(f"INVALID_DATA was rendered: {path.name}")
        if args.public_dir:
            rendered = args.public_dir / f"{path.stem}.html"
            if not rendered.exists():
                failures.append(f"missing HTML: {path.stem}.html")
            else:
                html_text = rendered.read_text(encoding="utf-8")
                if 'class="toss-shopping-card product-recommendation"' not in html_text:
                    failures.append(f"missing Toss widget: {rendered.name}")
                if "오늘 한정 특가 및 실구매자 후기 보기" not in html_text:
                    failures.append(f"missing Toss CTA: {rendered.name}")
    report = {"checked": len(paths), "failures": failures, "ok": not failures}
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures or (args.expected and len(paths) != args.expected):
        raise RuntimeError(f"bulk press QA failed: checked={len(paths)}, expected={args.expected}, failures={len(failures)}")
    return report


def _write_report(path: Path | None, payload: dict[str, object]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--posts-dir", type=Path, default=ROOT / "output/posts")
    collect_parser.add_argument("--output", type=Path, required=True)
    collect_parser.add_argument("--candidate-limit", type=int, default=2000)
    collect_parser.add_argument("--fetch-workers", type=int, default=12)
    collect_parser.add_argument("--scan-pages", type=int, default=80)
    collect_parser.add_argument("--start-date", default="2020-01-01")
    collect_parser.add_argument("--end-date", default="2099-12-31")
    collect_parser.add_argument("--report", type=Path)
    collect_parser.set_defaults(func=collect)

    article_parser = sub.add_parser("articleize")
    article_parser.add_argument("--input", type=Path, required=True)
    article_parser.add_argument("--posts-dir", type=Path, required=True)
    article_parser.add_argument("--chunk-size", type=int, default=1000)
    article_parser.add_argument("--workers", type=int, default=0)
    article_parser.add_argument("--target-success", type=int, default=0)
    article_parser.add_argument("--random-sample", type=int, default=0)
    article_parser.add_argument("--seed", type=int, default=20260925)
    article_parser.add_argument("--report", type=Path)
    article_parser.set_defaults(func=articleize)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--posts-dir", type=Path, required=True)
    verify_parser.add_argument("--public-dir", type=Path)
    verify_parser.add_argument("--expected", type=int, default=0)
    verify_parser.add_argument("--report", type=Path)
    verify_parser.set_defaults(func=verify)
    return root


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
