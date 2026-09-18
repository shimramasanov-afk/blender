# Ход 64: короткий `w` после релога

Дата: 2026-09-18. Новый `L2.exe` PID 3840 в госте. Frozen L1 не
трогали. Фарм не открывали. 8 с не слали (ADR-0064).

JSON: [l1-nudge-h17.json](live-s4/l1-nudge-h17.json)
SHA1 `b35dec4b6abf0c89195f468e872829e6ce4cc648`.

Окно 16372, host PID 68342. 3 сэмпла × 500 мс, blocked=0.
Первая попытка: `SourceLost` (окно ушло с Space). Вторая: 1.93 с,
hid_sent=true, stuck_keys=0, stall_risk=false.

| тик | flow | duplicate | confidence |
|---|---|---|---|
| 0 | 0 | false | 0.31 |
| 1 | 0.048 | false | 0.32 |
| 2 | 0.056 | false | 0.31 |

Кадр менялся. Это не F67 (тогда 3/3 duplicate). H17 не закрыта.

F69.
