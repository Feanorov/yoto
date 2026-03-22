# YOTO Card System Blueprint

Date: 2026-03-19

This document is the canonical repo-level definition of the YOTO card system as it should be understood and extended from this point forward.

It is grounded in the current repo, not an imagined redesign. It defines the active semantic families, the canonical family/template map, the shared composition model, the approved fallback policy, and the line between active YOTO ownership and legacy compatibility behavior.

This document does not rewrite the renderer architecture. It freezes the system model so future implementation work can be coherent instead of patch-driven.

## 1. Canonical Ownership

The active card system is defined by these seams:

- Selection contract:
  - `infrastructure/render/cards/renderer_selector.py`
  - `infrastructure/render/cards/asset_source.py`
- Main composition contract:
  - `infrastructure/render/cards/yoto_card_engine_v4.py`
- Roundup composition seam:
  - `infrastructure/render/cards/roundup_top_list_card_adapter.py`
  - `infrastructure/render/cards/yoto_card_engine_v4.py`
- Publish-facing family mapping:
  - `application/use_cases/publish_next.py`

Compatibility-only renderer:

- `infrastructure/render/cards/template_system.py`

Canonical rule:

- New primary card-system work should be expressed through the selector plus `YotoCardEngineV4` model.
- `TemplateSystem` remains operational fallback and historical reference, not the source of truth for future primary family design.

## 2. Canonical Card Families

These four semantic families are canonical because they already exist in `YotoCardType` and are reflected across the active engine and publish flow:

| Canonical family | Purpose | Active owner |
| --- | --- | --- |
| `FREE_GAME` | Freebie / giveaway cards | `renderer_selector.py` + `yoto_card_engine_v4.py` |
| `DISCOUNT` | Standard discount / sale cards | same |
| `FESTIVAL` | Event / festival / promotional event cards | same |
| `TOP_LIST` | Roundup / ranked / editorial list cards | `roundup_top_list_card_adapter.py` + `yoto_card_engine_v4.py` |

These are the only canonical semantic families for the repo-level card system.

## 3. Canonical Template To Family Map

Template ids may continue to exist operationally, but they must map into the semantic families below.

| Template id / publish shape | Canonical family | Status |
| --- | --- | --- |
| `epic_free` | `FREE_GAME` | active |
| `steam_free` | `FREE_GAME` | active |
| `steam_discount` | `DISCOUNT` | active |
| discount-like default game cards without freebie/event semantics | `DISCOUNT` | active |
| `festival_event` | `FESTIVAL` | active |
| `roundup_digest` | `TOP_LIST` | active |
| template ids containing `top` in router logic | `TOP_LIST` | active compatibility mapping |
| `final_push` | legacy theme variant, not a canonical family | legacy |
| `game_of_the_day` | legacy theme variant, not a canonical family | legacy |

Canonical rule:

- Family is the primary design contract.
- Template id is an implementation input, publish alias, or compatibility affordance.
- Future renderer work should extend family behavior first, not create new primary visual systems around one-off template names.

## 4. Active vs Legacy Variants

### 4.1 Active

The following are active, first-class YOTO card outputs:

- `FREE_GAME`
- `DISCOUNT`
- `FESTIVAL`
- `TOP_LIST`
- YOTO V4 selector-driven hero/gameplay choice
- YOTO V4 lower-third, badge, meta-row, and placeholder system
- Roundup cards rendered through `YotoCardEngineV4`

### 4.2 Legacy / compatibility-only

The following are explicitly legacy or compatibility-owned:

- `TemplateSystem` visual language as a primary design source
- `final_push`
- `game_of_the_day`
- legacy event/game slab themes inside `TemplateSystem`
- older validation-pack versions as historical evidence rather than canonical spec

Canonical rule:

- Legacy paths may remain for operational safety.
- They should not define the future premium YOTO card language unless a specific rule is deliberately migrated into the active blueprint.

## 5. Shared Composition Zones

All major YOTO card families should be understood as the same zone system with family-specific emphasis, not as unrelated layouts.

### 5.1 Zone model

| Zone | Purpose | Current repo evidence |
| --- | --- | --- |
| Top zone | source chip, free/discount/event signal, compact family status | `draw_platform_badge`, `draw_free_or_discount_badge`, `_top_zone_layout_profile` |
| Hero zone | main visual anchor and first-glance mood/source signal | `load_artwork`, hero crop logic, hero diagnostics |
| Optional gameplay strip | secondary visual proof only when it adds information | `draw_gameplay_strip`, gameplay selection diagnostics |
| Lower-third panel | stability layer for readability over variable art | `draw_lower_third_panel` |
| Title zone | primary reliable text read | `draw_title`, `_resolve_title_layout` |
| Info band / meta row | price, deadline, event/list metadata | `draw_free_game_meta_row`, `draw_price_information`, `draw_deadline_pill` |
| Brand lockup zone | YOTO signature and quiet identity | `draw_yoto_brand_lockup` |

### 5.2 Canonical zone policy

- Hero art should lead the emotional read.
- The lower third should carry the primary guaranteed-readable title.
- The top zone should carry no more than two functional signals at full weight.
- The gameplay strip is optional evidence, not a required decorative strip.
- The info band should carry the transaction/editorial facts that matter after the title.
- The brand lockup should remain supportive and quiet.

## 6. Shared Hierarchy Rules

These rules define the canonical YOTO card hierarchy across families.

### 6.1 First-glance reading order

Within roughly one second on the Telegram surface, a card should make these things clear:

1. What this is: freebie, discount, event, or roundup.
2. What title or subject this card is about.
3. What the action/state is: free now, sale now, event now, or editorial digest.
4. The key secondary fact: deadline, current price, old price, or list context.

### 6.2 Hierarchy rules

- The title zone is the primary reliable text read across all families.
- The hero should not have to carry the entire title burden.
- The top zone should communicate state and source, not repeat the full title.
- A gameplay strip should be suppressed when it simply repeats a logo-heavy hero.
- Metadata should be reduced to one primary row, not a stack of competing micro-panels.
- Brand presence should be visible but never the loudest read.
- Ukrainian copy must remain correct and glyph-safe in every state, including fallback.

## 7. Suppression, Compact, And Fallback Rules

These are canonical behavior classes already supported by the current system and approved for further reuse.

### 7.1 Suppression rules

- Suppress gameplay-strip rendering when the selected hero already carries a strong readable logo/title and the strip would repeat the same signal.
- Suppress redundant top-zone weight when the hero already carries dense upper-area information.
- Suppress decorative variation that does not improve readability or proof value.

### 7.2 Compact rules

- Use compact top-zone layouts for crowded or logo-heavy hero art.
- Use compact title mode for long titles, especially in fallback or low-asset states.
- Use compact source-chip treatments when both source and free/discount status are already strongly implied by the art and family context.

### 7.3 Fallback rules

- Try the best eligible real hero asset first.
- Reject weak or misleading art before composing it.
- Use placeholder artwork only after truthful real-asset options are exhausted.
- Keep fallback cards inside the same family skeleton rather than switching to a different visual language.
- Placeholder art must remain deterministic and seeded by truthful offer metadata.
- Do not fabricate gameplay, logos, or publishability.

## 8. Family-Specific Behavior

### 8.1 Epic freebie

Canonical family: `FREE_GAME`

Primary behavior:

- Lead with the sense of availability and urgency, not with discount arithmetic.
- Use logo-aware hero treatment because Epic key art often carries large built-in title/logo signals.
- Use a coordinated top-zone policy rather than independent chip/badge placement.
- Suppress redundant gameplay-strip/title repetition when the hero already carries the title strongly.
- Use the lower-third title as the stable readable anchor even when hero art is logo-heavy.
- Use deadline as the primary metadata signal and old price as a secondary reinforcement signal.

Current repo reference:

- `epic_free` is the most mature family-specific composition policy in the current codebase and should be the reference family for future family-level abstraction work.

### 8.2 Steam discount

Canonical family: `DISCOUNT`

Primary behavior:

- Lead with title plus real price context.
- Current price or discount state should be the strongest transaction read in the info band.
- Old price should support, not overpower, the current offer state.
- Gameplay or screenshot evidence is more valuable here than in logo-heavy freebie cases because Steam sale art is less consistently logo-led.
- The card should read as a deal signal, not as a freebie template recolor.

### 8.3 Festival / event

Canonical family: `FESTIVAL`

Primary behavior:

- Lead with event identity and timing, not store-price treatment.
- Use event/state labeling in the top zone and keep the lower third editorial rather than aggressively transactional.
- Favor event framing, curated atmosphere, and timing relevance over discount-style arithmetic density.
- Event cards should stay inside the shared zone system even when their palette and metadata emphasis differ from game-sale cards.

### 8.4 Roundup / top-list

Canonical family: `TOP_LIST`

Primary behavior:

- Lead with editorial curation rather than a single-item transaction.
- The title should explain the digest; the hero should support the theme or best-ranked lead item.
- Metadata should communicate list context, theme, or size, not sale urgency.
- Top-list cards should remain part of the same YOTO family system, even though their artwork selection currently enters through a separate adapter seam.

### 8.5 Fallback / low-asset

Fallback is not its own semantic family. It is a rendering mode that can happen inside any family.

Primary behavior:

- Preserve the family skeleton and hierarchy.
- Make the title and status readable without pretending the missing hero exists.
- Use deterministic branded placeholder composition, not generic empty-state visuals.
- Long-title fallback cards should compact safely without clipping or crowded duplication.

## 9. Recommended Lower-Third And Info-Band Strategy

The lower third is the core stability layer of the premium YOTO card system.

Canonical policy:

- The lower-third title is the primary text anchor for every family.
- The title block should be calm, readable, and not forced to compete with the hero.
- The info band should sit directly below the title and behave as one row of prioritized facts.
- Family-specific info-band emphasis:

| Family | Primary info-band signal | Secondary signal |
| --- | --- | --- |
| `FREE_GAME` | deadline / claim window | old price / prior value |
| `DISCOUNT` | current price / discount state | old price and deadline |
| `FESTIVAL` | event timing / event context | supporting editorial metadata |
| `TOP_LIST` | list label / roundup context | supporting editorial phrase |

- The brand lockup should sit as a quiet signature, typically at the right edge of the lower-third system, without competing with the title or primary metadata.

## 10. Recommended Fallback Strategy

Fallback strategy is canonical only when it remains truthful and stylistically inside the family system.

Approved fallback policy:

- Prefer localized or cached real assets when available.
- Preserve selector quality rules even in offline or snapshot-driven validation.
- Use deterministic placeholder art when no truthful usable asset survives the selector.
- Keep the same top zone, lower-third zone, and info-band logic as the active family.
- Never manufacture screenshots, store logos, or promotional proof that the source did not provide.
- Never make fallback look like a separate product line.

## 11. What A Premium YOTO Card Means Operationally

A premium YOTO card is not defined by ornament. It is defined by operational quality that survives real production conditions.

A card qualifies as premium when it is:

- truthful to the offer, state, and available media
- deterministic to render from the same inputs
- readable on the Telegram surface at first glance
- typographically clean in Ukrainian
- visually intentional across bright art, dark art, logo-heavy art, long titles, and fallback states
- consistent with its semantic family while still feeling like part of one YOTO system
- validated through the repo proof path, not just judged from code inspection

It is not premium when it:

- depends on lucky hero art to be readable
- repeats the same signal across multiple zones without reason
- shifts to a different visual language when assets are missing
- clips or corrupts Ukrainian text
- passes tests but produces weak Telegram-surface composition

## 12. Canonical Validation Expectation

Future card work should be evaluated against one multi-family review mindset rather than a single lucky case.

Minimum review set:

- logo-heavy hero art
- hero art without strong logo
- fallback / low-asset case
- long-title case
- short-title case
- darker hero
- brighter hero
- at least one truthful Telegram proof when publishable

Current repo evidence for this review model already exists in:

- `tools/generate_yoto_v451_live_validation_pack.py`
- `output/cards/live_validation_v45/validation_manifest.json`
- `output/cards/epic_free_composition_review_20260318T232611Z/review_manifest.json`

## 13. Implementation Guidance After This Blueprint

This blueprint implies the following practical rules for future work:

- Extend family behavior through the existing selector plus `YotoCardEngineV4` seam.
- Reuse the Epic family's composition-policy structure as a pattern, not as a copy-paste destination.
- Bring `DISCOUNT`, `FESTIVAL`, and `TOP_LIST` up to the same family-definition clarity before inventing new variants.
- Keep `TemplateSystem` fallback-safe, but stop treating it as the design center.
- Consolidate review around one canonical multi-family validation pack and Telegram proof path.

## Bottom Line

The canonical YOTO card system is:

- four semantic families
- one shared zone model
- one selector contract
- one primary YOTO composition engine
- one explicit fallback policy
- one legacy compatibility boundary

That is now the repo-level card-system reference for future implementation work.
