from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    channel_username: str
    timezone: str
    min_interval_minutes: int
    max_interval_minutes: int
    queue_target_size: int
    steam_scan_limit: int
    steam_enrich_limit: int
    min_free_review_percent: int
    http_timeout_seconds: int
    db_path: Path
    card_output_dir: Path
    calendar_events_path: Path

    @classmethod
    def from_env(cls, root_dir: Path) -> "Settings":
        load_dotenv(root_dir / ".env")
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        channel_username = os.getenv("CHANNEL_USERNAME", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN is not configured.")
        if not channel_username:
            raise RuntimeError("CHANNEL_USERNAME is not configured.")

        min_interval = int(os.getenv("MIN_INTERVAL_MINUTES", "20"))
        max_interval = int(os.getenv("MAX_INTERVAL_MINUTES", "90"))
        if min_interval < 5:
            raise RuntimeError("MIN_INTERVAL_MINUTES must be >= 5.")
        if max_interval < min_interval:
            raise RuntimeError("MAX_INTERVAL_MINUTES must be >= MIN_INTERVAL_MINUTES.")

        return cls(
            bot_token=bot_token,
            channel_username=channel_username,
            timezone=os.getenv("TIMEZONE", "Europe/Kyiv"),
            min_interval_minutes=min_interval,
            max_interval_minutes=max_interval,
            queue_target_size=max(1, int(os.getenv("QUEUE_TARGET_SIZE", "3"))),
            steam_scan_limit=max(100, int(os.getenv("STEAM_SCAN_LIMIT", "2000"))),
            steam_enrich_limit=max(10, int(os.getenv("STEAM_ENRICH_LIMIT", "40"))),
            min_free_review_percent=max(0, int(os.getenv("MIN_FREE_REVIEW_PERCENT", "65"))),
            http_timeout_seconds=max(5, int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))),
            db_path=root_dir / os.getenv("DB_PATH", "data/dealbot.sqlite3"),
            card_output_dir=root_dir / os.getenv("CARD_OUTPUT_DIR", "output/cards"),
            calendar_events_path=root_dir / "data/calendar_events.json",
        )
