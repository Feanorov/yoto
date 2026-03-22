# YOTO Card System Audit

Date: 2026-03-19

This document audits the current card system as it exists in the repo today. It is not a redesign brief. The goal is to map the existing renderer stack, card families, adaptive rules, fallback behavior, validation coverage, and the main fragmentation points before any broader card-system rewrite is attempted.

## Evidence Base

Primary code paths:
- `infrastructure/render/cards/renderer_selector.py`
- `infrastructure/render/cards/yoto_card_engine_v4.py`
- `infrastructure/render/cards/template_system.py`
- `infrastructure/render/cards/roundup_top_list_card_adapter.py`
- `infrastructure/render/cards/asset_source.py`
- `application/use_cases/publish_next.py`
- `application/use_cases/generate_roundup_artifacts.py`

Repo contracts and operator docs:
- `docs/YOTO_QA_MATRIX.md`
- `docs/YOTO_VALIDATION_PLAYBOOK.md`
- `docs/YOTO_COMMAND_INDEX.md`
- `docs/YOTO_ARCHITECTURE_GUARDRAILS.md`

Tests:
- `tests/test_yoto_card_engine_v4.py`
- `tests/test_renderer_selector_arch.py`
- `tests/test_render_diagnostics_arch.py`
- `tests/test_roundup_top_list_card_adapter_arch.py`
- `tests/test_card_engine_v2_layout.py`
- `tests/test_publish_roundup_integration_arch.py`

Validation / review tools and artifacts:
- `tools/generate_yoto_v451_live_validation_pack.py`
- `tools/generate_yoto_v45_smart_hero_smoke_pack.py`
- `tools/generate_yoto_v52_gameplay_examples.py`
- `tools/generate_yoto_v5_editorial_examples.py`
- `tools/generate_yoto_v44_integration_preview_pack.py`
- `output/cards/live_validation_v45/validation_manifest.json`
- `output/cards/preview_yoto_v44_integration_20260311T231905Z/comparison_manifest.json`
- `output/cards/smoke_yoto_v451_20260312T005308Z/smoke_manifest.json`
- `output/cards/gameplay_selection_examples_v1/gameplay_manifest.json`
- `output/cards/editorial_examples_v51/editorial_manifest.json`
- `output/cards/epic_free_composition_review_20260318T232611Z/review_manifest.json`
- `output/analytics/*card_qa_summary*.json`

## 1. Current Card Inventory

### 1.1 Canonical semantic families

The active YOTO engine uses four semantic card families in `YotoCardType` (`infrastructure/render/cards/yoto_card_engine_v4.py`):

| Family | Primary use | Main template ids / publish mapping | Main renderer path |
| --- | --- | --- | --- |
| `FREE_GAME` | Epic freebies, Steam freebies | `epic_free`, `steam_free` | `CardRendererRouter` -> `YotoCardRendererV42Adapter` -> `YotoCardEngineV4` |
| `DISCOUNT` | Standard Steam/discount posts | `steam_discount` and default discount-like templates | same |
| `FESTIVAL` | Event/festival posts | `festival_event` | same |
| `TOP_LIST` | Roundup/top-list cards | `roundup_digest`, template ids containing `top` | `RoundupTopListCardAdapter` -> `YotoCardEngineV4` or router mapping |

System-level family mapping is also encoded in `publish_next._card_family(...)` (`application/use_cases/publish_next.py`).

### 1.2 Template-level variants already in repo

The repo also contains older or narrower template-level variants that do not cleanly equal the four semantic families:

| Template / variant | Where it lives | Status today |
| --- | --- | --- |
| `steam_discount` | `template_system.py`, router, live validation tools | active |
| `epic_free` | `template_system.py`, router, live validation tools | active |
| `steam_free` | `template_system.py`, router | active but less reviewed than `epic_free` |
| `festival_event` | `template_system.py`, router | active |
| `final_push` | `template_system.py` only | legacy-theme variant, not a first-class YOTO semantic family |
| `game_of_the_day` | `template_system.py` only | legacy-theme variant, not a first-class YOTO semantic family |
| `roundup_digest` | roundup publish path, `publish_next.py`, adapter tests | active roundup-only path |

### 1.3 Major generated card surfaces in practice

| Surface | Current owner | Evidence |
| --- | --- | --- |
| Epic freebie cards | YOTO V4 engine + router heuristics | `renderer_selector.py`, `yoto_card_engine_v4.py`, `tests/test_yoto_card_engine_v4.py`, `output/cards/epic_free_composition_review_20260318T232611Z/` |
| Steam discount cards | YOTO V4 engine + router heuristics | `renderer_selector.py`, `template_system.py`, `tests/test_renderer_selector_arch.py`, `output/cards/live_validation_v45/validation_manifest.json` |
| Event / festival cards | YOTO V4 `FESTIVAL` family, plus legacy event theme in `TemplateSystem` | `test_yoto_card_engine_v4_supports_festival_variant_metadata`, `test_event_card_uses_editorial_panel_not_generic_deal_slab` |
| Roundup cards | `RoundupTopListCardAdapter` + `YotoCardEngineV4(TOP_LIST)` | `roundup_top_list_card_adapter.py`, `tests/test_roundup_top_list_card_adapter_arch.py`, `tests/test_publish_roundup_integration_arch.py` |
| Fallback / low-asset cards | YOTO placeholder path + router/adapter fallback decisions | `renderer_selector.py`, `yoto_card_engine_v4.py`, `tests/test_card_renderer_router_rejects_capsule_like_assets_and_uses_branded_fallback`, `tests/test_yoto_card_engine_v4_placeholder_artwork_varies_by_metadata` |
| Legacy safety-net cards | `TemplateSystem` | `template_system.py`, `test_card_engine_v2_layout.py`, router fallback tests |

## 2. Current Logic / Rules Inventory

### 2.1 Shared rendering pipeline

The current active pipeline is:

`publish_next / validation tool -> CardRendererRouter -> YotoCardRendererV42Adapter -> YotoCardEngineV4`

Key responsibilities are split as follows:
- `renderer_selector.py`: card-type routing, asset candidate collection, hero selection, gameplay selection, local-file asset resolution, renderer fallback.
- `yoto_card_engine_v4.py`: deterministic 1280x720 card composition, typography, badge/panel/title/meta/brand drawing, placeholder art, gameplay strip drawing.
- `template_system.py`: older standalone renderer family still used for compatibility and fallback.
- `roundup_top_list_card_adapter.py`: roundup-specific lead-artwork selection plus handoff into `YotoCardEngineV4` as `TOP_LIST`.

### 2.2 Selector and adaptive asset rules already in place

`renderer_selector.py` already contains a substantial rule system before pixels reach the main engine.

Current adaptive rules include:
- Card-type inference from `OfferSource`, `OfferKind`, and `template_id`.
- Hero candidate collection from `hero`, `header`, `screenshot`, and `fallback` assets.
- Visual hero scoring via `_inspect_visual_candidate(...)` with penalties and flags for:
  - capsule-like art
  - text-heavy / logo-dominant assets
  - UI-heavy frames
  - banner-like / promotional layouts
  - weak brightness / entropy / subject signal
- Hero quality floors (`_hero_quality_floor(...)`) and explicit rejection reasons such as `capsule_rejected_text_heavy`, `capsule_rejected_logo_dominant`, and `weak_asset_fallback`.
- Gameplay candidate extraction from primary screenshots plus `/extras/` media stills embedded in descriptions.
- Gameplay scoring with:
  - UI-like detection
  - banner / promo rejection
  - scene-richness scoring
  - aspect checks
  - diversity filtering using scene signatures and `_scene_distance(...)`
  - strategy / builder-specific UI penalty relaxation
  - rescue of borderline but better-late frames from weak/promo-heavy sets
- Local direct-path and `file://` asset reuse in `asset_source.py` for deterministic offline or cached validation inputs.

This selector layer is one of the strongest reusable parts of the current system.

### 2.3 YOTO V4 engine rules already in place

`yoto_card_engine_v4.py` already encodes a broad visual-rule system.

Shared engine behaviors:
- deterministic canvas and coordinates (`CARD_SIZE`, `HERO_HEIGHT`, `LOWER_THIRD_TOP`)
- per-family palette system via `_palette(...)`
- Ukrainian copy normalization and mojibake repair
- glyph-aware font fallback for Cyrillic
- title wrapping and line-count control
- optional gameplay strip rendering
- lower-third panel, price/deadline meta row, and brand lockup rendering
- deterministic metadata-seeded placeholder artwork

Card-type-specific behaviors already present:
- `FREE_GAME`: freebie badge, giveaway copy, claim-deadline / old-price meta row, strongest recent top-zone and composition work.
- `DISCOUNT`: discount badge, current-vs-old price emphasis, standard deadline pill + price line.
- `FESTIVAL`: event palette/copy and festival-style metadata treatment.
- `TOP_LIST`: roundup/top-list palette and list-label support.

### 2.4 Epic freebie composition rules already present

The current repo now has the most mature family-specific composition policy in `epic_free`.

Already implemented:
- top-zone scoring and layout profiles (`_top_zone_layout_profile(...)`)
- badge anchor selection (`top_right`, `top_inset`, `right_shoulder`)
- compact `EPIC` source chip for logo-heavy art
- softened freebie badge profile for logo-heavy Epic art
- logo-aware gameplay-strip suppression
- shared `epic_free_system_<mode_kind>_<brightness_band>` composition profile coordinating:
  - upper zone
  - lower-third silhouette
  - title sizing / wrapping
  - metadata chip row
  - brand lockup
  - bright / balanced / dark variants
  - clean / logo-heavy / fallback variants
- placeholder title compact mode for long-title fallback cards

This is the strongest evidence of a family-level system rather than isolated element tweaks.

### 2.5 Legacy template-system rules still present

`template_system.py` is still a real renderer family, not dead code.

It still owns:
- hero-first legacy layout for discount/freebie cards
- event feature-panel layout
- contain-mode handling for very wide/header-only art
- template-themed variants such as `final_push` and `game_of_the_day`
- title clipping / font-size step-down logic
- brand lockup and badge drawing separate from the YOTO V4 engine

It is currently both:
- a fallback path when the YOTO engine fails and `fallback_to_legacy=True`
- a historical source of design rules and tests (`tests/test_card_engine_v2_layout.py`)

### 2.6 Roundup-specific rules already present

Roundups are not routed through the normal offer-render pipeline end to end.

Current roundup-specific logic:
- `GenerateRoundupArtifactsUseCase` builds roundup posts from reserve items.
- `RoundupTopListCardAdapter` scores roundup items and selects lead artwork via weighted item score / rank / discount / review score.
- The adapter then renders a `TOP_LIST` card through `YotoCardEngineV4`.
- Publish-path tests verify that roundup render diagnostics are preserved and that `card_qa_summary` analytics are emitted.

This is useful reuse, but it is still a separate seam with its own artwork materialization logic.

### 2.7 Fallback behaviors already present

Fallback behavior exists at several levels:

| Fallback type | Where it happens | Current behavior |
| --- | --- | --- |
| Missing or unusable hero art | `renderer_selector.py` | reject capsule/text-heavy art, fall back to screenshot/header or placeholder |
| No usable YOTO render | `CardRendererRouter` | optional fallback to legacy `TemplateSystem` |
| No local/offline asset | offline snapshot + engine | render from localized asset if present; otherwise use existing placeholder/fallback behavior |
| No roundup lead artwork | `RoundupTopListCardAdapter` | use placeholder path through YOTO engine and mark warnings |
| Missing artwork inside engine | `YotoCardEngineV4.load_artwork()` | deterministic placeholder image, metadata-driven title panel |

## 3. Current Test / Validation Inventory

### 3.1 Contract tests

| Coverage area | Main evidence |
| --- | --- |
| Router selection, capsule rejection, gameplay scoring, legacy fallback | `tests/test_renderer_selector_arch.py` |
| YOTO V4 engine layouts, Ukrainian text repair, placeholder logic, Epic top-zone rules, gameplay suppression | `tests/test_yoto_card_engine_v4.py` |
| Legacy template layout rules | `tests/test_card_engine_v2_layout.py` |
| Legacy render diagnostics contract | `tests/test_render_diagnostics_arch.py` |
| Roundup adapter selection | `tests/test_roundup_top_list_card_adapter_arch.py` |
| Roundup publish-path and `card_qa_summary` analytics | `tests/test_publish_roundup_integration_arch.py` |

### 3.2 Validation-pack lineage already in repo

The repo already contains multiple generations of card review tooling. The important point is that validation history is fragmented, but rich.

| Tool / pack | Focus | Evidence artifact |
| --- | --- | --- |
| `generate_yoto_v4_acceptance_pack.py`, `generate_yoto_v41_acceptance_pack.py` | early acceptance passes | `output/cards/v4_acceptance_sources/`, `output/cards/v41_acceptance_sources/` |
| `generate_yoto_v42_integration_preview_pack.py` | legacy vs YOTO integration comparison | `output/cards/preview_yoto_v42_integration_20260311T221545Z/comparison_manifest.json` |
| `generate_yoto_v43_integration_preview_pack.py` | later integration comparison | `output/cards/preview_yoto_v43_integration_*` |
| `generate_yoto_v44_integration_preview_pack.py` | 13-case legacy vs YOTO comparison | `output/cards/preview_yoto_v44_integration_20260311T231905Z/comparison_manifest.json` |
| `generate_yoto_v44_smoke_pack.py` | focused smoke pack | `output/cards/smoke_yoto_v44_20260311T234312Z/smoke_manifest.json` |
| `generate_yoto_v45_smart_hero_smoke_pack.py` | smart hero-selection smoke | `output/cards/smoke_yoto_v45_20260312T001925Z/smoke_manifest.json` |
| `generate_yoto_v451_live_validation_pack.py` | current broad live/offline/golden validation pack | `output/cards/live_validation_v45/validation_manifest.json` |
| `generate_yoto_v52_gameplay_examples.py` | gameplay-selection examples | `output/cards/gameplay_selection_examples_v1/gameplay_manifest.json` |
| `generate_yoto_v5_editorial_examples.py` | editorial phrase examples | `output/cards/editorial_examples_v51/editorial_manifest.json` |
| Epic composition review pack | focused recent product review pack | `output/cards/epic_free_composition_review_20260318T232611Z/review_manifest.json` |

### 3.3 Live proof and analytics evidence

The repo also already records publish-facing card QA signals:
- live card validation manifests in `output/cards/live_validation_v45/`
- publish outcomes in `output/analytics/*publish_outcome*.json`
- card-window analytics in `output/analytics/*card_qa_summary*.json`

This means the system already has both per-card diagnostics and per-window publish QA summaries.

## 4. What Looks Strong And Reusable

- The router / selector seam is already a strong asset-selection subsystem and should be preserved, not replaced casually.
- `YotoCardEngineV4` already provides one real semantic family model (`FREE_GAME`, `DISCOUNT`, `FESTIVAL`, `TOP_LIST`) and a deterministic composition engine.
- Epic freebie work is mature enough to serve as the current reference family for premium-system thinking.
- Ukrainian text repair and glyph fallback are strong, repo-truthful quality guards that should remain first-class requirements.
- Validation coverage is stronger than it first appears: contract tests, comparison packs, smoke packs, live validation packs, editorial/gameplay packs, Telegram proof, and publish analytics all already exist.
- Roundup cards already reuse the main engine instead of inventing a separate image style from scratch.

## 5. Fragmentation / Conflict Points

### 5.1 Semantic family vs template-id drift

There are four semantic families in the active engine, but more template ids and legacy theme variants floating around (`final_push`, `game_of_the_day`, `steam_discount`, `epic_free`, `roundup_digest`). The system does not yet have one written mapping that says which template ids are canonical families, which are variants, and which are legacy compatibility shapes.

### 5.2 Two renderer families still coexist

The repo still contains:
- `YotoCardEngineV4` as the main renderer family
- `TemplateSystem` as a still-functional legacy renderer family

That is useful operationally, but it means not all visual rules live in one place yet.

### 5.3 Validation history is rich but scattered

There are many proof tools and packs (`v4`, `v41`, `v42`, `v43`, `v44`, `v45`, `v451`, `v52`, editorial `v5` / `v51`). This is valuable history, but it also means there is no single canonical card-system review pack that covers all families the same way.

### 5.4 Roundup is partially unified, partially separate

Roundup visuals reuse `YotoCardEngineV4`, which is good. But the adapter still:
- owns its own lead-artwork scoring
- owns its own remote materialization via `urlopen`
- emits custom diagnostics outside the standard router path

That makes roundup a partially integrated exception.

### 5.5 Maturity is uneven by family

| Family | Current maturity | Main weak spot |
| --- | --- | --- |
| Epic freebie | strongest | now carries the most family-specific logic and may drift away from others if copied ad hoc |
| Steam discount | solid | composition rules are less explicitly codified than Epic?s newer system pass |
| Festival / event | functional | fewer dedicated tests and fewer recent visual review packs |
| Roundup / top list | functional reuse | separate adapter seam and less broad visual QA |
| Fallback / low-asset | much improved | still reads as its own special language more than a fully unified family variant |

### 5.6 No dedicated written card-system brief exists yet

The repo has QA rules, playbooks, tests, manifests, and code comments, but no single document that explains the full card system as a product/design system. Today the real design rules live mostly in code and test names.

## 6. Recommended Path Toward One Unified Card System

This should be the next-step direction after the audit, without rewriting blindly.

### 6.1 Freeze the canonical model first

Write down one canonical semantic model before changing visuals again:
- semantic family
- template ids that map into that family
- shared regions (hero, top zone, lower third, meta row, brand block)
- allowed family-specific overrides

The active four-family model in `YotoCardEngineV4` is the best starting point.

### 6.2 Treat selector rules and composition rules as separate contracts

Do not mix these concerns in the future brief.

Two independent system layers already exist and should remain explicit:
- selection contract: what art is eligible and why
- composition contract: how a chosen asset becomes a readable card

The router already provides the first half well; the new premium brief should formalize the second half across all families.

### 6.3 Use Epic freebie as the reference family, not the only family

Epic freebie currently has the clearest family-specific composition policy. Reuse its best patterns as abstractions:
- top-zone hierarchy policy
- brightness-aware variants
- long-title handling
- coherent lower-third panel/profile

But move those ideas into a family-agnostic blueprint instead of cloning more `epic_free`-only patches.

### 6.4 Decide the future of `TemplateSystem` explicitly

Before a broader redesign, make one decision in the brief:
- which legacy layout ideas are still worth preserving
- which template ids remain compatibility-only
- whether the long-term target is ?YOTO engine owns all primary families, legacy stays fallback-only?

Right now this is implied, but not written down.

### 6.5 Consolidate validation around one canonical multi-family review pack

The repo should keep historical packs, but future card-system work should be judged primarily through one canonical pack that covers at least:
- Epic freebie
- Steam discount
- event/festival
- roundup/top-list
- fallback/low-asset
- short title / long title
- bright hero / dark hero
- real Telegram proof when publishable

`tools/generate_yoto_v451_live_validation_pack.py` plus the recent Epic review pack is the best current base for that.

## Bottom Line

The repo does not need a blind renderer rewrite to get to a premium unified card system.

It already has:
- a strong selector layer
- a viable semantic family model
- a mature Epic freebie family
- a reusable main engine
- fallback safety nets
- real validation infrastructure

What it lacks is one written blueprint that turns those existing strengths into a consistent cross-family system and clearly marks which remaining pieces are legacy compatibility, which are true shared primitives, and which are temporary family-specific exceptions.
