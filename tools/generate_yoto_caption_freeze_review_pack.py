from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer, OfferKind, OfferSource
from domain.entities.roundup_post import RoundupItem, RoundupPost
from infrastructure.db.repositories import Repositories
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder, YotoVoiceEngine
from infrastructure.telegram.roundup_draft_builder import TelegramRoundupDraftBuilder
from tools.generate_yoto_v1_live_caption_validation import html_to_text


GOLDEN_DB_PATH = REPO_ROOT / 'output' / 'offline_validation' / 'golden' / 'current' / 'dealbot.sqlite3'
LIVE_DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
ROUNDUP_SNAPSHOT_PATH = REPO_ROOT / 'output' / 'analytics' / '20260319T011757Z_roundup_snapshot_roundups.json'
OUTPUT_ROOT = REPO_ROOT / 'output' / 'captions'
BASELINE_GLOB = 'caption_freeze_before_*'
REVIEW_PREFIX = 'caption_freeze_review_'
CAPTION_LIMIT = 1024
SIGNAL_PATTERNS = {
    'keep_forever_mentions': 'назавжди',
    'claim_verb_mentions': 'забрати',
    'claim_term_mentions': 'клейм',
    'wishlist_mentions': 'wishlist',
    'comment_bait_mentions': 'коментар',
    'shortlist_mentions': 'shortlist',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate a multi-family YOTO caption freeze review pack.')
    parser.add_argument('--before-manifest', type=Path, default=None, help='Explicit baseline manifest path.')
    return parser.parse_args()


def find_latest_baseline_manifest() -> Path:
    candidates = sorted(OUTPUT_ROOT.glob(f'{BASELINE_GLOB}/baseline_manifest.json'))
    if not candidates:
        raise FileNotFoundError('No caption freeze baseline manifest found under output/captions/.')
    return candidates[-1]


def make_asset_bundle() -> AssetBundle:
    return AssetBundle(
        hero='https://example.com/hero.png',
        header='https://example.com/header.png',
        screenshot='https://example.com/screenshot.png',
    )


def make_fixture_offer(
    *,
    offer_id: str,
    source: OfferSource,
    offer_kind: OfferKind,
    title: str,
    store_url: str,
    price_before_minor: int | None,
    price_after_minor: int | None,
    discount_percent: int,
    promo_end: datetime | None,
    short_description: str,
    description: str,
    tags: list[str],
    genres: list[str],
    review_score: int | None = None,
    review_count: int | None = None,
    achievements_count: int | None = None,
    has_trading_cards: bool = False,
) -> Offer:
    return Offer(
        offer_id=offer_id,
        source=source,
        source_ref=offer_id,
        offer_kind=offer_kind,
        game_id=offer_id,
        franchise_key=offer_id.replace(':', '-'),
        title=title,
        store_url=store_url,
        price_before_minor=price_before_minor,
        price_after_minor=price_after_minor,
        currency='UAH',
        discount_percent=discount_percent,
        promo_start=None,
        promo_end=promo_end,
        review_score=review_score,
        review_count=review_count,
        achievements_count=achievements_count,
        has_trading_cards=has_trading_cards,
        tags=list(tags),
        genres=list(genres),
        assets=make_asset_bundle(),
        confidence_levels=ConfidenceLevels(),
        description=description,
        short_description=short_description,
        publisher_name='Fixture Publisher',
    )


def load_golden_record(offer_id: str):
    repositories = Repositories(GOLDEN_DB_PATH)
    for record in repositories.list_queue('planned'):
        if record.offer.offer_id == offer_id:
            return record
    raise KeyError(f'Offer {offer_id} not found in golden planned queue.')


def load_archive_case(offer_id: str) -> tuple[Offer, dict[str, object]]:
    con = sqlite3.connect(LIVE_DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT artifact_json, lane FROM post_artifacts ORDER BY created_at DESC').fetchall()
    for row in rows:
        payload = json.loads(row['artifact_json'])
        render_inputs = payload.get('render_inputs') or {}
        offer_payload = render_inputs.get('offer') or {}
        if offer_payload.get('offer_id') != offer_id:
            continue
        decision_json = dict(render_inputs.get('decision') or {})
        if 'lane' not in decision_json:
            decision_json['lane'] = row['lane']
        if 'template_id' not in decision_json:
            decision_json['template_id'] = payload.get('template_id') or 'steam_discount'
        return Offer.from_snapshot(offer_payload), decision_json
    raise KeyError(f'Archive offer {offer_id} not found in live post_artifacts.')


def roundup_from_snapshot(snapshot: dict[str, object]) -> RoundupPost:
    items = [
        RoundupItem(
            rank=int(item['rank']),
            offer_id=str(item['offer_id']),
            title=str(item['title']),
            store_url=str(item['store_url']),
            store=str(item['store']),
            source=str(item['source']),
            lane=str(item['lane']),
            score=float(item['score']),
            discount_percent=int(item['discount_percent']),
            review_score=int(item['review_score']) if item.get('review_score') is not None else None,
            is_freebie=bool(item['is_freebie']),
            price_after_minor=int(item['price_after_minor']) if item.get('price_after_minor') is not None else None,
            price_line=str(item['price_line']),
            callout=str(item['callout']),
            summary_line=str(item['summary_line']),
            reason_tags=list(item.get('reason_tags') or []),
        )
        for item in snapshot.get('items') or []
    ]
    return RoundupPost(
        roundup_id=str(snapshot['roundup_id']),
        title=str(snapshot['title']),
        intro=str(snapshot.get('intro') or ''),
        group_type=str(snapshot['group_type']),
        theme_label=str(snapshot.get('theme_label') or ''),
        item_count=int(snapshot.get('item_count') or len(items)),
        items=items,
    )


def load_roundup_case(roundup_id: str) -> RoundupPost:
    payload = json.loads(ROUNDUP_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    for roundup in payload.get('roundups') or []:
        if roundup.get('roundup_id') == roundup_id:
            return roundup_from_snapshot(roundup)
    raise KeyError(f'Roundup {roundup_id} not found in snapshot file.')


def build_discount_long_title_case() -> tuple[Offer, dict[str, object]]:
    offer = make_fixture_offer(
        offer_id='fixture:discount-long-title',
        source=OfferSource.STEAM,
        offer_kind=OfferKind.DISCOUNT,
        title='Black Desert Online: Land of the Morning Light Deluxe Founder Celebration Collection',
        store_url='https://store.steampowered.com/app/582660/Black_Desert/',
        price_before_minor=119900,
        price_after_minor=47900,
        discount_percent=60,
        promo_end=datetime(2026, 3, 26, 17, 0),
        short_description='',
        description='',
        tags=['Open World', 'RPG', 'Action'],
        genres=['Adventure'],
        review_score=76,
        review_count=55123,
    )
    return offer, {
        'lane': 'high_value_discount',
        'template_id': 'steam_discount',
        'queue_bucket': 'planned',
        'decision_reasons': ['editorial_importance:major_franchise', 'strong_discount'],
        'is_final_push': False,
    }


def build_festival_strong_case() -> tuple[Offer, dict[str, object]]:
    offer = make_fixture_offer(
        offer_id='fixture:festival-strong',
        source=OfferSource.EVENT,
        offer_kind=OfferKind.FESTIVAL,
        title='Steam Tower Defense Fest',
        store_url='https://store.steampowered.com/category/tower_defense',
        price_before_minor=None,
        price_after_minor=None,
        discount_percent=0,
        promo_end=datetime(2026, 3, 26, 17, 0),
        short_description='Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.',
        description='Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.',
        tags=['tower defense', 'strategy'],
        genres=[],
    )
    return offer, {
        'lane': 'event_festival',
        'template_id': 'festival_event',
        'queue_bucket': 'planned',
        'decision_reasons': ['event_festival'],
        'is_final_push': False,
    }


def build_festival_sparse_case() -> tuple[Offer, dict[str, object]]:
    offer = make_fixture_offer(
        offer_id='fixture:festival-sparse',
        source=OfferSource.EVENT,
        offer_kind=OfferKind.FESTIVAL,
        title='Steam Next Fest',
        store_url='https://store.steampowered.com/sale/nextfest',
        price_before_minor=None,
        price_after_minor=None,
        discount_percent=0,
        promo_end=datetime(2026, 3, 26, 17, 0),
        short_description='',
        description='',
        tags=['event'],
        genres=[],
    )
    return offer, {
        'lane': 'event_festival',
        'template_id': 'festival_event',
        'queue_bucket': 'planned',
        'decision_reasons': ['event_festival'],
        'is_final_push': False,
    }


def build_temporary_freebie_case() -> tuple[Offer, dict[str, object]]:
    offer = make_fixture_offer(
        offer_id='fixture:temporary-freebie',
        source=OfferSource.STEAM,
        offer_kind=OfferKind.FREEBIE,
        title='Space Raiders Free Weekend',
        store_url='https://store.steampowered.com/app/404040/Space_Raiders/',
        price_before_minor=39900,
        price_after_minor=0,
        discount_percent=100,
        promo_end=datetime(2026, 3, 21, 20, 0),
        short_description='',
        description='',
        tags=['Shooter', 'Co-op'],
        genres=['Action'],
        review_score=84,
        review_count=6800,
        achievements_count=27,
        has_trading_cards=True,
    )
    offer.metadata['free_access_type'] = 'temporary'
    return offer, {
        'lane': 'breaking_freebie',
        'template_id': 'steam_free',
        'queue_bucket': 'planned',
        'decision_reasons': ['breaking_freebie'],
        'is_final_push': False,
    }


CASE_BUILDERS: dict[str, Callable[[], dict[str, object]]] = {
    'free_game_real_cozy_grove': lambda: {
        'entry_type': 'offer',
        'family': 'FREE_GAME',
        'source_kind': 'golden_snapshot',
        'label': 'FREE_GAME / real freebie',
        'traits': ['free_game', 'real_offer'],
        'offer': load_golden_record('epic:c367569acede446995c5a3663e993446').offer,
        'decision_json': load_golden_record('epic:c367569acede446995c5a3663e993446').decision_json,
    },
    'free_game_fallback_turnip_boy': lambda: {
        'entry_type': 'offer',
        'family': 'FREE_GAME',
        'source_kind': 'archive_post_artifact',
        'label': 'FREE_GAME / fallback archive case',
        'traits': ['free_game', 'fallback', 'archive_case'],
        'offer': load_archive_case('epic:68d9f0e261464ba284e10418d98532ea')[0],
        'decision_json': load_archive_case('epic:68d9f0e261464ba284e10418d98532ea')[1],
    },
    'discount_high_titanfall_2': lambda: {
        'entry_type': 'offer',
        'family': 'DISCOUNT',
        'source_kind': 'golden_snapshot',
        'label': 'DISCOUNT / high discount',
        'traits': ['discount', 'high_discount'],
        'offer': load_golden_record('steam:1237970').offer,
        'decision_json': load_golden_record('steam:1237970').decision_json,
    },
    'discount_long_black_desert': lambda: {
        'entry_type': 'offer',
        'family': 'DISCOUNT',
        'source_kind': 'fixture',
        'label': 'DISCOUNT / long title',
        'traits': ['discount', 'long_title'],
        'offer': build_discount_long_title_case()[0],
        'decision_json': build_discount_long_title_case()[1],
    },
    'festival_strong_tower_defense': lambda: {
        'entry_type': 'offer',
        'family': 'FESTIVAL',
        'source_kind': 'fixture',
        'label': 'FESTIVAL / strong source',
        'traits': ['festival', 'strong_source'],
        'offer': build_festival_strong_case()[0],
        'decision_json': build_festival_strong_case()[1],
    },
    'festival_sparse_next_fest': lambda: {
        'entry_type': 'offer',
        'family': 'FESTIVAL',
        'source_kind': 'fixture',
        'label': 'FESTIVAL / sparse source',
        'traits': ['festival', 'sparse_source'],
        'offer': build_festival_sparse_case()[0],
        'decision_json': build_festival_sparse_case()[1],
    },
    'free_game_temporary_access': lambda: {
        'entry_type': 'offer',
        'family': 'FREE_GAME',
        'source_kind': 'fixture',
        'label': 'FREE_GAME / temporary-access edge case',
        'traits': ['free_game', 'temporary_access', 'edge_case'],
        'offer': build_temporary_freebie_case()[0],
        'decision_json': build_temporary_freebie_case()[1],
    },
    'top_list_roundup_big_discount_highlights': lambda: {
        'entry_type': 'roundup',
        'family': 'TOP_LIST',
        'source_kind': 'roundup_snapshot',
        'label': 'TOP_LIST / roundup editorial case',
        'traits': ['top_list', 'roundup', 'editorial_case'],
        'roundup': load_roundup_case('roundup_01_big_discount_highlights'),
    },
}

CASE_ORDER = [
    'free_game_real_cozy_grove',
    'free_game_fallback_turnip_boy',
    'discount_high_titanfall_2',
    'discount_long_black_desert',
    'festival_strong_tower_defense',
    'festival_sparse_next_fest',
    'free_game_temporary_access',
    'top_list_roundup_big_discount_highlights',
]


def signal_counts(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {label: lowered.count(pattern) for label, pattern in SIGNAL_PATTERNS.items()}


def summarize_counts(entries: list[dict[str, object]], side: str) -> dict[str, int]:
    summary = {label: 0 for label in SIGNAL_PATTERNS}
    for entry in entries:
        counts = entry[f'{side}_signals']
        for label in SIGNAL_PATTERNS:
            summary[label] += int(counts.get(label) or 0)
    return summary


def render_review_markdown(entries: list[dict[str, object]], baseline_manifest: Path, output_root: Path) -> str:
    before_summary = summarize_counts(entries, 'before')
    after_summary = summarize_counts(entries, 'after')
    lines = [
        '# YOTO Caption Freeze Review Pack',
        '',
        f'Generated at (UTC): {datetime.utcnow().isoformat()}Z',
        f'Baseline manifest: {baseline_manifest}',
        f'Output root: {output_root}',
        '',
        '## Summary',
        '',
        f'- cases: {len(entries)}',
        f"- before signals: {', '.join(f'{key}={value}' for key, value in before_summary.items())}",
        f"- after signals: {', '.join(f'{key}={value}' for key, value in after_summary.items())}",
    ]
    for entry in entries:
        lines.extend(
            [
                '',
                f"## {entry['label']}",
                '',
                f"- slug: `{entry['slug']}`",
                f"- family: `{entry['family']}`",
                f"- source_kind: `{entry['source_kind']}`",
                f"- title: `{entry['title']}`",
                f"- before signals: {entry['before_signals']}",
                f"- after signals: {entry['after_signals']}",
                f"- after debug: {entry.get('after_debug') or {}}",
                f"- comparison file: `comparisons/{entry['slug']}.md`",
                '',
                '### Before',
                '',
                '```html',
                str(entry['before_caption_html']),
                '```',
                '',
                '### After',
                '',
                '```html',
                str(entry['after_caption_html']),
                '```',
            ]
        )
    return '\n'.join(lines).strip() + '\n'




def compact_debug(debug: dict[str, object]) -> dict[str, object]:
    return {
        'presence': debug.get('presence') or debug.get('voice_presence'),
        'style': debug.get('style') or debug.get('voice_style'),
        'fallback_used': debug.get('fallback_used'),
        'repeat_risk': debug.get('repeat_risk'),
        'opening_repeat_risk': (debug.get('opening') or {}).get('repeat_risk'),
        'cta_repeat_risk': (debug.get('cta') or {}).get('repeat_risk'),
        'lane': debug.get('lane'),
    }

def write_comparison_file(output_root: Path, entry: dict[str, object]) -> None:
    path = output_root / 'comparisons' / f"{entry['slug']}.md"
    lines = [
        f"# {entry['label']}",
        '',
        f"- family: `{entry['family']}`",
        f"- source_kind: `{entry['source_kind']}`",
        f"- title: `{entry['title']}`",
        f"- before signals: {entry['before_signals']}",
        f"- after signals: {entry['after_signals']}",
        f"- after debug: {entry.get('after_debug') or {}}",
        '',
        '## Before',
        '',
        '```html',
        str(entry['before_caption_html']),
        '```',
        '',
        '## After',
        '',
        '```html',
        str(entry['after_caption_html']),
        '```',
    ]
    path.write_text('\n'.join(lines).strip() + '\n', encoding='utf-8')


def ensure_dirs(output_root: Path) -> None:
    for child in ('before', 'after', 'comparisons'):
        (output_root / child).mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    baseline_manifest = args.before_manifest or find_latest_baseline_manifest()
    baseline_payload = json.loads(baseline_manifest.read_text(encoding='utf-8'))
    baseline_entries = {entry['slug']: entry for entry in baseline_payload.get('entries') or []}

    run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_root = OUTPUT_ROOT / f'{REVIEW_PREFIX}{run_key}'
    ensure_dirs(output_root)

    shared_voice_engine = YotoVoiceEngine()
    caption_builder = TelegramCaptionBuilder(CAPTION_LIMIT, voice_engine=shared_voice_engine)
    roundup_builder = TelegramRoundupDraftBuilder(voice_engine=shared_voice_engine)

    review_entries: list[dict[str, object]] = []
    for slug in CASE_ORDER:
        if slug not in baseline_entries:
            raise KeyError(f'Baseline entry {slug} missing from {baseline_manifest}')
        current = CASE_BUILDERS[slug]()
        before = baseline_entries[slug]
        if current['entry_type'] == 'offer':
            offer = current['offer']
            decision_json = current['decision_json']
            after_caption_html, hashtags = caption_builder.build(offer, decision_json)
            after_debug = caption_builder.last_debug_snapshot()
            title = offer.title
        else:
            roundup = current['roundup']
            draft = roundup_builder.build(roundup)
            after_caption_html = draft.caption_html
            hashtags = roundup_builder._hashtags(roundup)
            after_debug = {
                'voice_presence': 'direct',
                'voice_style': 'roundup',
                'closing_cta': draft.closing_cta,
            }
            title = draft.title

        before_caption_html = str(before['caption_html'])
        after_caption_text = html_to_text(after_caption_html)
        before_caption_text = html_to_text(before_caption_html)

        (output_root / 'before' / f'{slug}.html').write_text(before_caption_html, encoding='utf-8')
        (output_root / 'before' / f'{slug}.txt').write_text(before_caption_text + '\n', encoding='utf-8')
        (output_root / 'after' / f'{slug}.html').write_text(after_caption_html, encoding='utf-8')
        (output_root / 'after' / f'{slug}.txt').write_text(after_caption_text + '\n', encoding='utf-8')

        entry = {
            'slug': slug,
            'label': current['label'],
            'family': current['family'],
            'source_kind': current['source_kind'],
            'traits': list(current['traits']),
            'title': title,
            'before_caption_html': before_caption_html,
            'before_caption_text': before_caption_text,
            'before_signals': signal_counts(before_caption_text),
            'before_hashtags': list(before.get('hashtags') or []),
            'after_caption_html': after_caption_html,
            'after_caption_text': after_caption_text,
            'after_signals': signal_counts(after_caption_text),
            'after_hashtags': list(hashtags),
            'after_debug': compact_debug(after_debug),
        }
        review_entries.append(entry)
        write_comparison_file(output_root, entry)

    review_manifest = {
        'manifest_version': 'yoto_caption_freeze_review_v1',
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'baseline_manifest': str(baseline_manifest),
        'output_root': str(output_root),
        'entries': [
            {
                key: value
                for key, value in entry.items()
                if key not in {'before_caption_html', 'before_caption_text', 'after_caption_html', 'after_caption_text'}
            }
            for entry in review_entries
        ],
    }
    review_manifest_path = output_root / 'review_manifest.json'
    review_manifest_path.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    review_path = output_root / 'review.md'
    review_path.write_text(render_review_markdown(review_entries, baseline_manifest, output_root), encoding='utf-8')
    print(f'Review pack written to: {output_root}')
    print(f'Manifest: {review_manifest_path}')
    print(f'Review: {review_path}')


if __name__ == '__main__':
    main()
