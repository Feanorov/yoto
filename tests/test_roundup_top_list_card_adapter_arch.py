from __future__ import annotations

from pathlib import Path

from PIL import Image

from domain.entities.roundup_post import RoundupItem, RoundupPost
from infrastructure.render.cards.roundup_top_list_card_adapter import RoundupTopListCardAdapter


def _png(path: Path, color: tuple[int, int, int]) -> None:
    Image.new('RGB', (32, 32), color).save(path, format='PNG')


def make_roundup(tmp_path: Path) -> RoundupPost:
    first_art = tmp_path / 'first.png'
    second_art = tmp_path / 'second.png'
    _png(first_art, (0, 0, 0))
    _png(second_art, (255, 255, 255))
    return RoundupPost(
        roundup_id='roundup_01_big_discount_highlights',
        title='Roundup: Big Discount Highlights',
        intro='Roundup intro',
        group_type='hero_discount',
        theme_label='Big Discount Highlights',
        item_count=2,
        items=[
            RoundupItem(
                rank=1,
                offer_id='steam:100',
                title='Lower Priority Item',
                store_url='https://store.steampowered.com/app/100',
                store='Steam',
                source='steam',
                lane='high_value_discount',
                score=80.0,
                discount_percent=40,
                review_score=70,
                is_freebie=False,
                price_after_minor=10000,
                price_line='40% off',
                callout='Reserve candidate',
                summary_line='40% off',
                reason_tags=['high_value_discount'],
                lead_artwork_url=str(first_art),
            ),
            RoundupItem(
                rank=2,
                offer_id='steam:101',
                title='Higher Priority Item',
                store_url='https://store.steampowered.com/app/101',
                store='Steam',
                source='steam',
                lane='high_value_discount',
                score=140.0,
                discount_percent=80,
                review_score=92,
                is_freebie=False,
                price_after_minor=5000,
                price_line='80% off',
                callout='Hero discount',
                summary_line='80% off',
                reason_tags=['high_value_discount', 'hero_discount'],
                lead_artwork_url=str(second_art),
            ),
        ],
    )


def test_roundup_top_list_card_adapter_scores_and_reports_selected_lead_artwork(tmp_path: Path) -> None:
    adapter = RoundupTopListCardAdapter(tmp_path / 'cards')
    roundup = make_roundup(tmp_path)

    result = adapter.render(roundup)

    assert result.image_path.exists()
    assert result.diagnostics['renderer_selected'] == 'yoto_v4'
    assert result.diagnostics['lead_artwork_selected_offer_id'] == 'steam:101'
    assert result.diagnostics['lead_artwork_selection_reason'] == 'highest_weighted_roundup_item_artwork'
    assert result.diagnostics['hero_candidates_count'] == 2
    assert result.diagnostics['hero_fallback_used'] is False
    assert result.diagnostics['used_placeholder_artwork'] is False
