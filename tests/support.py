from __future__ import annotations

from pathlib import Path

from dealbot.settings import (
    AppSettings,
    EditorialConfig,
    EditorialControlConfig,
    EventIngestionConfig,
    OperationalConfig,
    RenderingConfig,
    StaticConfig,
    SteamAccessConfig,
)


def make_test_settings(
    tmp_path: Path,
    *,
    static: StaticConfig | None = None,
    editorial: EditorialConfig | None = None,
    dry_run: bool = False,
    freeze_publish: bool = False,
    sale_event_mode: str = 'auto',
    degraded_sources: frozenset[str] = frozenset(),
) -> AppSettings:
    return AppSettings(
        bot_token='token',
        channel_username='@channel',
        db_path=tmp_path / 'repo.sqlite3',
        card_output_dir=tmp_path / 'cards',
        analytics_output_dir=tmp_path / 'analytics',
        video_manifest_output_dir=tmp_path / 'video_manifests',
        calendar_events_path=tmp_path / 'calendar.json',
        static=static or StaticConfig(),
        editorial=editorial or EditorialConfig(),
        steam_access=SteamAccessConfig(
            cache_root=tmp_path / 'steam_cache',
            appdetails_ttl_hours=24,
            reviews_ttl_hours=12,
            deadlines_ttl_hours=6,
            search_page_size=100,
            max_concurrent_requests=1,
            pacing_delay_ms=1,
            adaptive_slowdown_step=1.5,
            adaptive_slowdown_max=4.0,
            degraded_threshold=2,
            degraded_cooldown_seconds=60,
        ),
        editorial_control=EditorialControlConfig(
            control_dir=tmp_path / 'editorial_control',
            whitelist_priority_boost=20.0,
        ),
        event_ingestion=EventIngestionConfig(
            enabled=True,
            lookback_days=45,
            max_posts=40,
        ),
        operational=OperationalConfig(
            timezone='Europe/Kyiv',
            min_interval_minutes=20,
            max_interval_minutes=90,
            dry_run=dry_run,
            freeze_publish=freeze_publish,
            sale_event_mode=sale_event_mode,
            degraded_sources=degraded_sources,
        ),
        rendering=RenderingConfig(
            card_renderer='legacy',
            fallback_to_legacy=True,
            image_provider_mode='ai_first',
            image_pipeline_version='v1',
        ),
    )
