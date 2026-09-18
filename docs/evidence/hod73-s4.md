# Ход 73: батарея калибровки yaw/шаг

Дата: 2026-09-18. Профиль не писали. Frozen L1 не трогали.
Окно 16372. 67 живых JSON в
[calib-loop/](live-s4/calib-loop/).

Q5 не закрыт. KLT ни разу не дал ≥30 инлаеров при `|dx|≥30`.

## Что меняли в коде

- `SEARCH=80`, шаг 4.
- `grab()` копирует кадр (ADR-0066).
- `--mouse-dy`: вертикальный RMB (тангаж).

## Свип мыши у стены / площади

| tag | mouse | coarse_dx | KLT dx | inliers | physical |
|---|---|---|---|---|---|
| m32 | +32 | 0 | 0 | 200 | нет |
| m80–m120 | +80…120 | 0 | ~2 | 37–38 | нет |
| m150 | +150 | 1349 | 95 | 6 | да |
| m250 | +250 | 702 | −192 | 1 | да |
| square150 | +150 | 198 | 32 | 2 | да |
| corner-m50 | +50 | **54** | **55** | 2 | да |

Порог: ≤120 px на стене камера часто не едет; с 150 — скачок.
`corner-m50`: грубый и KLT median совпали (~54 px), но 2 инлаера.

## Крыша (после тангажа)

+350 dy — зенит. +180 вниз — фронтон дома.

| tag | mouse | coarse_dx | KLT dx | inliers |
|---|---|---|---|---|
| roof-m40 | +40 | −270 | −294 | 6 |
| roof-m40b | +40 | −288 | −506 | 1 |
| roof-m55 | +55 | −324 | 229 | 1 |
| roof-left | −50 | 504 | −68 | 1 |

Тот же +40 px мыши: ~270 px кадра на крыше и ~54 на углу.
Константы `px_cam_per_px_mouse` нет.

## Шаг и симметрия

- walk 500 мс: `step_shift_px` 66, peak 0.018, `motion_detected`.
- `--klt` 450 мс right/left: 1 инлаер, symmetry нет.

SHA1: corner-m50 `9feddfda…`, roof-m40 `14c9a2c8…`,
roof-m40b `57275371…`, walk `f6570709…`, klt-sym `5483c5af…`.

## Продолжение (тот же ход)

Третье лицо на площади: `tp-m50b` 8 инлаеров, KLT 101 / coarse 90.
`sq-m50b` KLT 44 / coarse 36, 5 инлаеров.
Шире маска персонажа: `wide-m50c` 11 инлаеров (лучший consensus
на живом большом сдвиге), Q5 всё равно нет.

Короткий `live-motion` 3+1 × 500 мс: flow_free **0.116**, тик
free[2] **0.238** (порог 0.25 не взят), `camera_turn`,
`stuck_detected=false`, duplicate нет. 2.43 с.

`--sync-diag`: unique_frame true, SCK desync нет, diff 35.6,
KLT −22, 6 инлаеров.

`wide-left50`: 18 инлаеров, KLT −70. `wide-left50e`: KLT −50 и
coarse −54 совпали. Q5 нет (нужно 30 инлаеров и ratio 0.70).

flow-short2: mean 0.204, тик **0.318**.
flow-short3: mean **0.230**, тик **0.529**. `FLOW_FREE_MIN` 0.25
на среднем free не взят. stuck false.

`wide-left50h`: **36 инлаеров**, ratio 0.47, KLT −21 (мало для
physical). `flow-short4`: mean 0.182, **ratio 3.64** (порог 3
взят), mean free 0.25 нет.

F78. ADR-0067.
