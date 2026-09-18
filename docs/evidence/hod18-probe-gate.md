# Probe Gate: разделение маневра по свободному ходу

Дата: 2026-09-17. Имён сцен нет. Порог детектора 0.12 не снижали. F14/F15 SHA без изменений
(`8f90a697f1a348dfea2547041e609e32fba4d265` / `6b7644ee7163fed22e62cb82d3d924dff7ae5c19`).

## Зачем

На тике 0 `steer` и `expansion` одинаково низкие у тупика (~1.4 м) и у стены (~3.0 м).
Спавн-Peel спасает `dead_end` и ломает обход. Подход без спавн-Peel открывал LOS у бокса
(seen 113 / 122 в ходе 17) и ломал `dead_end` (160–200).

Разница — не в первом кадре, а во времени до первого фронта.

## Политика

- Пока цели нет и `probe_done` ложен: `forward=0.45`, `turn=0`. Счётчик `probe_distance_ticks`
  растёт, пока нет фронта (`steer < 0.18` и `expansion < 0.03`). Unknown / `brake_risk` /
  stall-надбавка фронтом не считаются (F21).
- Первый фронт после warmup:
  - `probe_distance_ticks < 14` → `CLOSE_TRAP`: Peel на месте `turn=1.0`, `forward=0`
    (~18 тиков на 180°), без Slide.
  - иначе → `OBSTACLE_BYPASS`: Peel 26 тиков (`skirt_turn=0.45`, ~120°), затем Slide
    `forward=0.55`, `turn=0`.
- Нет фронта до `probe_give_up_ticks=55` → тот же bypass (глубокий объём без контакта).
- `conf >= search_conf` сразу рвёт Probe/Peel и берёт курс.

## Прогоны training v0, seed=0, max_steps=200

Официальный `run_episode` + тот же контур с `goal_observable` / позой.

| Сцена | Исход | Тики | col | probe | shallow | seen (LOS) | span_x | min_x |
|---|---|---|---|---|---|---|---|---|
| `dead_end` | **success** | **147** (≤150) | 0 | 9 | True | 23 | 5.14 | 3.91 |
| `u_trap` | success | 52 | 0 | 2 | True | 15 | 2.58 | 3.92 |
| `open_goal` | success | 72 | 0 | — | — | — | — | — |
| `narrow_gate` | success | 84 | 0 | — | — | — | — | — |
| `corridor` | success | 94 | 0 | — | — | — | — | — |
| `latency_drops` | success | 76 | 0 | — | — | — | — | — |
| `single_obstacle` | stuck 200 | 200 | 0 | 46 | False | **None** | 5.05 | 0.59 |
| `long_fence` | stuck 200 | 200 | 1 | 36 | False | **None** | 4.78 | 0.37 |
| `weak_texture` | stuck 200 | 200 | 0 | 55 | False | **None** | 4.60 | 1.40 |

Классификация совпала с геометрией спавна: тупики мелкие, барьеры глубокие.
`dead_end` уложился в 147 за счёт быстрого Peel (`trap_peel_turn=1.0`) после 9 зондирующих тиков.
При `skirt_turn=0.45` тот же latch давал success 159 — выше порога 150.

`open_goal` / `narrow_gate` / `corridor` / `latency_drops` без регрессии к ходу 17.

## Стена

LOS не открылся ни на одной из трёх сцен. После глубокого Probe агент делает ~120° и едет
прямо: `single_obstacle` конец (0.59, 1.26), `long_fence` (0.37, 0.33), `weak_texture` (1.40, 1.64).
AABB по-прежнему не скользит (F21): отворот меньше ~120° клинит шаг, а 120° + прямой Slide
смотрит от цели.

Относительно хода 17 компактные боксы снова уезжают к краю карты (`min_x` 3.40 → 0.59 / 1.40).
Это цена выбранного bypass, не ошибка классификации.

`pytest` `test_baseline` + `test_memory` + `test_repair_regressions` зелёный. Frozen 60 не гоняли.
