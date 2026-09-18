# Ход 55: поток у ворот деревни, stuck L1 нет

Дата: 2026-09-17. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали. Артефакт Хода 54 не перезаписывали.

## Прогон

JSON: [l1-flow-validation-village.json](live-s4/l1-flow-validation-village.json)
SHA1 `7c671ba3a510e89d1e6b8c83dbd4de64bbe51533`.

Окно 13944, PID 68342. Dual flags. Оператор стоял перед воротами
деревни Talking Island. 10 тиков свободного `w` 600 мс и 3 тика
той же команды как фаза `blocked`. hid_sent=true, stuck=0, 8.66 с.
`NavigationEncoder` без смены весов.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0089** | **0.0** | **0.513** |
| blocked | 3 | **0.0** | **0.0** | **0.530** |

`flow_magnitude` на free: 0.045, 0, 0, 0, 0, 0, 0, 0, 0.043, 0
(2 ненулевых тика из 10). `flow_ratio` = ∞ (`flow_blocked` = 0),
но `FLOW_FREE_MIN` 0.25 не взят → `stuck_detected=false`.
`l1_collision_signal_ready=false`.

Каждый тик: `unique_frame=true`, Δt ≈ 610 мс, `duplicate=false`,
label `uncertain`. encode p50 **46.8** мс, p95 **50.1** мс, max 51.0.

Фаза `blocked` — продолжение `w` после 10 тиков, не подтверждённый
упор в створку ворот. `motion_confidence` выше, чем на поляне
(F61 ≈ 0.40), но это пик SAD, не амплитуда 48×32.

## Что это не доказывает

Ворота сами по себе не дают `flow_free ≥ 0.25`. L1 collision
signal не готов. Пороги Frozen L1 не меняли.

F62. Протокол — ADR-0061.
