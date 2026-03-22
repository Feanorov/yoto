from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from application.use_cases.plan_queue import PlannedCandidate, SALE_EVENT_EVENT_SLOT_LIMIT
from dealbot.main import BotRuntime
from dealbot.settings import AppSettings
from domain.entities.decision import Lane


DEFAULT_OUTPUT = Path('temp/current_lane_report.json')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a live YOTO content lane report from current offers.')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='Path to write the JSON report.')
    parser.add_argument('--sample-size', type=int, default=24, help='Approximate number of sample rows to include.')
    return parser.parse_args()



def row_sort_key(row: dict) -> tuple[int, float, str]:
    mode_order = {
        'solo_post': 0,
        'roundup_candidate': 1,
        'capacity_hold': 2,
        'hard_suppress': 3,
    }
    raw_score = row['priority_score'] if row['priority_score'] is not None else -999999.0
    return (mode_order.get(row['recommended_post_mode'], 9), -raw_score, row['offer_title'])


async def build_report(output_path: Path, sample_size: int) -> Path:
    root_dir = Path(__file__).resolve().parents[1]
    settings = AppSettings.from_env(root_dir)
    output_path = output_path if output_path.is_absolute() else root_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with BotRuntime(settings) as runtime:
        now_utc, now_local = runtime.now()
        planner = runtime.planner
        publisher = runtime.publisher
        editorial_control = planner.control_loader.load() if planner.control_loader else None

        offers = await planner.ingest_source.execute(now_utc)
        offers = await planner.enrich_offer.enrich(offers, planner.settings.static.steam_enrich_limit)
        sale_event_context = planner._build_sale_event_context(offers, now_utc)

        day_key = now_local.date().isoformat()
        existing_lane_usage = {
            lane.value: planner.repositories.get_daily_lane_count(day_key, lane.value)
            for lane in Lane
        }
        game_of_day_already_used = existing_lane_usage.get(Lane.GAME_OF_THE_DAY.value, 0) >= 1

        rows: list[dict] = []
        candidates: list[PlannedCandidate] = []
        for offer in offers:
            game_history = planner.repositories.get_game_history(offer.game_id)
            franchise_history = planner.repositories.get_franchise_history(offer.franchise_key)
            dedup = planner.dedup_policy.evaluate(offer, game_history, franchise_history, now_utc)
            outcome = planner.decision_policy.decide(
                offer=offer,
                dedup=dedup,
                now_local=now_local,
                game_of_day_used=game_of_day_already_used,
                editorial_control=editorial_control,
            )
            if not outcome.accepted:
                reason_tags = list(outcome.quality.reasons) if not outcome.quality.accepted else [outcome.dedup.reason]
                if outcome.control.manual_reasons:
                    reason_tags.extend(outcome.control.manual_reasons)
                rows.append(
                    {
                        'offer_title': offer.title,
                        'offer_id': offer.offer_id,
                        'detected_lane': 'hard_suppress',
                        'priority_score': None,
                        'reason_tags': list(dict.fromkeys(reason_tags)),
                        'recommended_post_mode': 'hard_suppress',
                    }
                )
                continue

            sale_event_linked = planner._is_sale_event_linked(offer, sale_event_context)
            score = planner._score_offer(outcome, now_utc, sale_event_linked)
            decision_json = planner._build_decision_json(score, outcome, game_history)
            planner._attach_sale_event_debug(decision_json, offer, sale_event_context, sale_event_linked)
            priority = publisher.publish_priority_engine.evaluate(
                offer=offer,
                lane=decision_json['lane'],
                bucket=decision_json['queue_bucket'],
                decision_score=float(decision_json.get('score') or score),
                must_ship=bool(decision_json.get('must_ship')),
                manual_force_override=bool(decision_json.get('manual_force_override')),
                lane_published_today=existing_lane_usage.get(decision_json['lane'], 0),
                now_utc=now_utc,
            )
            rows.append(
                {
                    'offer_title': offer.title,
                    'offer_id': offer.offer_id,
                    'detected_lane': decision_json['lane'],
                    'priority_score': priority.total,
                    'reason_tags': [
                        tag for tag in dict.fromkeys([
                            *(decision_json.get('decision_reasons') or []),
                            *(decision_json.get('quality_reasons') or []),
                            decision_json.get('dedup_reason'),
                            'sale_event_linked' if (decision_json.get('debug') or {}).get('sale_event', {}).get('linked') else None,
                        ]) if tag
                    ],
                    'recommended_post_mode': 'accepted_pending_selection',
                }
            )
            candidates.append(PlannedCandidate(score=score, offer=offer, decision_json=decision_json))

        planned_pool = [item for item in candidates if item.decision_json['queue_bucket'] == 'planned']
        hero_candidate_count = planner._count_hero_discount(planned_pool)
        hero_bonus_slots = planner.content_lanes.hero_discount_bonus_slots(
            planner.settings.static.planned_queue_size,
            hero_candidate_count,
            len(planned_pool),
        )
        planned_size = planner.settings.static.planned_queue_size + hero_bonus_slots
        reserve_size = max(planner.settings.static.reserve_queue_size - hero_bonus_slots, 0)

        planned, remaining = planner._select_candidates(
            planned_pool,
            planned_size,
            existing_lane_usage.copy(),
            event_slot_limit=SALE_EVENT_EVENT_SLOT_LIMIT if sale_event_context is not None else None,
        )
        planned, remaining = planner._protect_hero_discount_slots(
            planned,
            remaining,
            hero_floor=planner.content_lanes.hero_discount_solo_floor(
                planned_size,
                hero_candidate_count,
                hero_bonus_slots,
            ),
        )
        reserve_source = remaining + [item for item in candidates if item.decision_json['queue_bucket'] == 'reserve']
        reserve, _ = planner._select_candidates(
            reserve_source,
            reserve_size,
            existing_lane_usage.copy(),
            event_slot_limit=None,
        )

        planned_ids = {item.offer.offer_id for item in planned}
        reserve_ids = {item.offer.offer_id for item in reserve}
        for row in rows:
            if row['recommended_post_mode'] == 'hard_suppress':
                continue
            if row['offer_id'] in planned_ids:
                row['recommended_post_mode'] = 'solo_post'
                row['reason_tags'].append('planned_queue')
            elif row['offer_id'] in reserve_ids:
                row['recommended_post_mode'] = 'roundup_candidate'
                row['reason_tags'].append('reserve_queue')
            else:
                row['recommended_post_mode'] = 'capacity_hold'
                row['reason_tags'].append('capacity_hold')

        lane_counts = Counter(row['detected_lane'] for row in rows)
        mode_counts = Counter(row['recommended_post_mode'] for row in rows)
        hero_rows = [row for row in rows if 'hero_discount' in row.get('reason_tags', [])]
        hero_mode_counts = Counter(row['recommended_post_mode'] for row in hero_rows)

        sample: list[dict] = []
        seen_ids: set[str] = set()
        per_mode_limits = [
            ('solo_post', max(4, sample_size // 4)),
            ('roundup_candidate', max(4, sample_size // 4)),
            ('capacity_hold', max(4, sample_size // 4)),
            ('hard_suppress', max(4, sample_size // 5)),
        ]
        for mode, limit in per_mode_limits:
            count = 0
            for row in sorted([item for item in rows if item['recommended_post_mode'] == mode], key=row_sort_key):
                if row['offer_id'] in seen_ids:
                    continue
                sample.append(row)
                seen_ids.add(row['offer_id'])
                count += 1
                if count >= limit:
                    break
        for row in sorted(rows, key=row_sort_key):
            if len(sample) >= sample_size:
                break
            if row['offer_id'] in seen_ids:
                continue
            sample.append(row)
            seen_ids.add(row['offer_id'])

        payload = {
            'generated_at_utc': now_utc.isoformat(),
            'summary': {
                'classified_total': len(rows),
                'offers_per_lane': dict(sorted(lane_counts.items())),
                'solo_post': mode_counts.get('solo_post', 0),
                'roundup_candidate': mode_counts.get('roundup_candidate', 0),
                'capacity_hold': mode_counts.get('capacity_hold', 0),
                'hard_suppress': mode_counts.get('hard_suppress', 0),
                'hero_discount_total': len(hero_rows),
                'hero_discount_solo_post': hero_mode_counts.get('solo_post', 0),
                'hero_discount_roundup_candidate': hero_mode_counts.get('roundup_candidate', 0),
                'hero_discount_capacity_hold': hero_mode_counts.get('capacity_hold', 0),
                'solo_post_examples': [row['offer_title'] for row in sorted([item for item in rows if item['recommended_post_mode'] == 'solo_post'], key=row_sort_key)[:15]],
                'roundup_examples': [row['offer_title'] for row in sorted([item for item in rows if item['recommended_post_mode'] == 'roundup_candidate'], key=row_sort_key)[:15]],
                'capacity_hold_examples': [row['offer_title'] for row in sorted([item for item in rows if item['recommended_post_mode'] == 'capacity_hold'], key=row_sort_key)[:15]],
                'hard_suppress_examples': [row['offer_title'] for row in sorted([item for item in rows if item['recommended_post_mode'] == 'hard_suppress'], key=row_sort_key)[:15]],
            },
            'sample': sample,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return output_path


async def async_main() -> None:
    args = parse_args()
    path = await build_report(args.output, args.sample_size)
    print(str(path))


if __name__ == '__main__':
    asyncio.run(async_main())
