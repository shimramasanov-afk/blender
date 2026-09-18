# Ход 25: рефлекс Брайтенберга в SNN

Дата: 2026-09-17. Baseline не меняли. Frozen 60 не гоняли. STDP нет.
F14/F15 / post-h22 / hod23 не перезаписывались.

## Зачем

hod24: timeout 200, col=0, mean_forward=0.21. Сеть жила (~52 Гц), но readout
не давал рабочего хода: 6 м / 0.025 м/тик ≈ 245 тиков > 200.

## Что сделано

Детерминированные пулы E: left | right | forward. I: anti-left | anti-right.

- `conf` и `align` → только forward.
- пеленг влево → left E и I, который тормозит right E; зеркально вправо.
- Тоник только на forward.
- Readout нормирует следы на `trace_ref` (50 Гц): при целевой частоте
  `forward≈0.70`, `yaw` в `[-0.40, 0.40]`.

Случайный шум во входных весах убран. Рекуррентность: слабое E–E внутри пула
и фиксированное контралатеральное I. Пластичности нет.

## Прогоны

`pytest tests/test_snn_dynamics.py` — 9 passed.

`open_goal:training:v0:s0`, seed=0:

| Поле | hod24 | hod25 |
|---|---|---|
| исход | timeout 200 | **success 61** |
| col | 0 | 0 |
| infer_ms_p50 | 1.653 | **1.704** (< 2.0) |
| mean_forward | 0.21 | 0.84 |

JSON: [hod25/open-goal-training-v0.json](hod25/open-goal-training-v0.json).

mean_forward 0.84 на эпизоде выше полосы 0.6–0.8, потому что conf+тоник
разгоняют forward-пул выше 50 Гц. Юнит-тест на `T=trace_ref` даёт 0.70.
Успех сцены ≤120 тиков выполнен. Это не H3/H4 и не Frozen 60.
