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
- optional `renderer_input.json`
- optional `scene_visual_qa_report.json`
- optional `scene_previews/01_hook.png` .. `05_telegram_cta.png`

The exporter reads an existing report from disk, normalizes it into `VideoOffer`, and saves offline review artifacts.

This is QA/export only. It does not call FFmpeg and does not generate MP4 output. PNG scene previews are rendered only when `--render-scene-previews` is explicitly requested.

`scene_asset_plan.json` is exported only when `--with-scene-plan` is requested. Default exporter behavior remains unchanged.
`scene_layout_payload.json` is exported only when `--with-layout-payload` is requested. That flag also implies `scene_asset_plan.json`.
`renderer_input.json` is exported only when `--with-renderer-input` is requested. That flag also implies `scene_asset_plan.json` and `scene_layout_payload.json`.
`scene_visual_qa_report.json` is exported only when `--with-visual-qa-report` is requested, or automatically when scene previews are rendered. That flag implies `renderer_input.json`.
`renderer_input_staged.json` and `staged_visuals/*` are exported only when `--stage-visuals` is requested, or when scene previews need staged local visuals.
`scene_previews/*.png` are rendered only when `--render-scene-previews` is requested. That flag also implies `scene_asset_plan.json`, `scene_layout_payload.json`, `renderer_input.json`, staged-local visual preparation, and `scene_visual_qa_report.json` before preview rendering.

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

## VIDEO-05 Renderer Input Adapter

`build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)` converts the offline planning contracts into a deterministic renderer-facing input payload.

Renderer input guarantees:

- `schema_version = 1`
- exactly 5 scenes
- fixed scene order:
  `hook`, `identity`, `offer_proof`, `trust_or_deadline`, `telegram_cta`
- fixed top-level canvas:
  `1080x1920`
- `fps = 30`
- cumulative `start_sec` / `end_sec` timestamps built deterministically from scene durations
- `total_duration_sec` must match the layout payload scene timing
- strict validation across upstream contracts for:
  `offer_id`, scene IDs, order, scene types, durations, selected visuals, and canvas
- no invented facts, text, asset refs, URLs, Telegram handles, or rendering outputs
- no rendering, Pillow, FFmpeg, Telegram, UI, or network calls

Top-level renderer fields:

- `schema_version`
- `offer_id`
- `template`
- `format`
- `canvas`
- `total_duration_sec`
- `fps`
- `voice_mode`
- `music_required`
- `scenes`
- `warnings`

Each renderer scene includes:

- `scene_id`
- `order`
- `scene_type`
- `start_sec`
- `end_sec`
- `duration_sec`
- `visual`
- `text_blocks`
- `safe_zone_profile`
- `motion`
- `warnings`

The CTA renderer scene also preserves `platform_variants` when they exist so downstream renderers can keep TikTok / Shorts / Reels CTA text available without re-deriving it.

## VIDEO-06 Offline Scene Preview Renderer

`render_scene_previews(renderer_input, output_dir)` renders deterministic offline PNG previews from the existing renderer input contract.

Preview renderer guarantees:

- exactly 5 PNG files
- fixed filenames:
  `01_hook.png`
  `02_identity.png`
  `03_offer_proof.png`
  `04_trust_or_deadline.png`
  `05_telegram_cta.png`
- fixed canvas per image:
  `1080x1920`
- deterministic scene order from `renderer_input.scenes`
- local still-image visuals only
- cover-cropped backgrounds
- restrained dark readability overlay
- text layout that respects `role`, `priority`, `alignment`, `anchor`, `size_class`, `max_lines`, and `safe_zone_profile`
- no downloads
- no FFmpeg
- no MP4 output
- no invented images, text, prices, or asset paths

Operational limits:

- a usable local Unicode font must exist; the renderer checks `YOTO_SCENE_PREVIEW_FONT_PATH` first, then local system font fallbacks
- remote URLs and local non-image files fail clearly
- trailer/video refs are not rendered into frames

Current limits after VIDEO-06:

- only normalized single-offer planning contracts are defined
- no renderer integration
- no FFmpeg integration
- no MP4 generation
- no production command wiring
- no old `video_generator` reuse in runtime
- no dynamic scene timing beyond the fixed 14.5-second MVP plan
- no voice script generation

## VIDEO-07 Local Visual Staging Adapter

`stage_renderer_visuals(renderer_input, output_dir)` converts renderer-scene visual refs into preview-safe local still images before PNG scene rendering.

Visual staging guarantees:

- `renderer_input.json` stays unchanged as the raw upstream contract artifact
- remote image refs are rewritten only in a separate staged payload:
  `renderer_input_staged.json`
- allowed remote sources are limited to direct image assets with:
  `.jpg`, `.jpeg`, `.png`, `.webp`
- URLs without an image extension are accepted only when the response returns a safe supported image content-type
- unsupported schemes, trailer/video refs, non-image URLs, and missing local files fail clearly
- staged downloads are written into:
  `staged_visuals/`
- scene order, durations, timestamps, text blocks, motion hints, safe-zone profiles, CTA variants, and warnings are preserved exactly
- preview rendering still rejects raw remote URLs; it only succeeds after staged-local rewrite
- no Steam API calls
- no page scraping
- no Telegram, FFmpeg, UI, or MP4 integration

Exporter behavior after VIDEO-07:

- `--stage-visuals` implies `--with-renderer-input`
- `--stage-visuals` writes:
  `renderer_input.json`
  `renderer_input_staged.json`
  `staged_visuals/*`
- `--render-scene-previews` stages visuals first and renders previews from the staged local payload
- default exporter behavior without staging or preview flags remains unchanged

## VIDEO-08 Scene Visual QA Report

`build_scene_visual_qa_report(renderer_input)` inspects renderer-scene visuals offline and produces `scene_visual_qa_report.json` before any future MP4 work.

Visual QA guarantees:

- accepts either raw `renderer_input` or staged-local `renderer_input_staged`
- does not modify images
- uses Pillow only for local image dimension inspection
- reports:
  missing visual files
  remote visual URLs
  unsupported visual file extensions
  duplicate visual reuse across scenes
  fallback/card-image visual usage
  non-vertical source aspect-ratio risk
  very small source images
  empty text blocks
  scenes with too many text blocks
  CTA scenes missing primary CTA text
  scene-count mismatch from the 5-scene MVP contract
- no FFmpeg
- no MP4 rendering
- no Telegram, UI, Steam API, or page-scraping calls

Report structure includes:

- `status`
- `error_count`
- `warning_count`
- top-level `findings`
- per-scene QA entries under `scenes`
- duplicate reuse groups under `duplicate_visual_groups`

Exporter behavior after VIDEO-08:

- `--with-visual-qa-report` implies `--with-renderer-input`
- when staged renderer input exists, visual QA uses the staged payload instead of raw remote refs
- `--render-scene-previews` now writes `scene_visual_qa_report.json` automatically after staging and before preview rendering
- default exporter behavior without QA / staging / preview flags remains unchanged

## Why This Is Not A Renderer Task

This task stops at data normalization and planning because the current MVP bottleneck is contract quality, not media export.

`VideoOffer` and the draft manifest are upstream contracts. They make later rendering work safer by ensuring the future video layer receives:

- one resolved offer
- one resolved card image
- known caption and hash identity
- known official/fallback visual references
- stable CTA variants

That is why VIDEO-01 is a contract task, not an MP4 task.
