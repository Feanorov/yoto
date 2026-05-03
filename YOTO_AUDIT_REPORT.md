# YOTO Audit Report

## Scope

- Repository root: `D:\Telegram_portable_bundle`
- Git branch: `dev`
- HEAD commit: `4d33151b532c514a4fcc7d29e99e7946d04a5d88`
- Audit mode: factual only, no code changes

## Audit-local verification actually run

- `py_compile` on the current YOTO/image/provider/smoke files: PASS
- Targeted test suite:
  - Command: `D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_asset_cache.py tests/test_official_asset_source.py tests/test_visual_decision_engine.py tests/test_ai_card_smoke.py`
  - Result: `27 passed, 1 failed`
  - Current failing test: `tests/test_ai_card_smoke.py::test_ai_card_smoke_quality_reject_uses_valid_decision_asset_before_ai`
  - Observed failure: runtime selected `steam_library_capsule`, while the test still expects `official_press_key_art` or `steam_main_capsule`
- Local smoke run 1:
  - Command: `D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py current_env --runs 1 --debug-ai`
  - Result: `provider_attempted = comfyui`, `provider = comfyui`, `final_source = ai`, `ai_source_mode = reference_assisted`
  - Output batch: `D:\Telegram_portable_bundle\output\cards\ai_card_smoke_batch_current_env_20260425T105040055346Z\batch_summary.json`
- Local smoke run 2:
  - Command: `D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py quality_reject --runs 1 --game-set minimal --debug-ai`
  - Result summary: `total_runs = 5`, `ai_fallback_count = 1`, `ai_attempted_true_runs = 1`, `fallback_used_runs = 1`
  - Output batch: `D:\Telegram_portable_bundle\output\cards\ai_card_smoke_batch_quality_reject_20260425T104902276418Z\batch_summary.json`

## 1. Current card pipeline entrypoints

### Production offer pipeline

- `dealbot/main.py`
  - `BotRuntime.__aenter__()` wires `CardRendererRouter(...)` into `DryRunRenderUseCase(...)`
- `application/use_cases/dry_run_render.py`
  - `DryRunRenderUseCase.execute()` calls `self.renderer.render(...)`
- `infrastructure/render/cards/renderer_selector.py`
  - `CardRendererRouter.render()` routes to legacy or YOTO
  - `YotoCardRendererV42Adapter.render()` builds `YotoCardData` and calls `YotoCardEngineV4.render_card(...)`
- `infrastructure/render/cards/yoto_card_engine_v4.py`
  - `YotoCardEngineV4.render_card(...)` is the final card render entrypoint

### Roundup/top-list pipeline

- `application/use_cases/generate_roundup_artifacts.py`
  - `_render_roundup_cards()` calls `roundup_card_adapter.render(roundup)`
- `infrastructure/render/cards/roundup_top_list_card_adapter.py`
  - `RoundupTopListCardAdapter.render(...)` builds `YotoCardData(type=TOP_LIST)` and calls `YotoCardEngineV4.render_card(...)`

### Smoke/runtime-proof entrypoint

- `tools/ai_card_smoke.py`
  - CLI entrypoint: `main()`
  - Single run entrypoint: `run_scenario(...)`
  - Batch entrypoint: `render_ai_card_smoke(...)`

### Operator/wrapper entrypoints found

- `yoto.bat`
  - Exact action names found: `preview`, `preview-offline`, `preview-golden`, `send-test`, `send-test-offline`, `send-test-golden`, `daily-check`, `doctor`, `status`, `latest-artifacts`, `build-voice-package`, `run`, `run-once`, `run-once-offline`, `run-once-golden`, `snapshot-offline`, `snapshot-golden`, `test-planner`, `test-caption`, `test-cards`, `test-publish`, `test-video`, `generate-captions`, `generate-captions-offline`, `generate-captions-golden`, `generate-cards`, `generate-cards-offline`, `generate-cards-golden`, `video-worker`, `video-loop`, `video-smoke`
- `dealbot/operator_cli.py`
  - Exact subcommands found: `preview`, `send-test`, `daily-check`, `doctor`, `latest-artifacts`, `build-voice-package`

## 2. Current AI / ComfyUI provider files

- `infrastructure/render/cards/image_providers/base.py`
  - Defines `IMAGE_PIPELINE_VERSION = 'v1'`
  - Defines valid modes: `artwork_only`, `artwork_then_ai`, `ai_first`
  - Defines `ImageResolutionRequest` and `ResolvedImage`
- `infrastructure/render/cards/image_providers/artwork_provider.py`
  - `ArtworkImageProvider`
  - Resolves local/readable artwork into `selected_source = artwork`
- `infrastructure/render/cards/image_providers/comfyui_provider.py`
  - `ComfyUIImageProvider`
  - Supports `reference_assisted` and `pure_generation`
  - Tracks detailed ComfyUI diagnostics in `latest_diagnostics`
  - Pure-generation output path: `output/cards/comfyui_generated`
- `infrastructure/render/cards/image_providers/placeholder_provider.py`
  - `PlaceholderImageProvider`
  - Returns `selected_source = placeholder`
- `infrastructure/render/cards/image_providers/resolver.py`
  - `YotoImageResolver`
  - Orchestrates artwork -> AI -> placeholder selection and attaches resolver trace
- `infrastructure/render/cards/image_providers/__init__.py`
  - Re-exports the current provider/resolver symbols

## 3. Current resolver / visual decision files

- `infrastructure/render/cards/image_providers/resolver.py`
  - Current resolver order and fallback policy
  - Attaches `resolver_trace`, `decision_reason`, `actual_image_source_type`, `actual_image_path_or_url`
- `infrastructure/render/cards/visual_decision_engine.py`
  - Current official-first cover decision logic
  - Exposes `build_cover_decision(...)`
  - Exposes `resolve_cover_decision_asset_bridge(...)`
  - Current hardcoded thresholds:
    - `MIN_READABILITY_SCORE = 0.55`
    - `MIN_FOCUS_SCORE = 0.50`
    - `CLOSE_SCORE_OFFICIAL_TIEBREAK_THRESHOLD = 0.03`
- `infrastructure/render/cards/asset_source.py`
  - Resolves existing local asset paths and `file://` asset paths
- `infrastructure/render/cards/asset_sources/official_asset_source.py`
  - Builds official/local/fallback asset candidate lists
  - Builds deterministic cache paths
  - Optional remote asset download support
- `infrastructure/render/cards/asset_sources/asset_cache.py`
  - Validates cached images
  - Downloads remote image assets into the cache contract

## 4. Current smoke / test tools

### Smoke / runtime tools

- `tools/ai_card_smoke.py`
  - Scenarios found: `current_env`, `broken_comfyui`, `quality_reject`, `pure_generation`
  - CLI flags found: `--runs`, `--debug-ai`, `--prompt-variant`, `--game-set`, `--game-eval`, `--seeds-per-game`, `--compare-prompt-variants`, `--download-assets`
- `yoto.bat test-cards`
  - Runs: `tests/test_renderer_selector_arch.py`, `tests/test_render_diagnostics_arch.py`, `tests/test_yoto_card_engine_v4.py`

### Current YOTO/image-specific tests found

- `tests/test_ai_card_smoke.py`
- `tests/test_visual_decision_engine.py`
- `tests/test_official_asset_source.py`
- `tests/test_asset_cache.py`
- `tests/test_renderer_selector_arch.py`
- `tests/test_yoto_card_engine_v4.py`

### Pytest config

- `pytest.ini`
  - `norecursedirs = legacy .venv output`

## 5. Current config / env flags related to images, AI, providers, scoring

### Env/config flags found

| Name | Source file | Current/default value found | Notes |
|---|---|---|---|
| `CARD_OUTPUT_DIR` | `.env.example`, `dealbot/settings.py` | `output/cards` | Final card output root in app settings |
| `CARD_RENDERER_MODE` | `.env.example`, `dealbot/settings.py` | `yoto_v4` | App-level renderer selection |
| `CARD_RENDERER_FALLBACK_TO_LEGACY` | `.env.example`, `dealbot/settings.py` | `1` | Enables router fallback to legacy |
| `IMAGE_PROVIDER_MODE` | `.env.example`, `dealbot/settings.py` | `ai_first` | App-level image resolver mode |
| `IMAGE_PIPELINE_VERSION` | `.env.example`, `dealbot/settings.py`, `image_providers/base.py` | `v1` | Also hardcoded as `IMAGE_PIPELINE_VERSION = 'v1'` |
| `COMFYUI_ENABLED` | `.env.example`, `dealbot/settings.py` | `1` | App-level ComfyUI enable flag |
| `COMFYUI_URL` | `.env.example`, `dealbot/settings.py` | `http://127.0.0.1:8188` | App-level ComfyUI base URL |
| `COMFYUI_CHECKPOINT` | `.env.example`, `dealbot/settings.py`, `comfyui_provider.py` | `auto` | Provider checkpoint selection |
| `CARD_RENDERER_DEBUG_HERO_SELECTION` | `renderer_selector.py` | no default in `.env.example` | Enables hero-selection debug logging |
| `CARD_RENDERER_DEBUG_GAMEPLAY_SELECTION` | `renderer_selector.py` | no default in `.env.example` | Enables gameplay-selection debug logging |
| `ANALYTICS_OUTPUT_DIR` | `dealbot/settings.py` | `output/analytics` | Debug/report artifact output |
| `VIDEO_MANIFEST_OUTPUT_DIR` | `dealbot/settings.py` | `output/video_manifests` | Video manifest output |
| `MIN_GAME_OF_THE_DAY_SCORE` | `dealbot/settings.py` | `65` | Editorial scoring threshold |
| `WHITELIST_PRIORITY_BOOST` | `dealbot/settings.py` | `24` | Editorial/control priority boost |
| `MIN_REVIEW_COUNT` | `dealbot/settings.py` | `50` | Quality gate threshold |
| `MIN_PRICE_DROP_MINOR` | `dealbot/settings.py` | `1000` | Editorial/decision threshold |
| `MIN_DISCOUNT_DELTA` | `dealbot/settings.py` | `10` | Editorial/decision threshold |

### Hardcoded image/visual scoring values found

- `infrastructure/render/cards/visual_decision_engine.py`
  - `MIN_READABILITY_SCORE = 0.55`
  - `MIN_FOCUS_SCORE = 0.50`
  - `CLOSE_SCORE_OFFICIAL_TIEBREAK_THRESHOLD = 0.03`
  - `VISUAL_SOURCE_PREFERENCE` maps are hardcoded per visual type
  - `SOURCE_STRENGTH_MAP` is hardcoded
- `infrastructure/render/cards/asset_sources/official_asset_source.py`
  - `MAX_DOWNLOAD_CANDIDATES_PER_GAME = 3`
- `infrastructure/render/cards/asset_sources/asset_cache.py`
  - `ASSET_DOWNLOAD_TIMEOUT_SECONDS = 10`
  - `ASSET_DOWNLOAD_MAX_BYTES = 8 * 1024 * 1024`

### Important call-path default mismatch found

- Via `dealbot.settings.load_rendering_config(...)`
  - Defaults are `IMAGE_PROVIDER_MODE = ai_first` and `COMFYUI_ENABLED = 1`
- Via direct `YotoCardEngineV4()` construction without prior settings load
  - Constructor defaults are `IMAGE_PROVIDER_MODE = artwork_only` and `COMFYUI_ENABLED = 0`
- This is a real code-path difference, not a guess

## 6. What is confirmed by code

- The app-level production path wires `CardRendererRouter` through `dealbot/main.py` into `DryRunRenderUseCase`, not directly into legacy-only rendering.
- `CardRendererRouter` currently aliases `yoto_v42` to `yoto_v4` and instantiates `YotoCardRendererV42Adapter`.
- `YotoCardRendererV42Adapter` currently uses `YotoCardEngineV4`.
- `YotoCardEngineV4` always constructs a resolver with three providers:
  - `ArtworkImageProvider`
  - `ComfyUIImageProvider`
  - `PlaceholderImageProvider`
- `YotoImageResolver` currently does all of the following:
  - records `resolver_trace`
  - records `decision_reason`
  - records `ai_attempted` and `ai_succeeded`
  - records `actual_image_source_type`
  - records `actual_image_path_or_url`
  - rejects AI output if size is below the requested image size
- `VisualDecisionEngine` is currently official-first:
  - if usable official assets exist, it selects from them first
  - AI becomes primary only when there are no official candidates or all official candidates fail thresholds
- `resolve_cover_decision_asset_bridge(...)` only accepts a local, readable, official-like asset path for bridge use.
- `ComfyUIImageProvider` supports two concrete modes:
  - `reference_assisted`
  - `pure_generation`
- Pure-generation output is persisted under `output/cards/comfyui_generated`.
- Official asset caching is persisted under `output/cards/official_asset_cache`.

## 7. What is confirmed by local runtime in this audit

- `current_env` smoke produced a real local runtime-proof for the current code path:
  - `provider_attempted = comfyui`
  - `provider = comfyui`
  - `final_source = ai`
  - `ai_source_mode = reference_assisted`
  - `generated_image_origin = local_reference_asset`
  - `workflow_mode = scene_content_reference_assisted`
- In that same `current_env` run:
  - `cover_decision.use_ai = false`
  - `cover_decision.image_source_type = official_press_key_art`
  - `resolver_trace.final_selected_provider = comfyui`
  - `resolver_trace.final_selected_source = ai`
  - `decision_asset_candidate_valid = false`
  - `decision_asset_reject_reason = invalid_or_nonlocal_asset_path`
- `quality_reject --game-set minimal` smoke proved current fallback behavior in local runtime:
  - `5` total runs
  - `4` ended as `official_asset`
  - `1` ended as `ai_fallback`
  - `ai_attempted_true_runs = 1`
  - `fallback_used_runs = 1`
- The latest `quality_reject` batch summary shows at least one concrete runtime selection change:
  - For `hades_ii`, current runtime selected `steam_library_capsule`
  - The selected asset came from `output/cards/official_asset_cache/steam/1145350/steam_library_capsule_1.jpg`
  - `decision_asset_used = true`
  - `final_source = asset`

## 8. What is NOT confirmed without additional runtime logs

- Live `pure_generation` against the actual ComfyUI server at the current `COMFYUI_URL`
  - The local audit did not prove real `/prompt` submit, `/history` polling, or final image fetch from a live ComfyUI runtime
- Live checkpoint availability on the current ComfyUI server
  - `COMFYUI_CHECKPOINT = auto` exists in code/config, but current audit did not prove which checkpoint the live server would actually pick
- Live offer selection behavior in the real queue during `dealbot.main --preview` / `--send-test`
  - The audit proved local smoke behavior, not live queue behavior on the current ingest state
- Live remote asset download success against current external network conditions
  - Code and tests prove the cache contract
  - The audit did not prove real Steam/Epic CDN availability from this machine at this moment
- Live operator-truth / analytics artifacts showing a real production queue run with `provider = comfyui`
  - The audit proved smoke/runtime artifacts, not a live production preview/send-test cycle

## 9. What commands should be run to prove current behavior

See `YOTO_AUDIT_COMMANDS.ps1`.

The main proof commands are:

- `D:\Telegram\.venv\Scripts\python.exe -m py_compile ...`
- `D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_asset_cache.py tests/test_official_asset_source.py tests/test_visual_decision_engine.py tests/test_ai_card_smoke.py`
- `D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py current_env --runs 1 --debug-ai`
- `D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py quality_reject --runs 1 --game-set minimal --debug-ai`

## 10. Where generated cards, manifests, debug logs, and selected assets are written

### Final/generated card images

- App default card output root:
  - `D:\Telegram_portable_bundle\output\cards`
- Engine output naming:
  - `output/cards/yoto_card_<slug>.png`
- Smoke run card output:
  - `output/cards/ai_card_smoke_<scenario>_<slug>_<prompt_variant>_<run_key>\cards\yoto_card_<slug>.png`

### Smoke manifests and review outputs

- Per-run smoke manifest:
  - `output/cards/ai_card_smoke_<...>\ai_card_smoke_manifest.json`
- Per-batch smoke summary:
  - `output/cards/ai_card_smoke_batch_<scenario>_<batch_key>\batch_summary.json`
- Per-batch smoke review cards:
  - `output/cards/ai_card_smoke_batch_<scenario>_<batch_key>\review_cards\*.png`

### ComfyUI-generated images

- `output/cards/comfyui_generated\*.png`

### Selected/cached official assets

- Official asset cache root:
  - `output/cards/official_asset_cache`
- Current namespaces seen in code:
  - `steam`
  - `epic`
  - `local_manifest`
  - `fixture_fallback`
- Example current cached path from local runtime:
  - `D:\Telegram_portable_bundle\output\cards\official_asset_cache\steam\1145350\steam_library_capsule_1.jpg`

### Roundup-selected assets

- Roundup cache:
  - `output/cards/_roundup_cache`
- Roundup final card:
  - `output/cards/yoto_card_roundup_<roundup_id>.png`

### Debug/report artifacts

- Analytics/report output root:
  - `output/analytics`
- Artifact writer emits:
  - `*_operator_truth_report_*.json`
  - `*_operator_truth_report_*.csv`
  - `*_run_diagnostics_*.json`
  - `*_run_diagnostics_*.csv`
  - `*_operator_workflow_*.json`
  - `*_operator_workflow_*.csv`
  - other analytics artifacts written by the same writer

### Video manifests

- `output/video_manifests\*.json`

### Offline validation snapshots

- `output/offline_validation\...`

### Where selected asset identity is stored

- In smoke manifests and batch summaries:
  - `provider_metadata.cover_decision_selected_asset`
  - `provider_metadata.actual_image_source_type`
  - `provider_metadata.actual_image_path_or_url`
  - `provider_metadata.selected_asset_remote_url`
  - `provider_metadata.selected_asset_cache_path`
  - `provider_metadata.selected_asset_cache_status`
- In render diagnostics / manifest payloads:
  - `render_diagnostics.selected_asset_path`
  - `render_diagnostics.hero_asset_used`
  - `render_diagnostics.asset_used`

## 11. Any obvious mismatch between existing HEAD and actual code

### HEAD vs current worktree

- The current worktree is not equal to `HEAD`.
- Modified tracked files:
  - `.env.example`
  - `AGENTS.md`
  - `HEAD_YOTO.md`
  - `dealbot/settings.py`
  - `infrastructure/render/cards/image_providers/base.py`
  - `infrastructure/render/cards/image_providers/comfyui_provider.py`
  - `infrastructure/render/cards/image_providers/resolver.py`
  - `infrastructure/render/cards/yoto_card_engine_v4.py`
- Untracked YOTO-related files currently present in the worktree but absent from `HEAD`:
  - `infrastructure/render/cards/asset_sources/__init__.py`
  - `infrastructure/render/cards/asset_sources/asset_cache.py`
  - `infrastructure/render/cards/asset_sources/official_asset_manifest.local.json`
  - `infrastructure/render/cards/asset_sources/official_asset_source.py`
  - `infrastructure/render/cards/visual_decision_engine.py`
  - `tests/test_ai_card_smoke.py`
  - `tests/test_asset_cache.py`
  - `tests/test_official_asset_source.py`
  - `tests/test_visual_decision_engine.py`
  - `tools/ai_card_smoke.py`
  - `yoto_card_runtime_smoke.patch`
  - `yoto_resolver_ai_runtime.patch`

### HEAD snapshot document vs current worktree/runtime

- `HEAD_YOTO.md` currently says:
  - runtime-proof of AI-provider usage is not implemented
  - validation requires at least one run with `provider = comfyui`
- Current worktree/runtime already contains:
  - `tools/ai_card_smoke.py`
  - `tests/test_ai_card_smoke.py`
  - `infrastructure/render/cards/visual_decision_engine.py`
  - `infrastructure/render/cards/asset_sources/*`
  - an audit-local `current_env` smoke run with `provider = comfyui`
- This makes `HEAD_YOTO.md` outdated relative to the current worktree and audit-local runtime evidence.

### Current test expectation vs current runtime

- `tests/test_ai_card_smoke.py::test_ai_card_smoke_quality_reject_uses_valid_decision_asset_before_ai`
  - Expected source type: `official_press_key_art` or `steam_main_capsule`
  - Observed local runtime source type: `steam_library_capsule`
  - Result: this targeted test currently fails

