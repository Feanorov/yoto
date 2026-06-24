# YOTO VideoOffer Contract

## Purpose

`VideoOffer` is the first normalized data contract for the new YOTO Video MVP.

It exists to bridge current YOTO preview artifacts and a future renderer-ready video layer without coupling that layer to:

- Telegram publish commands
- Operator UI
- old `video_generator`
- MP4 rendering

The contract is intentionally small and isolated. It converts already resolved YOTO artifacts into a stable single-offer payload that a future video renderer can consume.

## Supported Source Artifacts

The adapter currently supports:

- a YOTO preview truth report that contains `pinned_publish`
- a direct `pinned_publish` payload

The adapter reads defensively from current YOTO-native fields such as:

- `pinned_publish`
- `candidate`
- `artifact`
- `offer_snapshot`
- `decision_snapshot`
- `send_test_target`

## Required Fields

The normalized `VideoOffer` requires these fields to build successfully:

- `offer_id`
- `source_kind`
- `title`
- `store`
- `platform`
- `store_url`
- `caption_html`
- `card_image_path`
- `image_hash`
- `caption_hash`
- `idempotency_key`
- `visual_assets.card_image`
- `cta.default`
- `cta.tiktok`
- `cta.shorts`
- `cta.reels`

`source_report_path` is carried when available. The adapter accepts it as an explicit input because preview reports may be loaded from memory or from disk.

## Optional Fields

The contract preserves optional values when they exist and leaves them as `None` when missing:

- `discount_percent`
- `current_price_text`
- `old_price_text`
- `savings_text`
- `deadline_text`
- `reviews_text`
- `positive_percent_text`
- `achievements_text`
- `cards_text`
- `visual_assets.official_screenshots`
- `visual_assets.official_trailers`
- `visual_assets.fallback_image`

Missing optional fields do not block contract creation.

## Validation Rules

The adapter follows these rules:

- missing required fields raise `VideoOfferValidationError` with the exact missing field names
- prices are not invented
- deadlines are not invented
- reviews and positive percentages are not invented
- optional text can be derived from existing numeric fields when the source already contains those numeric facts
- `voice_mode` defaults to `none`

Offer type resolution:

- if current price looks like `0`, `free`, or a localized free-label token, then `offer_type = freebie`
- else if a discount marker or price pair exists, then `offer_type = discount`
- else `offer_type = unknown`

Template hint resolution:

- `freebie`
- `single_discount`
- `top3`
- `unknown`

## How VideoOffer Becomes A Draft Video Manifest

`build_video_manifest_draft(video_offer)` does not render a video.

It produces a renderer-ready planning dict with:

- `format = vertical_1080x1920`
- target duration range `14..18`
- template `single_offer_gameplay_first`
- `voice_mode`
- `music_required = true`
- five planned scenes
- per-platform CTA endcards

Scene layout:

1. `hook`
2. `identity`
3. `offer_proof`
4. `trust_or_deadline`
5. `telegram_cta`

The draft manifest is intentionally descriptive. It tells a future renderer what to build, not how to encode or export MP4.

## Offline Exporter

An offline QA exporter is available for selected preview artifacts:

- preview report or preview workflow report
- `video_offer.json`
- `draft_video_manifest.json`
- optional `scene_asset_plan.json`
- optional `scene_layout_payload.json`

The exporter reads an existing report from disk, normalizes it into `VideoOffer`, and saves both JSON artifacts for review.

This is QA/export only. It does not render scenes, does not call FFmpeg, and does not generate MP4 output.

`scene_asset_plan.json` is exported only when `--with-scene-plan` is requested. Default exporter behavior remains unchanged.
`scene_layout_payload.json` is exported only when `--with-layout-payload` is requested. That flag also implies `scene_asset_plan.json`.

## VIDEO-03 Scene Asset Planner

`build_scene_asset_plan(video_offer, draft_manifest)` creates a deterministic offline scene plan for the MVP.

Planner guarantees:

- exactly 5 scenes
- fixed order:
  `hook`, `identity`, `offer_proof`, `trust_or_deadline`, `telegram_cta`
- fixed durations:
  `2.0`, `2.5`, `3.0`, `3.0`, `4.0`
- total duration:
  `14.5`
- no downloads
- no asset validation
- no fabricated asset paths
- no invented prices, discounts, deadlines, reviews, ratings, or CTA handles

Scene asset priority:

- `hook`: trailer -> screenshot -> card image -> fallback
- `identity`: screenshot -> trailer -> card image -> fallback
- `offer_proof`: card image -> screenshot -> fallback
- `trust_or_deadline`: screenshot -> card image -> fallback
- `telegram_cta`: card image -> fallback

When only the card image exists, the planner reuses it and emits warnings.

When no visual asset exists, the planner fails clearly.

## VIDEO-04 Scene Layout Payload

`build_scene_layout_payload(video_offer, scene_asset_plan)` converts the 5-scene asset plan into deterministic renderer-ready text/layout payloads.

Layout guarantees:

- exactly 5 layout scenes
- fixed order:
  `hook`, `identity`, `offer_proof`, `trust_or_deadline`, `telegram_cta`
- fixed canvas per scene:
  `1080x1920`
- deterministic safe-zone profiles
- selected visual carried from the scene asset plan
- no invented prices, discounts, deadlines, review stats, or CTA text
- no store URL in CTA payloads
- no rendering, Pillow, FFmpeg, Telegram, or network calls

Per-scene payload fields:

- `scene_id`
- `scene_type`
- `duration_sec`
- `selected_visual`
- `canvas`
- `safe_zone_profile`
- `text_blocks`
- `motion_hint`
- `warnings`

Each `text_block` includes:

- `role`
- `text`
- `priority`
- `required`
- `max_lines`
- `alignment`
- `anchor`
- `size_class`

Scene text rules:

- `hook`:
  large offer headline, max 2 lines, centered in the upper/middle safe area
- `identity`:
  title plus platform/store, max 3 total lines
- `offer_proof`:
  discount/free badge, current price, old price, optional savings when those facts exist
- `trust_or_deadline`:
  deadline first; otherwise positive score/reviews when available
- `telegram_cta`:
  Telegram CTA only, with platform-specific CTA variants preserved and no raw store URL

Current limits after VIDEO-04:

- only normalized single-offer planning contracts are defined
- no renderer integration
- no FFmpeg integration
- no MP4 generation
- no production command wiring
- no old `video_generator` reuse in runtime
- no dynamic scene timing beyond the fixed 14.5-second MVP plan
- no voice script generation

## Why This Is Not A Renderer Task

This task stops at data normalization and planning because the current MVP bottleneck is contract quality, not media export.

`VideoOffer` and the draft manifest are upstream contracts. They make later rendering work safer by ensuring the future video layer receives:

- one resolved offer
- one resolved card image
- known caption and hash identity
- known official/fallback visual references
- stable CTA variants

That is why VIDEO-01 is a contract task, not an MP4 task.
