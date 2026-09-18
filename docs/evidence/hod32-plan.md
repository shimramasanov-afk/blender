# План: ход 32 — мини-сводка пяти контроллеров

Дата плана: 2026-09-17. Цифр исходов здесь нет.

## Гипотеза / отклонение

На фиксированном срезе из 5 сцен (`training:v0:s0`, seed=0)
`baseline_memory_v1` даёт не меньше успехов, чем любой из
`gru_v1` / `snn_v1` / `snn_rstdp` / `malecns_bio`. Среди нейронных
ядер целевой кандидат в связку с L2 — калиброванный `snn_v1`, если
он не хуже остальных по успехам и укладывается в бюджет infer.

Отклоняем прогон, если падение, правка весов существующих контроллеров,
запуск Frozen 60, или таблица публикуется как рейтинг каталога / H3 / H4 /
готовность клиента.

## База

`baseline_memory_v1` (замороженный L1). Эталон ресурсов — `snn_v1`.

## Независимые переменные

Только имя контроллера. Сцены, seed, энкодер `navigation_v1`, лимиты
действия — общие.

## Контроли

`snn_rstdp` — те же уравнения, что `snn_v1`, веса `w_in` после серии
хода 27 (8 эпизодов, noise=0.35, freeze). `malecns_bio` — научный
контроль топологии, не претендент в runtime.

## Метрики

По клетке (модель, сцена): исход, тики, коллизии, infer p50/p95,
K, n_params, state_floats, direction_changes, mean_progress
(= path_length / ticks). Сводка: успехи из 5.

n=1 на клетку: репрезентативный срез, не мультисид.

## Сцены

`open_goal`, `camera_spin`, `latency_drops`, `vanishing_target`,
`single_obstacle` — только `training` variant 0. Не Frozen 60.

## Команда

```text
python -m l2_brain.bench.suite_runner --out docs/evidence/hod32/final-comparison.json
```

## JSON

`docs/evidence/hod32/final-comparison.json`
