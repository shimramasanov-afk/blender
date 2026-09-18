# Ход 43: чистый захват и попытка урона

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм не запускали.
Отдельной ходьбы (`W`) нет.

## Сценарий

`--clean-target`: Escape до `not alive`, F1 пока HP цели > 0.85,
двойной F2 через 200 мс, окно HP 8 с с ранним выходом при дельте ≥ 0.05.
Потолок 12 с / 360 тиков.

Пустая подложка после Escape = `locked+dead`, не «цель жива».
До трёх импульсов F1, если снова берётся раненый моб.

## Живые прогоны, окно 13944

| файл | исход |
|---|---|
| [second-combat-probe-clear-timeout.json](live-s4/second-combat-probe-clear-timeout.json) | первый: 1 с ждали `locked==false`, abort `clear_timeout` |
| [second-combat-probe-clean-hp-low.json](live-s4/second-combat-probe-clean-hp-low.json) | сброс прошёл; F1 → HP 0.444; abort `clean_hp_low` |
| [second-combat-probe.json](live-s4/second-combat-probe.json) | канон хода. SHA1 `4d0c6edac540c55dcc2cd64b94658d053f42b4f5` |

Канон:

| поле | значение |
|---|---|
| ok | false |
| aborted | **clean_hp_low** |
| hid_sent | true |
| session_ms | **4605** |
| ticks | **64** |
| start_self_hp | **0.943** |
| pre-clear | пустая подложка, dead, hp 0.0 |
| F1 × 3 | каждый раз **0.444** |
| f2_pulses | 0 |
| damage_detected | **false** |
| stuck_keys_count | **0** |

Шаги канона: capture → self bars → Escape → cleared (dead plate) →
F1 / F1 / F1 (все 0.444) → abort.

## Что это не доказывает

Нового моба с полным HP нет. F1 трижды вернул ту же полоску 0.444 —
это тот же гремлин хода 42, либо F1 не является next-target
(на F45 в слоте F1 меч). Двойной F2 и дельту HP этот ход не видел.
Не 95%. Не H8.

ADR-0050. F50.
