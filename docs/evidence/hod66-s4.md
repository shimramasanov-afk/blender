# Ход 66: 8 с после коротких nudge

Дата: 2026-09-18. Frozen L1 не трогали. Фарм не открывали.

JSON: [l1-flow-validation-8s-h17.json](live-s4/l1-flow-validation-8s-h17.json)
SHA1 `327f0da4c16f5a7f95f8e6a841de028c86ce56ac`.

Окно 16372, 10+3 × 600 мс, 8.66 с, hid_sent=true, stuck_keys=0,
stall_risk=true.

| фаза | flow | duplicate |
|---|---|---|
| free | **0.014** (пик 0.095 на [5]) | [7..9] true |
| blocked | 0 | все true |

blocked[2] `time_delta_ms` **961** (обычно ≈610).
`stuck_detected=false`.

Тот же рисунок, что F65/F66: живые кадры, потом замирание с ~5 с.
H17 не закрыта, пока оператор не кликнет/не пойдёт.

F71.
