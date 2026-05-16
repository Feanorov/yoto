from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import sys

from dotenv import dotenv_values


class ConfigurationError(RuntimeError):
    """Raised when required operator configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class BootstrapDiagnostics:
    python_executable: Path
    project_root: Path
    env_path: Path
    env_found: bool
    env_loaded: bool
    bot_token_line_found: bool
    channel_username_line_found: bool
    bot_token_present: bool
    channel_username_present: bool


@dataclass(frozen=True, slots=True)
class StaticConfig:
    caption_limit: int = 1024
    http_timeout_seconds: int = 30
    steam_scan_limit: int = 2000
    steam_enrich_limit: int = 40
    planned_queue_size: int = 6
    reserve_queue_size: int = 18


@dataclass(frozen=True, slots=True)
class EditorialConfig:
    min_review_count: int = 50
    min_game_of_the_day_score: int = 65
    cooldown_game_days: int = 30
    franchise_cooldown_hours: int = 36
    min_price_drop_minor: int = 1000
    min_discount_delta: int = 10
    publisher_whitelist: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class SteamAccessConfig:
    cache_root: Path
    appdetails_ttl_hours: int
    reviews_ttl_hours: int
    deadlines_ttl_hours: int
    search_page_size: int
    max_concurrent_requests: int
    pacing_delay_ms: int
    adaptive_slowdown_step: float
    adaptive_slowdown_max: float
    degraded_threshold: int
    degraded_cooldown_seconds: int


@dataclass(frozen=True, slots=True)
class EditorialControlConfig:
    control_dir: Path
    whitelist_priority_boost: float


@dataclass(frozen=True, slots=True)
class EventIngestionConfig:
    enabled: bool
    lookback_days: int
    max_posts: int


@dataclass(frozen=True, slots=True)
class OperationalConfig:
    timezone: str
    min_interval_minutes: int
    max_interval_minutes: int
    dry_run: bool
    freeze_publish: bool
    sale_event_mode: str
    degraded_sources: frozenset[str]


@dataclass(frozen=True, slots=True)
class RenderingConfig:
    card_renderer: str
    fallback_to_legacy: bool
    image_provider_mode: str
    image_pipeline_version: str
    comfyui_enabled: bool = False
    comfyui_url: str = 'http://127.0.0.1:8188'
    comfyui_checkpoint: str = 'auto'


def resolve_project_root(root_dir: Path) -> Path:
    return Path(root_dir).resolve()


def _read_dotenv_values(env_path: Path) -> dict[str, str]:
    parsed = dotenv_values(dotenv_path=env_path, encoding='utf-8-sig')
    normalized: dict[str, str] = {}
    for raw_key, raw_value in parsed.items():
        if raw_key is None:
            continue
        key = str(raw_key).lstrip('\ufeff').strip()
        if not key:
            continue
        normalized[key] = '' if raw_value is None else str(raw_value)
    return normalized


def _apply_dotenv_values(values: dict[str, str], *, override: bool) -> None:
    for key, value in values.items():
        existing = os.environ.get(key)
        if override or existing is None or not str(existing).strip():
            os.environ[key] = value


def load_project_env(root_dir: Path, *, override: bool = False) -> BootstrapDiagnostics:
    project_root = resolve_project_root(root_dir)
    env_path = project_root / '.env'
    env_found = env_path.is_file()
    env_loaded = False
    parsed_values: dict[str, str] = {}
    if env_found:
        parsed_values = _read_dotenv_values(env_path)
        _apply_dotenv_values(parsed_values, override=override)
        env_loaded = True
    return BootstrapDiagnostics(
        python_executable=Path(sys.executable).resolve(),
        project_root=project_root,
        env_path=env_path,
        env_found=env_found,
        env_loaded=env_loaded,
        bot_token_line_found='BOT_TOKEN' in parsed_values,
        channel_username_line_found='CHANNEL_USERNAME' in parsed_values,
        bot_token_present=bool(os.getenv('BOT_TOKEN', '').strip()),
        channel_username_present=bool(os.getenv('CHANNEL_USERNAME', '').strip()),
    )


def render_bootstrap_diagnostics(bootstrap: BootstrapDiagnostics) -> list[str]:
    return [
        f'bootstrap :: python_executable={bootstrap.python_executable}',
        f'bootstrap :: project_root={bootstrap.project_root}',
        (
            f'bootstrap :: env_path={bootstrap.env_path} '
            f':: found={"yes" if bootstrap.env_found else "no"} '
            f':: loaded={"yes" if bootstrap.env_loaded else "no"}'
        ),
        (
            'bootstrap :: '
            f'BOT_TOKEN present={"yes" if bootstrap.bot_token_present else "no"} '
            f':: CHANNEL_USERNAME present={"yes" if bootstrap.channel_username_present else "no"}'
        ),
    ]


def _format_missing_required_env_message(
    missing_names: list[str],
    bootstrap: BootstrapDiagnostics,
) -> str:
    missing = ', '.join(missing_names)
    return (
        f'Missing required environment variable(s): {missing}. '
        f'Checked .env path: {bootstrap.env_path} '
        f'(found={"yes" if bootstrap.env_found else "no"}, '
        f'loaded={"yes" if bootstrap.env_loaded else "no"}). '
        'Secret values are not printed.'
    )


def load_rendering_config(root_dir: Path, *, load_env: bool = True) -> RenderingConfig:
    resolved_root = resolve_project_root(root_dir)
    if load_env:
        bootstrap = load_project_env(resolved_root)
        resolved_root = bootstrap.project_root
    rendering = RenderingConfig(
        card_renderer=os.getenv('CARD_RENDERER_MODE', 'yoto_v4').strip().lower() or 'yoto_v4',
        fallback_to_legacy=os.getenv('CARD_RENDERER_FALLBACK_TO_LEGACY', '1').strip() != '0',
        image_provider_mode=os.getenv('IMAGE_PROVIDER_MODE', 'ai_first').strip().lower() or 'ai_first',
        image_pipeline_version=os.getenv('IMAGE_PIPELINE_VERSION', 'v1').strip() or 'v1',
        comfyui_enabled=os.getenv('COMFYUI_ENABLED', '1').strip() == '1',
        comfyui_url=os.getenv('COMFYUI_URL', 'http://127.0.0.1:8188').strip() or 'http://127.0.0.1:8188',
        comfyui_checkpoint=os.getenv('COMFYUI_CHECKPOINT', 'auto').strip() or 'auto',
    )
    os.environ['IMAGE_PROVIDER_MODE'] = rendering.image_provider_mode
    os.environ['IMAGE_PIPELINE_VERSION'] = rendering.image_pipeline_version
    os.environ['COMFYUI_ENABLED'] = '1' if rendering.comfyui_enabled else '0'
    os.environ['COMFYUI_URL'] = rendering.comfyui_url
    os.environ['COMFYUI_CHECKPOINT'] = rendering.comfyui_checkpoint
    return rendering


@dataclass(frozen=True, slots=True)
class AppSettings:
    bot_token: str
    channel_username: str
    db_path: Path
    card_output_dir: Path
    analytics_output_dir: Path
    video_manifest_output_dir: Path
    calendar_events_path: Path
    static: StaticConfig
    editorial: EditorialConfig
    steam_access: SteamAccessConfig
    editorial_control: EditorialControlConfig
    event_ingestion: EventIngestionConfig
    operational: OperationalConfig
    rendering: RenderingConfig

    @classmethod
    def from_env(cls, root_dir: Path) -> 'AppSettings':
        bootstrap = load_project_env(root_dir)
        root_dir = bootstrap.project_root
        rendering = load_rendering_config(root_dir, load_env=False)
        bot_token = os.getenv('BOT_TOKEN', '').strip()
        channel_username = os.getenv('CHANNEL_USERNAME', '').strip()
        missing_names = []
        if not bot_token:
            missing_names.append('BOT_TOKEN')
        if not channel_username:
            missing_names.append('CHANNEL_USERNAME')
        if missing_names:
            raise ConfigurationError(_format_missing_required_env_message(missing_names, bootstrap))

        whitelist = frozenset(item.strip().lower() for item in os.getenv('PUBLISHER_WHITELIST', '').split(',') if item.strip())
        degraded = frozenset(item.strip().lower() for item in os.getenv('DEGRADED_SOURCES', '').split(',') if item.strip())

        return cls(
            bot_token=bot_token,
            channel_username=channel_username,
            db_path=root_dir / os.getenv('DB_PATH', 'data/dealbot.sqlite3'),
            card_output_dir=root_dir / os.getenv('CARD_OUTPUT_DIR', 'output/cards'),
            analytics_output_dir=root_dir / os.getenv('ANALYTICS_OUTPUT_DIR', 'output/analytics'),
            video_manifest_output_dir=root_dir / os.getenv('VIDEO_MANIFEST_OUTPUT_DIR', 'output/video_manifests'),
            calendar_events_path=root_dir / os.getenv('CALENDAR_EVENTS_PATH', 'data/calendar_events.json'),
            static=StaticConfig(
                caption_limit=int(os.getenv('CAPTION_LIMIT', '1024')),
                http_timeout_seconds=int(os.getenv('HTTP_TIMEOUT_SECONDS', '30')),
                steam_scan_limit=int(os.getenv('STEAM_SCAN_LIMIT', '2000')),
                steam_enrich_limit=int(os.getenv('STEAM_ENRICH_LIMIT', '40')),
                planned_queue_size=int(os.getenv('PLANNED_QUEUE_SIZE', '6')),
                reserve_queue_size=int(os.getenv('RESERVE_QUEUE_SIZE', '18')),
            ),
            editorial=EditorialConfig(
                min_review_count=int(os.getenv('MIN_REVIEW_COUNT', '50')),
                min_game_of_the_day_score=int(os.getenv('MIN_GAME_OF_THE_DAY_SCORE', '65')),
                cooldown_game_days=int(os.getenv('COOLDOWN_GAME_DAYS', '30')),
                franchise_cooldown_hours=int(os.getenv('FRANCHISE_COOLDOWN_HOURS', '36')),
                min_price_drop_minor=int(os.getenv('MIN_PRICE_DROP_MINOR', '1000')),
                min_discount_delta=int(os.getenv('MIN_DISCOUNT_DELTA', '10')),
                publisher_whitelist=whitelist,
            ),
            steam_access=SteamAccessConfig(
                cache_root=root_dir / os.getenv('STEAM_CACHE_ROOT', 'data/steam_cache'),
                appdetails_ttl_hours=int(os.getenv('STEAM_APPDETAILS_TTL_HOURS', '24')),
                reviews_ttl_hours=int(os.getenv('STEAM_REVIEWS_TTL_HOURS', '12')),
                deadlines_ttl_hours=int(os.getenv('STEAM_DEADLINES_TTL_HOURS', '6')),
                search_page_size=int(os.getenv('STEAM_SEARCH_PAGE_SIZE', '100')),
                max_concurrent_requests=int(os.getenv('STEAM_MAX_CONCURRENT', '2')),
                pacing_delay_ms=int(os.getenv('STEAM_PACING_DELAY_MS', '350')),
                adaptive_slowdown_step=float(os.getenv('STEAM_ADAPTIVE_SLOWDOWN_STEP', '1.75')),
                adaptive_slowdown_max=float(os.getenv('STEAM_ADAPTIVE_SLOWDOWN_MAX', '8.0')),
                degraded_threshold=int(os.getenv('STEAM_DEGRADED_THRESHOLD', '3')),
                degraded_cooldown_seconds=int(os.getenv('STEAM_DEGRADED_COOLDOWN_SECONDS', '900')),
            ),
            editorial_control=EditorialControlConfig(
                control_dir=root_dir / os.getenv('EDITORIAL_CONTROL_DIR', 'data/editorial_control'),
                whitelist_priority_boost=float(os.getenv('WHITELIST_PRIORITY_BOOST', '24')),
            ),
            event_ingestion=EventIngestionConfig(
                enabled=os.getenv('AUTO_EVENTS_ENABLED', '1').strip() == '1',
                lookback_days=int(os.getenv('AUTO_EVENT_LOOKBACK_DAYS', '45')),
                max_posts=int(os.getenv('AUTO_EVENT_MAX_POSTS', '40')),
            ),
            operational=OperationalConfig(
                timezone=os.getenv('TIMEZONE', 'Europe/Kyiv'),
                min_interval_minutes=int(os.getenv('MIN_INTERVAL_MINUTES', '20')),
                max_interval_minutes=int(os.getenv('MAX_INTERVAL_MINUTES', '90')),
                dry_run=os.getenv('DRY_RUN', '0').strip() == '1',
                freeze_publish=os.getenv('FREEZE_PUBLISH', '0').strip() == '1',
                sale_event_mode=os.getenv('SALE_EVENT_MODE', 'auto').strip().lower(),
                degraded_sources=degraded,
            ),
            rendering=rendering,
        )
