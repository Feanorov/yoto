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

The exporter reads an existing report from disk, normalizes it into `VideoOffer`, and saves both JSON artifacts for review.

This is QA/export only. It does not render scenes, does not call FFmpeg, and does not generate MP4 output.

## Remaining Limitations

Current limits of VIDEO-01:

- only the normalized single-offer contract is defined
- no renderer integration
- no FFmpeg integration
- no MP4 generation
- no production command wiring
- no old `video_generator` reuse in runtime
- no automatic scene timing beyond the 14-18 second target band
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
