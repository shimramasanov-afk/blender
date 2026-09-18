# Ход 59: непрерывный `w` в клиенте, stuck L1 нет

Дата: 2026-09-17. `sim/` и Frozen L1 (52/60) не трогали. Фарм не
открывали. Боевые клавиши не слали. Артефакты F61–F64 не
перезаписывали.

## Прогон

JSON: [l1-flow-validation-hold.json](live-s4/l1-flow-validation-hold.json)
SHA1 `f03090d0b9f5fe000698604cf9db42689000baa5`.

Окно 13944, PID 68342. Dual flags. `hold_mode=continuous`.
Один `w` down, 10+3 сэмпла по 600 мс, один up. 2 события HoldKey,
stuck_keys=0, watchdog=false, hid_sent=true, 8.34 с.

| фаза | n | flow_magnitude | expansion | motion_confidence |
|---|---|---|---|---|
| free | 10 | **0.0048** | **0.0** | **0.284** |
| blocked | 3 | **0.0** | **0.0** | **0.0** |

`flow_magnitude` на free: 0, 0, 0, 0, **0.048**, 0, затем нули.
С free[6] по blocked[2]: `duplicate=true`, confidence 0. Упор в
середине «свободной» фазы. `FLOW_FREE_MIN` 0.25 не взят →
`stuck_detected=false`. encode p50 **44.7** мс, p95 **48.4** мс.

Ввод больше не пульсирует. Амплитуда 48×32 на этом кадре всё ещё
нулевая на большинстве тиков.

## Что это не доказывает

Непрерывный `w` не заменяет текстуру mid-plane. L1 collision
signal не готов. Пороги Frozen L1 не меняли.

F65. ADR-0062.
