# FESTIVAL / strong source

- family: `FESTIVAL`
- source_kind: `fixture`
- title: `Steam Tower Defense Fest`
- before signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after debug: {'presence': 'indirect', 'style': 'festival', 'fallback_used': False, 'repeat_risk': False, 'opening_repeat_risk': False, 'cta_repeat_risk': False, 'lane': 'event_festival'}

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

Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у список бажаного.

#steam #festival #gaming #strategy
```
