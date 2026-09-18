# Peel & Slide — слепой обход

Дата: 2026-09-17. Имён сцен нет. Порог 0.12 не снижали.

## Динамика (не 8 тиков = 180°)

`turn=0.45` × `max_turn=0.18` → **0.081 рад/тик**.  
8 тиков ≈ 37°, 10 ≈ 46°, 40 ≈ 185°.  
Чтобы цель за спиной попала в FOV 1.2, нужно ≈ 40 тиков Peel, не 8–10.

`peel_ticks=40`. Если цель хоть раз взята (`had_target`), повторный Slide не включается — иначе `dead_end` после срыва пятна вползает в боковую стену.

## `_blind_command`

- Peel (`peel_age ≤ 40`): `turn = sign·0.45`, `forward = 0.20`
- Slide: `turn = sign·0.05`, `forward ≥ 0.50`
- `conf ≥ search_conf`: `side_lock=0`, `peel_age=0`, штатный seek/course_lock

## Прогоны

| Сцена | Исход | Тики |
|---|---|---|
| `dead_end` v0 | **success** | **140** (≤150) |
| `open_goal` v0 | success | 72 |
| `narrow_gate` v0 | success | 84 |
| `u_trap` v0 | success | 69 |
| `single_obstacle` v0 | timeout 200 | col=91, цель не появилась |
| `long_fence` v0 | stuck 200 | col=106 |
| `weak_texture` v0 | stuck 200 | col=104 |

15 стеновых вариантов: финиша нет. После Peel ≈180° корпус смотрит назад, Slide уносит к краю мира (x≈0.3), LOS на цель не открывается. Это не дребезг (`dir` 0–3), и не циркуляция на пятачке: смещение span_x≈3.4, но **от** препятствия.

`pytest` зелёный.
