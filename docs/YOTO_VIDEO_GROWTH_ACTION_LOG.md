# YOTO VIDEO / GROWTH ACTION LOG

## Current HEAD

Branch focus:
YOTO Video Strategy / Growth

Current phase:
VIDEO-01-NORMALIZED-VIDEO-OFFER-CONTRACT

Current next action:
Create normalized VideoOffer adapter from YOTO preview/pinned_publish artifacts.

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
