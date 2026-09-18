# Ход 72: сильнее RMB, coarse видит yaw

Дата: 2026-09-18. Профиль не писали. Frozen L1 не трогали.

JSON: [motion-calibration-wall-harder.json](live-s4/motion-calibration-wall-harder.json)
SHA1 `f0c0106f20483ae66f45aa114cbac23adab45c22`.

PNG: [yaw-rmb_drag-t0.png](live-s4/yaw-rmb_drag-t0.png),
[yaw-rmb_drag-t1.png](live-s4/yaw-rmb_drag-t1.png);
копии [hod72-harder/](live-s4/hod72-harder/).

Окно 16372, 3.28 с. RMB +800 / 40×20 мс. Стрелку не слали:
грубый замер уже `physical`.

| поле | значение |
|---|---|
| KLT inliers | 2 / 37, ratio 0.29 |
| KLT median_dx | 53.7 (unreliable) |
| coarse_dx | **1313** |
| pixel_diff_mean | 14.33 |
| assumed_yaw_deg | 23.9 (FOV 75°, не GT) |
| physical | true (coarse) |
| q5_closed | false |

T0: нос в стену. T1: площадь деревни, NPC справа.
Q5 не закрыт: KLT не сошёлся, градусы с допущенного FOV.

F77. ADR-0066.
