# Ход 33: непрерывный спот-цикл

Дата: 2026-09-17. Клиент и HID нет. Baseline / Frozen 60 не трогали.
`Observation` без позы и дистанции. Range / loot xy только на `TelemetryHub`.

L1: `snn_v1` (походка). L2: заголовок по синтетическому пеленгу
(`turn = clip(-bearing/0.6)`), потому что знак `atan2−yaw` не совпадает
с калибровкой SNN на `navigation_v1`.

## FSM

`SCAN → TARGET → APPROACH → COMBAT → LOOT → RESET → SCAN`

Сторожа: approach 60, combat 40, loot 12.

## Прогон 250 тиков, seed=0

`pytest tests/test_spot_loop.py` — 4 passed.

| метрика | значение |
|---|---|
| исход | spot_loop_ok |
| фраги | **4** (тики 38, 83, 154, 197) |
| лут | **4** (тики 43, 89, 160, 203) |
| серия | 4 |
| watchdog | 0 |
| hid_sent | false |
| фазы | SCAN TARGET APPROACH COMBAT LOOT RESET |

JSON: [hod33/spot-loop.json](hod33/spot-loop.json).
SHA1 `c1d216fd33fa2874dff96a32242bde6d4bf09662`.
