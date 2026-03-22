from __future__ import annotations

from datetime import datetime

from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer, OfferKind, OfferSource
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder, YotoVoiceEngine
from tools.generate_yoto_v1_live_caption_validation import (
    build_offer_preview_entry,
    build_report_payload,
    render_review_markdown,
    summarize_entries,
)


def make_offer() -> Offer:
    return Offer(
        offer_id='epic:test-freebie',
        source=OfferSource.EPIC,
        source_ref='epic:test-freebie',
        offer_kind=OfferKind.FREEBIE,
        game_id='epic:test-freebie',
        franchise_key='test-freebie',
        title='Turnip Boy Robs a Bank',
        store_url='https://store.epicgames.com/uk/p/turnip-boy-robs-a-bank',
        price_before_minor=69900,
        price_after_minor=0,
        currency='UAH',
        discount_percent=100,
        promo_start=None,
        promo_end=datetime(2026, 3, 15, 18, 0),
        review_score=84,
        review_count=2500,
        achievements_count=None,
        has_trading_cards=False,
        tags=['Co-op', 'Roguelite'],
        genres=['Action'],
        assets=AssetBundle(hero='https://example.com/header.png', header='https://example.com/header.png'),
        confidence_levels=ConfidenceLevels(),
        description='Український опис для тестової роздачі.',
        short_description='Український опис для тестової роздачі.',
        publisher_name='Test Publisher',
    )


def make_decision() -> dict:
    return {
        'lane': 'breaking_freebie',
        'template_id': 'epic_free',
        'queue_bucket': 'planned',
        'decision_reasons': ['breaking_freebie'],
        'is_final_push': False,
    }


def test_build_offer_preview_entry_exposes_voice_metadata_and_safe_caption() -> None:
    builder = TelegramCaptionBuilder(1024, voice_engine=YotoVoiceEngine())

    entry = build_offer_preview_entry(
        builder,
        position=1,
        section_name='recent_archive_addendum',
        origin='post_artifact',
        offer=make_offer(),
        decision_json=make_decision(),
        created_at='2026-03-12T22:00:00',
        bucket='published',
        score=None,
    )

    assert entry['voice_presence'] == 'direct'
    assert entry['direct_mode'] == 'freebie'
    assert entry['caption_limit_safe'] is True
    assert '<a href="https://store.epicgames.com/uk/p/turnip-boy-robs-a-bank"><b>Turnip Boy Robs a Bank</b></a>' in entry['caption_html']
    assert 'Йото' in entry['caption_html']
    assert '<a href=' not in entry['caption_text']



def test_render_review_markdown_includes_section_summary_and_caption() -> None:
    builder = TelegramCaptionBuilder(1024, voice_engine=YotoVoiceEngine())
    entry = build_offer_preview_entry(
        builder,
        position=1,
        section_name='recent_archive_addendum',
        origin='post_artifact',
        offer=make_offer(),
        decision_json=make_decision(),
        created_at='2026-03-12T22:00:00',
        bucket='published',
        score=None,
    )
    sections = [
        {
            'name': 'recent_archive_addendum',
            'label': 'Recent Published Post Addendum',
            'summary': summarize_entries([entry]),
            'entries': [entry],
        }
    ]
    payload = build_report_payload(
        generated_at='2026-03-12T22:30:00',
        queue_snapshot_at='2026-03-12T22:00:00',
        sections=sections,
        notes=['Archive-only test note.'],
    )

    markdown = render_review_markdown(payload)

    assert 'Recent Published Post Addendum' in markdown
    assert 'Archive Addendum Summary' in markdown
    assert 'voice `direct` / `freebie`' in markdown
    assert 'Turnip Boy Robs a Bank' in markdown
    assert '```html' in markdown
