# PARTIAL_REUSE

Old `video_generator/` is not usable as-is for the new YOTO Video MVP, but it is also not dead code that should be dropped blindly. The package still has working helper layers, current-project touchpoints, and a mostly green test suite. The right read is: keep it as audited reference, selectively reuse low-level helpers, and rewrite the planning/render pipeline around a new MVP contract.

## Verdict

- `PARTIAL_REUSE`
- Reuse candidates are mostly helper/infrastructure pieces:
  `manifest_loader.py`, `asset_resolver.py`, `font_loader.py`, `ffmpeg_renderer.py`, `run_worker.py`, and parts of `cli.py`.
- Rewrite candidates are the MVP-shaping pieces:
  `entities.py`, `scene_planner.py`, `template_selector.py`, `scene_image_renderer.py`, and `render_manifest.py`.
- Keep-as-reference candidates are the voice-ready branch and old proof-of-concept artifacts:
  `voice_script_builder.py` and `build_voice_ready_package.py`.

## Folder Inventory

### Runtime Python modules

- 21 runtime `.py` modules under `video_generator/`:
  `__main__.py`, `cli.py`, 3 use cases, 4 domain files, and 6 infrastructure files plus package `__init__` files.
- Native entry points:
  `python -m video_generator`
  `video_generator.__main__`
  `video_generator.cli.main()`

### CLI entry points and modes

- Default worker pass:
  `python -m video_generator`
- Continuous worker:
  `python -m video_generator --loop`
- Voice-ready package builder:
  `python -m video_generator --package-manifest <path>`
- Main CLI flags:
  `--manifests-dir`
  `--videos-dir`
  `--temp-scenes-dir`
  `--voice-ready-output-dir`
  `--ffmpeg-bin`
  `--sleep-seconds`
  `--skip-preview-video`

### Tests

- 7 test files
- 33 collected tests
- Files:
  `video_generator/tests/test_asset_resolver.py`
  `video_generator/tests/test_font_loader.py`
  `video_generator/tests/test_isolation.py`
  `video_generator/tests/test_manifest_loader.py`
  `video_generator/tests/test_pipeline.py`
  `video_generator/tests/test_scene_planner.py`
  `video_generator/tests/test_voice_ready_package.py`

### Assets, fonts, cache, smoke files, generated artifacts

- `assets/`
  - `default_background.png`
  - `fallback_game_image.png`
  - `badges/` exists but is currently empty
  - `cache/` has 12 files, total `4,835,955` bytes
  - `fonts/` has 7 files, total `7,533,835` bytes
- Fonts shipped in repo:
  `arial.ttf`
  `arialbd.ttf`
  `segoeui.ttf`
  `segoeuib.ttf`
  `tahoma.ttf`
  `tahomabd.ttf`
  `README.txt`
- `smoke_test/`
  - `assets/` has 2 local images
  - `manifests/` has 1 manifest
  - `videos/` has 1 generated `.mp4` and 1 generated `.json`
  - `temp/video_scenes/` directory exists and is currently empty
- Smoke generated artifacts in repo:
  - `video_df1a168...5811e.mp4` at `94,650` bytes
  - `video_df1a168...5811e.json` at `1,365` bytes

### Runtime junk currently present

- 6 `__pycache__/` directories
- 27 `.pyc` files

## Module Classification

| Module | Classification | Why |
|---|---|---|
| `video_generator/cli.py` | `REUSE_WITH_SMALL_CHANGES` | The composition root and file-based worker wiring are still useful, but current flags and modes are shaped around the old render path and the voice-ready branch. |
| `video_generator/domain/entities.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | The scene model is built around `headline/body/cta/voiceover_text` and the old static-scene pipeline, not gameplay-first MVP scenes. |
| `video_generator/domain/scene_planner.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | Hardcoded 3-scene offer flow and 4-scene roundup flow with fixed 10-second totals do not match the new 14-18 second gameplay-first MVP. |
| `video_generator/domain/template_selector.py` | `KEEP_AS_REFERENCE` | Useful only as old theme mapping by content type; it is too tied to the old palette/template families to be a direct MVP base. |
| `video_generator/domain/voice_script_builder.py` | `KEEP_AS_REFERENCE` | Not MVP-default because voice is future work, but it contains real parsing logic for `caption_html`, prices, deadlines, and freebie wording. |
| `video_generator/infrastructure/manifest_loader.py` | `REUSE_WITH_SMALL_CHANGES` | Already handles both old list-style and current dict-style `asset_refs`, computes stable hashes, and accepts manifest v2 payloads. |
| `video_generator/infrastructure/asset_resolver.py` | `REUSE_WITH_SMALL_CHANGES` | Download/cache/materialize/validate behavior is reusable, but the role model is too narrow for gameplay opener, trailer, and per-platform render inputs. |
| `video_generator/infrastructure/scene_image_renderer.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | Renders static vertical poster scenes with text panels; no motion, no opener clip support, no platform endcards, no safe-zone variants. |
| `video_generator/infrastructure/ffmpeg_renderer.py` | `REUSE_WITH_SMALL_CHANGES` | The concat/export shell is useful, but it currently only loops still PNG scenes and emits silent H.264 video without audio or platform variants. |
| `video_generator/infrastructure/font_loader.py` | `REUSE_WITH_SMALL_CHANGES` | Cyrillic-capable font resolution and bootstrap behavior are still useful for video overlays. |
| `video_generator/application/use_cases/render_manifest.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | The orchestration shape is clean, but it bakes in the old planner/template/static-scene render sequence. |
| `video_generator/application/use_cases/run_worker.py` | `REUSE_WITH_SMALL_CHANGES` | File discovery, skip-on-second-pass behavior, and failure signature tracking are generic and reusable. |
| `video_generator/application/use_cases/build_voice_ready_package.py` | `KEEP_AS_REFERENCE` | Useful reference for future voice experiments and already used by current tooling, but not core to the no-voice MVP path. |
| `video_generator/tests/test_manifest_loader.py` | `REUSE_WITH_SMALL_CHANGES` | Good coverage for manifest v1/v2 loading and remote asset materialization. |
| `video_generator/tests/test_asset_resolver.py` | `REUSE_WITH_SMALL_CHANGES` | Useful regression coverage for small-asset rescue behavior. |
| `video_generator/tests/test_font_loader.py` | `REUSE_WITH_SMALL_CHANGES` | Still relevant for deterministic font fallback behavior. |
| `video_generator/tests/test_scene_planner.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | Encodes the old 3-scene/4-scene contract and old timing assumptions. |
| `video_generator/tests/test_pipeline.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | Encodes the old static scene pipeline and old artifact expectations. |
| `video_generator/tests/test_voice_ready_package.py` | `KEEP_AS_REFERENCE` | Still useful only if voice-ready tooling remains supported. |
| `video_generator/tests/test_isolation.py` | `REWRITE_FOR_NEW_YOTO_VIDEO_MVP` | The intent is useful, but the current rule is broken by BOM files and no longer matches the actual package dependency boundary. |

## Useful Components

- `manifest_loader.py`
  Current loader already accepts current-style manifest v2 payloads and old list-style payloads.
- `asset_resolver.py`
  Remote/local materialization, cache naming, image validation, and placeholder fallback are reusable.
- `font_loader.py`
  Repo-local Cyrillic font fallback is valuable for deterministic render output.
- `ffmpeg_renderer.py`
  Minimal but useful MP4 export shell.
- `run_worker.py`
  Good skeleton for manifest polling and file-based processing.
- `cli.py`
  Good composition-root reference if a standalone worker remains desirable.

## Components To Rewrite

- `scene_planner.py`
  Old flow is `hook -> summary -> urgency` or `hook -> roundup_page_one -> roundup_page_two -> urgency`.
- `scene_image_renderer.py`
  Old visuals are static poster scenes, not gameplay-first video scenes.
- `render_manifest.py`
  Old orchestration assumes still-image scene generation and simple concat.
- `entities.py`
  The current dataclasses are too voice/text-overlay centric for the new normalized video offer contract.

## Components To Ignore Or Delete Later

- `video_generator/__pycache__/`
- `video_generator/**/*.pyc`
- `video_generator/assets/cache/*`
- `video_generator/smoke_test/temp/*`
- `video_generator/smoke_test/videos/*.mp4`
- `video_generator/smoke_test/videos/*.json`
- `video_generator/assets/default_background.png`
- `video_generator/assets/fallback_game_image.png`

Notes:

- Do not delete the placeholder PNGs until the new renderer has its own fallback strategy.
- Do not delete the font files blindly; `FontLoader` actively depends on them.
- Do not delete the voice-ready branch blindly; current repo tooling still references it.

## Test Status

### Exact commands used

- Attempted:
  `pytest video_generator/tests -q`
- Result:
  failed because `pytest` is not on PATH in this workspace shell.
- Attempted:
  `python -m pytest video_generator/tests -q`
- Result:
  failed because `python` is not on PATH in this workspace shell.
- Successful command:
  `D:\Telegram\.venv\Scripts\python.exe -m pytest video_generator/tests -q`
- Collection check:
  `D:\Telegram\.venv\Scripts\python.exe -m pytest video_generator/tests --collect-only -q`

### Observed result

- `33` tests collected
- `32` passed
- `1` failed

### Failing test

- Failing test:
  `video_generator/tests/test_isolation.py::test_video_generator_package_stays_isolated_from_existing_project_layers`
- Immediate failure reason:
  `ast.parse(...)` crashes on UTF-8 BOM-prefixed source files inside `video_generator/`
- First exact failure hit during the run:
  `video_generator/application/use_cases/build_voice_ready_package.py`
  `SyntaxError: invalid non-printable character U+FEFF`

### Additional manual inspection behind the failure

- BOM-prefixed Python files found:
  `video_generator/cli.py`
  `video_generator/application/use_cases/build_voice_ready_package.py`
  `video_generator/domain/scene_planner.py`
  `video_generator/domain/voice_script_builder.py`
  `video_generator/tests/test_pipeline.py`
  `video_generator/tests/test_voice_ready_package.py`
- Real isolation breach found after parsing with `utf-8-sig`:
  `video_generator/domain/voice_script_builder.py` imports `dealbot.utils.ua`

### Interpretation

- The single red test is not a render bug.
- It is a repository hygiene plus boundary issue:
  BOM-encoded `.py` files break the AST-based isolation test before it can finish.
- Even after BOM cleanup, the current isolation contract would still fail because the voice-ready path depends on current project code in `dealbot.utils.ua`.

### Dependency read

- Old generator is not fully standalone anymore.
- Confirmed dependency on current project modules:
  `dealbot.utils.ua`
- The rendering tests do not require real FFmpeg because they stub the renderer.
- Remote asset tests use a local in-process HTTP server, not external network.

## Current YOTO Compatibility

### What is directly compatible today

- Current manifest v2 payloads emitted by `application/use_cases/generate_video_manifests.py`
- Evidence:
  `video_generator.ManifestLoader + TemplateSelector + ScenePlanner` successfully load and plan a current file such as `output/video_manifests/20260516T162726Z_video_manifest_steam_227300.json`
- Additional evidence:
  existing current `output/video_voice_ready/*/package_manifest.json` files point back to current `output/video_manifests/*.json`, so the voice-ready path has already consumed current manifests in practice

### What is not directly compatible today

- Operator preview report JSON
- `pinned_publish` payload JSON
- Raw `caption_html + image_path + offer_snapshot + decision_snapshot` bundles

The old generator expects a video-manifest-shaped payload, not an operator-report-shaped payload.

### Field support matrix

| Current YOTO field | Old generator support | Notes |
|---|---|---|
| `title` | `YES` | Uses top-level `short_title`; voice-ready path also reads `voice_facts.title`. |
| `store/platform` | `PARTIAL` | Uses `context.store` and sometimes `context.source`; no richer platform-target contract. |
| `discount` | `PARTIAL` | Supported through `voice_facts.discount_percent` or already-baked text in `hook_line`. |
| `current price` | `PARTIAL` | Voice-ready path supports `voice_facts.price_after_minor`; base render path does not render a dedicated proof block. |
| `old price` | `PARTIAL` | Voice-ready path supports `voice_facts.price_before_minor`; base render path does not render a dedicated proof block. |
| `savings` | `NO` | No dedicated `savings` field is read or displayed. |
| `reviews` | `NO` | Current v2 manifest may carry `voice_facts.review_count`, but old generator does not consume it. |
| `positive %` | `NO` | Current v2 manifest may carry `voice_facts.review_score`, but old generator does not consume it. |
| `deadline` | `PARTIAL` | Uses `urgency_line`; voice-ready path also reads `voice_facts.promo_end`. |
| `store URL` | `NO` | Current v2 manifest may carry `voice_facts.store_url`, but old generator does not use it. |
| `generated card image` | `PARTIAL` | `card_image` and `source_artifact.image_path` are used in some paths, but not as a universal primary render source. |
| `official screenshots` | `PARTIAL` | Supports single `game_image` and `background` refs; no richer multi-frame gameplay contract. |
| `trailer refs` | `NO` | No trailer/video input contract exists. |

### Important compatibility nuance

- Current YOTO already has a partial adapter path:
  `generate_video_manifests.py` converts live `Offer + decision_json + PostArtifact + image_path` into a manifest v2 that the old package can read.
- That means the old generator is not directly preview-report-native.
- It is manifest-v2-native.

## Missing Adapter Layer

The missing adapter for the new MVP should be explicit and separate:

`YOTO preview report -> normalized video offer object -> video manifest -> renderer`

More concretely:

- `operator_truth_report` or `pinned_publish`
- extract `offer_snapshot`, `decision_snapshot`, `artifact.caption_html`, `artifact.image_path`, and render diagnostics
- normalize into a new video-offer contract:
  gameplay opener candidates
  proof block fields
  trust proof fields
  deadline/CTA/platform fields
  local asset refs
- emit renderer-ready manifest(s)
- render per platform

What is missing right now:

- No adapter from preview report JSON directly into old generator inputs
- No normalized object for gameplay opener/trailer/music/platform outputs
- No explicit per-platform manifest fan-out

## Gaps Against New MVP

| New MVP requirement | Status in old generator | Read |
|---|---|---|
| Gameplay / trailer / motion screenshot opener | `MISSING` | Old planner starts with a static text-led `hook` scene. |
| Motion screenshot fallback | `MISSING` | Old renderer exports still PNG scenes only. |
| Music bed | `MISSING` | FFmpeg path renders silent video only. |
| Platform-specific endcards for TikTok / Shorts / Reels | `MISSING` | No platform dimension in manifest, planner, or renderer. |
| Telegram CTA variants | `MINIMAL ONLY` | CTA is generic and template-hint based, not platform-tailored or A/B structured. |
| 14-18 sec timing contract | `MISSING` | Offer flow totals `10s`; roundup flow also totals `10s`. |
| Safe zones for vertical platforms | `MISSING` | Layout is one fixed 1080x1920 poster layout with no platform-safe variants. |
| No-voice default | `PARTIAL / ALREADY SILENT` | Base render output is silent, but the scene model is still voice-oriented and there is no explicit audio-mode contract. |
| Old price -> new price proof block | `MISSING` | No dedicated on-screen proof component exists. |
| Freebie / deadline proof format | `PARTIAL` | Old templates recognize freebie/event lanes, but there is no normalized proof block matching the new MVP. |
| Batch render per platform | `MISSING` | Worker renders one output per manifest. |
| Telegram invite-link attribution | `MISSING` | No field or output artifact carries invite attribution. |

## Risks

- `video_generator/` is not fully dormant.
  Current repo tooling still references it from `dealbot/operator_cli.py`, `yoto.bat`, docs, and `tools/generate_yoto_voice_ready_review_pack.py`.
- The package has mixed historical assumptions.
  Repo contains both older v1-style manifests and current v2-style manifests.
- Artifact portability is weak.
  Some committed smoke/generated JSON artifacts still point to old absolute paths under `D:\Telegram\...`, not the current portable workspace root.
- Test isolation is misleading in current form.
  It is broken by BOM files and also out of sync with the actual shared-utils dependency.
- Asset cache and pycache contents will keep creating noisy diff risk if the folder is touched during future work.

## Recommended Next Codex Task

Recommended next task:

- `VIDEO-01-NORMALIZED-VIDEO-OFFER-CONTRACT`

Recommended scope:

- Do not integrate rendering yet.
- Define a new normalized `video_offer` contract for the new MVP only.
- Inputs should be current YOTO-native:
  `pinned_publish` or preview report
  `offer_snapshot`
  `decision_snapshot`
  `caption_html`
  `image_path`
  render diagnostics / official asset refs
- Output should be one or more renderer-ready manifests for:
  Telegram-first vertical video
  future per-platform variants

Why this should be next:

- The audit shows the biggest missing piece is not helper code.
- The biggest missing piece is the adapter and contract boundary between current YOTO artifacts and a new gameplay-first video renderer.
