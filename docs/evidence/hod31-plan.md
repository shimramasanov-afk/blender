# План: ход 31 — синтетический подграф MaleCNS

Дата плана: 2026-09-17. Цифр исходов здесь нет.

## Гипотеза / отклонение

На `open_goal:training:v0:s0` нативная топология экстракта (`bio`) даёт
меньше тиков, чем degree-preserving `shuffled`. Эталон — `snn_v1`.
Отрицательный результат (bio не лучше shuffle / хуже SNN) закрывает этап.

Отклоняем прогон, если NaN, нет пути вход→DN в `bio`, Observation с позой,
или заявлен полный коннектом / «MaleCNS уже играет».

## База

`snn_v1` на той же сцене. Не Frozen 60. Не H11.

## Независимые переменные

Только `mode` ∈ {bio, shuffled, random_sparse}. LIF, K=50, 6 признаков — те же.

## Источник графа

Локального FlyEM-среза в репозитории нет. Используется
`synthetic_visuomotor_extract_v0` (не скачанный коннектом).

## Команда

```text
pytest tests/test_malecns.py -q
l2-brain malecns-eval --out docs/evidence/hod31/malecns-comparison.json
```
