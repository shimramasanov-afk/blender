# Ход 57: подход к стене, stuck L1 нет

Дата: 2026-09-17. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали. Артефакты F61–F63 не
перезаписывали.

## Прогон

JSON: [l1-flow-validation-approach.json](live-s4/l1-flow-validation-approach.json)
SHA1 `669fb1ba83e47cf39e62061ecb53bb9673f50316`.

Окно 13944, PID 68342. Dual flags. 10 тиков `w` 600 мс и 3 тика
как `blocked`. hid_sent=true, stuck=0, 8.65 с.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0139** | **0.0** | **0.232** |
| blocked | 3 | **0.0** | **0.0** | **0.0** |

`flow_magnitude` на free: 0, **0.095**, 0.043, 0, 0, затем пять нулей.
Пик 0.095 — лучший одиночный тик F61–F64. С free[5] по blocked[2]:
`duplicate=true`, confidence 0, label `low_confidence`. Упор начался
в середине «свободной» фазы.

`flow_ratio` = ∞, `FLOW_FREE_MIN` 0.25 не взят →
`stuck_detected=false`. encode p50 **43.3** мс, p95 **47.7** мс.

## Что это не доказывает

Средний свободный поток ниже порога, потому что половина free-тиков
уже упор. L1 collision signal не готов. Пороги Frozen L1 не меняли.

F64. Протокол — ADR-0061.
