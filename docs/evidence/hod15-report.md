# Ход 15 — Frozen 60 и обход без пеленга

Дата: 2026-09-17.  
S2 / HID / SNN / Metal не открывались. F14/F15 не перезаписывались.  
Ветки по имени сцены нет.

## Шаг 1. Канон до правок

`baseline-eval --seed 0 --suite frozen` → [post-h14/frozen-baseline.json](post-h14/frozen-baseline.json)

**44 / 60.** success 44, oscillate 11, stuck 3, timeout 2.  
train 27/36, val 9/12, held-out 8/12.

Пеленговые сцены 40/40. `moving_target` 4/5.  
`single_obstacle`+`long_fence`+`weak_texture` **0/15** (oscillate 11, stuck 2, timeout 2).

Подробно: [post-h14/report.md](post-h14/report.md). Это не замена F14 (23/60).

## Шаг 2. Side-bias

Причина осцилляции: при `side=0` знак поиска брался из `last_bearing`, а команда каждый тик инвертировала этот знак.

Правка (без имён сцен):

- вслепую фиксируется `side` (градиент L/R или +1);
- смена знака yaw блокируется `side_lock` на 20 тиков;
- пока цели нет: `forward≥0.21`, `turn=sign·0.45`;
- команда не крутит пеленг, если трека ещё не было.

## Дельта проблемных сцен (5 вариантов каждая)

| Сцена | До (freeze) | После |
|---|---|---|
| `single_obstacle` v0 | oscillate 200, dir высокий | **stuck 200, dir=0** |
| `long_fence` v0 | oscillate 200 | **stuck 200, dir=0** |
| `weak_texture` v0 | oscillate 200 | **stuck 200, dir=0** |
| все 15 вариантов | 11 oscillate / 2 stuck / 2 timeout | **15 stuck, dir=0** |

Финиша нет: агент перестал дрожать рулём, но не огибает барьер до пятна.  
Попытка «сначала прямо, потом peel» ломала `dead_end` (200 stuck) — откатили.

## Регрессия training v0

| Сцена | Freeze / ход 14 | После шага 2 |
|---|---|---|
| `open_goal` | 72 | 72 |
| `narrow_gate` | 84 | 84 |
| `dead_end` | 138 | **141** |
| `u_trap` | 179 | **77** |
| `corridor` | 94 | 94 |
| `latency_drops` | 76 | 76 |

## Проверки

`pytest` зелёный. F14/F15 SHA без изменений.
