# Ход 14 — системные баги навигации

Дата: 2026-09-17.  
CLI: `docs/evidence/hod14-nav.json` (40 эпизодов, 39 успехов).  
F14/F15 не перезаписывались (`baseline-nav.json`, `baseline-memory-nav.json`).  
S2 / HID / SCK / Metal / SNN / MaleCNS / карты не открывались.  
Порог детектора `target_min_conf=0.12` не снижался глобально.

База «до» — training v0, 200 тиков, `navigation_v1`, до правок хода 14.

## Шаг 1. C4 / C7 — порог движения

**Симптом.** `search_forward=0.18` < `cmd_forward_min=0.20` → поиск не считался командой вперёд.

**Правка.** `cmd_forward_min=0.18` и проверка `cmd_forward_min <= search_forward`.

**Дельта training v0.** `open_goal` 170→170 success; `dead_end` 155→155 success. Константы синхронизированы. `rear_goal_*` не менялись.

## Шаг 2. S4 — `narrow_gate`

**Симптом.** Цель видна (~64 px, conf 0.125), ударов 0, timeout 200. После фикса курса recovery срабатывал на тике 13: столбы дают повтор сцены, `expansion=0`, evidence ≥ 0.62.

**Правка.** Course lock: после 4 тиков с `|bearing|≤0.22` `forward≥0.72`, в допуске turn=0. На время lock evidence/recovery не копятся. Вне допуска курс не глушится.

**Дельта.**

| Эпизод | До | После |
|---|---|---|
| `narrow_gate` training v0 | timeout 200, col=0 | success **84**, col=0 |
| `narrow_gate` 5 вариантов | — | **5/5**, 83–84 тика |
| `open_goal` v0 | success 170 | success **72** |
| `dead_end` v0 | success 155 | success **138** |
| `u_trap` v0 | success 195 | success **179**, col=5 |

## Шаг 3. S6 — `latency_drops`

**Симптом.** `color_blob` 5/5, полный контур 0/5: SAD/расширение на дропе и сдвиг пеленга командой на stale.

**Правка.** `stale_flow_hold=2`: поток и expansion зануляются на drop и ещё 2 кадра. На stale пеленг не крутится последней командой, только decay.

**Дельта.** `latency_drops` 0/5 timeout 200 → **5/5** (v0 76 тиков; v1 135). `color_blob` остаётся 5/5.

## Шаг 4. S3 / V1 — `corridor`

**Симптом.** Пятно есть, mass≈0.011, raw conf=0.088 < 0.12, контроллер в `search`.

**Правка.** Гистерезис: acquire 0.12; удержание/первый захват при `conf≥0.08`, если уже трек или пятно центрировано **и** компактно (`center ≥ 2·max(left,right)`).

**Дельта.**

| | До | После |
|---|---|---|
| `corridor` training v0 | timeout 200, miss 0.442, conf 0.072 | success **94** |
| `corridor` 5 вариантов | 4/5 (v0 timeout) | **5/5**, по 94 тика |
| пустые текстуры (4 кадра) | — | FP **0/4** (шум не захватывается) |

## Что не закрыто

- `single_obstacle`, `long_fence`, `weak_texture` — oscillate 200 на training v0.
- `moving_target` held_out v4 — stuck 200; training/val 4/4 success. Held-out не тюнили.
- Полный frozen 60 не гоняли; этот файл не замена F14 (23/60) и не H15 (24/60).
- Recovery на каталоге по-прежнему 0 GT-окон.

## Проверки

`pytest` зелёный. CLI `baseline-eval --seed 0` на 8 сценах → 39/40.
