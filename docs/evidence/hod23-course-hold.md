# Ход 23: курс при потере цели отдельно от Probe/Bypass

Дата: 2026-09-17. Имён сцен нет. Порог 0.12 не снижали. Константы wrap/reslide/Probe
не меняли (`edge_reslide=32`, wrap 10+20+6, `wrap_clear=8`, sprint 1.0,
`probe_forward=0.45`, `probe_gate=14`, `probe_give_up=55`). F14/F15 и
[post-h22](post-h22/frozen-post-h22.json) не перезаписывались
(`8f90a697f1a348dfea2547041e609e32fba4d265` /
`6b7644ee7163fed22e62cb82d3d924dff7ae5c19` /
`724b5d708e65c132b1b0c6d4e90dfd3999ed1e69`).

Frozen: [hod23/frozen-hod23.json](hod23/frozen-hod23.json). ADR-0029.
Кинематика забора по-прежнему ADR-0028: [hod23-kinematic-cut.md](hod23-kinematic-cut.md).

## Зачем

post-h22 дал 46/60 (+8/−6 к post-h14). Осцилляции сняты, стена впервые закрывается,
но потеряны 6 ранее стабильных эпизодов: vanish 5/5→2/5, по одному на
`open_goal` / `narrow_gate` / `corridor`. Забор не трогали.

## Первый тик срыва (до правки)

На `vanishing_target` цель скрывается на тике 8. Память пеленга шла в тот же контур,
что и живой захват: attract + интеграция yaw крутили `last_bearing` к ±1, stall
надувал `steer_risk` до порога «фронт», стартовали Probe/Peel на пустом поле.

На пеленговых сценах lock снимался при `|bearing| > 0.22`. Полный
attract+persist+memory разворачивал нос, LOS в створе пропадал, дальше Peel.

## Что сделано

- `_bearing` возвращает флаг `live`. Память курса — не живая цель.
- После `had_target` и потери цели: не стартовать Probe и первичный Peel, пока нет
  контактоподобного looming (`expansion ≥ 0.08`). Держать `course_lock` / прямой ход.
- `hard_front` только по expansion. Stall-boost `steer_risk` стену не рисует.
- Если обход уже начат (`probe_done`), мерцающий захват курс не замораживает.
- Пока цель живая и lock есть: при малом пеленге `turn=0`; при уходе с оси —
  только attract, потолок `course_lock_track=0.16` (следить за движущейся целью
  без полного срыва в обход).
- Высокий conf на курсе не запускает bypass.

## Что отвергли

- Ломать hold по `steer_risk` (в т.ч. stall ≈0.40): vanish 0/5, уход в край мира.
- Жёсткий `turn=0` и при живой цели: `moving_target` train/val 4/5→0/5.

## Прогоны seed=0, max_steps=200

Целевые (как в задаче) и контроли:

| Эпизод | post-h22 | hod23 |
|---|---|---|
| `vanishing_target` training v0 | stuck 200 | **success 64** |
| `vanishing_target` training v1 | stuck 200 | **success 64** |
| `vanishing_target` training v2 | success 65 | success 63 |
| `vanishing_target` validation v3 | stuck 200 | **success 65** |
| `vanishing_target` held_out v4 | success 62 | success 62 |
| `narrow_gate` training v1 | stuck 200 | **success 84** |
| `open_goal` held_out v4 | timeout 200 | **success 73** |
| `corridor` held_out v4 | timeout 200 | **success 95** |
| `single_obstacle` training v0 | success 193 | success 185 |
| `weak_texture` training v0 | success 190 | success 191 |
| `dead_end` training v0 | success 147 | success 87 |
| `long_fence` training v0 | timeout 200, col=0 | timeout 200, col=0 |

`moving_target` train/val снова 4/5 (v0 81). held_out v4 stuck, как на post-h14/h22.

`dead_end` быстрее не из-за смены фаз тупика: после захвата курс не срывается в лишний Peel.

## Frozen 60, seed=0

**52 / 60**. train 32/36, val 10/12, held-out 10/12. oscillate 0.

| Исход | post-h14 | post-h22 | hod23 |
|---|---|---|---|
| success | 44 | 46 | **52** |
| oscillate | 11 | 0 | 0 |
| stuck | 3 | 7 | 3 |
| timeout | 2 | 7 | 5 |

Δ к post-h22: **+6 / −0**. Восстановлены ровно 6 регрессий, новых провалов нет.

По сценам: vanish / open_goal / narrow_gate / corridor снова 5/5. weak 5/5, box 3/5,
fence 0/5 (те же 3 timeout / 2 stuck, col 0/0/27/0/26).

8 незакрытых: `long_fence` ×5 (ADR-0028 + коллизии v2/v4), `single_obstacle` v2/v3,
`moving_target` held_out v4.

`pytest` `test_baseline` + `test_memory` + `test_repair_regressions` зелёный.

Команда:

```text
python -m l2_brain baseline-eval --seed 0 --suite frozen --max-steps 200 \
  --out docs/evidence/hod23/frozen-hod23.json \
  --compare docs/evidence/post-h22/frozen-post-h22.json
```
