# Ход 56: поток у стены, stuck L1 нет

Дата: 2026-09-17. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали. Артефакты F61/F62 не
перезаписывали.

## Прогон

JSON: [l1-flow-validation-wall.json](live-s4/l1-flow-validation-wall.json)
SHA1 `f21c18adcb0be0ebb45294adf4540c710efceabe`.

Окно 13944, PID 68342. Dual flags. Оператор у стены деревни.
10 тиков свободного `w` 600 мс и 3 тика той же команды как фаза
`blocked`. hid_sent=true, stuck=0, 8.67 с. `NavigationEncoder`
без смены весов.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0137** | **0.0** | **0.452** |
| blocked | 3 | **0.0** | **0.0** | **0.161** |

`flow_magnitude` на free: 0.043, 0, 0, 0, 0, 0.043, 0, 0.050, 0, 0
(3 ненулевых тика из 10). `flow_ratio` = ∞ (`flow_blocked` = 0),
но `FLOW_FREE_MIN` 0.25 не взят → `stuck_detected=false`.
`l1_collision_signal_ready=false`.

Каждый тик: `unique_frame=true`, Δt ≈ 610 мс. encode p50 **47.0** мс,
p95 **48.4** мс, max 50.5.

blocked[0]: `duplicate=false`, confidence 0.483.
blocked[1] и blocked[2]: `duplicate=true`, confidence **0.0**,
label `low_confidence`. Это первый живой признак упора: кадр
перестал меняться. Не замена `flow_free ≥ 0.25`.

## Что это не доказывает

Свободный бег по-прежнему не даёт амплитуду 48×32. L1 collision
signal не готов. Пороги Frozen L1 не меняли.

F63. Протокол — ADR-0061.
