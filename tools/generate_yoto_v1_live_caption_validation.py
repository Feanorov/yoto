from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from html import unescape
import json
from pathlib import Path
import re
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.use_cases.generate_roundup_artifacts import GenerateRoundupArtifactsUseCase, PlannedCandidate
from application.use_cases.offline_validation_snapshot import OfflineValidationSnapshotManager
from domain.entities.offer import Offer
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import QueueRecord, Repositories
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder, YotoVoiceDecision, YotoVoiceEngine
from infrastructure.telegram.roundup_draft_builder import TelegramRoundupDraftBuilder


DEFAULT_DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
DB_PATH = DEFAULT_DB_PATH
OUTPUT_ROOT = REPO_ROOT / 'output' / 'captions' / 'yoto_voice_v1_live_validation'
DEFAULT_ROUNDUP_LIMIT = 3
DEFAULT_ARCHIVE_LIMIT = 2
DEFAULT_PREVIEW_CAPTION_LIMIT = 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate a live YOTO Voice V1 caption validation pack.')
    parser.add_argument(
        '--planned-limit',
        type=int,
        default=0,
        help='Maximum number of current planned solo posts to include. Use 0 for all planned items.',
    )
    parser.add_argument(
        '--roundup-limit',
        type=int,
        default=DEFAULT_ROUNDUP_LIMIT,
        help='Maximum number of current roundups to rebuild from the reserve queue.',
    )
    parser.add_argument(
        '--archive-limit',
        type=int,
        default=DEFAULT_ARCHIVE_LIMIT,
        help='Maximum number of recent published posts to include as an addendum.',
    )
    parser.add_argument('--db-path', type=Path, default=None, help='Explicit SQLite database path to read queue state from.')
    parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Read queue state from an offline validation snapshot. Omit the value to use the latest snapshot.',
    )
    return parser.parse_args()


def load_live_queue(repositories: Repositories) -> tuple[list[QueueRecord], list[QueueRecord]]:
    return repositories.list_queue('planned'), repositories.list_queue('reserve')


def load_recent_archive_cases(limit: int) -> list[dict[str, object]]:
    if limit <= 0 or not DB_PATH.exists():
        return []

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT artifact_json, lane, created_at FROM post_artifacts ORDER BY created_at DESC LIMIT 80').fetchall()
    cases: list[dict[str, object]] = []
    seen_offer_ids: set[str] = set()

    for row in rows:
        payload = json.loads(row['artifact_json'])
        render_inputs = payload.get('render_inputs') or {}
        offer_payload = render_inputs.get('offer') or {}
        decision_payload = dict(render_inputs.get('decision') or {})
        if not offer_payload:
            continue
        offer = Offer.from_snapshot(offer_payload)
        if offer.offer_id in seen_offer_ids:
            continue
        seen_offer_ids.add(offer.offer_id)
        if 'lane' not in decision_payload:
            decision_payload['lane'] = row['lane']
        if 'template_id' not in decision_payload:
            decision_payload['template_id'] = payload.get('template_id') or 'steam_discount'
        cases.append(
            {
                'offer': offer,
                'decision_json': decision_payload,
                'created_at': str(row['created_at']),
                'lane': row['lane'],
            }
        )
        if len(cases) >= limit:
            break

    cases.sort(key=lambda item: str(item['created_at']))
    return cases


def build_current_roundups(
    reserve_records: list[QueueRecord],
    *,
    voice_engine: YotoVoiceEngine,
    roundup_limit: int,
) -> list:
    if roundup_limit <= 0 or not reserve_records:
        return []

    reserve_candidates = [
        PlannedCandidate(score=record.score, offer=record.offer, decision_json=record.decision_json)
        for record in reserve_records
    ]
    roundup_builder = TelegramRoundupDraftBuilder(voice_engine=voice_engine)
    roundup_use_case = GenerateRoundupArtifactsUseCase(
        repositories=Repositories(DB_PATH),
        writer=AnalyticsArtifactWriter(REPO_ROOT / 'output' / 'analytics'),
        draft_builder=roundup_builder,
    )
    return roundup_use_case._build_roundups(reserve_candidates)[:roundup_limit]


def build_offer_preview_entry(
    builder: TelegramCaptionBuilder,
    *,
    position: int,
    section_name: str,
    origin: str,
    offer: Offer,
    decision_json: dict,
    created_at: str | None,
    bucket: str | None,
    score: float | None,
) -> dict[str, object]:
    caption_html, hashtags, voice = build_offer_preview(builder, offer, decision_json)
    return {
        'entry_type': 'offer',
        'section_name': section_name,
        'position': position,
        'origin': origin,
        'title': offer.title,
        'offer_id': offer.offer_id,
        'source': offer.source.value,
        'offer_kind': offer.offer_kind.value,
        'bucket': bucket,
        'lane': decision_json.get('lane'),
        'score': round(float(score), 2) if score is not None else None,
        'created_at': created_at,
        'template_id': decision_json.get('template_id'),
        'decision_reasons': list(decision_json.get('decision_reasons') or []),
        'voice_presence': voice.presence,
        'voice_style': voice.style,
        'direct_mode': voice.direct_mode,
        'access_type': voice.access_type,
        'hashtags': list(hashtags),
        'caption_html': caption_html,
        'caption_text': html_to_text(caption_html),
        'caption_char_count': len(caption_html),
        'caption_limit_safe': len(caption_html) <= builder.caption_limit,
    }


def build_offer_preview(
    builder: TelegramCaptionBuilder,
    offer: Offer,
    decision_json: dict,
) -> tuple[str, list[str], YotoVoiceDecision]:
    hashtags = builder._build_hashtags(offer, decision_json)
    voice = builder.voice_engine.select_offer_voice(offer, decision_json)
    copy = builder._pick_copy(offer, decision_json, voice)
    caption = builder._compose(offer, decision_json, copy, hashtags, voice)
    if len(caption) <= builder.caption_limit:
        return caption, hashtags, voice

    for limit in (240, 200, 160, 120, 90):
        copy = builder._pick_copy(offer, decision_json, voice, max_length=limit)
        caption = builder._compose(offer, decision_json, copy, hashtags, voice)
        if len(caption) <= builder.caption_limit:
            return caption, hashtags, voice

    trimmed_tags = hashtags[:]
    while len(trimmed_tags) > 3:
        trimmed_tags.pop()
        caption = builder._compose(offer, decision_json, copy, trimmed_tags, voice)
        if len(caption) <= builder.caption_limit:
            return caption, trimmed_tags, voice

    trimmed_copy = {**copy, 'summary': ''}
    caption = builder._compose(offer, decision_json, trimmed_copy, trimmed_tags, voice)
    if len(caption) <= builder.caption_limit:
        return caption, trimmed_tags, voice

    return caption[: builder.caption_limit - 1].rstrip() + '...', trimmed_tags, voice


def build_roundup_preview_entries(roundups: list) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for index, roundup in enumerate(roundups, start=1):
        draft = roundup.telegram_draft
        if draft is None:
            continue
        entries.append(
            {
                'entry_type': 'roundup',
                'section_name': 'current_live_roundups',
                'position': index,
                'origin': 'live_reserve_roundup',
                'title': draft.title,
                'roundup_id': roundup.roundup_id,
                'group_type': roundup.group_type,
                'theme_label': roundup.theme_label,
                'item_count': roundup.item_count,
                'item_titles': [item.title for item in roundup.items],
                'voice_presence': 'direct',
                'voice_style': 'roundup',
                'direct_mode': 'roundup',
                'caption_html': draft.caption_html,
                'caption_text': html_to_text(draft.caption_html),
                'caption_char_count': len(draft.caption_html),
                'caption_limit_safe': True,
            }
        )
    return entries


def summarize_entries(entries: list[dict[str, object]]) -> dict[str, object]:
    total = len(entries)
    presence_counts = Counter(str(entry.get('voice_presence') or 'unknown') for entry in entries)
    style_counts = Counter(str(entry.get('voice_style') or 'unknown') for entry in entries)
    direct_mode_counts = Counter(
        str(entry.get('direct_mode'))
        for entry in entries
        if entry.get('direct_mode')
    )
    lane_counts = Counter(
        str(entry.get('lane') or entry.get('group_type') or 'unknown')
        for entry in entries
    )
    source_counts = Counter(
        str(entry.get('source') or entry.get('entry_type') or 'unknown')
        for entry in entries
    )
    average_chars = round(
        sum(int(entry.get('caption_char_count') or 0) for entry in entries) / total,
        1,
    ) if total else 0.0
    max_chars = max((int(entry.get('caption_char_count') or 0) for entry in entries), default=0)
    return {
        'total': total,
        'presence_counts': dict(sorted(presence_counts.items())),
        'style_counts': dict(sorted(style_counts.items())),
        'direct_mode_counts': dict(sorted(direct_mode_counts.items())),
        'lane_counts': dict(sorted(lane_counts.items())),
        'source_counts': dict(sorted(source_counts.items())),
        'average_caption_chars': average_chars,
        'max_caption_chars': max_chars,
        'direct_rate': round((presence_counts.get('direct', 0) / total), 3) if total else 0.0,
    }


def build_report_payload(
    *,
    generated_at: str,
    queue_snapshot_at: str | None,
    sections: list[dict[str, object]],
    notes: list[str],
) -> dict[str, object]:
    live_entries: list[dict[str, object]] = []
    archive_entries: list[dict[str, object]] = []
    for section in sections:
        entries = list(section.get('entries') or [])
        if str(section.get('name', '')).startswith('recent_archive'):
            archive_entries.extend(entries)
        else:
            live_entries.extend(entries)

    return {
        'generated_at': generated_at,
        'queue_snapshot_at': queue_snapshot_at,
        'notes': list(notes),
        'sections': sections,
        'live_stream_summary': summarize_entries(live_entries),
        'archive_summary': summarize_entries(archive_entries),
    }


def render_review_markdown(payload: dict[str, object]) -> str:
    lines = [
        '# YOTO Voice V1 Live Caption Validation',
        '',
        f"Generated at (UTC): {payload.get('generated_at')}",
    ]
    if payload.get('queue_snapshot_at'):
        lines.append(f"Live queue snapshot: {payload.get('queue_snapshot_at')}")
    notes = list(payload.get('notes') or [])
    if notes:
        lines.extend(['', '## Notes', ''])
        for note in notes:
            lines.append(f'- {note}')

    lines.extend(
        [
            '',
            '## Live Stream Summary',
            '',
            summarize_markdown_lines(payload.get('live_stream_summary') or {}),
        ]
    )
    archive_summary = payload.get('archive_summary') or {}
    if int(archive_summary.get('total') or 0) > 0:
        lines.extend(
            [
                '',
                '## Archive Addendum Summary',
                '',
                summarize_markdown_lines(archive_summary),
            ]
        )

    for section in payload.get('sections') or []:
        lines.extend(
            [
                '',
                f"## {section.get('label')}",
                '',
                summarize_markdown_lines(section.get('summary') or {}),
            ]
        )
        entries = list(section.get('entries') or [])
        if not entries:
            lines.append('- No entries in this section.')
            continue
        for entry in entries:
            title = entry.get('title') or entry.get('roundup_id') or 'Untitled'
            lines.extend(
                [
                    '',
                    f"### {entry.get('position')}. {title}",
                    '',
                ]
            )
            if entry.get('entry_type') == 'offer':
                lines.append(
                    '- '
                    + ' | '.join(
                        [
                            f"voice `{entry.get('voice_presence')}` / `{entry.get('voice_style')}`",
                            f"mode `{entry.get('direct_mode') or '-'}`",
                            f"lane `{entry.get('lane')}`",
                            f"bucket `{entry.get('bucket') or '-'}`",
                            f"source `{entry.get('source')}`",
                            f"chars `{entry.get('caption_char_count')}`",
                        ]
                    )
                )
                lines.append(
                    '- '
                    + ' | '.join(
                        [
                            f"offer `{entry.get('offer_id')}`",
                            f"score `{entry.get('score')}`",
                            f"origin `{entry.get('origin')}`",
                            f"created `{entry.get('created_at') or '-'}`",
                        ]
                    )
                )
                lines.append(f"- reasons: {', '.join(entry.get('decision_reasons') or []) or '-'}")
                lines.append(f"- hashtags: {' '.join(entry.get('hashtags') or [])}")
            else:
                lines.append(
                    '- '
                    + ' | '.join(
                        [
                            'voice `direct` / `roundup`',
                            f"mode `{entry.get('direct_mode')}`",
                            f"group `{entry.get('group_type')}`",
                            f"items `{entry.get('item_count')}`",
                            f"chars `{entry.get('caption_char_count')}`",
                        ]
                    )
                )
                lines.append(f"- item_titles: {', '.join(entry.get('item_titles') or [])}")
            lines.extend(
                [
                    '',
                    '```html',
                    str(entry.get('caption_html') or ''),
                    '```',
                ]
            )
    return '\n'.join(lines).strip() + '\n'


def summarize_markdown_lines(summary: dict[str, object]) -> str:
    total = int(summary.get('total') or 0)
    if total <= 0:
        return '- total: 0'
    lines = [
        f"- total: {total}",
        f"- presence: {format_counter(summary.get('presence_counts') or {}, total)}",
        f"- styles: {format_counter(summary.get('style_counts') or {}, total)}",
        f"- direct_modes: {format_counter(summary.get('direct_mode_counts') or {}, total, allow_empty=True)}",
        f"- lanes: {format_counter(summary.get('lane_counts') or {}, total)}",
        f"- sources: {format_counter(summary.get('source_counts') or {}, total)}",
        f"- caption_chars: avg {summary.get('average_caption_chars')} / max {summary.get('max_caption_chars')}",
        f"- direct_rate: {summary.get('direct_rate')}",
    ]
    return '\n'.join(lines)


def format_counter(counter_payload: dict[str, object], total: int, *, allow_empty: bool = False) -> str:
    items = [(str(key), int(value)) for key, value in (counter_payload or {}).items()]
    if not items:
        return '-' if allow_empty else 'none'
    return ', '.join(f'{key} {value}/{total}' for key, value in items)


def html_to_text(value: str) -> str:
    without_tags = re.sub(r'<[^>]+>', '', value or '')
    normalized = unescape(without_tags)
    normalized = normalized.replace('\r', '')
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized.strip()


def write_validation_pack(output_root: Path, payload: dict[str, object]) -> tuple[Path, Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / 'validation_manifest.json'
    review_path = output_root / 'review.md'
    rows_path = output_root / 'validation_rows.csv'

    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    review_path.write_text(render_review_markdown(payload), encoding='utf-8')
    write_csv_rows(rows_path, payload)
    return manifest_path, review_path, rows_path


def write_csv_rows(path: Path, payload: dict[str, object]) -> None:
    headers = [
        'section',
        'entry_type',
        'position',
        'title',
        'offer_id',
        'roundup_id',
        'source',
        'offer_kind',
        'bucket',
        'lane',
        'group_type',
        'score',
        'voice_presence',
        'voice_style',
        'direct_mode',
        'caption_char_count',
        'caption_limit_safe',
        'origin',
        'created_at',
    ]
    lines = [','.join(headers)]
    for section in payload.get('sections') or []:
        section_name = str(section.get('name') or '')
        for entry in section.get('entries') or []:
            row = {
                'section': section_name,
                'entry_type': entry.get('entry_type'),
                'position': entry.get('position'),
                'title': entry.get('title'),
                'offer_id': entry.get('offer_id'),
                'roundup_id': entry.get('roundup_id'),
                'source': entry.get('source'),
                'offer_kind': entry.get('offer_kind'),
                'bucket': entry.get('bucket'),
                'lane': entry.get('lane'),
                'group_type': entry.get('group_type'),
                'score': entry.get('score'),
                'voice_presence': entry.get('voice_presence'),
                'voice_style': entry.get('voice_style'),
                'direct_mode': entry.get('direct_mode'),
                'caption_char_count': entry.get('caption_char_count'),
                'caption_limit_safe': entry.get('caption_limit_safe'),
                'origin': entry.get('origin'),
                'created_at': entry.get('created_at'),
            }
            lines.append(','.join(csv_cell(row[key]) for key in headers))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def csv_cell(value: object) -> str:
    escaped = str(value if value is not None else '')
    escaped = escaped.replace('"', '""')
    if any(token in escaped for token in (',', '\n', '"')):
        return f'"{escaped}"'
    return escaped


def generate_validation_pack(
    *,
    planned_limit: int | None = None,
    roundup_limit: int = DEFAULT_ROUNDUP_LIMIT,
    archive_limit: int = DEFAULT_ARCHIVE_LIMIT,
    output_root_base: Path = OUTPUT_ROOT,
) -> tuple[Path, dict[str, object]]:
    repositories = Repositories(DB_PATH)
    planned_records, reserve_records = load_live_queue(repositories)
    live_queue_timestamp = max(
        (
            record.created_at.isoformat()
            for record in planned_records + reserve_records
        ),
        default=None,
    )

    shared_voice_engine = YotoVoiceEngine()
    live_builder = TelegramCaptionBuilder(DEFAULT_PREVIEW_CAPTION_LIMIT, voice_engine=shared_voice_engine)
    planned_slice = planned_records[:planned_limit] if planned_limit else planned_records
    planned_entries = [
        build_offer_preview_entry(
            live_builder,
            position=index,
            section_name='current_live_planned_solos',
            origin='live_queue',
            offer=record.offer,
            decision_json=record.decision_json,
            created_at=record.created_at.isoformat(),
            bucket=record.bucket,
            score=record.score,
        )
        for index, record in enumerate(planned_slice, start=1)
    ]

    roundups = build_current_roundups(
        reserve_records,
        voice_engine=shared_voice_engine,
        roundup_limit=roundup_limit,
    )
    roundup_entries = build_roundup_preview_entries(roundups)

    archive_cases = load_recent_archive_cases(archive_limit)
    archive_builder = TelegramCaptionBuilder(DEFAULT_PREVIEW_CAPTION_LIMIT, voice_engine=YotoVoiceEngine())
    archive_entries = [
        build_offer_preview_entry(
            archive_builder,
            position=index,
            section_name='recent_archive_addendum',
            origin='post_artifact',
            offer=case['offer'],
            decision_json=case['decision_json'],
            created_at=str(case['created_at']),
            bucket='published',
            score=None,
        )
        for index, case in enumerate(archive_cases, start=1)
    ]

    sections = [
        {
            'name': 'current_live_planned_solos',
            'label': 'Current Live Planned Solo Posts',
            'summary': summarize_entries(planned_entries),
            'entries': planned_entries,
        },
        {
            'name': 'current_live_roundups',
            'label': 'Current Live Roundups Rebuilt From Reserve',
            'summary': summarize_entries(roundup_entries),
            'entries': roundup_entries,
        },
    ]
    if archive_entries:
        sections.append(
            {
                'name': 'recent_archive_addendum',
                'label': 'Recent Published Post Addendum',
                'summary': summarize_entries(archive_entries),
                'entries': archive_entries,
            }
        )

    generated_at = datetime.utcnow().isoformat()
    notes = [
        'The live queue was read from the current database state; refresh it with `python -m dealbot.main --preview` before rerunning if you want a newer stream.',
        'Solo captions are generated only from the current planned queue, so reserve items are represented through rebuilt roundups instead of fake solo posts.',
        'The recent archive addendum exists to expose real shipped voice behavior, including freebie cases that may be absent from the current live queue.',
    ]
    payload = build_report_payload(
        generated_at=generated_at,
        queue_snapshot_at=live_queue_timestamp,
        sections=sections,
        notes=notes,
    )

    run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_root = output_root_base / run_key
    write_validation_pack(output_root, payload)
    return output_root, payload


def resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db_path is not None:
        return Path(args.db_path)
    if args.offline_snapshot is not None:
        manager = OfflineValidationSnapshotManager(REPO_ROOT / 'output' / 'offline_validation')
        return manager.resolve(args.offline_snapshot).base_db_path
    return DEFAULT_DB_PATH


def main() -> None:
    global DB_PATH

    args = parse_args()
    DB_PATH = resolve_db_path(args)
    planned_limit = args.planned_limit or None
    output_root, payload = generate_validation_pack(
        planned_limit=planned_limit,
        roundup_limit=args.roundup_limit,
        archive_limit=args.archive_limit,
    )
    live_summary = payload.get('live_stream_summary') or {}
    print(f'Validation pack written to: {output_root}')
    print(
        'Live stream summary: '
        f"total={live_summary.get('total')} "
        f"direct_rate={live_summary.get('direct_rate')} "
        f"presence={live_summary.get('presence_counts')}"
    )


if __name__ == '__main__':
    main()


