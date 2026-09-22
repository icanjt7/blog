from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from blog_agent.toss_webhook import WEBHOOK_PATH, app, save_event, verify_signature


class TossWebhookTest(unittest.TestCase):
    @staticmethod
    def _signed_headers(body: bytes, secret: str, transmission_time: str) -> dict[str, str]:
        digest = hmac.new(
            secret.encode(), body + b":" + transmission_time.encode(), hashlib.sha256
        ).digest()
        return {
            "content-type": "application/json",
            "sharelink-webhook-transmission-time": transmission_time,
            "sharelink-webhook-signature": "v1:" + base64.b64encode(digest).decode(),
        }

    def test_signature_uses_raw_body_and_transmission_time(self) -> None:
        body = b'{"eventId":"event-1"}'
        secret = "test-secret"
        now = datetime.now(timezone.utc)
        transmission_time = now.isoformat()
        digest = hmac.new(
            secret.encode(), body + b":" + transmission_time.encode(), hashlib.sha256
        ).digest()
        signature = "v1:" + base64.b64encode(digest).decode()

        self.assertTrue(verify_signature(body, transmission_time, signature, secret, now=now))
        self.assertFalse(verify_signature(body + b" ", transmission_time, signature, secret, now=now))
        self.assertFalse(
            verify_signature(
                body,
                transmission_time,
                signature,
                secret,
                now=now + timedelta(minutes=6),
            )
        )

    def test_confirm_is_stored_and_duplicate_is_ignored(self) -> None:
        event = {
            "eventId": "confirm-1",
            "eventType": "CONFIRM",
            "orderId": "order-1",
            "orderProductId": "order-product-1",
            "productId": "product-1",
            "productName": "확정 상품",
            "occurredAt": "2026-09-22T10:00:00+09:00",
            "recordedAt": "2026-09-22T10:00:01+09:00",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.sqlite3"
            self.assertTrue(save_event(event, path))
            self.assertFalse(save_event(event, path))
            with closing(sqlite3.connect(path)) as connection:
                event_count = connection.execute("SELECT COUNT(*) FROM toss_order_events").fetchone()[0]
                state = connection.execute(
                    "SELECT state FROM toss_order_products WHERE order_product_id = ?",
                    ("order-product-1",),
                ).fetchone()[0]

        self.assertEqual(event_count, 1)
        self.assertEqual(state, "CONFIRMED")

    def test_cancel_is_not_reverted_by_late_purchase_or_confirm(self) -> None:
        base = {"orderId": "order-1", "orderProductId": "item-1"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.sqlite3"
            for event_id, event_type in (
                ("cancel-1", "CANCEL"),
                ("purchase-1", "PURCHASE"),
                ("confirm-1", "CONFIRM"),
            ):
                save_event({**base, "eventId": event_id, "eventType": event_type}, path)
            with closing(sqlite3.connect(path)) as connection:
                state = connection.execute(
                    "SELECT state FROM toss_order_products WHERE order_product_id = 'item-1'"
                ).fetchone()[0]

        self.assertEqual(state, "CANCELED")

    def test_unknown_event_is_saved_without_crashing(self) -> None:
        event = {
            "eventId": "future-1",
            "eventType": "FUTURE_EVENT",
            "orderId": "order-1",
            "orderProductId": "item-1",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.sqlite3"
            self.assertTrue(save_event(event, path))
            with closing(sqlite3.connect(path)) as connection:
                stored = json.loads(
                    connection.execute("SELECT payload_json FROM toss_order_events").fetchone()[0]
                )
        self.assertEqual(stored["eventType"], "FUTURE_EVENT")

    def test_endpoint_accepts_signed_confirm_and_rejects_bad_signature(self) -> None:
        secret = "endpoint-secret"
        body = json.dumps(
            {
                "eventId": "confirm-endpoint-1",
                "eventType": "CONFIRM",
                "orderId": "order-1",
                "orderProductId": "item-1",
            },
            separators=(",", ":"),
        ).encode()
        transmission_time = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {
                "TOSS_SECRET_KEY": secret,
                "TOSS_WEBHOOK_DB_PATH": str(Path(tmp) / "events.sqlite3"),
            },
        ):
            client = TestClient(app)
            response = client.post(
                WEBHOOK_PATH,
                content=body,
                headers=self._signed_headers(body, secret, transmission_time),
            )
            rejected = client.post(
                WEBHOOK_PATH,
                content=body,
                headers={
                    **self._signed_headers(body, secret, transmission_time),
                    "sharelink-webhook-signature": "v1:invalid",
                },
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(rejected.status_code, 401)


if __name__ == "__main__":
    unittest.main()
