# Как пользоваться правилами и skills

Правила задают ограничения. Skills задают процедуру. Текст не дублировать: если спор о запрете — правило; если нужен порядок шагов — skill.

## Правила

| Файл | Когда действует |
|---|---|
| [00-project-core.mdc](../.cursor/rules/00-project-core.mdc) | Всегда. Ядро проекта. |
| [graphify.mdc](../.cursor/rules/graphify.mdc) | Всегда. Сначала `graphify query/path/explain`, не сырой обход. |
| [10-architecture.mdc](../.cursor/rules/10-architecture.mdc) | Контракты, слои, `src/**/*.py`, `architecture.md`. |
| [20-experiments.mdc](../.cursor/rules/20-experiments.mdc) | Оценка, evidence, гипотезы. |
| [30-python.mdc](../.cursor/rules/30-python.mdc) | Пакет, тесты, `pyproject.toml`. |
| [40-macos-metal.mdc](../.cursor/rules/40-macos-metal.mdc) | Swift, захват, `accel.py`. |
| [50-perception-control.mdc](../.cursor/rules/50-perception-control.mdc) | Признаки, контроллеры, ввод, среда. |
| [55-l1-baseline-freeze.mdc](../.cursor/rules/55-l1-baseline-freeze.mdc) | Замороженный `baseline_memory_v1` (52/60). |
| [60-learning.mdc](../.cursor/rules/60-learning.mdc) | SNN, пластичность, награда. |

Всегда: ядро и Graphify. При конфликте побеждает ядро. Специализация — через globs и явный skill.
Граф — ориентация по коду, не прогон и не право менять замороженный baseline.

## Какой skill к какой задаче

| Задача | Skill |
|---|---|
| Сравнить контроллеры или заявить выигрыш архитектуры | [experiment-design](../.cursor/skills/experiment-design/SKILL.md) |
| Добавить/проверить сцены стенда, столкновения, камеру | [simulator-validation](../.cursor/skills/simulator-validation/SKILL.md) |
| Новый зрительный признак, поток, HUD-маска | [visual-sensor-engineering](../.cursor/skills/visual-sensor-engineering/SKILL.md) |
| Уравнения SNN, dt, эталон, пластичность | [snn-engineering](../.cursor/skills/snn-engineering/SKILL.md). Не трогать замороженный baseline (ADR-0030). Не путать с `controllers/snn.py`. |
| Узкое место, MPS, Metal, копии кадра | [apple-silicon-profiling](../.cursor/skills/apple-silicon-profiling/SKILL.md) |
| Конкретная игра, окно, dry-run, калибровка | [game-adapter-integration](../.cursor/skills/game-adapter-integration/SKILL.md) |
| Застревание, ложный удар, срыв ввода | [failure-analysis](../.cursor/skills/failure-analysis/SKILL.md) |

Канон цели и этапов: [project-brief.md](project-brief.md), [vision.md](vision.md), [roadmap.md](roadmap.md). Открытые неизвестные: [open-questions.md](open-questions.md).

## Примеры запросов

Создать исполняемый каркас стенда (первый следующий шаг):

> По skill `simulator-validation` и правилам 10 и 30 собери исполняемый каркас локального стенда: `SimulationEnvironment`, обязательные сцены (включая `not_implemented`, если сцены ещё нет), контракты наблюдения без privileged-полей, разделение намерения и эффекта. Не подключай игру, Metal и MaleCNS. Существующие файлы не переписывай без нужды — дополни недостающее.

Сравнение контроллеров:

> По skill `experiment-design` подготовь план H1/H2 на стенде. Не пиши цифры в docs до прогона.

Разбор сбоя:

> По skill `failure-analysis` разбери эпизод &lt;путь записи&gt;: застревание у препятствия.

Игра (только когда названы игра и разрешение):

> По skill `game-adapter-integration` сделай шаг 1–3 для игры &lt;имя и версия&gt;. Ввод в клиент не слать.

Не использовать: «добавь мозг мухи», «сделай чтобы не застревал», «ускорь через MPS» без профилирования.
