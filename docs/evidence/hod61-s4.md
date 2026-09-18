# Ход 61: рестарт клиента, окно 16372

Дата: 2026-09-18. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали. Артефакты F61–F65 не
перезаписывали.

## Прогон

JSON: [l1-flow-validation-restart.json](live-s4/l1-flow-validation-restart.json)
SHA1 `293715d3d360adfaf63b15a9ec3bdad351386407`.

Окно **16372** (старое 13944 списано), PID 68342. Dual flags.
`hold_mode=continuous`. 8.32 с, stuck_keys=0, watchdog=false.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0436** | **0.004** | **0.330** |
| blocked | 3 | **0.0** | **0.0** | **0.114** |

`flow_magnitude` на free: 0, **0.105**, 0, 0, 0.050, 0, 0, 0,
0.050, **0.231**. free[1] label `approach`. Пик 0.231 — лучший
тик линейки, порог 0.25 не взят. blocked[1..2]: `duplicate=true`,
confidence 0. encode p50 **47.4** мс, p95 **48.8** мс.

`stuck_detected=false`. `l1_collision_signal_ready=false`.

## Что это не доказывает

Средний свободный поток ниже 0.25. Q5 не закрыт. Frozen L1 не
меняли.

F66.
