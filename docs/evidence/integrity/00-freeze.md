# Фиксация исходного состояния

Не перезаписывать `docs/evidence/baseline-nav.json` и `docs/evidence/baseline-memory-nav.json`.
Машина снимка: `docs/evidence/integrity/freeze.json`.
Цифры воспроизведения — только после прогона в этом каталоге.

## Запрет на этом шаге

SNN, MaleCNS, новое обучение, Metal/MPS не начинать.
Стенд, зрение и контроллер в этом блоке не менять.

## Команды воспроизведения

```text
.venv/bin/python -m l2_brain baseline-eval --seed 0 --no-recovery --out docs/evidence/integrity/repro-baseline-v1.json
.venv/bin/python -m l2_brain baseline-eval --seed 0 --out docs/evidence/integrity/repro-baseline-memory-v1.json --compare docs/evidence/baseline-nav.json
```

Seed 0. Каталог `nav-sim-v1`: 12 сцен × 5 вариантов = 60. `max_steps` из `SimConfig` (200), если флаг не задан.

## Зафиксированные артефакты

| контроллер | файл | package | успех | исходы |
|---|---|---|---|---|
| `baseline_v1` | `docs/evidence/baseline-nav.json` | 0.5.0 | 23/60 | success 23, timeout 16, stuck 21 |
| `baseline_memory_v1` | `docs/evidence/baseline-memory-nav.json` | 0.7.0 | 23/60 | success 23, timeout 16, stuck 21 |

`git_rev` в обоих JSON: `9eff9f266480fd079c462cd082f5d647d5ac5d45`, dirty. Текущий пакет 0.7.0, тот же rev, дерево dirty.

## Среда на момент фиксации

- Darwin arm64, Python 3.14.7, numpy 2.5.3, pytest 9.1.1
- git корень — Desktop; `L2_brain/` не отдельный репозиторий

## Что уже совпадает в артефактах (без нового прогона)

Общие ключи `BaselineConfig` у v1 и memory **равны** (притяжение, тормоз, круиз, окна пеленга и стороны).
У memory дополнительно поля восстановления; в прогоне F15 `recovery=true`.
`SimConfig` по умолчанию: кадр 64×64, `tick_hz=20`, `max_steps=200`, `max_speed=0.12`, `max_turn=0.18`, `goal_radius=0.75`, `fov_h=1.2`.
`MotorIntent.clipped`: `forward` ∈ [0, 1], отрицательное становится 0. Это не задний ход.
Оба каталожных прогона: энкодер `navigation_v1`, `learned=false`, held-out не для подбора.

## Воспроизведение (факт прогона)

Исходные JSON не перезаписывались (размеры 57505 и 71894 байт).

Новые файлы:

- `docs/evidence/integrity/repro-baseline-v1.json` (`--no-recovery`, `recovery=false`)
- `docs/evidence/integrity/repro-baseline-memory-v1.json` (`recovery=true`)

Оба: 23/60, success 23 / timeout 16 / stuck 21, vision 20 / control 17.
По полям успех/тики/исход/причина/столкновения/путь/смещение/miss/conf:

- исходный v1 = воспроизведённый v1 (0 расхождений);
- исходная memory = воспроизведённая memory (0);
- воспроизведённый v1 = воспроизведённая memory (0).

Расхождение с 23/60 нет. Текущий `--no-recovery` уже содержит модуль `ShortTermMemory`; на этом каталоге он не меняет поведение относительно артефакта 0.5.0.

## Одинаковые условия сравнения

| условие | v1 | memory | совпадает |
|---|---|---|---|
| каталог | `catalog(0)`, 60 id | те же id | да |
| наблюдения | `NavigationEncoder` 48×32 | то же | да |
| действия | `MotorIntent.clipped`, forward∈[0,1] | то же | да |
| бюджет | `max_steps=200`, `tick_hz=20` | то же | да |
| успех | дистанция ≤ `goal_radius` 0.75 | то же | да |
| коэффициенты суммы | общие ключи `BaselineConfig` | те же значения | да |
| восстановление | выключено | включено | нет; на каталоге не срабатывало |

Проверка аудита: [audit-check.md](audit-check.md).
