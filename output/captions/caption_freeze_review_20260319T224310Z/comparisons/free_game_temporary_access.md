# FREE_GAME / temporary-access edge case

- family: `FREE_GAME`
- source_kind: `fixture`
- title: `Space Raiders Free Weekend`
- before signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 1, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after debug: {'offer_id': 'fixture:temporary-freebie', 'lane': 'breaking_freebie', 'presence': 'indirect', 'style': 'temporary_freebie', 'opening': {'selected': 'Безкоштовний доступ відкритий саме для того, щоб перевірити гру без покупки.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False, 'line': 'Безкоштовний доступ відкритий саме для того, щоб перевірити гру без покупки.'}, 'cta': {'selected': 'Якщо хотіли чесний тест-драйв без ризику, це саме той випадок.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False}, 'selected_opener': 'Безкоштовний доступ відкритий саме для того, щоб перевірити гру без покупки.', 'normalization_applied': {'removed_replacement_chars': False, 'removed_garbage_unicode': False, 'normalized_dashes': False, 'normalized_whitespace': False, 'normalized_punctuation_spacing': False}, 'weird_symbol_detected': False, 'repeat_risk': False, 'fallback_used': True}

## Before

```html
🎁 <a href="https://store.steampowered.com/app/404040/Space_Raiders/"><b>Space Raiders Free Weekend</b></a>

Тут варто думати не про клейм, а про нормальну пробу перед покупкою.

Це гарна знахідка для бібліотеки, особливо якщо вам заходять екшени.

Замість 399 грн у гру зараз можна <a href="https://store.steampowered.com/app/404040/Space_Raiders/"><b>пограти безкоштовно</b></a>; доступ тимчасовий.

Безкоштовний доступ відкритий до 21 березня 2026, 20:00.

84% позитивних із 6800 оцінок • 27 досягнень • є картки

Якщо хотіли спробувати гру, зараз якраз зручне вікно зайти безкоштовно.

#steam #freegame #shooter #coop #action
```

## After

```html
🎁 <a href="https://store.steampowered.com/app/404040/Space_Raiders/"><b>Space Raiders Free Weekend</b></a>

Безкоштовний доступ відкритий саме для того, щоб перевірити гру без покупки.

Ключовий акцент тут — шутер, кооператив та екшен, тож безкоштовне вікно виглядає доречно.

Замість 399 грн зараз можна <a href="https://store.steampowered.com/app/404040/Space_Raiders/"><b>зіграти безкоштовно</b></a>; доступ тимчасовий.

Безкоштовний доступ відкритий до 21 березня 2026, 20:00.

84% позитивних із 6800 оцінок • 27 досягнень • є картки

Якщо хотіли чесний тест-драйв без ризику, це саме той випадок.

#steam #freegame #shooter #coop #action
```
