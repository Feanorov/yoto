from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import uuid

from .models import Offer, OfferHistory, OfferSource, PostKind, QueueItem


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(slots=True)
class Database:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def transaction(self) -> sqlite3.Connection:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS offer_history (
                    source TEXT NOT NULL,
                    offer_id TEXT NOT NULL,
                    last_posted_at TEXT,
                    last_discount_pct INTEGER,
                    last_final_price_uah REAL,
                    last_initial_price_uah REAL,
                    last_sale_end TEXT,
                    total_posts INTEGER NOT NULL DEFAULT 0,
                    final_day_alert_sent INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (source, offer_id)
                );

                CREATE TABLE IF NOT EXISTS queue_items (
                    queue_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    offer_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS post_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    offer_id TEXT NOT NULL,
                    post_kind TEXT NOT NULL,
                    posted_at TEXT NOT NULL,
                    discount_pct INTEGER,
                    final_price_uah REAL,
                    sale_end TEXT,
                    note TEXT,
                    message_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS daily_posts (
                    day_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    offer_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (day_key, kind)
                );
                """
            )

    def reset(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                DELETE FROM offer_history;
                DELETE FROM queue_items;
                DELETE FROM post_log;
                DELETE FROM daily_posts;
                """
            )

    def get_history(self, source: OfferSource, offer_id: str) -> OfferHistory | None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM offer_history
                WHERE source = ? AND offer_id = ?
                """,
                (source.value, offer_id),
            ).fetchone()
        if row is None:
            return None
        return OfferHistory(
            source=OfferSource(row["source"]),
            offer_id=row["offer_id"],
            last_posted_at=_dt(row["last_posted_at"]),
            last_discount_pct=row["last_discount_pct"],
            last_final_price_uah=row["last_final_price_uah"],
            last_initial_price_uah=row["last_initial_price_uah"],
            last_sale_end=_dt(row["last_sale_end"]),
            total_posts=row["total_posts"],
            final_day_alert_sent=bool(row["final_day_alert_sent"]),
        )

    def save_queue(self, offers: list[tuple[float, Offer]]) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM queue_items")
            created_at = datetime.utcnow().isoformat()
            for score, offer in offers:
                connection.execute(
                    """
                    INSERT INTO queue_items (
                        queue_id, source, offer_id, score, created_at, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        offer.source.value,
                        offer.offer_id,
                        score,
                        created_at,
                        json.dumps(offer.to_json_dict(), ensure_ascii=False),
                    ),
                )

    def list_queue(self) -> list[QueueItem]:
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM queue_items
                ORDER BY score DESC, created_at ASC
                """
            ).fetchall()
        return [
            QueueItem(
                queue_id=row["queue_id"],
                score=row["score"],
                created_at=datetime.fromisoformat(row["created_at"]),
                offer=Offer.from_json_dict(json.loads(row["payload_json"])),
            )
            for row in rows
        ]

    def pop_next_queue_item(self) -> QueueItem | None:
        items = self.list_queue()
        if not items:
            return None
        item = items[0]
        with self.transaction() as connection:
            connection.execute("DELETE FROM queue_items WHERE queue_id = ?", (item.queue_id,))
        return item

    def was_daily_posted(self, day_key: str, kind: PostKind) -> bool:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM daily_posts WHERE day_key = ? AND kind = ?",
                (day_key, kind.value),
            ).fetchone()
        return row is not None

    def mark_daily_post(self, day_key: str, kind: PostKind, offer: Offer) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO daily_posts (day_key, kind, source, offer_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (day_key, kind.value, offer.source.value, offer.offer_id, datetime.utcnow().isoformat()),
            )

    def record_post(
        self,
        offer: Offer,
        message_id: int | None,
        note: str | None = None,
        final_day_alert_sent: bool | None = None,
    ) -> None:
        now_iso = datetime.utcnow().isoformat()
        history = self.get_history(offer.source, offer.offer_id)
        total_posts = 1 if history is None else history.total_posts + 1
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO post_log (
                    source, offer_id, post_kind, posted_at, discount_pct, final_price_uah, sale_end, note, message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    offer.source.value,
                    offer.offer_id,
                    offer.post_kind.value,
                    now_iso,
                    offer.discount_pct,
                    offer.final_price_uah,
                    offer.sale_end.isoformat() if offer.sale_end else None,
                    note,
                    message_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO offer_history (
                    source, offer_id, last_posted_at, last_discount_pct, last_final_price_uah,
                    last_initial_price_uah, last_sale_end, total_posts, final_day_alert_sent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, offer_id) DO UPDATE SET
                    last_posted_at = excluded.last_posted_at,
                    last_discount_pct = excluded.last_discount_pct,
                    last_final_price_uah = excluded.last_final_price_uah,
                    last_initial_price_uah = excluded.last_initial_price_uah,
                    last_sale_end = excluded.last_sale_end,
                    total_posts = excluded.total_posts,
                    final_day_alert_sent = excluded.final_day_alert_sent
                """,
                (
                    offer.source.value,
                    offer.offer_id,
                    now_iso,
                    offer.discount_pct,
                    offer.final_price_uah,
                    offer.original_price_uah,
                    offer.sale_end.isoformat() if offer.sale_end else None,
                    total_posts,
                    int(final_day_alert_sent if final_day_alert_sent is not None else (history.final_day_alert_sent if history else False)),
                ),
            )
