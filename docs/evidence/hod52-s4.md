# Ход 52: RMB Drag / arrow pulse, Q5 не закрыта

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм не открывали.
Полный оборот 360° не крутили.

## Прогон

JSON: [motion-calibration-v3.json](live-s4/motion-calibration-v3.json)
SHA1 `f799cfed7e18c9dfbf515b804fad3b91ddad918a`.

Окно 13944 (0,39, 2056×1290, on_screen), PID 68342. Dual flags.
OpenCV `goodFeaturesToTrack` + `calcOpticalFlowPyrLK`. hid_sent=true,
stuck=0, 1.34 с.

1. RMB Drag: курсор 50%/40%, 5 шагов, суммарно +150 px, шаг 10 мс,
   `deltaX`/`deltaY`, post на PID и HID tap.
2. Резерв: 10 тапов `right_arrow` с интервалом 40 мс.

Рабочая зона y 30–70%, x 15–85%; вычтены персонаж (x 42–58%,
y 45–100%) и HUD. quality 0.01, minDistance 8, maxCorners 200,
`|dy| ≤ 8`.

| импульс | features | tracked | horiz | inliers | ratio | median_dx |
|---|---|---|---|---|---|---|
| rmb_drag +150 | 55 | 55 | 47 | **39** | 0.830 | −0.001 |
| arrow_pulse ×10 | 62 | 60 | 50 | **39** | 0.780 | +0.004 |

Критерий физического сдвига: `|median_dx| ≥ 30`, inliers ≥ 30,
ratio ≥ 0.70. KLT сошёлся, сдвига нет (`shift_too_small`).

`physical=false`. `reliable=false`. `parallels_l2.json` не писали
(нужно `|dx| ≥ 50` и сходимость).

`px_cam_per_px_mouse` ≈ 0. `deg_per_mouse_px` ≈ 0 при FOV 75°
(допуск).

## Что это не доказывает

CGEvent ушёл (hid_sent=true), но рендер не повернулся. Либо гость
не принимает относительный RMB/стрелки из PostToPid+HID, либо в
клиенте нет бинда на этот жест в текущем фокусе. 75° FOV по-прежнему
допуск. 360° по ориентиру нет. Метры шага нет. Q5 не закрыт.

ADR-0059. F59.
