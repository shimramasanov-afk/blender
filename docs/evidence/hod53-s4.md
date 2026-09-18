# Ход 53: изоляция T0/T1, Q5 не закрыта

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм не открывали.

## Прогон

JSON: [motion-sync-diag.json](live-s4/motion-sync-diag.json)
SHA1 `7d94e634a2dc93b9fcec4bcb5ee490d796329bf7`.

Окно 13944, PID 68342. Dual flags. hid_sent=true, stuck=0, 2.99 с.

T0/T1: `.copy()`, settle 300 мс, кадр с
`timestamp_capture_ns > ts_t0 + input_duration`. RMB +200 px без
`RightMouseUp` до T1. Затем `right_arrow` 600 мс.

PNG кропа анализа: [calibration_t0.png](live-s4/calibration_t0.png),
[calibration_t1.png](live-s4/calibration_t1.png)
(SHA1 `ebf5ca74…` / `d8378355…`). Это пара RMB hold.

| импульс | diff_mean | Δt мс | unique | shares_mem | features | inliers | median_dx |
|---|---|---|---|---|---|---|---|
| rmb_drag_hold +200 | **7.05** | **371** | true | false | 60 | 41 | −0.007 |
| arrow_hold 600 мс | **7.81** | **984** | true | false | 55 | 38 | −0.002 |

`identical_frames_error=false`. `sck_desync=false`.

На PNG T0 и T1 — разные кадры (трава, ножны). Горизонтального
уезда среднего плана, который KLT считает yaw, нет: поляна почти
однородна, персонаж в маске трекера вырезан.

`physical=false`. `parallels_l2.json` не писали.

## Что это не доказывает

Рассинхрон latest-only как причина нуля хода 52 **не подтверждён**:
метки разные, буферы разные, пиксели разные. Нулевой KLT на этой
поляне не равен «камера не двигалась» и не равен «захват сравнивает
кадр сам с собой». Числового yaw нет. Q5 не закрыт.

ADR-0060. F60.
