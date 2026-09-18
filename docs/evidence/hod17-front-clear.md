# Peel/Slide по освобождению фронта

Дата: 2026-09-17. Имён сцен нет. Порог 0.12 не снижали. F14/F15 SHA без изменений.

## Что измерили до правки

`brake_risk` на спавне ≈0.43 и у `dead_end`, и у стены: нет prev-frame / unknown. Это не «нос в барьер».

`steer`/`expansion` на тике 0 низкие у обеих. Стена (бокс 6.7–7.5) в 3 м, тупик — в 1.4 м. Стенд не скользит по AABB: заступ радиуса 0.28 отменяет весь шаг, поэтому отворот 70° вдоль грани оставляет агента в коллизии.

## Политика

- `front_blocked`: `steer_risk ≥ 0.18` или `expansion ≥ 0.03`. Не unknown, не stall-надбавка.
- `initial_front_blocked` после `front_warmup_ticks=1` (тик 0 без потока → False).
- Нет фронта: Peel на месте (`search_peel_forward=0`) до `peel_ticks=40` (~180°).
- Нет цели: unwind 17 тиков, подход `forward=0.50`, `turn=0`.
- Контакт после подхода (`approach_ticks≥16` и streak, или `approach_give_up=55`): Peel 26–28 тиков (~120°), Slide `turn=0` / `forward=0.55`, sidestep 30 + restore 13.
- `had_target` по-прежнему запрещает повторный Slide после срыва пятна.

## Прогоны training v0, seed=0, max_steps=200

| Сцена | Исход | Тики | col | span_x | min_x | seen (LOS) |
|---|---|---|---|---|---|---|
| `dead_end` | **success** | **134** (≤150) | 0 | 4.67 | 3.93 | 31 |
| `u_trap` | success | 64 | 0 | — | — | — |
| `open_goal` | success | 72 | 0 | — | — | — |
| `narrow_gate` | success | 84 | 0 | — | — | — |
| `corridor` | success | 94 | 0 | — | — | — |
| `latency_drops` | success | 76 | 0 | — | — | — |
| `single_obstacle` | stuck 200 | 200 | 0 | 2.92 | 3.40 | None |
| `long_fence` | stuck 200 | 200 | 0 | 2.99 | 0.41 | None |
| `weak_texture` | stuck 200 | 200 | 0 | 2.84 | 3.40 | None |

`open_goal` / `narrow_gate` / `corridor` / `latency_drops` без регрессии к ходу 16.

На стене LOS не открылся. `long_fence` ушёл к `min_x=0.41` (не x≈0.28 хода 16, но западный снос остался). `single_obstacle` / `weak_texture` на край мира не выехали (`min_x=3.40`).

Подход без спавн-Peel открывал LOS у бокса (seen 113 / 122) и ломал `dead_end` (160 или 200). Один таймер / одна фаза со спавна по-прежнему не закрывает оба класса.

`pytest` `test_baseline` + `test_memory` + `test_repair_regressions` зелёный. Frozen 60 не гоняли.
