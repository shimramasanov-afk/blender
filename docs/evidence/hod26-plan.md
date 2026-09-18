# План: ход 26 — GRU и мини-бенч

Дата плана: 2026-09-17. Цифр исходов здесь нет.

## Гипотеза / отклонение

На одном эпизоде `open_goal:training:v0:s0` (seed=0, тот же мир) четыре
контроллера (`baseline_v1`, `baseline_memory_v1`, `gru_v1`, `snn_v1`)
завершают тик без исключения и отдают `MotorIntent`.

Отклоняем, если любой контроллер падает, отдаёт NaN/Inf, или этот прогон
публикуется как превосходство архитектуры / закрытие H3/H4 / Frozen 60.

## База

`baseline_memory_v1` (замороженный эталон, канон 52/60 на другом наборе).
На этой сцене он не обязан быть лучшим: сцена открытая.

## Независимые переменные

Только имя контроллера. Веса GRU не обучаются. SNN — `snn_core_v1` как есть.
Baseline не меняется.

## Контрольные условия

Один spec из `catalog(0, suite="frozen")`: scenario=`open_goal`, split=`training`,
variant=0. Один энкодер `navigation_v1`. Бюджет тика сцены не меняется.
n=1, потому что это мини-набор хода 26, не каталог. Held-out не трогаем.

## Метрики

Исход, тики, коллизии, `n_params` (для baseline — число скаляров конфига, не
веса сети), размер состояния в float, K суб-шагов, `infer_ms` p50/p95 на CPU.

Порога «кто лучше» нет. Порог отказа — падение или нечисловой выход.

## Команда

```text
pytest tests/test_gru_controller.py tests/test_snn_dynamics.py -q
l2-brain bench --scenario open_goal --split training --variant 0 --seed 0 \
  --out docs/evidence/hod26/open-goal-training-v0.json
```

JSON ещё не записан на момент плана.
