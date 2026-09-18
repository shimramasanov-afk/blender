# Budget trim: вынос за торец и спринт после wrap

Дата: 2026-09-17. Имён сцен нет. Порог 0.12 не снижали. F14/F15 SHA без изменений
(`8f90a697f1a348dfea2547041e609e32fba4d265` / `6b7644ee7163fed22e62cb82d3d924dff7ae5c19`).

## Зачем

После Post-Edge Wrap захват на `long_fence` был на 186 при лимите 200, dist=5.12.
14 тиков × `max_speed=0.12` = 1.68 м — финиш физически не укладывается.

## Что пробовали и отвергли

`probe_forward` 0.45 → 0.75 и `probe_gate` 14 → 9. На открытом объёме expansion
на скорости 0.75 даёт тот же порог `0.08`, что и контакт в `dead_end`. Probe
обрывается на `x≈5.2` вместо `x≈5.9`: Peel/Slide/Hook у компактного бокса
срываются в южную грань (stuck, десятки коллизий). Порог контакта Probe
отдельно от `front_blocked` не разделяет тупик и стену — оба дают expansion 0.08.
`probe_forward` оставлен **0.45**, gate **14**.

`edge_reslide` 25: wrap стартует у `y≈4.0`, вынос на восток скребёт южную грань
забора (радиус 0.28). Оставлено **32**.

## Что осталось

- `edge_reslide_ticks=32` (было 35): торец проходится, без ухода на `y=3.11`.
- После wrap-захвата: `wrap_clear_ticks=8` с `turn=0` (не сразу в торец), затем
  `wrap_sprint_forward=1.0` при `|bearing| ≤ 0.22`.
- Recovery не стартует, пока идёт clear.
- `CLOSE_TRAP`, первый hook и `hook_clear=12` у бокса без изменений.

## Прогоны training v0, seed=0, max_steps=200

| Сцена | Исход | Тики | col | seen | acq | примечание |
|---|---|---|---|---|---|---|
| `dead_end` | **success** | **147** | 0 | 23 | 24 | probe=9 shallow |
| `u_trap` | success | 52 | 0 | — | — | |
| `open_goal` | success | 72 | 0 | — | — | |
| `narrow_gate` | success | 84 | 0 | — | — | |
| `corridor` | success | 94 | 0 | — | — | |
| `latency_drops` | success | 76 | 0 | — | — | |
| `single_obstacle` | **success** | **193** | 0 | 118 | 119 | |
| `weak_texture` | **success** | **190** | 0 | 127 | 128 | |
| `long_fence` | **timeout** | 200 | 0 | **182** | **183** | wrap 151, min_y=3.55, конец (8.54, 4.47), dist=4.47 |

Забор ближе, чем на hod21 (acq 186 / dist 5.12), финиша в 200 нет: после 183
остаётся ~17 тиков на ~4.5 м.

`pytest` `test_baseline` + `test_memory` + `test_repair_regressions` зелёный. Frozen 60 не гоняли.
