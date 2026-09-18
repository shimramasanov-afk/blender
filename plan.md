# PROMPT 0 — Зафиксировать исходное состояние

Работаем с:

`/Users/apple/Desktop/L2_brain`

Перед архитектурными изменениями подготовь проект к безопасному рефакторингу.

ВАЖНО:

- Не трогай соседний git-репозиторий `/Users/apple/Desktop`.
- Не добавляй файлы других проектов.
- Не запускай live HID.
- Не запускай `CGEvent` на реальное окно.
- Не меняй Frozen `baseline_memory_v1`.
- Не ретюнь `sim/`.
- Не меняй SNN / GRU / MaleCNS.
- Не меняй существующие evidence JSON.
- Не переписывай историю экспериментов.

Проверь, есть ли `/Users/apple/Desktop/L2_brain/.git`.

Если собственного git нет, инициализируй git ТОЛЬКО внутри:

`/Users/apple/Desktop/L2_brain`

Добавь нормальный `.gitignore` для:

- `.venv`
- `__pycache__`
- `.pytest_cache`
- `.DS_Store`
- build artifacts
- временных runtime-файлов
- локальных capture/session файлов, если они не являются canonical evidence.

Не удаляй существующие evidence.

После этого:

1. Запусти:

```bash
.venv/bin/python -m pytest tests --tb=no -q

```

1. Сохрани baseline результата.

Ожидаемое текущее состояние из аудита:

- около 336 tests;
- 0 failed.

Если результат отличается — остановись и опиши отличие.

Создай:

`docs/live-agent-refactor.md`

Пока только с разделами:

```text
# Live Agent Refactor

## Baseline

## Constraints

## Architecture target

## Migration status

```

В `Constraints` явно зафиксируй:

- simulation не рефакторим;
- Frozen 52/60 не меняем;
- MaleCNS/SNN не подключаем live на этом этапе;
- planner/quests/OCR/navigation не реализуем;
- live HID нельзя запускать автоматически;
- существующие probes должны продолжать работать во время миграции.

Не делай другие архитектурные изменения на этом шаге.

---

# PROMPT 1 — Ввести единый контракт Skill

Теперь начни рефакторинг live-части.

Цель шага:

создать reusable skill abstraction, НЕ меняя фактическое live-поведение.

Существующие live сценарии сейчас содержат действия прямо внутри:

- `live/spot_loop.py`
- `live/npc_dialog_probe.py`
- `live/layout_slots_probe.py`
- `live/s4_probe.py`

Нужно добавить пакет:

```text
src/l2_brain/live/skills/

```

Предлагаемая структура:

```text
skills/
    __init__.py
    base.py
    result.py
    movement.py
    targeting.py
    combat.py
    npc.py
    ui.py

```

Не обязан буквально следовать файлам, если текущая структура проекта требует лучшее разбиение, но публичный контракт должен быть единым.

Создай enum:

```python
class SkillStatus(Enum):
    READY = ...
    RUNNING = ...
    SUCCESS = ...
    FAILED = ...
    ABORTED = ...

```

Создай dataclass результата примерно такого смысла:

```python
@dataclass
class SkillResult:
    status: SkillStatus
    reason: str | None = None
    data: dict[str, object] = field(default_factory=dict)

```

Создай базовый интерфейс/Protocol для skill:

```python
class Skill(Protocol):
    name: str

    def can_start(self, state) -> bool:
        ...

    def start(self, context, state) -> SkillResult:
        ...

    def tick(self, context, state) -> SkillResult:
        ...

    def cancel(self, context, reason: str) -> SkillResult:
        ...

```

Если для текущего проекта лучше synchronous API — допустимо упростить, но обязательно должны существовать:

- явный start;
- состояние RUNNING;
- SUCCESS;
- FAILED;
- ABORTED;
- reason;
- отсутствие скрытого бесконечного цикла внутри skill.

На этом этапе НЕ переписывай все probes.

Реализуй только первые низкоуровневые skills на основе уже существующего live-кода:

### Movement

- `WalkPulse`
- `RotateLeft`
- `RotateRight`
- при необходимости `UTurn`

### Targeting

- `TargetNext`
- `TargetByName`

### UI

- `CloseDialog`

Не копируй safety logic.

Skills должны использовать существующий:

- `CGEventInputBackend`;
- существующие `GameAction`;
- существующий focus/watchdog/release logic.

Нельзя создавать второй HID backend.

Особое ограничение:

длительное удержание `w` не вводить.

Сохраняем существующие короткие импульсы, соответствующие ADR по H17.

Добавь unit tests.

Тесты должны использовать fake/recording backend и НЕ слать HID.

Проверь минимум:

- SUCCESS;
- FAILED;
- ABORTED;
- cancel вызывает безопасное завершение;
- никакой skill не обходит существующую safety-систему;
- `TargetByName` использует существующий `chat_commander.target_by_name`, а не дублирует его.

В конце обнови:

`docs/live-agent-refactor.md`

Раздел `Migration status`.

После изменений весь существующий test suite должен оставаться зелёным.

---

# PROMPT 2 — Создать Live WorldState

Следующий шаг: создать единое состояние live-мира.

Сейчас состояния распределены по:

- `HUDParseResult`;
- `VisionTelemetryBridge`;
- локальным `phase`;
- `payload`;
- WindowManager;
- отдельным probe-переменным.

Нельзя удалять их прямо сейчас.

Нужно добавить слой агрегации.

Создай модуль примерно:

```text
src/l2_brain/live/world_state.py

```

или эквивалентное место, если архитектурно логичнее.

Создай immutable или контролируемо обновляемый dataclass `WorldState`.

Минимальные поля:

```python
@dataclass
class WorldState:
    timestamp: float

    capture_ok: bool
    focus_ok: bool

    self_hp: float | None
    self_cp: float | None
    self_mp: float | None

    target_locked: bool
    target_hp: float | None
    target_dead: bool

    dialog_open: bool
    dialog_items: tuple[...]

    ui_modal_open: bool | None

    motion_magnitude: float | None

    last_error: str | None

```

Не добавляй пока:

- координаты мира;
- player XY;
- quest state;
- quest objective;
- OCR text;
- NPC identity из vision;
- inventory contents;
- planner state.

Если данных нет — `None`, а не выдуманное значение.

Добавь enum уровня live-mode:

```python
class AgentMode(Enum):
    IDLE
    MOVING
    COMBAT
    NPC_INTERACTION
    RECOVERY
    ABORTED

```

Но `AgentMode` не должен вычисляться самим perception parser.

Это состояние агента, а не факт изображения.

Разделяй:

```text
WorldState = что мы наблюдаем
AgentMode  = что агент сейчас делает

```

Создай `PerceptionHub`, который собирает текущее состояние из уже существующих компонентов:

- SCKGrabber;
- HUDParser;
- dialog parser;
- NavigationEncoder только там, где он уже используется.

Не переписывай:

- HUDParser;
- dialog_parser;
- NavigationEncoder.

Новый слой должен агрегировать их результаты.

Желательный API:

```python
state = perception.observe()

```

или:

```python
state = perception.update(frame)

```

Но один вызов должен возвращать единый `WorldState`.

Добавь tests на:

1. HP parsing → WorldState.
2. target lock.
3. target death.
4. dialog detected.
5. dialog absent.
6. capture failure.
7. focus failure.
8. отсутствие данных не превращается в ложный `False/0`.
9. WorldState не содержит quest state.
10. perception не отправляет input.

Очень важно:

PerceptionHub не должен импортировать `CGEventInputBackend`.

После шага существующие probes могут продолжать использовать старые parser напрямую.

Миграцию пока не делать.

---

# PROMPT 3 — Создать SkillContext и SkillRegistry

Теперь свяжи skills с runtime-контекстом.

Создай единый контекст:

```python
@dataclass
class SkillContext:
    input_backend: ...
    perception: ...
    clock: ...
    telemetry: ...

```

Не клади в него всё подряд.

Не помещай туда:

- planner;
- quest;
- global singleton;
- mutable WorldState как бесконтрольный dict.

Создай `SkillRegistry`.

Примерный смысл:

```python
registry.get("target_next")
registry.get("open_npc_dialog")
registry.get("attack_target")

```

Никакой динамической магии/entrypoints/plugins сейчас не нужно.

Регистрация должна быть явной и простой.

Добавь следующие skills, перенося существующую доказанную live-логику:

### Combat

`AttackTarget`

Использует существующую семантику F2 для combat context.

Условия SUCCESS:

- target death;  
или существующая подтверждённая логика завершения боя.

Failure:

- combat timeout;
- target lost без условия смерти;
- low HP согласно текущему поведению;
- focus/capture failure.

Не добавляй heal.

### Loot

`LootTarget`

Использует текущий F3×3 сценарий.

ВАЖНО:

поскольку inventory contents не читаются, `SUCCESS` здесь означает:

`loot input sequence completed`

а НЕ:

`loot confirmed in inventory`.

Это обязательно отразить в названии reason/data/documentation.

### NPC

`ApproachNamedNpc`

Использует текущий F2 после `/target`.

Не считай достижение NPC гарантированным по таймеру.

SUCCESS допускается только если появляется подтверждённый downstream signal, который реально существует сейчас.

Если такого сигнала недостаточно, верни PARTIAL/FAILED semantics через конкретный reason.

### OpenNpcDialog

Перенеси доказанный путь F85:

```text
TargetByName
→ F2 approach
→ click (0.50, 0.48)
→ wait dialog

```

Не добавляй OCR.

Не пытайся определить, какой именно пункт меню открылся.

SUCCESS:

`dialog_open == true`

а не «NPC понял нас».

### ClickDialogItem

Input:

- индекс или bbox существующего найденного пункта.

Не текст.

SUCCESS означает подтверждённый click, если после клика нет semantic signal.

Не называй его `AcceptQuest`.

Добавь unit tests.

Существующие probes ещё не удалять.

---

# PROMPT 4 — LiveRuntime

Теперь создаём центральный live runtime.

Цель:

один долгоживущий процесс, в котором существует:

```text
capture
→ perception
→ WorldState
→ skill execution
→ input

```

Создай пакет/модуль примерно:

```text
src/l2_brain/live/runtime.py

```

Основной объект:

```python
class LiveRuntime:
    ...

```

Ответственность LiveRuntime:

1. создать/получить SCK capture;
2. создать PerceptionHub;
3. хранить последний WorldState;
4. хранить AgentMode;
5. запускать один skill;
6. тикать текущий skill;
7. завершать skill;
8. безопасно abort;
9. release keys при завершении;
10. записывать telemetry/log.

Не добавляй planner.

LiveRuntime не должен решать сам:

- кого атаковать;
- какой quest выполнять;
- куда идти;
- какой dialog item выбирать.

Он только исполняет skills.

Минимальный API:

```python
runtime.observe()
runtime.start_skill(...)
runtime.tick()
runtime.cancel_skill(...)
runtime.shutdown()

```

Допускается другой API, если он лучше ложится в код.

Ключевые требования:

### Только один активный skill

Пока никакого параллельного исполнения.

### Safety

При:

- F12;
- focus loss;
- capture failure;
- exception;
- shutdown;

обязательно:

- cancel active skill;
- release_all;
- AgentMode → ABORTED или безопасный IDLE согласно причине.

### Никаких hidden loops

Никакой skill не должен блокировать runtime на десятки секунд.

Runtime должен получать управление обратно.

### Никакого Circuit integration

Не пытайся на этом этапе вставить всё внутрь `Circuit.run()`.

`Circuit` оставить неизменённым.

### Никакого simulation refactor

Не менять:

- `SyntheticEnv`;
- `SimulationEnvironment`;
- `BaselineController`;
- Frozen weights;
- SNN;
- GRU;
- MaleCNS.

Добавь tests:

- runtime starts IDLE;
- skill start;
- skill RUNNING;
- skill SUCCESS;
- FAILED;
- cancel;
- exception;
- focus lost;
- capture failure;
- release_all called;
- second skill cannot start while another RUNNING;
- no real HID used in tests.

После этого test suite должен быть зелёным.

---

# PROMPT 5 — Добавить безопасный CLI agent-live

Добавь новый CLI:

```bash
python -m l2_brain agent-live ...

```

Но пока он НЕ должен выполнять автономный сценарий.

Он должен только запускать единый `LiveRuntime`.

Требования safety должны быть такими же строгими или строже существующих S4 CLI:

- `--live`
- `--danger-confirmed`
- `--window-id`
- `--target-pid`

Без двух confirmation flags создание live input backend запрещено.

Режим по умолчанию:

```text
observe-only

```

То есть:

- capture;
- perception;
- WorldState;
- telemetry;
- никаких HID действий.

Для тестового ручного запуска допускаются explicit subcommands/flags вида:

```text
--skill target-next
--skill open-guide

```

НО:

не добавляй автоматический quest loop.

Не добавляй farm loop.

Не добавляй hour-long loop.

Не добавляй navigation.

CLI обязан иметь:

- понятный startup summary;
- текущий mode;
- capture state;
- focus state;
- активный skill;
- причину завершения;
- clean shutdown.

Добавь tests парсинга CLI без запуска live backend.

---

# PROMPT 6 — Мигрировать NPC probe на новые skills

Теперь возьми:

`src/l2_brain/live/npc_dialog_probe.py`

и постепенно переведи его на новые abstractions.

Не удаляй CLI.

Существующая команда должна продолжать работать.

Но внутри она больше не должна самостоятельно реализовывать:

- `/target`;
- approach;
- talk click;
- ожидание dialog;
- close dialog,

если эти операции уже представлены соответствующими skills.

Probe должен стать сценарием orchestration примерно:

```text
start TargetByName
wait result

start ApproachNpc
wait result

start OpenNpcDialog
wait result

for item:
    start ClickDialogItem
    wait result

start CloseDialog
wait result

```

Если `OpenNpcDialog` уже включает target+approach по текущему дизайну — не дублируй эти шаги.

Главное:

probe должен использовать публичный Skill API.

Не надо идеально сохранить старую внутреннюю структуру.

Нужно сохранить наблюдаемое поведение F85:

- заранее известное имя `Newbie Guide`;
- `/target`;
- F2;
- click 0.50/0.48;
- detection HTML;
- blue links;
- Escape.

Не добавлять:

- OCR;
- quest semantics;
- accept quest;
- completion.

Добавь regression tests на orchestration.

---

# PROMPT 7 — Мигрировать combat spot на skills

Теперь рефакторим:

`src/l2_brain/live/spot_loop.py`

Цель:

FSM может остаться.

Но FSM больше не должен напрямую владеть низкоуровневым input.

Вместо:

```text
phase → напрямую CGEvent

```

должно быть:

```text
phase → Skill → LiveRuntime → CGEvent

```

Сохрани существующие фазы:

- idle;
- scan;
- roam;
- combat;
- loot.

Можно заменить строки enum'ом, если это не ломает evidence/replay/tests.

Сохрани доказанное поведение F82:

- F1 target-next;
- F2 attack;
- F3 loot;
- roam;
- u-turn;
- aggro interrupt;
- HP stop;
- short movement pulses;
- no heal;
- kill cap;
- farm=false;
- никакого Frozen L1.

Особенно:

НЕ подключать:

- `BaselineController`;
- `SNNController`;
- `MaleCNSController`;
- Circuit FeatureController.

После миграции combat FSM должен использовать:

- `TargetNext`;
- `AttackTarget`;
- `LootTarget`;
- `WalkPulse`;
- rotate/u-turn skills.

Существующие JSON evidence не переписывать.

Новый код не должен утверждать, что новый runtime уже live-proven, пока не будет отдельного живого прогона.

Добавь regression tests.

---

# PROMPT 8 — Первый Agent Task без квестов

После появления Runtime + WorldState + Skills создай минимальный task layer.

НЕ полноценный planner.

Создай простой deterministic Task/FSM:

```text
GuideInteractionTask

```

Цель:

```text
IDLE
→ OpenNpcDialog("Newbie Guide")
→ убедиться dialog_open
→ CloseDialog
→ убедиться dialog_open=false
→ SUCCESS

```

Вариант repeat:

```text
repeat N times

```

N должен задаваться аргументом.

Default для dry/test:

`N=1`

Live cap:

не более 10 без явного изменения кода/конфига.

Создай статусы:

```python
TaskStatus:
    READY
    RUNNING
    SUCCESS
    FAILED
    ABORTED

```

Task должен оркестрировать skills.

Task НЕ имеет права напрямую:

- нажимать клавиши;
- кликать мышь;
- обращаться к CGEvent backend.

Только:

```text
Task → Skill

```

Добавь CLI режим:

```bash
python -m l2_brain agent-live \
  --task guide-open-close \
  --repeat 1 \
  --live \
  --danger-confirmed ...

```

Не запускай его сам.

Добавь dry fake integration test:

```text
open
→ observed dialog
→ close
→ observed closed
→ task success

```

Добавь failure cases:

- target fail;
- dialog timeout;
- focus lost;
- capture lost;
- close failed.

При любом fail:

- task прекращается;
- input released;
- причина записана.

---

# PROMPT 9 — Recovery layer v1

После того как task layer работает, добавь минимальный recovery.

Не делай AI planner.

Recovery должен быть deterministic.

Нужны только подтверждённые ситуации:

### dialog не открылся

Допускается:

```text
Escape
→ повтор OpenNpcDialog один раз

```

Не бесконечно.

### stale modal

```text
Escape
→ observe

```

### target lost

Вернуть FAILED вызывающему Task.

### capture lost

ABORT.

### focus lost

ABORT.

### HP danger

ABORT для task, где это имеет значение.

Создай:

```python
RecoveryPolicy

```

или аналогичный небольшой компонент.

Обязательное правило:

каждая recovery-ветка имеет hard retry limit.

Никаких:

```python
while not success:
    retry()

```

Добавь tests на retry limits.

---

# PROMPT 10 — Architecture cleanup после миграции

Только после успешных предыдущих шагов проведи аудит live-кода.

Проверь:

- где остались прямые вызовы `CGEventInputBackend.send_action`;
- где live probe напрямую жмёт клавиши;
- где дублируется target/dialog/combat logic;
- где дублируется safety;
- где `payload dict` используется вместо WorldState;
- где локальная phase machine может использовать Skill API.

Не удаляй код автоматически.

Составь сначала отчёт:

`docs/live-agent-migration-audit.md`

Формат:

| File | Legacy behavior | Replacement exists | Safe to remove? | Reason |

После отчёта удаляй legacy logic только там, где:

1. новая реализация покрыта тестами;
2. старый CLI остаётся совместим;
3. нет потери safety;
4. поведение подтверждено regression tests.

Не удалять:

- Circuit;
- Simulation;
- Frozen L1;
- SNN;
- GRU;
- MaleCNS;
- evidence;
- calibration history.

---

# PROMPT 11 — Критерий завершения Live Agent Core

Проведи финальную проверку архитектуры.

Milestone называется:

`Live Agent Core v0.8`

DONE только если выполнены все пункты:

## Architecture

- есть `WorldState`;
- есть `PerceptionHub`;
- есть единый `Skill` contract;
- есть `SkillResult`;
- есть `SkillRegistry`;
- есть `LiveRuntime`;
- есть `Task` abstraction;
- Task не шлёт HID напрямую;
- Skill не дублирует safety backend;
- только один live input backend.

## Existing abilities preserved

- combat scenario всё ещё представлен;
- NPC Guide scenario всё ещё представлен;
- layout tools не сломаны.

## Isolation

Не изменены функционально:

- nav-sim;
- Frozen 52/60;
- SNN;
- GRU;
- MaleCNS;
- Circuit mock behavior.

## Tests

Запусти:

```bash
.venv/bin/python -m pytest tests --tb=no -q

```

Все тесты должны быть зелёными.

Добавь новые tests для:

- WorldState;
- PerceptionHub;
- Skills;
- LiveRuntime;
- Tasks;
- Recovery.

## Safety

Проверь:

- F12;
- focus loss;
- watchdog;
- release_all;
- dual flags;
- PID restriction.

## Не должно существовать

На этом milestone всё ещё НЕ должны быть реализованы:

- planner квестов;
- OCR;
- quest understanding;
- inventory understanding;
- `go_to(x,y)`;
- map navigation;
- Frozen L1 live;
- SNN live;
- MaleCNS live;
- autonomous farm.

## Итоговый документ

Обнови:

`docs/live-agent-refactor.md`

Добавив:

```text
## Final architecture

## Migrated code

## Legacy code remaining

## Tests

## Safety

## Known limitations

## Next milestone

```

`Next milestone` только описать, не реализовывать.

Следующим milestone должен быть кандидат:

`One Quest`

но только если Live Agent Core действительно выполнен.

В конце дай короткий отчёт:

```text
LIVE AGENT CORE STATUS: DONE / NOT DONE

Blocking issues:
- ...

Files added:
- ...

Files materially changed:
- ...

Tests:
- ...

Live testing performed:
NO

```

Не запускать live HID для подтверждения milestone без отдельной команды оператора.