from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response


WEBHOOK_PATH = "/webhooks/toss-sharelink/orders"
SUPPORTED_EVENT_TYPES = frozenset({"PURCHASE", "CANCEL", "CONFIRM"})
MAX_BODY_BYTES = 1_000_000
SIGNATURE_TOLERANCE_SECONDS = 5 * 60

app = FastAPI(title="BriefWave Toss ShareLink webhook", docs_url=None, redoc_url=None)


def verify_signature(
    body: bytes,
    transmission_time: str | None,
    signature: str | None,
    secret: str,
    *,
    now: datetime | None = None,
) -> bool:
    if not transmission_time or not signature or not signature.startswith("v1:") or not secret:
        return False
    try:
        sent_at = datetime.fromisoformat(transmission_time.replace("Z", "+00:00"))
        if sent_at.tzinfo is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if abs((current.astimezone(timezone.utc) - sent_at.astimezone(timezone.utc)).total_seconds()) > SIGNATURE_TOLERANCE_SECONDS:
            return False
        received = base64.b64decode(signature[3:], validate=True)
    except (ValueError, binascii.Error):
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        body + b":" + transmission_time.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(received, expected)


def _database_path() -> Path:
    return Path(os.getenv("TOSS_WEBHOOK_DB_PATH", "state/toss_order_events.sqlite3"))


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 3000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS toss_order_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            order_id TEXT NOT NULL,
            order_product_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            occurred_at TEXT,
            recorded_at TEXT,
            received_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS toss_order_products (
            order_product_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            product_id TEXT,
            product_name TEXT,
            state TEXT NOT NULL,
            latest_event_id TEXT NOT NULL,
            latest_occurred_at TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    return connection


def _required_string(event: dict[str, Any], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _next_state(current: str | None, event_type: str) -> str:
    if event_type == "CANCEL":
        return "CANCELED"
    if current == "CANCELED":
        return current
    if event_type == "CONFIRM":
        return "CONFIRMED"
    if current == "CONFIRMED":
        return current
    if event_type == "PURCHASE":
        return "PURCHASED"
    return current or "UNKNOWN"


def save_event(event: dict[str, Any], database_path: Path | None = None) -> bool:
    event_id = _required_string(event, "eventId")
    event_type = _required_string(event, "eventType").upper()
    order_id = _required_string(event, "orderId")
    order_product_id = _required_string(event, "orderProductId")
    received_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))

    with closing(_connect(database_path or _database_path())) as connection:
        with connection:
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO toss_order_events
                    (event_id, event_type, order_id, order_product_id, payload_json,
                     occurred_at, recorded_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    order_id,
                    order_product_id,
                    payload,
                    event.get("occurredAt"),
                    event.get("recordedAt"),
                    received_at,
                ),
            ).rowcount
            if not inserted:
                return False

            existing = connection.execute(
                "SELECT state FROM toss_order_products WHERE order_product_id = ?",
                (order_product_id,),
            ).fetchone()
            state = _next_state(existing["state"] if existing else None, event_type)
            connection.execute(
                """
                INSERT INTO toss_order_products
                    (order_product_id, order_id, product_id, product_name, state,
                     latest_event_id, latest_occurred_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_product_id) DO UPDATE SET
                    order_id = excluded.order_id,
                    product_id = excluded.product_id,
                    product_name = excluded.product_name,
                    state = excluded.state,
                    latest_event_id = excluded.latest_event_id,
                    latest_occurred_at = excluded.latest_occurred_at,
                    updated_at = excluded.updated_at
                """,
                (
                    order_product_id,
                    order_id,
                    event.get("productId"),
                    event.get("productName"),
                    state,
                    event_id,
                    event.get("occurredAt"),
                    received_at,
                ),
            )
    return True


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(WEBHOOK_PATH, include_in_schema=False)
async def receive_toss_order_event(request: Request) -> Response:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="application/json required")

    body = await request.body()
    if not body or len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=400, detail="invalid request body")

    secret = os.getenv("TOSS_SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=503, detail="webhook secret is not configured")
    if not verify_signature(
        body,
        request.headers.get("sharelink-webhook-transmission-time"),
        request.headers.get("sharelink-webhook-signature"),
        secret,
    ):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("event body must be an object")
        save_event(event)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="event storage unavailable") from exc

    # Unknown future event types are persisted as UNKNOWN instead of causing a 5xx.
    return Response(status_code=204)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "blog_agent.toss_webhook:app",
        host=os.getenv("TOSS_WEBHOOK_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
