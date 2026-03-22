# Strong source case

- title: `Steam Tower Defense Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Це один із тих фестивалів, де зручно за один раз скласти короткий список.', 'selected_cta': 'Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у список бажаного.', 'repeat_risk': False, 'fallback_used': False}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Тут сенс не в тому, щоб дивитися все підряд, а в тому, щоб швидко знайти кілька точних попадань.', 'selected_cta': 'Зайдіть хоча б на основні секції фестивалю: за кілька хвилин стане ясно, чи є тут ваші тайтли.', 'repeat_risk': False, 'fallback_used': False}
- before signals: {'generic_window_mentions': 1, 'shortlist_mentions': 1, 'wishlist_mentions': 1, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}

## Before

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Це один із тих фестивалів, де зручно за один раз скласти короткий список.

Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.

Подія триватиме до 26 березня 2026, 17:00.

Пробігтися сторінкою варто хоча б заради демо й кількох можливих попадань у список бажаного.

#steam #festival #gaming #strategy
```

## After

```html
🎉 <a href="https://store.steampowered.com/category/tower_defense"><b>Steam Tower Defense Fest</b></a>

Тут сенс не в тому, щоб дивитися все підряд, а в тому, щоб швидко знайти кілька точних попадань.

Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.

Вікно фестивалю — до 26 березня 2026, 17:00.

Зайдіть хоча б на основні секції фестивалю: за кілька хвилин стане ясно, чи є тут ваші тайтли.

#steam #festival #gaming #strategy
```
