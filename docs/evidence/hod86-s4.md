# Ход 86: сетка слотов UI и калибровочный оверлей

Дата: 2026-09-18. Frozen L1 и `sim/` не трогали. Фарм нет.
ADR-0075. F86.

## Что сделано в коде

Жёсткие слоты в `parallels_l2.json`. CLI `layout-grid` рисует
оверлей. `WindowManager` ведёт стек и закрывает `Escape`.
Занятость: кромка окна, не плоская трава.

Первый живой прогон по проектному слоту Б `[1636, 140, 360, 480]`
дал `inventory_not_in_slot_b`: Tab открыл инвентарь ниже.
Слот Б совмещён с измеренной стоянкой.

JSON: [layout-slots-validation.json](live-s4/layout-slots-validation.json).  
PNG: `run/layout_guide.png`.

## Проверки

`pytest tests/test_layout_slots.py` — зелёный. Frozen L1 / `sim/`
не трогали.

## Живой прогон

Окно 16372, PID 68342. Dual flags. **1.330 с**. `ok=true`.
SHA1 `1ac0f4eb…`. `farm=false`. F1–F4 нет. Tab×1, Escape×2.

| поле | факт |
|---|---|
| slot_a window_px | 60, 140, 400, 520 |
| slot_b window_px | 1592, 650, 342, 307 |
| slot_b на кадре 4112×2580 | 3184, 1300, 3868, 1914 |
| clean_free | true |
| after_tab_occupied | true |
| after_escape_free | true |
| hid_sent | true |
| stuck_keys_count | 0 |

SCK 0.8 с на старте давал `no frame`; зонд ждёт 4.0 с.
Q5 не закрыт. Скилы (`Alt+K`) и макросы (`Alt+R`) не открывали.
