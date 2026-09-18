# Ход 24: изолированное SNN-ядро (песочница)

Дата: 2026-09-17. Baseline и `controllers/snn.py` не меняли. Frozen 60 не гоняли.
F14/F15 / post-h22 / hod23 SHA без изменений
(`8f90a697f1a348dfea2547041e609e32fba4d265` /
`6b7644ee7163fed22e62cb82d3d924dff7ae5c19` /
`724b5d708e65c132b1b0c6d4e90dfd3999ed1e69` /
`b8d99b4f7a89872eca5b633dbdace1d96e1408c4`).

Пакет: `src/l2_brain/control/snn/`. Протокол: `CircuitController` → `MotorIntent`.
Уравнения и единицы — в `lif.py`. Пластичности нет. Metal/MPS нет. MaleCNS нет.

## Время

`dt_ms=1.0`, `tick_ms=50.0`, ровно `K=50` шагов Эйлера на тик контура.
Сеть: 64 нейрона, 80% E / 20% I, Dale, density 0.20, CPU numpy.

## Шаг A — юнит-тесты

`pytest tests/test_snn_dynamics.py` — 6 passed:

- релаксация к `V_reset` без тока;
- ступенчатый ток, ISI ≥ `t_ref`;
- `I=1e4` без NaN/Inf, V и I ограничены;
- `get_state`/`set_state` побитово совпадают;
- знаки Дейла и нулевая диагональ;
- `steps_per_tick == 50`.

## Шаг B — один эпизод

`open_goal:training:v0:s0`, seed=0, 200 тиков.
Артефакт: [hod24/open-goal-training-v0.json](hod24/open-goal-training-v0.json).

| Поле | Значение |
|---|---|
| исход | timeout 200, col=0 (успех сцены не критерий) |
| `infer_ms_p50` | **1.653** (< 2.0) |
| `firing_rate_hz` mean / last | 52.21 / 84.06 |
| `silent_ratio` last | 0.203 |
| `saturated_ratio` last | 0.0 |
| `v_range` last | min 0.00, mean 0.39, max 0.98 |
| MotorIntent | есть; mean forward 0.21 |

Тоник 0.22 давал нулевую частоту (V_max≈0.53 < порог). Оставлен `tonic_e=1.15`,
чтобы спайки и телеметрия были ненулевыми. Это не подгонка под Frozen 60.

CLI: `baseline-eval --controller snn` требует `--scenario` (полный frozen закрыт).

Это не H3/H4 и не сравнение с `baseline_memory_v1`.
