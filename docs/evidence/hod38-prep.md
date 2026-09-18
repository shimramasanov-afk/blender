# Ход 38: нативный фокус и калибровка HUD

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Боевой ввод в клиент
не слали. `live_confirmed` для физического HID не включали.

## Фокус

`osascript` с горячего пути снят. `frontmost_app()` читает
`NSWorkspace.sharedWorkspace.frontmostApplication` через ctypes/libobjc.

JSON: [hod38/focus-bench.json](hod38/focus-bench.json)
SHA1 `3df7eb2005c7a911b3acd7e4d16da539db3f91e9`.

| метрика | значение |
|---|---|
| backend | `nsworkspace` |
| focus p50 / p95 | **0.0047 / 0.0055 мс** (n=80, warmup=12) |
| act_ms p50 / p95 | **0.016 / 0.019 мс** |
| osascript в контуре | false |
| hid_sent | **false** |
| контроль osascript p50 / p95 | 175.9 / 183.9 мс (n=8, не в коде ввода) |

`act_ms` этого замера — `RecordingPoster` + нативная проверка фокуса.
Это не повтор live-CGEvent в гостя. Узкое место хода 37 (спавн
интерпретатора ~176–216 мс) с горячего пути убрано.

CLI: `l2-brain focus-bench`.

## Кадр клиента

Окно Parallels `Windows 11` id **13944** сначала было на соседнем Space
(`on_screen=false`). Скрытый захват не брали. На хосте один раз
Control+Right (Mission Control), затем SCK без профиля (маски профиля
чёрнят ROI и для калибровки непригодны), затем возврат.

В госте в этот момент был `L2.exe` (Console). HID не слали.

| поле | значение |
|---|---|
| кадр | 4112×2580, mean luma 64.8, не чёрный |
| hid_sent | **false** |
| клиент | оконный Interlude на рабочем столе гостя, не fullscreen VM |
| плейсхолдеры `self_*` / `target_*` | попали в хром VM / Recycle Bin, **не в HUD** |
| виджеты на кадре | макро (слева сверху), чат, хотбар, System Menu |
| цель | нет |
| полосы HP/MP/CP | отдельный статус-виджет не выделен |

Эталон: [live-s4/client-reference.png](live-s4/client-reference.png)
SHA1 `314cfba2a9338b4b5c9b044d1274ead4dc2c3373`.

Оверлей плейсхолдеров: [live-s4/hud-overlay.png](live-s4/hud-overlay.png).

Оранжевая рамка окна клиента: [live-s4/hud-overlay-measured.png](live-s4/hud-overlay-measured.png).

JSON: [live-s4/calibrate-hud.json](live-s4/calibrate-hud.json)
SHA1 `34f95deef81d1806d109679b15192ddaae1b667f`.

Измеренное окно клиента в координатах кадра (не HUD):
`pixel_box [591, 272, 3585, 2465]`,
`norm_rect [0.1437, 0.1054, 0.7281, 0.8500]`.
Низ рамки обрезан над панелью задач гостя, допуск ±15 px.

В чате кадра читается `LineageII Interlude Server`. Это хроника на
этом прогоне, не допуск Q6 и не разметка полос.

CLI: `l2-brain calibrate-hud --window-id <id>`.

`parallels_l2.json`: числа HUD не переписывали. В `note` записано, что
плейсхолдеры не попадают в виджеты Interlude.

## Чего нет

S4. H8. Живой ввод в `L2.exe`. Новые координаты `self_hp` / `target_hp`.
Повторный live-probe с физическим HID. Заявка «act_ms < 2 мс в госте».
