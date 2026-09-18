# Ход 29: телеметрия и синтетический бой

Дата: 2026-09-17. Клиент не подключали. pcap/инъекций нет. HID нет.
Baseline и Frozen 60 не трогали. `Observation` без позы и дистанции.

## Что сделано

- `src/l2_brain/telemetry/` — события и `TelemetryHub` (кольцо 64, stale 300 мс).
- `src/l2_brain/sim/combat.py` — арена `combat_dummy_v0` (не каталог Frozen).
- `src/l2_brain/control/tactical.py` — FSM SEEK→…→VICTORY. Baseline не используется.
- Дальность на шине как `RangeCue` с `source=sim_ground_truth`, не в Observation.
- Урон только при `TargetSelect` (conf>0.3) и `SkillActivate("F2")` на ≤1.8 м.

## Прогоны

`pytest tests/test_combat_scenario.py` — 5 passed.

`l2-brain combat-dry-run`:

| поле | значение |
|---|---|
| исход | combat_success |
| тики | 80 |
| урон | 100 |
| фазы | SEEK → TARGET → APPROACH → ATTACK → VICTORY |
| hid_sent | false |

JSON: [hod29/combat-dummy-v0.json](hod29/combat-dummy-v0.json).
SHA1 `ac6122d4b815622d45ebacaf4a1722db8f213a3b`.

Это не боевой цикл в клиенте и не закрытие Q4 для живой телеметрии.
