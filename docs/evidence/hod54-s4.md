# Ход 54: живой поток на `w`, stuck L1 не готов

Дата: 2026-09-17. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали.

## Прогон

JSON: [l1-flow-validation.json](live-s4/l1-flow-validation.json)
SHA1 `a93f7685141128870c63445df4898f03a6fa6364`.

Окно 13944, PID 68342. Dual flags. 10 тиков свободного `w` 600 мс
(удержание до T1) и 3 тика той же команды как фаза `blocked`.
hid_sent=true, stuck=0, 8.66 с. `NavigationEncoder` без смены весов.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0** | **0.0** | **0.399** |
| blocked | 3 | **0.0** | **0.0** | **0.404** |

`flow_ratio` = 0. Критерий ≥ 3 не выполнен.
`stuck_detected=false`. `l1_collision_signal_ready=false`.

Каждый тик: `unique_frame=true`, Δt ≈ 610 мс, `duplicate=false`,
label `uncertain`. Один раз `near_expansion` 0.034.

`encode_ms`: p50 **47.4**, p95 **48.0**, max 50.6 (n=13).

Фаза `blocked` — продолжение бега вперёд после 10 тиков, не
подтверждённый упор в дерево/камень. На однородной поляне векторы
блочного потока 48×32 нулевые, хотя `motion_confidence` ≈ 0.40
(пик SAD, не амплитуда сдвига).

## Что это не доказывает

L1 не готов выдать живой collision/stuck: нет контраста free/blocked
и нет ненулевой `flow_magnitude`. `motion_confidence` не заменяет
амплитуду. Пороги Frozen L1 не меняли.

ADR-0061. F61.
