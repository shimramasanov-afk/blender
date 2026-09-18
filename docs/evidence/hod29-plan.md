# План: ход 29 — телеметрия и синтетический бой

Дата плана: 2026-09-17. Цифр исхода здесь нет.

## Гипотеза / отклонение

На `combat_dummy_v0` тактический FSM проходит SEEK→TARGET→APPROACH→ATTACK→VICTORY
за ≤200 тиков. Урон только при `TargetSelect` и дистанции ≤1.8 м.
`Observation` без координат и дистанции. HID не отправляется.

Отклоняем, если нет победы, урон без лока/вне радиуса, утечка позы в
`Observation`, или живой ввод.

## База

Синтетическая арена, не Frozen 60, не baseline.

## Независимые переменные

Наличие `TargetSelect` и дистанция. Источник телеметрии — только
`sim_ground_truth` / mock.

## Метрики

Исход, тики, урон, смерть манекена, цепочка FSM, `hid_sent=false`.

## Команда

```text
pytest tests/test_combat_scenario.py -q
l2-brain combat-dry-run --out docs/evidence/hod29/combat-dummy-v0.json
```
