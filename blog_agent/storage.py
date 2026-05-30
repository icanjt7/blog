from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Draft, PublishResult, Topic


class RunStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "runs.sqlite3"
        self._init_db()

    def new_run(self, count: int, dry_run: bool, publisher: str) -> str:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self._execute(
            "insert into runs(run_id, status, count, dry_run, publisher, started_at) values (?, ?, ?, ?, ?, ?)",
            (run_id, "running", count, int(dry_run), publisher, datetime.now().isoformat()),
        )
        return run_id

    def add_event(self, run_id: str, stage: str, status: str, payload: dict[str, Any] | None = None) -> None:
        self._execute(
            "insert into events(run_id, stage, status, payload, created_at) values (?, ?, ?, ?, ?)",
            (
                run_id,
                stage,
                status,
                json.dumps(payload or {}, ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )

    def add_draft(self, run_id: str, draft: Draft, result: PublishResult | None = None) -> None:
        self._execute(
            """
            insert into drafts(
                run_id, slug, title, keyword, category, quality_score,
                review_notes, publish_ok, publish_url, publish_message, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                draft.slug,
                draft.title,
                draft.topic.keyword,
                draft.topic.category,
                draft.quality_score,
                json.dumps(draft.review_notes, ensure_ascii=False),
                None if result is None else int(result.ok),
                None if result is None else result.url,
                None if result is None else result.message,
                datetime.now().isoformat(),
            ),
        )

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        self._execute(
            "update runs set status = ?, error = ?, finished_at = ? where run_id = ?",
            (status, error, datetime.now().isoformat(), run_id),
        )

    def latest_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                select r.*, count(d.slug) as draft_count,
                       sum(case when d.publish_ok = 1 then 1 else 0 end) as published_count
                from runs r
                left join drafts d on d.run_id = r.run_id
                group by r.run_id
                order by r.started_at desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def write_manifest(self, run_id: str, topics: list[Topic], drafts: list[Draft], results: list[PublishResult]) -> Path:
        path = self.state_dir / f"{run_id}.json"
        payload = {
            "run_id": run_id,
            "topics": [topic.model_dump(mode="json") for topic in topics],
            "drafts": [draft.model_dump(mode="json") for draft in drafts],
            "publish_results": [result.model_dump(mode="json") for result in results],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                create table if not exists runs (
                    run_id text primary key,
                    status text not null,
                    count integer not null,
                    dry_run integer not null,
                    publisher text not null,
                    started_at text not null,
                    finished_at text,
                    error text
                );

                create table if not exists events (
                    id integer primary key autoincrement,
                    run_id text not null,
                    stage text not null,
                    status text not null,
                    payload text not null,
                    created_at text not null
                );

                create table if not exists drafts (
                    id integer primary key autoincrement,
                    run_id text not null,
                    slug text not null,
                    title text not null,
                    keyword text not null,
                    category text not null,
                    quality_score real not null,
                    review_notes text not null,
                    publish_ok integer,
                    publish_url text,
                    publish_message text,
                    created_at text not null
                );
                """
            )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, params)
