# FESTIVAL / strong source

- family: `FESTIVAL`
- source_kind: `fixture`
- title: `Steam Tower Defense Fest`
- before signals: {'назавжди': 0, 'забрати': 0, 'клейм': 0, 'wishlist': 0, 'коментар': 0, 'shortlist': 0}
- after signals: {'назавжди': 0, 'забрати': 0, 'клейм': 0, 'wishlist': 1, 'коментар': 0, 'shortlist': 0}
- after debug: {'offer_id': 'fixture:festival-strong', 'lane': 'event_festival', 'presence': 'indirect', 'style': 'festival', 'opening': {'selected': 'Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False, 'line': 'Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.'}, 'cta': {'selected': 'Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у wishlist.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False}, 'selected_opener': 'Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.', 'normalization_applied': {'removed_replacement_chars': False, 'removed_garbage_unicode': False, 'normalized_dashes': False, 'normalized_whitespace': False, 'normalized_punctuation_spacing': False}, 'weird_symbol_detected': False, 'repeat_risk': False, 'fallback_used': False}

## Before

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Steam Tower Defense Fest збирає знижки, демо та жанрові знахідки в одному місці.

Тематична подія зі знижками, демоверсіями та тематичними добірками, тож це хороший момент пройтися по фестивалю.

Фестиваль триває до 26 березня 2026, 17:00.

Перегляньте фестиваль зараз, поки він у розпалі.

#steam #festival #gaming
```

## After

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.

Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.

Подія триватиме до 26 березня 2026, 17:00.

Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у wishlist.

#steam #festival #gaming #strategy
```
