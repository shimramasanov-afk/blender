# Ход 26: GRU и единый мини-бенч

Дата: 2026-09-17. Baseline и SNN-динамику не меняли. Frozen 60 не гоняли.
F14/F15 / post-h22 / hod23 не перезаписывались. Обучения нет.

## Зачем

SNN закрыл `open_goal:training:v0` (hod25). Нужен компактный неспайковый
рекуррентный контроллер на тех же 6 признаках и один раннер, чтобы таблица
ресурсов и исхода не смешивалась с Frozen 60 и не выдавалась за H3/H4.

## Что сделано

- `src/l2_brain/control/gru/`: NumPy GRU, H=16, голова H→(yaw, forward).
  Выход = рефлекс Брайтенберга + residual. При `residual_scale=0` голова
  нулевая: скрытое состояние обновляется, но не ломает рефлекс.
  `with_memory=false` обнуляет `h` каждый тик.
- `src/l2_brain/control/bench.py` и CLI `l2-brain bench`.
- Четыре контроллера на одном spec: `baseline_v1`, `baseline_memory_v1`,
  `gru_v1`, `snn_v1`.
- `n_params` baseline — число скаляров `BaselineConfig`, не веса сети.
  SNN считает плотные `w_rec+w_in` (разреженность не вычитается).

План: [hod26-plan.md](hod26-plan.md).

## Прогоны

`pytest tests/test_gru_controller.py tests/test_snn_dynamics.py` — 14 passed.

`l2-brain bench --scenario open_goal --split training --variant 0 --seed 0`

Эпизод `open_goal:training:v0:s0`, n=1:

| controller | исход | тики | col | N_params | state | K | infer p50 | infer p95 |
|---|---|---|---|---|---|---|---|---|
| baseline_v1 | success | 72 | 0 | 101 knobs | 4 | 1 | 0.044 | 0.063 |
| baseline_memory_v1 | success | 72 | 0 | 101 knobs | 8 | 1 | 0.056 | 0.078 |
| gru_v1 | success | 162 | 0 | 1186 | 16 | 1 | 0.070 | 0.098 |
| snn_v1 | success | 61 | 0 | 4480 stored | 128 | 50 | 1.627 | 1.697 |

JSON: [hod26/open-goal-training-v0.json](hod26/open-goal-training-v0.json).
SHA1 `6d274fb76d74fd44acb6e9b1b8575b4034005902`. Блок `extras` дописан после
прогона; строки `ticks` / `infer_ms` те же, что напечатал CLI.

GRU без обучения медленнее эвристики и SNN-рефлекса на этой сцене: нет
круизного пола baseline и нет тоника SNN. Это не рейтинг каталога.
SNN по-прежнему K=50 и ~1.6 мс; GRU K=1 и <0.1 мс.

H3/H4 не закрыты. Frozen 60 не гоняли.
