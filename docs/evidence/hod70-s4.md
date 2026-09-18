# Ход 70: KLT не видит большой yaw

Дата: 2026-09-18. Профиль не писали. Frozen L1 не трогали.
Живой повтор не слали.

Оператор по F74: камера развернулась примерно на 45°.
JSON F74 этого не показывает: KLT `SEARCH=40` px, `median_dx≈0`.

Оценка порядка, не GT: 4112 × (45 / 75) ≈ 2467 px. Локальный
трекер на периодичной стене алиасит в ноль.

В `run_v3_yaw_calibration.measure()`:

- `coarse_shift` — фаза на mid-plane без персонажа/HUD;
- `pixel_diff_mean`;
- PNG `yaw-<mechanism>-t0.png` / `t1.png`;
- `physical` = KLT `|dx|≥30` **или** грубый сдвиг / diff;
- `q5_closed` только с KLT.

Синтетика: roll 80 px → KLT `|dx|<20`, coarse ≈ 81 px.
`tests/test_klt_yaw.py` — 11 зелёных.

Q5 не закрыт. H18 принята. ADR-0065. F75.
