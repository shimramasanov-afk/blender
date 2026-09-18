# Сцены восстановления

Замороженный каталог `suite=frozen` (12 имён, 60 эпизодов, бюджет 200) не изменён.
`u_trap` / `dead_end` оставлены в frozen. Семантические имена: `rear_goal_u`, `rear_goal_corridor`.

Заднего хода нет: `MotorIntent.forward` клипуется в [0, 1]. Разворот на месте не называется движением назад.

## Что проверяет старое имя

| старое | новое | фактическая проверка |
|---|---|---|
| `u_trap` | `rear_goal_u` | цель с LOS за спиной; поворот на месте достаточен |
| `dead_end` | `rear_goal_corridor` | то же в коридоре |

## Новые автономные сцены (`suite=integrity`)

| сцена | зачем | проходимость старта/цели | замечание |
|---|---|---|---|
| `detour_visible` | временно уйти от прямого курса при видимой цели | да / да | старт видит цель; прямое +x упирается в стену |
| `side_hold_jog` | удержать сторону в изломе | да / да | с места цель не в LOS; это исследование, не чистый hold |
| `loop_yard` | двор с одним выходом, риск круга | да / да | цель видна с места |

Автономный прогон integrity **ещё не гоняли** — сначала зафиксирован бюджет.

## Диагностика детектора, не оценка политики

`push_wall`: стена сразу впереди. Скрипт всегда шлёт `forward=1`.

Прогон: `scripted_push_blockage()` → `physical_blockage=true`, 1 окно. Не входит в `suite=frozen`.

Команды:

```text
# только frozen, сравнимо с F14
.venv/bin/python -m l2_brain baseline-eval --seed 0 --suite frozen --out docs/evidence/integrity/repro-....json

# новые сцены — отдельный suite, не смешивать с 23/60
.venv/bin/python -m l2_brain baseline-eval --seed 0 --suite integrity --out docs/evidence/integrity/integrity-nav.json
```
