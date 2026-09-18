# Ход 31: синтетический подграф MaleCNS

Дата: 2026-09-17. Полный коннектом не загружался. FlyEM-файлов в дереве нет.
Baseline / GRU / `snn_v1` не меняли. Frozen 60 не гоняли. H11 не закрыта.

Источник графа: `synthetic_visuomotor_extract_v0` — компактный зрительно-моторный
мотив с аннотациями Ach/GABA, не скачанный MaleCNS.

## Экстракт

| поле | значение |
|---|---|
| N | 208 |
| E | 616 |
| плотность | 0.0143 |
| знаки | Ach → +1, GABA → −1; вес ∝ log1p(контакты) |
| режимы | bio / shuffled (степени out) / random_sparse (ER) |

`pytest tests/test_malecns.py` — 8 passed (Dale, путь vis→DN, затухание, n=1 бенч).

## `open_goal:training:v0:s0`, n=1

| контроллер | исход | тики | col | infer p50 мс | rate Гц |
|---|---|---|---|---|---|
| snn_v1 | success | 61 | 0 | 1.630 | 21.4 |
| malecns_bio | success | 178 | 0 | 1.814 | 5.2 |
| malecns_shuffled | success | 191 | 0 | 1.800 | 5.2 |
| malecns_random | timeout | 200 | 0 | 1.825 | 5.3 |

Нативная топология экстракта быстрее shuffle на 13 тиков. Оба медленнее
калиброванного `snn_v1` (61). ER не закрыл сцену. Это не рейтинг каталога
и не «биология играет».

JSON: [hod31/malecns-comparison.json](hod31/malecns-comparison.json).
SHA1 `0c5c01015b73b38fe4eafd6af11482d6cba82ffa`.
