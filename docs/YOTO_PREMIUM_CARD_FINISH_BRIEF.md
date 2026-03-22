# YOTO Premium Card Finish Brief

Date: 2026-03-19

This pass defines the finish rules for the active YOTO card system after the typography system work. It does not redesign renderer ownership or family semantics. It tightens the current engine so the four canonical families read as one premium editorial product on Telegram.

## Target Hierarchy

Every card should read in this order:

1. Family / source state.
2. Title or roundup subject.
3. Primary action or editorial context.
4. Supporting fact row.
5. Quiet YOTO signature.

The lower third is the main reliability layer. It should feel sculpted and intentional, not like generic UI pasted over art.

## Shared Finish Rules

- Use one shared lower-third rhythm across families: kicker, anchored title shelf, fact row, quiet brand lockup.
- Keep the title as the strongest stable read, but support it with a subtle editorial shelf so it does not float over the panel.
- Use one chip grammar: one active pill for the primary fact, one muted pill for support, no stack of equal-weight micro-panels.
- Keep the top-right family badge deliberate and compact enough that it signals state without overpowering the hero.
- Preserve deterministic Ukrainian-safe font fallback and avoid decorative effects that hurt crispness.
- Fallback cards must keep the same hierarchy language as live-art cards.

## Family-Specific Finish Rules

### FREE_GAME
- Lead with availability and deadline.
- Keep the free signal bright, but let the title shelf and lower-third rhythm carry the premium feel.

### DISCOUNT
- Lead with title plus current deal signal.
- Price chips should feel transactional and sharp, not loud.

### FESTIVAL
- Lead with event identity and timing.
- Use the lower-third fact row as editorial event context, not discount arithmetic.
- Keep the badge calmer than sale/free cards.

### TOP_LIST
- Read as editorial curation, not as a recolored deal card.
- Use the lower-third fact row to surface list context so the card does not feel empty.
- The rank/list signal should be compact, premium, and clearly subordinate to the roundup title.

## Premium-Finished Means

A card is premium-finished in YOTO terms when:

- the four canonical families feel related at a glance
- TOP_LIST and FESTIVAL no longer look like weaker exceptions
- title, fact row, and brand lockup feel anchored to one shared system
- bright art, dark art, long titles, and fallback cases all stay readable on Telegram
- proof artifacts show the finish pass clearly, not only tests or code
