# Ход 39: измеренные ROI HUD Interlude

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. HID не слали.
SCK в этом ходе не открывали: разметка по уже записанному кадру F45.

## Кадр

[interlude-target-active.png](live-s4/interlude-target-active.png)
SHA1 `902009e4dc9872ea36cc5ccc816210341fce676e`.
4112×2580, mean luma 60.18.

Оконный Interlude. Свои полосы: **BotEbaniy** CP 50/50, HP 126/126,
MP 38/38. Цель: **Gremlin**, текстового HP на виджете нет.

Оверлей: [hud-overlay-hod39.png](live-s4/hud-overlay-hod39.png)
SHA1 `ef9df8677e254549a17dbacb1a9dc5d366ae003c`.
Верх: [hod39-overlay-top.png](live-s4/hod39-overlay-top.png).

JSON: [calibrate-hud-hod39.json](live-s4/calibrate-hud-hod39.json)
SHA1 `790157a06356e86056a38f8ba3ee01ed4719023e`.

`hid_sent` **false**. CLI:
`l2-brain calibrate-hud --from-png docs/evidence/live-s4/interlude-target-active.png --tag hod39`.

## Измеренные боксы (4112×2580)

| ROI | pixel_box |
|---|---|
| `self_bars` | 48, 96, 448, 268 |
| `self_cp` | 300, 177, 404, 184 |
| `self_hp` | 316, 205, 404, 211 |
| `self_mp` | 300, 218, 404, 236 |
| `target_frame` | 1940, 76, 2760, 165 |
| `target_hp` | 2001, 139, 2711, 142 |

Записаны в `config/window_profiles/parallels_l2.json`.
Плейсхолдеры F44 не переносились.

## Парсер на этом кадре

| поле | значение | сверка |
|---|---|---|
| `valid` | true | кадр не чёрный |
| `self_cp_ratio` | **0.962** | текст 50/50 = 1.0 |
| `self_hp_ratio` | **0.943** | текст 126/126 = 1.0 |
| `self_mp_ratio` | **0.952** | текст 38/38 = 1.0 |
| `target_locked` | **true** | виджет Gremlin |
| `target_hp_ratio` | **0.444** | текста HP нет, не GT |

Свои полосы в пределах **8 п.п.** от 1.0. Скруглённые края Classic
не дают синтетические ±2%.

`VisionTelemetryBridge`: 2 события, `source=ui_vision`.
`HealthUpdate.current_hp` 94.3 / 100 (доля, не 126).
`TargetState.locked=true`, `hp_percent` 44.4.

## Ложные срабатывания

Кадр F44 [client-reference.png](live-s4/client-reference.png) при этих
ROI: `self_*` = 0, `target_locked=false`. Виджеты в другой раскладке
(окно/камера). Старый детектор «контраст рамки» на камне F44 дал бы
цель; замок теперь только по красной полосе `target_hp`.

Пустая полоса цели (смерть) = `target_locked=false`. Это тот же ответ,
что «цели нет». Отдельного признака трупа нет.

Перетаскивание окон Classic сдвигает ROI.

## Что изменили в коде

- `HP_RED` нижняя граница R 140→130 (тёмная кромка Interlude).
- `target_locked` по `extract_bar_ratio(target_hp) > 0`, не по std/span.
- `read_png`, `calibrate-hud --from-png` (офлайн, без SCK).
- Синтетика ±2% и контраст без красного → не цель: `tests/test_hud_parser.py`.

`pytest` зелёный. Frozen 60 / `sim/` не гоняли.

## Чего нет

S4. H8. H14. Живой ввод. Хотбар. Q6. Снятие `sim_ground_truth`.
Стабильность на пачке кадров. Дальность с пикселей.
