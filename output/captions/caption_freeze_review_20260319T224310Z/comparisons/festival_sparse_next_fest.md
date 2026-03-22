# FESTIVAL / sparse source

- family: `FESTIVAL`
- source_kind: `fixture`
- title: `Steam Next Fest`
- before signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 2}
- after debug: {'offer_id': 'fixture:festival-sparse', 'lane': 'event_festival', 'presence': 'indirect', 'style': 'festival', 'opening': {'selected': 'Це один із тих фестивалів, де зручно за один раз скласти shortlist.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False, 'line': 'Це один із тих фестивалів, де зручно за один раз скласти shortlist.'}, 'cta': {'selected': 'Це зручне вікно, щоб за один прохід скласти собі короткий shortlist.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False}, 'selected_opener': 'Це один із тих фестивалів, де зручно за один раз скласти shortlist.', 'normalization_applied': {'removed_replacement_chars': False, 'removed_garbage_unicode': False, 'normalized_dashes': False, 'normalized_whitespace': False, 'normalized_punctuation_spacing': False}, 'weird_symbol_detected': False, 'repeat_risk': False, 'fallback_used': True}

## Before

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Steam Next Fest збирає знижки, демо та жанрові знахідки в одному місці.

Тематична подія зі знижками, демоверсіями та тематичними добірками, тож це хороший момент пройтися по фестивалю.

Фестиваль триває до 26 березня 2026, 17:00.

Перегляньте фестиваль зараз, поки він у розпалі.

#steam #festival #gaming
```

## After

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Це один із тих фестивалів, де зручно за один раз скласти shortlist.

Фестиваль варто читати як коротке вікно для відбору свого, а не як чергову шумну вітрину.

Подія триватиме до 26 березня 2026, 17:00.

Це зручне вікно, щоб за один прохід скласти собі короткий shortlist.

#steam #festival #gaming
```
