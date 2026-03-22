from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from video_generator.domain.scene_planner import ScenePlanner
from video_generator.domain.template_selector import TemplateSelector
from video_generator.infrastructure.manifest_loader import ManifestLoader


def write_manifest(
    tmp_path: Path,
    *,
    template_hint: str,
    context: dict,
    short_title: str = 'YOTO Video Item',
    hook_line: str = '????????? ????? ??? ?????.',
    summary_line: str = '???????? ???? ??? ????????? ?????.',
    urgency_line: str = '??? ?????????? ??????????.',
    roundup_items: list[dict] | None = None,
) -> Path:
    asset = tmp_path / 'game.png'
    Image.new('RGB', (900, 900), (80, 90, 120)).save(asset)
    payload = {
        'manifest_version': 2,
        'run_key': '20260314T120000Z',
        'created_at': '2026-03-14T12:00:00',
        'offer_id': 'content:1',
        'short_title': short_title,
        'hook_line': hook_line,
        'summary_line': summary_line,
        'urgency_line': urgency_line,
        'asset_refs': {
            'game_image': str(asset),
            'background': str(asset),
            'card_image': str(asset),
        },
        'template_hint': template_hint,
        'context': context,
    }
    if roundup_items is not None:
        payload['roundup_items'] = roundup_items
    path = tmp_path / f"{context.get('lane', 'generic')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


def load_manifest(path: Path):
    return ManifestLoader().load(path)


def test_scene_planner_plans_discount_manifest_into_three_scenes(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='deal-spotlight',
            context={
                'lane': 'high_value_discount',
                'offer_kind': 'discount',
                'store': 'Steam',
            },
        )
    )

    template = TemplateSelector().select(manifest)
    scenes = ScenePlanner().plan(manifest, template)

    assert template.name == 'deal_spotlight'
    assert [scene.scene_id for scene in scenes] == ['hook', 'summary', 'urgency']
    assert [scene.duration_seconds for scene in scenes] == [2.0, 5.0, 3.0]


def test_scene_planner_plans_freebie_manifest_into_three_scenes(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='freebie-flash',
            context={
                'lane': 'breaking_freebie',
                'offer_kind': 'freebie',
                'store': 'Epic Games Store',
            },
        )
    )

    template = TemplateSelector().select(manifest)
    scenes = ScenePlanner().plan(manifest, template)

    assert template.name == 'freebie_flash'
    assert len(scenes) == 3
    assert scenes[-1].cta is not None


def test_scene_planner_plans_event_manifest_into_three_scenes(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='event-countdown',
            context={
                'lane': 'event_festival',
                'offer_kind': 'event',
                'store': 'Steam',
            },
        )
    )

    template = TemplateSelector().select(manifest)
    scenes = ScenePlanner().plan(manifest, template)

    assert template.name == 'event_countdown'
    assert len(scenes) == 3
    assert scenes[-1].scene_id == 'urgency'


def test_scene_planner_summary_prefers_short_title_when_summary_line_is_over_budget(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='deal-spotlight',
            short_title='Slay the Spire',
            summary_line='?? ???? ?????? ???? ?????, ???? ???????? ?????????? ????????? ?????? ? ?? ??????? ??? ? ??????? ????????? ????????? ????? ??? ?????????.',
            context={
                'lane': 'high_value_discount',
                'offer_kind': 'discount',
                'store': 'Steam',
            },
        )
    )

    scenes = ScenePlanner().plan(manifest, TemplateSelector().select(manifest))

    assert scenes[1].headline == 'Slay the Spire'
    assert scenes[1].body == 'Steam - \u0417\u043d\u0438\u0436\u043a\u0430'


def test_scene_planner_urgency_compresses_to_single_short_clause(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='deal-spotlight',
            urgency_line='?????????? ???????? ????: ??????? ?????????? ?????, ???? ?? ?????? ?? ??????? ? ?? ?????? ?? ???????? ????????.',
            context={
                'lane': 'final_push',
                'offer_kind': 'discount',
                'store': 'Steam',
            },
        )
    )

    scenes = ScenePlanner().plan(manifest, TemplateSelector().select(manifest))

    assert len(scenes[2].headline) <= ScenePlanner.URGENCY_HEADLINE_MAX
    assert '???? ?? ?????? ?? ???????' not in scenes[2].headline


def test_scene_planner_plans_roundup_digest_into_four_scenes_with_compact_item_lines(tmp_path: Path) -> None:
    manifest = load_manifest(
        write_manifest(
            tmp_path,
            template_hint='deal-spotlight',
            hook_line='???? ???????? ?? ?????? ???? ???????? ?????????? ?? ???????. ??? ? ?????? ?????, ?????? ?????? ? ???????, ??? ????? ???????? ??? ???????? roundup.',
            context={
                'lane': 'roundup_digest',
                'template_id': 'roundup_digest',
                'video_template_intent': 'roundup_digest',
                'offer_kind': 'discount',
                'store': 'Steam',
            },
            roundup_items=[
                {'title': 'Battlefield 2042 Definitive Mega Edition', 'discount_percent': 95},
                {'title': 'STAR WARS Jedi: Survivor Deluxe', 'discount_percent': 90},
                {'title': 'Dead Space Digital Deluxe', 'discount_percent': 85},
                {'title': 'Titanfall 2 Ultimate Edition', 'discount_percent': 80},
            ],
        )
    )

    template = TemplateSelector().select(manifest)
    scenes = ScenePlanner().plan(manifest, template)

    assert template.name == 'roundup_digest'
    assert [scene.scene_id for scene in scenes] == ['hook', 'roundup_page_one', 'roundup_page_two', 'urgency']
    assert len(scenes) == 4
    assert len(scenes[0].body) <= ScenePlanner.ROUNDUP_HOOK_BODY_MAX

    first_page_lines = scenes[1].body.splitlines()
    second_page_lines = scenes[2].body.splitlines()
    assert len(first_page_lines) == 2
    assert len(second_page_lines) == 2
    assert first_page_lines[0].startswith('1. -95%')
    assert first_page_lines[1].startswith('2. -90%')
    assert second_page_lines[0].startswith('3. -85%')
    assert second_page_lines[1].startswith('4. -80%')
