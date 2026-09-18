# Post-H14 — канонический Frozen 60

Дата: 2026-09-17.  
Команда: `python -m l2_brain baseline-eval --seed 0 --suite frozen --out docs/evidence/post-h14/frozen-baseline.json`  
Контроллер: `baseline_memory_v1`. Энкодер: `navigation_v1`. Каналы: `all`.  
Логику до этого прогона не меняли. F14/F15 не перезаписывались.

## Счёт

**44 / 60** успехов. train 27/36, val 9/12, held-out 8/12.

| Исход | N |
|---|---|
| success | 44 |
| oscillate | 11 |
| stuck | 3 |
| timeout | 2 |

Причины: none 44, mixed 15, control 1.  
Recovery: GT-окон 0, детекций 0. encode p50 3.78 мс, infer p50 0.044 мс.

Это не замена F14 (23/60) и не H15 (24/60): другой код после хода 14.

## По сценам

| Сцена | Успех | Исходы провалов |
|---|---|---|
| `open_goal` | 5/5 | — |
| `narrow_gate` | 5/5 | — |
| `corridor` | 5/5 | — |
| `u_trap` | 5/5 | — |
| `dead_end` | 5/5 | — |
| `vanishing_target` | 5/5 | — |
| `camera_spin` | 5/5 | — |
| `latency_drops` | 5/5 | — |
| `moving_target` | 4/5 | held_out v4 stuck 200 |
| `single_obstacle` | 0/5 | osc 2, stuck 1, timeout 2 |
| `long_fence` | 0/5 | osc 4, stuck 1 |
| `weak_texture` | 0/5 | oscillate 5 |

Категории:

- **Пеленг есть / курс держится (40/40):** open_goal, gate, corridor, ловушки, vanish, spin, drops.
- **Цель движется (4/5):** moving_target; held-out не тюнили.
- **Цели нет в LOS, фронт закрыт (0/15):** obstacle, fence, weak_texture — осцилляция руля у барьера.

## Что замораживается

Этот JSON — база хода 15. Правка обхода сравнивается с ним, не с F14.
