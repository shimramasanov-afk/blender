# Ход 44: урон по цели с HP 0.444

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм не запускали.

Оператор: F1 = `/targetnext`, F2 = Attack, F3 = Pickup.
`--engage-any`: принять цель с HP ≥ 0.15, двойной F2, окно 8 с.

## Прогон

JSON: [combat-damage-probe.json](live-s4/combat-damage-probe.json)
SHA1 `40cb7c2c6b7a1028f66bcee31a8f062bdfe0d1f7`.

Окно 13944, PID 68342.

| поле | значение |
|---|---|
| ok | true |
| damage_detected | **true** |
| start_self_hp | 0.943 |
| initial_target_hp | **0.444** |
| final_target_hp | **0.366** |
| дельта | **0.078** |
| F1 → lock | 256 мс |
| F2 × 2 | пауза 180 мс |
| F2 → drop | **1031** мс |
| session_ms | **2577** |
| ticks | **34** / 360 |
| stuck_keys_count | **0** |

Шаги: capture → self bars → F1 → lock 0.444 → F2 → F2 → HP 0.366 → Escape.

## Ограничения

Тот же гремлин, не новый моб с полным HP. Не килл (полоска не 0).
Не H8. Не 95% как свойство контура — один короткий удар.

ADR-0051. F51.
