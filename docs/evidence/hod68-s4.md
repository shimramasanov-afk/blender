# Ход 68: yaw у стены, Q5 нет

Дата: 2026-09-18. Без `w`. Профиль не писали. Frozen L1 не трогали.

JSON: [motion-calibration-wall.json](live-s4/motion-calibration-wall.json)
SHA1 `ccbbed0be00d695e228b46d3986a55df5a50c9bc`.

Окно 16372, 1.85 с. RMB Drag +150 px, затем fallback arrow pulse.

| механизм | features | inliers | ratio | median_dx |
|---|---|---|---|---|
| rmb_drag | 39 | **39** | 1.00 | **0.0** |
| arrow_pulse | 40 | 37 | 0.93 | −0.0005 |

Текстура стены есть (KLT держит точки). Сдвига кадра нет.
`physical=false`. `q5_closed=false`.

F73.
