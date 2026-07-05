# YOTO VIDEO / GROWTH ACTION LOG

## Current HEAD

Branch focus:
YOTO Video Strategy / Growth

Current phase:
VIDEO-07-LOCAL-VISUAL-STAGING-ADAPTER

Current next action:
Stage remote direct-image visuals into local preview artifacts before offline scene preview rendering.

Do not touch:
Operator UI, publish-previewed, VDE, card renderer, caption pipeline, old video_generator behavior.

---

## Log

### 2026-05-25 - Branch opened

- Created YOTO Video Strategy / Growth branch.
- Goal: build short vertical video system for TikTok / Shorts / Reels that drives users to Telegram.
- Main metric: Telegram joins / 1000 views.

### 2026-05-25 - Deep Research result

- Recommended MVP format:
  single-offer, gameplay-first, no-voice vertical video.
- Duration:
  14-18 seconds.
- Structure:
  gameplay/trailer opener -> offer proof -> trust/deadline -> Telegram CTA.
- Voice:
  no voice by default; AI voice only as future A/B test.
- Mascot:
  not core MVP; possible future branding layer.
- Top-3:
  second wave, not first acquisition format.

### 2026-05-25 - Old video_generator audit

- Old video_generator audited.
- Document:
  docs/YOTO_VIDEO_OLD_GENERATOR_AUDIT.md
- Verdict:
  PARTIAL_REUSE
- Tests:
  32 passed, 1 failed
- Failure:
  isolation/hygiene issue caused by BOM files and dealbot.utils.ua import in voice_script_builder.py.
- Decision:
  do not delete folder, do not integrate old pipeline, keep low-level helpers as reference.

### 2026-05-25 - VIDEO-01 selected

- Next Codex task:
  VIDEO-01-NORMALIZED-VIDEO-OFFER-CONTRACT
- Goal:
  create adapter:
  preview report / pinned_publish -> VideoOffer -> draft video manifest
- Scope:
  no MP4 rendering, no UI changes, no production integration.

### 2026-05-25 - VIDEO-01 implementation

- Create isolated video contract namespace.
- Create VideoOffer model.
- Create adapter from preview/pinned_publish-like reports.
- Create draft video manifest builder.
- Add tests.
- Keep old video_generator untouched.

### 2026-05-25 - VIDEO-02 selected

- Next Codex task:
  VIDEO-02-DRAFT-MANIFEST-EXPORTER
- Goal:
  export VideoOffer JSON and draft video manifest JSON from a selected preview report.
- Scope:
  offline QA only, no MP4 rendering, no UI wiring, no production behavior changes.

### 2026-05-25 - VIDEO-02 implementation

- Added offline exporter for selected preview reports.
- Added JSON artifacts:
  video_offer.json
  draft_video_manifest.json
- Added tests.
- Production behavior unchanged.

### 2026-06-18 - VIDEO-03 selected

- Next Codex task:
  VIDEO-03-SCENE-ASSET-PLANNER
- Goal:
  create deterministic offline scene planner:
  VideoOffer + draft manifest -> scene_asset_plan.json
- Scope:
  no rendering, no MP4, no FFmpeg, no UI wiring, no Telegram integration.

### 2026-06-18 - VIDEO-03 implementation

- Added `dealbot/video/scene_planner.py`.
- Added deterministic 5-scene asset selection plan with fixed MVP timings.
- Added optional exporter / CLI flag:
  `--with-scene-plan`
- Added `scene_asset_plan.json` export for QA only.
- Added tests for asset priority, card-only warnings, no-visual failure, deterministic ordering, and exporter flag wiring.
- Production behavior unchanged by default.

### 2026-06-25 - VIDEO-04 selected

- Next Codex task:
  VIDEO-04-SCENE-LAYOUT-PAYLOAD
- Goal:
  convert the deterministic 5-scene asset plan into renderer-ready text/layout payloads
- Scope:
  offline only, no rendering, no MP4, no Telegram, no UI wiring

### 2026-06-25 - VIDEO-04 implementation

- Added `dealbot/video/layout_builder.py`.
- Added deterministic scene text block and safe-zone payload generation from `VideoOffer + SceneAssetPlan`.
- Added optional exporter / CLI flag:
  `--with-layout-payload`
- `--with-layout-payload` implies scene planning and exports:
  `scene_asset_plan.json`
  `scene_layout_payload.json`
- Added tests for stable layout ordering, required text blocks, CTA variant preservation, non-fabrication, and exporter flag behavior.
- Production behavior unchanged by default.

### 2026-06-25 - VIDEO-05 selected

- Next Codex task:
  VIDEO-05-RENDERER-INPUT-ADAPTER
- Goal:
  convert `VideoOffer + SceneAssetPlan + SceneLayoutPayload` into deterministic renderer-facing input JSON
- Scope:
  offline only, no rendering, no MP4, no UI wiring, no Telegram integration

### 2026-06-25 - VIDEO-05 implementation

- Added `dealbot/video/renderer_input_adapter.py`.
- Added strict cross-contract validation for scene IDs, order, types, durations, selected visuals, and canvas.
- Added optional exporter / CLI flag:
  `--with-renderer-input`
- `--with-renderer-input` implies:
  `scene_asset_plan.json`
  `scene_layout_payload.json`
  `renderer_input.json`
- Added renderer metadata on export results:
  `renderer_input_json_path`
  `renderer_scene_count`
  `renderer_total_duration_sec`
- Added tests for deterministic timestamps, strict mismatch failures, CTA preservation, non-fabrication, and export flag behavior.
- Production behavior unchanged by default.

### 2026-06-25 - VIDEO-06 selected

- Next Codex task:
  VIDEO-06-OFFLINE-SCENE-PREVIEW-RENDERER
- Goal:
  render deterministic vertical PNG scene previews from `renderer_input.json`
- Scope:
  offline only, no MP4, no FFmpeg, no UI wiring, no Telegram integration

### 2026-06-25 - VIDEO-06 implementation

- Added `dealbot/video/scene_preview_renderer.py`.
- Added offline Pillow-based preview rendering for the 5 renderer scenes.
- Added optional exporter / CLI flag:
  `--render-scene-previews`
- `--render-scene-previews` implies:
  `scene_asset_plan.json`
  `scene_layout_payload.json`
  `renderer_input.json`
  `scene_previews/*.png`
- Added exporter metadata:
  `scene_previews_dir_path`
  `rendered_scene_count`
- Added tests for deterministic filenames, local visual rendering, safe-zone text fitting, Cyrillic rendering, clear failure modes, and flag wiring.
- Production behavior unchanged by default.

### 2026-07-05 - VIDEO-07 selected

- Next Codex task:
  VIDEO-07-LOCAL-VISUAL-STAGING-ADAPTER
- Goal:
  convert remote renderer visual refs into staged local still-image files before preview rendering
- Scope:
  offline-safe preview preparation only, no MP4, no FFmpeg, no UI wiring, no Telegram integration

### 2026-07-05 - VIDEO-07 implementation

- Added `dealbot/video/visual_staging.py`.
- Added `stage_renderer_visuals(renderer_input, output_dir)` for staged-local visual rewrites.
- Added optional exporter / CLI flag:
  `--stage-visuals`
- `--stage-visuals` implies:
  `renderer_input.json`
  `renderer_input_staged.json`
  `staged_visuals/*`
- `--render-scene-previews` now stages remote direct-image visuals before rendering PNG previews.
- Preview renderer remains strict:
  raw remote URLs still fail when passed directly.
- Added tests for remote staging, local preservation, clear failure modes, staged exporter artifacts, and preview rendering through staged visuals.
- Production behavior unchanged without staging / preview flags.
