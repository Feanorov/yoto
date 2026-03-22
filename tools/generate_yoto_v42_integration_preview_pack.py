from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.entities.offer import AssetBundle, Offer, OfferKind, OfferSource
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter


OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
EVENT_MANIFEST_PATH = REPO_ROOT / 'output' / 'video_manifests' / '20260310T231720Z_video_manifest_event_category_tower_defense.json'


@dataclass(slots=True)
class PreviewCase:
    slug: str
    label: str
    offer: Offer
    template_id: str
    notes: list[str]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_queue_offers() -> dict[str, tuple[Offer, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT offer_json, decision_json FROM queue_items ORDER BY score DESC").fetchall()
    offers: dict[str, tuple[Offer, str]] = {}
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        offers[offer.title] = (offer, str(decision.get('template_id') or 'steam_discount'))
    return offers


def _load_post_artifact_offers() -> dict[str, tuple[Offer, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT artifact_json FROM post_artifacts ORDER BY rowid DESC").fetchall()
    offers: dict[str, tuple[Offer, str]] = {}
    for row in rows:
        payload = json.loads(row['artifact_json'])
        offer_payload = (payload.get('render_inputs') or {}).get('offer') or {}
        decision = (payload.get('render_inputs') or {}).get('decision') or {}
        if not offer_payload:
            continue
        offer = Offer.from_snapshot(offer_payload)
        offers.setdefault(offer.title, (offer, str(decision.get('template_id') or 'epic_free')))
    return offers


def _load_event_offer() -> tuple[Offer, str]:
    payload = json.loads(EVENT_MANIFEST_PATH.read_text(encoding='utf-8'))
    title = payload.get('short_title') or 'Steam Tower Defense Fest is on now!'
    urgency_line = payload.get('urgency_line') or ''
    promo_end = None
    marker = 'Ends '
    if urgency_line.startswith(marker):
        raw = urgency_line[len(marker):].replace(' UTC.', '').replace(' UTC', '')
        promo_end = datetime.fromisoformat(raw)
    asset_refs = list(payload.get('asset_refs') or [])
    asset = asset_refs[0] if asset_refs else None
    offer = Offer(
        offer_id=str(payload.get('offer_id') or 'event:category:tower_defense'),
        source=OfferSource.EVENT,
        source_ref='event:category:tower_defense',
        offer_kind=OfferKind.FESTIVAL,
        game_id='event:category:tower_defense',
        franchise_key='tower_defense_fest',
        title=title,
        store_url='https://store.steampowered.com/category/tower_defense/',
        price_before_minor=None,
        price_after_minor=None,
        currency='UAH',
        discount_percent=0,
        promo_start=None,
        promo_end=promo_end,
        review_score=None,
        review_count=None,
        achievements_count=None,
        has_trading_cards=False,
        assets=AssetBundle(hero=asset, header=asset, screenshot=asset, fallback=None),
        short_description=payload.get('summary_line') or '',
        description=payload.get('hook_line') or '',
    )
    return offer, 'festival_event'


def _require(mapping: dict[str, tuple[Offer, str]], title: str) -> tuple[Offer, str]:
    if title not in mapping:
        raise RuntimeError(f'Missing offer snapshot for {title}')
    return mapping[title]


def build_cases() -> list[PreviewCase]:
    queue_offers = _load_queue_offers()
    artifact_offers = _load_post_artifact_offers()
    cases: list[PreviewCase] = []

    turnip, turnip_template = _require(artifact_offers, 'Turnip Boy Robs a Bank')
    idle, idle_template = _require(artifact_offers, 'Idle Champions of the Forgotten Realms')
    cities, cities_template = _require(queue_offers, 'Cities: Skylines')
    black_desert, black_desert_template = _require(queue_offers, 'Black Desert')
    far_cry, far_cry_template = _require(queue_offers, 'Far Cry® 5')
    motorfest, motorfest_template = _require(queue_offers, 'The Crew Motorfest')
    slay, slay_template = _require(queue_offers, 'Slay the Spire')
    dead_space, dead_space_template = _require(queue_offers, 'Dead Space')
    deep_rock, deep_rock_template = _require(queue_offers, 'Deep Rock Galactic')
    danganronpa, danganronpa_template = _require(queue_offers, 'Danganronpa V3: Killing Harmony')
    event_offer, event_template = _load_event_offer()

    cases.extend(
        [
            PreviewCase('epic_turnip_boy', 'Epic Freebie / Turnip Boy', turnip, turnip_template, ['real', 'epic freebie']),
            PreviewCase('epic_idle_champions_long_title', 'Epic Freebie / Idle Champions', idle, idle_template, ['real', 'long title']),
            PreviewCase('steam_cities_skylines', 'Steam Discount / Cities: Skylines', cities, cities_template, ['real', 'steam discount']),
            PreviewCase('steam_black_desert', 'Steam Discount / Black Desert', black_desert, black_desert_template, ['real', 'steam discount']),
            PreviewCase('steam_far_cry_symbol_title', 'Steam Discount / Far Cry® 5', far_cry, far_cry_template, ['real', 'symbol-heavy title']),
            PreviewCase('steam_motorfest', 'Steam Discount / The Crew Motorfest', motorfest, motorfest_template, ['real', 'steam discount']),
            PreviewCase('steam_slay_the_spire', 'Steam Discount / Slay the Spire', slay, slay_template, ['real', 'steam discount']),
            PreviewCase('steam_dead_space', 'Steam Discount / Dead Space', dead_space, dead_space_template, ['real', 'steam discount']),
            PreviewCase('steam_deep_rock_galactic', 'Steam Discount / Deep Rock Galactic', deep_rock, deep_rock_template, ['real', 'steam discount']),
            PreviewCase('steam_danganronpa_v3', 'Steam Discount / Danganronpa V3', danganronpa, danganronpa_template, ['real', 'long title']),
            PreviewCase('event_tower_defense_fest', 'Festival / Tower Defense Fest', event_offer, event_template, ['real', 'festival event']),
            PreviewCase(
                'edge_cities_no_image',
                'Edge / Cities: Skylines (No Image)',
                replace(cities, assets=AssetBundle()),
                cities_template,
                ['edge', 'fallback no-image'],
            ),
            PreviewCase(
                'edge_motorfest_header_only',
                'Edge / The Crew Motorfest (Header Only)',
                replace(
                    motorfest,
                    assets=AssetBundle(
                        hero=None,
                        header=motorfest.assets.header or motorfest.assets.hero,
                        screenshot=None,
                        fallback=None,
                    ),
                ),
                motorfest_template,
                ['edge', 'sparse header-only asset'],
            ),
        ]
    )
    return cases


def _pair_image(case_label: str, legacy_path: Path, yoto_path: Path, output_path: Path) -> None:
    with Image.open(legacy_path) as legacy_image, Image.open(yoto_path) as yoto_image:
        legacy = legacy_image.convert('RGB')
        yoto = yoto_image.convert('RGB')
    canvas = Image.new('RGB', (2640, 860), '#091019')
    draw = ImageDraw.Draw(canvas)
    title_font = _font(34)
    label_font = _font(22)
    small_font = _font(16)
    draw.text((42, 26), case_label, fill='white', font=title_font)
    draw.text((54, 90), 'Legacy', fill='#aebdcc', font=label_font)
    draw.text((1330, 90), 'YOTO V4.2', fill='#aebdcc', font=label_font)
    canvas.paste(legacy, (40, 130))
    canvas.paste(yoto, (1320, 130))
    draw.text((40, 780), legacy_path.name, fill='#8091a3', font=small_font)
    draw.text((1320, 780), yoto_path.name, fill='#8091a3', font=small_font)
    canvas.save(output_path)


def _contact_sheet(items: list[tuple[str, Path]], output_path: Path) -> None:
    thumb_size = (420, 136)
    cols = 2
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 470, rows * 206 + 36), '#091019')
    draw = ImageDraw.Draw(sheet)
    label_font = _font(20)
    small_font = _font(14)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        col = index % cols
        row = index // cols
        x = 24 + col * 470
        y = 20 + row * 206
        sheet.paste(thumb, (x, y))
        draw.text((x, y + 144), label, fill='white', font=label_font)
        draw.text((x, y + 170), image_path.name, fill='#8fa0b3', font=small_font)
    sheet.save(output_path)


async def render_preview_pack() -> Path:
    run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    preview_root = OUTPUT_ROOT / f'preview_yoto_v42_integration_{run_key}'
    legacy_dir = preview_root / 'legacy'
    yoto_dir = preview_root / 'yoto_v42'
    pairs_dir = preview_root / 'pairs'
    cache_dir = preview_root / 'asset_cache'
    manifest_path = preview_root / 'comparison_manifest.json'
    contact_sheet_path = preview_root / 'comparison_contact_sheet.png'
    for directory in (legacy_dir, yoto_dir, pairs_dir, cache_dir):
        directory.mkdir(parents=True, exist_ok=True)

    legacy_renderer = CardRendererRouter(legacy_dir, renderer_mode='legacy', fallback_to_legacy=True, cache_dir=cache_dir)
    yoto_renderer = CardRendererRouter(yoto_dir, renderer_mode='yoto_v42', fallback_to_legacy=False, cache_dir=cache_dir)
    cases = build_cases()
    results: list[dict[str, object]] = []
    contact_inputs: list[tuple[str, Path]] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        http = ResilientHttpClient(client)
        for case in cases:
            legacy_result = await legacy_renderer.render(http, case.offer, case.template_id)
            yoto_result = await yoto_renderer.render(http, case.offer, case.template_id)
            pair_path = pairs_dir / f'{case.slug}_comparison.png'
            _pair_image(case.label, legacy_result.image_path, yoto_result.image_path, pair_path)
            contact_inputs.append((case.label, pair_path))
            results.append(
                {
                    'slug': case.slug,
                    'label': case.label,
                    'notes': case.notes,
                    'template_id': case.template_id,
                    'offer_id': case.offer.offer_id,
                    'legacy_image_path': str(legacy_result.image_path),
                    'legacy_diagnostics': legacy_result.diagnostics.to_snapshot(),
                    'yoto_image_path': str(yoto_result.image_path),
                    'yoto_diagnostics': yoto_result.diagnostics.to_snapshot(),
                    'pair_image_path': str(pair_path),
                }
            )

    _contact_sheet(contact_inputs, contact_sheet_path)
    manifest = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'preview_root': str(preview_root),
        'legacy_dir': str(legacy_dir),
        'yoto_dir': str(yoto_dir),
        'pairs_dir': str(pairs_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'case_count': len(results),
        'cases': results,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return preview_root


def main() -> None:
    preview_root = asyncio.run(render_preview_pack())
    print(preview_root)


if __name__ == '__main__':
    main()
