from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.entities.offer import Offer
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder
from tools.generate_yoto_v1_live_caption_validation import html_to_text

OUTPUT_ROOT = REPO_ROOT / 'output' / 'captions'
BEFORE_GLOB = 'festival_freeze_before_*/before_manifest.json'
REVIEW_PREFIX = 'festival_freeze_review_'
CAPTION_LIMIT = 1024
SIGNAL_PATTERNS = {
    'generic_window_mentions': 'подія триватиме',
    'shortlist_mentions': 'короткий список',
    'wishlist_mentions': 'список бажаного',
    'focused_scan_mentions': 'точково',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate a focused FESTIVAL caption freeze review pack.')
    parser.add_argument('--before-manifest', type=Path, default=None, help='Explicit FESTIVAL before-manifest path.')
    return parser.parse_args()



def find_latest_before_manifest() -> Path:
    candidates = sorted(OUTPUT_ROOT.glob(BEFORE_GLOB))
    if not candidates:
        raise FileNotFoundError('No FESTIVAL before manifest found under output/captions/.')
    return candidates[-1]



def signal_counts(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {label: lowered.count(pattern) for label, pattern in SIGNAL_PATTERNS.items()}



def compact_debug(debug: dict[str, object]) -> dict[str, object]:
    opening = dict(debug.get('opening') or {})
    cta = dict(debug.get('cta') or {})
    return {
        'presence': debug.get('presence'),
        'style': debug.get('style'),
        'selected_opening': opening.get('selected'),
        'selected_cta': cta.get('selected'),
        'repeat_risk': debug.get('repeat_risk'),
        'fallback_used': debug.get('fallback_used'),
    }



def ensure_dirs(output_root: Path) -> None:
    for child in ('before', 'after', 'comparisons'):
        (output_root / child).mkdir(parents=True, exist_ok=True)



def render_review_markdown(entries: list[dict[str, object]], before_manifest: Path, output_root: Path) -> str:
    before_summary = {label: 0 for label in SIGNAL_PATTERNS}
    after_summary = {label: 0 for label in SIGNAL_PATTERNS}
    for entry in entries:
        for label in SIGNAL_PATTERNS:
            before_summary[label] += int(entry['before_signals'][label])
            after_summary[label] += int(entry['after_signals'][label])

    lines = [
        '# FESTIVAL Caption Freeze Review Pack',
        '',
        f'Generated at (UTC): {datetime.utcnow().isoformat()}Z',
        f'Before manifest: {before_manifest}',
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
                f"- title: `{entry['title']}`",
                f"- before debug: {entry['before_debug']}",
                f"- after debug: {entry['after_debug']}",
                f"- before signals: {entry['before_signals']}",
                f"- after signals: {entry['after_signals']}",
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



def write_comparison_file(output_root: Path, entry: dict[str, object]) -> None:
    path = output_root / 'comparisons' / f"{entry['slug']}.md"
    lines = [
        f"# {entry['label']}",
        '',
        f"- title: `{entry['title']}`",
        f"- before debug: {entry['before_debug']}",
        f"- after debug: {entry['after_debug']}",
        f"- before signals: {entry['before_signals']}",
        f"- after signals: {entry['after_signals']}",
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



def main() -> None:
    args = parse_args()
    before_manifest = args.before_manifest or find_latest_before_manifest()
    before_payload = json.loads(before_manifest.read_text(encoding='utf-8'))
    before_entries = list(before_payload.get('entries') or [])

    run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_root = OUTPUT_ROOT / f'{REVIEW_PREFIX}{run_key}'
    ensure_dirs(output_root)

    builder = TelegramCaptionBuilder(CAPTION_LIMIT)
    review_entries: list[dict[str, object]] = []
    for before in before_entries:
        offer = Offer.from_snapshot(before['offer_snapshot'])
        decision_json = dict(before['decision_json'])
        after_caption_html, after_hashtags = builder.build(offer, decision_json)
        after_debug = builder.last_debug_snapshot()

        before_caption_html = str(before['caption_html'])
        before_caption_text = str(before['caption_text'])
        after_caption_text = html_to_text(after_caption_html)
        slug = str(before['slug'])

        (output_root / 'before' / f'{slug}.html').write_text(before_caption_html, encoding='utf-8')
        (output_root / 'before' / f'{slug}.txt').write_text(before_caption_text + '\n', encoding='utf-8')
        (output_root / 'after' / f'{slug}.html').write_text(after_caption_html, encoding='utf-8')
        (output_root / 'after' / f'{slug}.txt').write_text(after_caption_text + '\n', encoding='utf-8')

        entry = {
            'slug': slug,
            'label': str(before['label']),
            'title': str(before['title']),
            'before_caption_html': before_caption_html,
            'before_caption_text': before_caption_text,
            'before_hashtags': list(before.get('hashtags') or []),
            'before_debug': compact_debug(dict(before.get('debug') or {})),
            'before_signals': signal_counts(before_caption_text),
            'after_caption_html': after_caption_html,
            'after_caption_text': after_caption_text,
            'after_hashtags': list(after_hashtags),
            'after_debug': compact_debug(after_debug),
            'after_signals': signal_counts(after_caption_text),
        }
        review_entries.append(entry)
        write_comparison_file(output_root, entry)

    review_manifest = {
        'manifest_version': 'festival_caption_freeze_review_v1',
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'before_manifest': str(before_manifest),
        'output_root': str(output_root),
        'entries': [
            {
                key: value
                for key, value in entry.items()
                if key not in {
                    'before_caption_html',
                    'before_caption_text',
                    'after_caption_html',
                    'after_caption_text',
                }
            }
            for entry in review_entries
        ],
    }
    review_manifest_path = output_root / 'review_manifest.json'
    review_manifest_path.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    review_path = output_root / 'review.md'
    review_path.write_text(render_review_markdown(review_entries, before_manifest, output_root), encoding='utf-8')
    print(f'Review pack written to: {output_root}')
    print(f'Manifest: {review_manifest_path}')
    print(f'Review: {review_path}')



if __name__ == '__main__':
    main()
