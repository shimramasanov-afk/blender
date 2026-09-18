# Corner Hook: бюджет Slide и доворот за угол

Дата: 2026-09-17. Имён сцен нет. Порог детектора 0.12 не снижали. F14/F15 SHA без изменений
(`8f90a697f1a348dfea2547041e609e32fba4d265` / `6b7644ee7163fed22e62cb82d3d924dff7ae5c19`).

## Зачем

После глубокого Probe отворот ~120° плюс бесконечный Slide (`turn=0`) идёт назад-вбок в край
карты (`min_x` 0.59 / 0.37). Цель не попадает в FOV. `CLOSE_TRAP` не трогали.

## Политика (`OBSTACLE_BYPASS`)

1. Peel 26 тиков (`skirt_turn=0.45`, ~120°).
2. Slide 22 тика: `forward=0.55`, `turn=0`.
3. Corner Hook: `forward=0.35`, `turn=-sign * skirt_turn`, пока нет пятна.
4. Пятно (`conf >= 0.12`): сторона по пеленгу; 16 тиков держат курс хука (`forward=0.90`),
   чтобы не врезаться в угол AABB; дальше seek с полом `bypass_seek_forward=0.68`
   (бокс в кадре сбоку иначе душит тормоз).
5. Срыв пятна после deep-обхода: разворот на месте к `last_bearing`, не исходный Peel.

`dead_end` / `u_trap` остаются `CLOSE_TRAP` (`shallow`), hook не запускается.

## Прогоны training v0, seed=0, max_steps=200

| Сцена | Исход | Тики | col | probe | shallow | hook | seen | acq | min_x |
|---|---|---|---|---|---|---|---|---|---|
| `dead_end` | **success** | **147** (≤150) | 0 | 9 | True | — | 23 | 24 | 3.91 |
| `u_trap` | success | 52 | 0 | 2 | True | — | 15 | 16 | 3.92 |
| `open_goal` | success | 72 | 0 | — | — | — | — | — | — |
| `narrow_gate` | success | 84 | 0 | — | — | — | — | — | — |
| `corridor` | success | 94 | 0 | — | — | — | — | — | — |
| `latency_drops` | success | 76 | 0 | — | — | — | — | — | — |
| `single_obstacle` | **success** | **190** | 0 | 46 | False | 95 | **118** | 119 | 3.45 |
| `weak_texture` | **success** | **191** | 0 | 55 | False | 104 | **127** | 128 | 3.45 |
| `long_fence` | timeout 200 | 200 | 0 | 36 | False | 85 | **None** | — | 3.45 |

`single_obstacle`: span_x=6.84, span_y=2.38, конец (10.29, 7.79). Край мира не задет.

`long_fence` (грань ~8.4 м) не очищается за 22 тика Slide; hook заворачивает, пока агент ещё
перед забором. LOS нет. Это не регрессия компактного бокса.

`pytest` `test_baseline` + `test_memory` + `test_repair_regressions` зелёный. Frozen 60 не гоняли.
