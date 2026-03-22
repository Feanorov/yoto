# FESTIVAL Caption Freeze Review Pack

Generated at (UTC): 2026-03-19T23:23:31.543377Z
Before manifest: D:\Telegram\output\captions\festival_freeze_before_20260319T230822Z\before_manifest.json
Output root: D:\Telegram\output\captions\festival_freeze_review_20260319T232331Z

## Summary

- cases: 3
- before signals: generic_window_mentions=2, shortlist_mentions=3, wishlist_mentions=1, focused_scan_mentions=0
- after signals: generic_window_mentions=0, shortlist_mentions=0, wishlist_mentions=0, focused_scan_mentions=1

## Strong source case

- slug: `strong_source`
- title: `Steam Tower Defense Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Це один із тих фестивалів, де зручно за один раз скласти короткий список.', 'selected_cta': 'Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у список бажаного.', 'repeat_risk': False, 'fallback_used': False}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Тут сенс не в тому, щоб дивитися все підряд, а в тому, щоб швидко знайти кілька точних попадань.', 'selected_cta': 'Зайдіть хоча б на основні секції фестивалю: за кілька хвилин стане ясно, чи є тут ваші тайтли.', 'repeat_risk': False, 'fallback_used': False}
- before signals: {'generic_window_mentions': 1, 'shortlist_mentions': 1, 'wishlist_mentions': 1, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- comparison file: `comparisons/strong_source.md`

### Before

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Це один із тих фестивалів, де зручно за один раз скласти короткий список.

Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.

Подія триватиме до 26 березня 2026, 17:00.

Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у список бажаного.

#steam #festival #gaming #strategy
```

### After

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Тут сенс не в тому, щоб дивитися все підряд, а в тому, щоб швидко знайти кілька точних попадань.

Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.

Вікно фестивалю — до 26 березня 2026, 17:00.

Зайдіть хоча б на основні секції фестивалю: за кілька хвилин стане ясно, чи є тут ваші тайтли.

#steam #festival #gaming #strategy
```

## Sparse source case

- slug: `sparse_source`
- title: `Steam Next Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.', 'selected_cta': 'Такі фестивалі найкраще працюють, коли швидко відсікаєте своє прямо зі сторінки.', 'repeat_risk': False, 'fallback_used': True}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Цей фестиваль краще читати як коротку добірку по темі, а не як ще одну довгу вітрину.', 'selected_cta': 'Почніть із верхівки сторінки та тематичних секцій: цього вже вистачить, щоб швидко відмітити своє.', 'repeat_risk': False, 'fallback_used': True}
- before signals: {'generic_window_mentions': 1, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- comparison file: `comparisons/sparse_source.md`

### Before

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.

Фестиваль варто читати як коротке вікно для відбору свого, а не як чергову шумну вітрину.

Подія триватиме до 26 березня 2026, 17:00.

Такі фестивалі найкраще працюють, коли швидко відсікаєте своє прямо зі сторінки.

#steam #festival #gaming
```

### After

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Цей фестиваль краще читати як коротку добірку по темі, а не як ще одну довгу вітрину.

Це коротке тематичне вікно, яке краще читати через ключові секції, а не довгим суцільним скролом.

Вікно фестивалю — до 26 березня 2026, 17:00.

Почніть із верхівки сторінки та тематичних секцій: цього вже вистачить, щоб швидко відмітити своє.

#steam #festival #gaming
```

## Edge case / no deadline / English-only source

- slug: `edge_no_deadline`
- title: `Steam Automation Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'У Steam зараз є тематичне вікно, яке варте швидкого проходу.', 'selected_cta': 'Це зручне вікно, щоб за один прохід скласти собі короткий список.', 'repeat_risk': False, 'fallback_used': True}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'У Steam відкрилося тематичне вікно, яке зручніше проходити точково, ніж суцільним скролом.', 'selected_cta': 'Найкращий хід тут простий: відкласти кілька точних попадань і не тонути в решті каталогу.', 'repeat_risk': False, 'fallback_used': True}
- before signals: {'generic_window_mentions': 0, 'shortlist_mentions': 2, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 1}
- comparison file: `comparisons/edge_no_deadline.md`

### Before

```html
🎉 <a href="https://store.steampowered.com/category/automation"><b>Steam Automation Fest</b></a>

У Steam зараз є тематичне вікно, яке варте швидкого проходу.

Ключова тема цього фестивалю — симулятор: сторінку зручно пройти як короткий маршрут по демо та знижках.

Подія вже триває, тож короткий список краще скласти без відкладань.

Це зручне вікно, щоб за один прохід скласти собі короткий список.

#steam #festival #gaming #simulation
```

### After

```html
🎉 <a href="https://store.steampowered.com/category/automation"><b>Steam Automation Fest</b></a>

У Steam відкрилося тематичне вікно, яке зручніше проходити точково, ніж суцільним скролом.

Фокус тут — симулятор. Сторінку зручно пройти як короткий маршрут по ключових секціях фестивалю.

Фестиваль уже триває, тож сторінку краще пройти одним заходом.

Найкращий хід тут простий: відкласти кілька точних попадань і не тонути в решті каталогу.

#steam #festival #gaming #simulation
```
