# План: ход 33 — непрерывный спот-цикл

Дата плана: 2026-09-17. Цифр исходов здесь нет.

## Гипотеза / отклонение

На `multi_dummy_arena_v0` агент L2 (SNN как L1) за 250 тиков делает
серию ≥3 убийств с фазами LOOT и сменой цели, без HID и без позы в
Observation. Watchdog сбрасывает недосягаемую цель в RESET→SCAN.
LOOT не длиннее 12 тиков.

Отклоняем, если живой клиент, Observation с GT, правка baseline,
зависание фазы дольше сторожа, или заявка «играет в MMORPG».

## База

`combat_dummy_v0` + `tactical_combat_v0` (ход 29). Не Frozen 60.

## Команда

```text
pytest tests/test_spot_loop.py -q
python -m l2_brain.cli spot-loop --out docs/evidence/hod33/spot-loop.json
```
