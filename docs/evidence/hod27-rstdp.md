# Ход 27: R-STDP и привилегированная награда

Дата: 2026-09-17. Baseline не меняли. Frozen 60 не гоняли.
F14/F15 / post-h22 / hod23 не перезаписывались.

## Зачем

Нужно локальное обучение на стенде без смешения сенсора и критика.
Расстояние до цели — только `RewardEngine` по `GroundTruth`.

## Правило

```text
τ_e de/dt = -e + S_pre S_post
ΔW        = clip(η R e, ±δ_max)
W         = clip_Dale(W + ΔW)
```

`τ_e=150` мс, `η=2e-4`, `δ_max=0.03`, `W∈[0, 3.6]` для `w_in`.
`freeze()` / `unfreeze()` / `checkpoint`. ES для GRU — тот же скаляр R,
без автограда; поведенческую серию GRU не гоняли.

## Прогоны

`pytest tests/test_plasticity.py tests/test_snn_dynamics.py tests/test_gru_controller.py`
— 24 passed (10 пластичность + 9 LIF + 5 GRU).

`l2-brain learn --episodes 8 --noise 0.35` на `open_goal:training:v0:s0`:

| этап | тики | success | col |
|---|---|---|---|
| контроль (шум, freeze) | 59 | да | 0 |
| train 1–8 | 59, 59, 59, 60, 58, 58, 59, 58 | да | 0 |
| eval после freeze | 58 | да | 0 |

JSON: [hod27/open-goal-rstdp.json](hod27/open-goal-rstdp.json).
SHA1 `c4dc3667202974a30e3c127206c8665cbbb57c8b`.

Формально 58 < 59, критерий плана выполнен. Содержательно это **1 тик
на n=1** — не доказательство, что R-STDP учит навигацию. Observation
привилегий не получил. H3/H4 не закрыты.
