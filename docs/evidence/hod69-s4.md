# Ход 69: сильнее yaw, Q5 нет

Дата: 2026-09-18. Профиль не писали. Frozen L1 не трогали.

JSON: [motion-calibration-wall-hard.json](live-s4/motion-calibration-wall-hard.json)
SHA1 `b426bf9bbac4852cafec1ba228ad61766964a83a`.

Окно 16372, 3.63 с. RMB +480 px, 24 шага × 25 мс; 24 тапа
`right_arrow`; удержание 800 мс.

| механизм | inliers | median_dx | std_dx |
|---|---|---|---|
| rmb_drag | 40 | **0.0** | 1.00 |
| arrow_pulse | 38 | 0.003 | 0.68 |
| arrow_hold | 37 | −0.004 | 0.005 |

Точки на стене есть. KLT `median_dx≈0`, `physical=false`.
Интерпретация «камера не поехала» снята: оператор видел ≈45°
(F75, [hod70-s4.md](hod70-s4.md)).

F74.
