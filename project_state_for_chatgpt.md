# L2_brain — CURRENT STATE SNAPSHOT

**Дата снимка:** 2026-09-18  
**Каталог:** `/Users/apple/Desktop/L2_brain`  
**Пакет:** `l2-brain` 0.7.0 (`src/l2_brain/__init__.py`)  
**Автор снимка:** аудит кода, конфигов, ADR, JSON evidence и безопасный `pytest`. Код проекта **не менялся**. Live HID **не запускался**.

**Как читать статусы**

| Метка | Значение |
|---|---|
| EXISTS | есть в коде этого каталога |
| UNIT-TESTED | покрыто `tests/` и зелёно на этом прогоне |
| LIVE-PROVEN | есть JSON/отчёт живого прогона в `docs/evidence/` |
| PLANNED | в `docs/vision.md` / `docs/roadmap.md`, в runtime нет |
| STALE-DOC | документ противоречит текущему коду или более новым фактам |
| OBSOLETE-FOR-LIVE | код жив на стенде, но **не** управляет живым персонажем |
| UNKNOWN | из репозитория достоверно не установить |

Цифры ниже — только из кода, `docs/assumptions.md`, ADR или JSON. Если цифры нет в этих источниках — `UNKNOWN`.

---

# 1. Executive Summary

`L2_brain` сейчас — исследовательский сенсомоторный стенд и набор **отдельных живых зондов** для Lineage 2 Interlude в видимом окне Parallels на Apple Silicon. Это **не** единый замкнутый агент и **не** готовый игровой бот.

Три стека сосуществуют и **не склеены** в один runtime:

1. **Стенд S0** — `types.Observation` → `ControlLoop` → `types.Action` на `SyntheticEnv`. Учебные контроллеры `reactive` / `recurrent` / `snn`.
2. **Контур Circuit** — `contracts.Frame` → encoder → `MotorIntent` → `Command` → `InputBackend`. По умолчанию mock. `build_sck_circuit()` берёт живой SCK и **намеренно** `MockInputBackend` (захват без HID).
3. **Живые зонды** — `SCKGrabber` + `HUDParser` / `dialog_parser` + жёсткие сценарии + `CGEventInputBackend` на PID хоста Parallels. Это **не** `Circuit.run()`.

**Что агент реально умеет (LIVE-PROVEN, узко):**

- Снимать видимое окно Parallels через ScreenCaptureKit (~30 FPS, H7/F40).
- Слать легальный host HID (`CGEventPostToPid`) в окно Parallels при двух флагах `--live --danger-confirmed`.
- Читать с кадра свои CP/HP/MP, рамку цели, HP цели, смерть цели (HP=0 или пропажа рамки), готовность слотов F1–F3. Без OCR.
- На Talking Island: цикл «F1 `/targetnext` → F2 Attack → смерть → F3 Pickup → короткий roam стрелка+`w`», серия **10/10 за 150 с** (F82). Хила нет (`no_heal=true`). Потолок 10 фрагов зашит.
- Один мирный путь к `Newbie Guide`: чат `/target Newbie Guide` → F2 (подбег, не атака) → ЛКМ в норме (0.50, 0.48) → синие HTML-ссылки в **левой** панели → клик всех 6 пунктов с Escape между ними (F85).
- Tab занимает слот, Escape освобождает — доказано на **старой стоянке инвентаря** `[1592,650,342,307]`, не на текущей целевой сетке 2560×1600 (F86 vs ADR-0077).
- Живой click-through оверлей рамок поверх окна Parallels (ход 86b, без HID).

**Чего агент НЕ умеет:**

- Хранить цель уровня «выполнить квест» и самому выбирать навыки.
- Читать текст (OCR нет), квестовый журнал, счётчики, имена пунктов меню.
- Знать мировую позу, карту, метры, канонический yaw (Q5 открыт).
- Команды `go_to(x,y)` нет.
- Универсально находить NPC, кроме заранее известного имени в чате.
- Выйти из деревни к квестовой цели и вернуться.
- Принять/сдать квест и проверить награду.
- Замкнуть `SCK → perception → CircuitController → CGEvent` в одном `Circuit.run()`.
- Использовать Frozen L1 `baseline_memory_v1` 52/60 в live.
- Использовать SNN / GRU / MaleCNS как живой контроллер персонажа.
- Фарм, хил F4, торговля, инвентарь как навык, макросы, второй персонаж.

**Автономность фактически:** оператор готовит окно, фокус, PID, dual flags, хоткеи, парковку UI. Агент исполняет **короткий заранее написанный сценарий** (бой 10 фрагов **или** обход меню гида **или** Tab/Escape). Между сценариями общего планировщика нет. После abort — стоп, не recovery-политика. Это **scripted live skills under supervision**, не long-horizon autonomy.

**Последний подтверждённый milestone**

- Последний **live HID**: F86 (2026-09-18) — Tab/Escape на инвентаре в слоте Б `[1592,650,342,307]`, SHA1 `1ac0f4eb`.
- Последний **мирный live**: F85 — `/target`+F2+ЛКМ, HTML 6/6, SHA1 `ce2cec6a`.
- Последний **боевой live**: F82 — 10/10, 150 с, SHA1 `388921ec`.
- Последние **кодовые/док** ходы 86b/86c: оверлей и смена `ref_window` на guest 2560×1600, слот Б цели `[2140,140,360,480]`. Повторного live `layout-slots` после смены сетки **нет**. F86 не переписывали.

**Bottleneck сейчас:** не «слабая сеть» и не отсутствие MaleCNS. Живой край — набор несовместимых сценариев без модели мира, без reusable skills с условиями завершения и без навигации с позой. Q5 (метры/yaw) открыт. Quest text отсутствует. Circuit не исполняет live HID.

**Этап по факту, не по старому roadmap.** Roadmap: S0→S1 (закрыть H1)→S2→S3→S4 один навык; квесты/диалоги в v1 не входили. Оператор открыл живой край **до** закрытия H1. H1–H5 официально не закрыты. S4 как «один узкий навык» частично выполнен боем (F82) и одним NPC-путём (F85), но выход S4 (H10, H14) не закрыт. Проект фактически в **S4-probes / pre-agent**: живой сенсор+актуатор есть, единого агента нет.

**CURRENT PROJECT STAGE:** `S4 live probes, no unified agent`.  
Есть легальный кадр и легальный host HID. Есть два доказанных узких навыка (спот 10/10 и меню Newbie Guide) и зачатки сетки UI. Нет замкнутого Circuit на клиенте, нет Frozen L1 в игре, нет цели/квеста, нет позы, нет OCR. Учебный v1 из `vision.md` (три контроллера, H1–H5 решены) **не завершён**. Живой Interlude **опередил** этот v1 и пошёл отдельной кодовой веткой (`live/*`), которую нельзя выдавать за «продолжение Frozen 52/60». Следующий архитектурный шаг — решить, склеивать ли зонды в агента или сначала закрывать научный v1; это операторское решение, не факт репозитория.

---

# 2. Git / состояние репозитория

## Git history проекта L2_brain

**Недоступна как история этого каталога.**

| Поле | Значение |
|---|---|
| Git root | `/Users/apple/Desktop` (не `L2_brain`) |
| Ветка Desktop | `main` |
| HEAD Desktop | `9eff9f266480fd079c462cd082f5d647d5ac5d45` |
| Дата HEAD Desktop | 2026-09-15 19:52:03 +0300 |
| Сообщение HEAD | `Фаза 0: watchdog, UserInfo (MP/CP/SP/вес/адена), replay мира в SQLite.` |
| `L2_brain/.git` | нет |
| Файлов `L2_brain` в индексе Desktop | **0** |
| Статус `L2_brain` | целиком untracked: `?? L2_brain/` |
| Commits с путём `L2_brain` | нет |

HEAD Desktop относится к **другому** дереву («L2 Autopilot», Erica, XOR-поток, `prlctl`). Это **не** история `L2_brain`. Цитировать эти коммиты как эволюцию этого проекта нельзя.

Последние 10 commit Desktop (чужой проект, только чтобы не скрыть факт):

1. `9eff9f2` — Фаза 0: watchdog, UserInfo, replay SQLite  
2. `2e90a96` — Мышь: `PrlDevMouse_SetPos`  
3. `78e4ccc` — Живая сессия Erica, XOR-поток  
4. `162d15e` — Сетевой тап, `l2_decode`  
5. `ee3a385` — BPF, калибровка клавиатуры, SCK-проба  
6. `96830af` — PLAN v0.3, recon VM  
7. `1e3928d` — план v0.2  

Для `L2_brain` это **не** changelog.

**Uncommitted / untracked:** весь каталог `L2_brain` не в git. «Незакоммиченные изменения, которые меняют архитектуру» — весь проект вне VCS. Внутри каталога нет отдельного dirty tree относительно собственного HEAD (HEAD нет).

## Python и зависимости

Проверено в `.venv` этого каталога, 2026-09-18:

| Компонент | Версия |
|---|---|
| Python | 3.14.7 |
| numpy | 2.5.3 |
| pytest | 9.1.1 |
| opencv (`cv2`) | 5.0.0 |
| torch | 2.14.0, `mps.is_available()=True` |

`pyproject.toml`: `requires-python >=3.11`; обязательная зависимость только `numpy>=2.1`. Опционально: `pytest`, `torch`, `opencv-python-headless`. Скрипты: `l2-brain`, `l2-brain-eval`.

Системный Python без venv numpy/pytest не содержит (F4). Стенд идёт из `.venv`.

## Команды запуска

Общий вход: `python -m l2_brain <cmd>` из корня с активированным `.venv` (или `l2-brain`, если editable install).

Безопасные (без HID):

```bash
pytest
python -m l2_brain doctor
python -m l2_brain mock --ticks 16 --seed 0 --record run/mock-session.jsonl
python -m l2_brain eval --controller reactive --scenario open_field --episodes 8
python -m l2_brain sim-eval --seed 0 --split training --max-steps 4 --out run/nav-suite.json
python -m l2_brain baseline-eval --seed 0 --out docs/evidence/baseline-nav.json
# baseline-eval не крутить веса Frozen (ADR-0030)
```

Живые (dual flags, не запускались в этом аудите):

```bash
python -m l2_brain s4-integrated-spot --live --danger-confirmed --window-id … --target-pid …
python -m l2_brain s4-npc-dialog --live --danger-confirmed --via-chat --window-id … --target-pid …
python -m l2_brain layout-slots --live --danger-confirmed --window-id … --target-pid …
python -m l2_brain layout-overlay --window-id … --seconds 180   # без HID
```

Тесты: `pytest` или `python -m pytest tests`. Live HID в suite нет (флаги не передаются). `tests/test_live_blocked.py` проверяет, что `LiveClientEnv` / `LiveHIDActuator` бросают `NotImplementedError`.

---

# 3. Структура проекта

Значимое дерево (без `__pycache__`, `.venv`, `graphify-out`, `.build`):

```text
L2_brain/
  pyproject.toml
  README.md                          STALE-DOC (см. §20)
  config/window_profiles/parallels_l2.json
  macos/CaptureProbe/                Swift SCK helper, pipe L2F1
  macos/LayoutOverlay/               Swift click-through overlay
  src/l2_brain/                      пакет (145 .py на аудит)
  tests/                             44 файла test_*.py
  docs/                              status, architecture, assumptions, ADR, evidence
  tools/                             вспомогательные скрипты
  run/                               локальные прогоны, не канон
  memory/                            заметки агента, не игровая память
```

## Модули

| Путь | Назначение | Ключевые символы | Кто вызывает | Слой |
|---|---|---|---|---|
| `types.py` | стенд Observation/Action | `Observation`, `Action`, `TickMetrics` | `loop.py`, `evaluate.py`, `controllers/*`, `env/*` | simulation |
| `contracts.py` | контур Frame/Observation/MotorIntent | `Frame`, `Observation`, `MotorIntent`, `Command`, `Effect` | `circuit/*`, `vision/encoder.py`, `control/*` | Circuit |
| `loop.py` | стендовая петля | `ControlLoop`, `run_episode` | `evaluate.py` | simulation |
| `evaluate.py` | сравнение reactive/recurrent/snn | `main`, `CONTROLLERS` из `config.py` | CLI `eval` | simulation / tests |
| `factory.py` | сборка энкодера | `build_encoder` | Circuit | Circuit / perception |
| `safety.py` | текстовый блок LiveClientEnv | `LIVE_CLIENT_BLOCKED_REASON` | `env/live.py`, `actuators/live.py` | STALE-DOC vs S4 |
| `circuit/loop.py` | `Circuit.step/run` | `Circuit`, `build_mock_circuit` | CLI mock/record; `capture/circuit.py` | Circuit |
| `circuit/policy.py` | реактивная политика контура | `FeatureController`, `PulseDecoder` | `build_mock_circuit`, `build_sck_circuit` | Circuit |
| `circuit/mock_io.py` | искусственные кадры/ввод | `MockFrameSource`, `MockInputBackend` | Circuit builders | Circuit |
| `capture/sck.py` | SCK → Frame | `SCKFrameSource` | `SCKGrabber`, Circuit SCK | perception |
| `capture/circuit.py` | SCK+mock HID | `build_sck_circuit` | CLI capture record | Circuit, **не live HID** |
| `capture/helper.py` | Swift helper | `resolve_helper`, `list_windows` | live probes, overlay | perception |
| `vision/encoder.py` | сектора, поток, expansion | `NavigationEncoder.encode` | Circuit; live-motion; spot_loop (flow) | perception / nav-sim |
| `vision/hud_parser.py` | полосы HUD | `HUDParser`, `HUDParseResult` | все live combat/NPC | perception / live |
| `vision/dialog_parser.py` | синие ссылки слева, без OCR | `parse_dialog`, `extract_menu_items` | `npc_dialog_probe` | perception / NPC |
| `vision/layout_slots.py` | сетка слотов | `LayoutSlots.box_on_frame` | overlay, layout-slots, ui_manager | UI |
| `vision/ui_manager.py` | занятость слота | `WindowManager.is_slot_occupied` | `layout_slots_probe` | UI |
| `vision/flow.py` | SAD/KLT-соседство | `reference_flow` | encoder | perception |
| `calibration/klt_yaw.py` | KLT yaw | coarse/KLT | `calibrate-motion` | experimental / Q5 |
| `control/baseline.py` | Frozen L1 | `BaselineController.step` → `MotorIntent` | `baseline-eval`, bench; **не live/** | nav-sim, OBSOLETE-FOR-LIVE |
| `control/memory.py` | STM восстановления | `ShortTermMemory` | только BaselineController | nav-sim |
| `control/snn/` | LIF CPU | `SNNController` | bench/learn/suite | experimental, sim |
| `control/gru/` | GRU H=16 | `GRUController` | bench | experimental, sim |
| `control/malecns/` | синтетический экстракт | `MaleCNSController`, `load_subgraph` | `malecns-eval` | experimental, sim |
| `control/tactical.py` | синтетический бой FSM | `TacticalCombatController` | `combat-dry-run` | simulation / combat |
| `control/spot_agent.py` | синтетический спот, L1=snn_v1 | `SpotAutonomousAgent` | CLI `spot-loop` | simulation |
| `controllers/*` | стенд Action | `ReactiveController`, `RecurrentController`, `SpikingController` | `evaluate` | simulation |
| `sim/` | nav-sim + dummy combat | `SimulationEnvironment`, `spot_arena` | sim-eval, baseline-eval | simulation / navigation |
| `env/synthetic.py` | SyntheticEnv | `SyntheticEnv` | evaluate | simulation |
| `env/live.py` | заглушка | `LiveClientEnv` → `NotImplementedError` | тесты блока | **не live** |
| `actuators/live.py` | заглушка | `LiveHIDActuator` → `NotImplementedError` | тесты блока | **не live** |
| `io/cgevent_backend.py` | живой HID | `CGEventInputBackend.send_action` | все live probes | input / live |
| `io/chat_commander.py` | `/target Name` | `target_by_name` | npc via-chat | input / NPC |
| `io/actions.py` | семантика команд | `GameAction`, `HoldKey`, `SkillActivate` | decoder + live | input |
| `io/decoder.py` | MotorIntent→GameAction | `IntentDecoder` | dry-run, synthetic L2 | Circuit / sim |
| `io/safety.py` | watchdog удержаний | `InputWatchdog` | CGEvent, DryRun | input |
| `io/focus.py` | NSWorkspace | `is_allowed_frontmost` | CGEvent | input |
| `live/s4_probe.py` | боевые режимы S4 | `run_s4_probe`, `SCKGrabber` | CLI `s4-probe` | live / combat |
| `live/spot_loop.py` | серия фрагов | `run_integrated_spot` | CLI `s4-integrated-spot` | live / combat |
| `live/npc_dialog_probe.py` | NPC/меню | `run_npc_dialog_probe` | CLI `s4-npc-dialog` | live / NPC |
| `live/layout_slots_probe.py` | Tab/Escape | `run_layout_slots_probe` | CLI `layout-slots` | live / UI |
| `tools/layout_overlay.py` | рамки | `run_layout_overlay` | CLI `layout-overlay` | live / UI, без HID |
| `telemetry/` | шина событий | `TelemetryHub`, `VisionTelemetryBridge` | spot_loop, hud | perception |
| `learning/` | R-STDP / ES | `RewardEngine` | CLI `learn` | experimental |
| `experiment/` | запись сессий Circuit | `build_recorder` | Circuit | Circuit / tests |
| `cli.py` | все entrypoints | `main` | `python -m l2_brain` | all |

**Реальные связи live (не схема желаемого):**

```text
cli.py
  ├─ s4-integrated-spot → live.spot_loop.run_integrated_spot
  │     ├─ SCKGrabber (live.s4_probe)
  │     ├─ HUDParser + VisionTelemetryBridge
  │     ├─ NavigationEncoder только для flow_magnitude (не BaselineController)
  │     └─ CGEventInputBackend
  ├─ s4-probe → live.s4_probe.run_s4_probe
  ├─ s4-npc-dialog → live.npc_dialog_probe
  │     ├─ chat_commander.target_by_name
  │     ├─ dialog_parser / HUDParser
  │     └─ CGEvent
  ├─ layout-slots → live.layout_slots_probe + WindowManager
  └─ layout-overlay → tools.layout_overlay + macos/LayoutOverlay
```

`control/tactical.py` и `control/spot_agent.py` **не** вызываются из `live/`.

---

# 4. Реальная архитектура на сегодня

## Общая картина (факт)

```text
                    ┌─────────────────────────────┐
                    │  НЕТ единого агента         │
                    └─────────────────────────────┘
         ┌──────────────────┬─────────────────────┬─────────────────────┐
         ▼                  ▼                     ▼
   SyntheticEnv        Circuit.run()         Live probes
   types.Action        MotorIntent           hardcoded FSM
   evaluate/sim        Mock HID (даже SCK)   CGEvent HID
```

## Simulation / nav-sim

```text
sim.environment.SimulationEnvironment
        │  кадр + GT в StepInfo (не в Observation)
        ▼
vision.encoder.NavigationEncoder.encode  →  contracts.Observation.navigation
        │
        ▼
control.baseline.BaselineController.step → MotorIntent
        │
        ▼
control.eval.run_episode  /  CLI baseline-eval
```

Рядом, **другой** стенд:

```text
env.synthetic.SyntheticEnv
        │  types.Observation (сырой кадр)
        ▼
controllers.reactive|recurrent|snn.step → types.Action
        ▼
loop.ControlLoop / evaluate
```

Два Observation **несовместимы** (ADR-0011). Отчёты нельзя смешивать.

Синтетический бой/спот:

```text
sim.combat / sim.spot_arena
        → control.tactical.TacticalCombatController
        → control.spot_agent.SpotAutonomousAgent  (L1 = snn_v1)
        → io.decoder.IntentDecoder → DryRun InputBackend
```

HID нет. F35, F39.

## Circuit

```text
FrameSource.latest()                capture/sck.py | circuit/mock_io.py
        │
        ▼
VisualEncoder.encode()              factory: color_blob | navigation_v1
        │                           circuit/encode.py ColorBlobEncoder
        │                           vision/encoder.py NavigationEncoder
        ▼
contracts.Observation
        │
        ▼
CircuitController.step()            circuit/policy.py FeatureController
        │                           (НЕ BaselineController в default builder)
        ▼
MotorIntent
        │
        ▼
PulseDecoder.decode()               circuit/policy.py
        ▼
Command
        │
        ▼
InputBackend.send()                 MockInputBackend  ← build_sck_circuit()
        ▼
Effect(mock=True)
```

`Circuit.run()` (`circuit/loop.py:214`) крутит `step()` N тиков и в `finally` закрывает backend.  
`build_sck_circuit` (`capture/circuit.py:13-24`):

```python
backend=MockInputBackend(),
controller=FeatureController(),
```

**`Circuit.run()` в live игре не используется.** Builder SCK+CGEvent **отсутствует**.

## Live pipeline

```text
macos/CaptureProbe  --pipe L2F1-->  SCKFrameSource.latest()
                                           │
                                    SCKGrabber.latest_image()
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
             HUDParser.parse        dialog_parser.parse     NavigationEncoder
             (HP/lock/dead)         (blue links, no OCR)    (flow only in spot)
                    │                      │                      │
                    ▼                      ▼                      ▼
             VisionTelemetryBridge   is_dialog_open         flow_magnitude_midnear
                    │                      │                      │
                    └──────────┬───────────┴──────────────────────┘
                               ▼
                    probe-local phase string + payload dict
                    (idle|scan|roam|combat|loot)   ИЛИ
                    (chat target → F2 → LMB → crawl) ИЛИ
                    (Escape → Tab → occupancy)
                               │
                               ▼
                    io.actions.GameAction
                    (HoldKey, SkillActivate, GroundClick, CameraRotate)
                               │
                               ▼
                    CGEventInputBackend.send_action / type_text
                    CGEventPostToPid(target_pid=Parallels)
```

Конкретные переходы:

| Переход | Файл / функция |
|---|---|
| Capture | `live/s4_probe.py` `SCKGrabber.start/latest_image` → `capture/sck.py` `SCKFrameSource` |
| HUD | `vision/hud_parser.py` `HUDParser.parse` |
| Dialog | `vision/dialog_parser.py` `parse_dialog` / `extract_menu_items` / `is_dialog_open` |
| Combat FSM | `live/spot_loop.py` `run_integrated_spot` phase=`idle|scan|roam|combat|loot` |
| NPC script | `live/npc_dialog_probe.py` `run_npc_dialog_probe` |
| Chat target | `io/chat_commander.py` `target_by_name` |
| HID | `io/cgevent_backend.py` `CGEventInputBackend.send_action` |
| Focus | `io/focus.py` `is_allowed_frontmost` bundle `com.parallels.desktop.console` |

## Ответы на обязательные вопросы

| Вопрос | Ответ |
|---|---|
| Есть ли единый замкнутый агент? | **Нет.** Три стека, live = отдельные CLI. |
| Используется ли `Circuit.run()` в live? | **Нет.** |
| Есть ли путь `SCK → perception → controller → CGEvent` в одной архитектуре? | **Нет как Circuit.** Live: SCK → parser → **скрипт/FSM зонда** → CGEvent. «Controller» в смысле `BaselineController`/`CircuitController` на этом пути нет. |
| Какие live-сценарии отдельно от Circuit? | `s4-probe` режимы, `s4-integrated-spot`, `s4-npc-dialog`, `layout-slots`, `live-motion`, `calibrate-motion`, `bench-h8`, `input-probe` (Notepad). Overlay без HID. |
| Где FSM? | Live: `spot_loop.py` (строки фаз ~248+). Стенд: `tactical.py` `CombatPhase`, `spot_agent.py` `SpotPhase`. Это **разные** машины. |
| Frozen L1 в live? | **Нет.** `live/` не импортирует `BaselineController`. ADR-0068: живой L1 = encoder flow + peel-стрелки, не 52/60. |
| `BaselineController` / `NavigationEncoder` / SNN / recurrent где? | Baseline: только nav-sim / bench. Encoder: Circuit + live-motion + spot (только magnitude). SNN/GRU/MaleCNS: sim bench. Recurrent/reactive: только `evaluate` SyntheticEnv. |

---

# 5. L1 / L2 / L3

`docs/architecture.md` описывает иерархию как **цель продукта**, не один runtime. Ниже — факт кода.

## L1 — сенсомотор / movement / reactive

**Реализовано (sim):** Frozen `baseline_memory_v1`, канон **52/60** seed=0 (F28/F29, ADR-0030). Веса не крутить. Восемь незакрытых эпизодов законсервированы. Код: `control/baseline.py` `BaselineController.step` (~строка 88), память `control/memory.py` `ShortTermMemory`.

**Реализовано (live, другое значение «L1»):** в `spot_loop.py` «L1» = `should_l1_unjam` + peel стрелками, если F2 активен ≥3 с, цель не дамажится, поток статичен 6 тиков. На F82 **l1_triggers=0**. Это не Frozen контроллер.

**Вызывается live:** `NavigationEncoder` для `flow_magnitude_midnear`; пороги `L1_FLOW_STATIC_MAX=0.01`.  
**Experimental/dead для live:** SNN, GRU, MaleCNS, `controllers/*`, `FeatureController` на клиенте.  
**Evidence:** Frozen 52/60 — sim JSON `docs/evidence/hod23/`. Live flow — F61–F72, F79. Q5/H17 открыты.  
**Нет:** замкнутого L1, который ведёт персонажа `MotorIntent`→клавиши как на nav-sim.

## L2 — тактика / бой / FSM

**Реализовано live:** `run_integrated_spot` — scan F1, roam (стрелка+`w` 450 мс), combat F2, loot F3×3, agro по падению своего HP, abort при HP<0.10.  
**Реализовано sim:** `TacticalCombatController`, `SpotAutonomousAgent` (L1=snn_v1).  
**Вызывается live:** только `spot_loop` / `s4_probe`.  
**Не вызывается live:** `tactical.py`, `spot_agent.py`.  
**Evidence:** F49–F55, F80–F82.  
**Нет:** тактики вне спота (пати, скиллы кроме F1–F3, хил).

## L3 — цели / planning / quests

**Реализовано:** нет планировщика. Есть один скрипт меню гида и сетка слотов UI.  
`architecture.md` строка про L3 «зонд окна NPC (ход 83)» — **STALE-DOC**: ход 83 = лок без окна; рабочий путь — ход 85.  
**Нет:** quest graph, goal stack, skill planner, progress tracker.

### Есть ли компонент «выполнить квест и выбрать навыки»?

**Нет.** Ни класса, ни поля, ни CLI. `quest_link_clicks` в NPC-зонде — счётчик кликов по синим прямоугольникам, не понимание квеста.

---

# 6. Perception

OCR в дереве **нет** (явные комментарии `dialog_parser.py`, `layout_slots.py`, `ui_manager.py`). Детектора объектов/сущностей нет (`NavigationEncoder`: «No object-recognition network»). Универсального UI detector нет: фиксированные ROI + цветные эвристики + слоты.

| Signal | Implemented | File/Class | Live tested | Reliability / limitations |
|---|---|---|---|---|
| own HP | да, доля красной полосы | `HUDParser` / `HUDParseResult.self_hp_ratio` | да, F45–F47, F80–F82 | ROI одного windowed layout; перетаскивание виджетов ломает |
| own CP | да | `self_cp_ratio` | офлайн F45, в бою пишется | то же |
| own MP | да | `self_mp_ratio` | офлайн F45 | то же |
| target frame | да, brown plate | `target_locked` | F45–F47, F82, F85 | пустая подложка может дать locked+dead (F46) |
| target HP | да | `target_hp_ratio` | F51–F53, F82 | без текста; пороги 0.08 vanish |
| target lost | да, через `TargetState(locked=false)` | `VisionTelemetryBridge` | F47 | не победа |
| target death | да, HP=0 на рамке или vanish ≤0.08 | `EntityDefeated` | F52, F82 | лут в инвентаре не читали |
| NPC identity | нет с кадра | — | — | только чат `/target <Name>` если имя заранее известно |
| dialog open | частично | `is_dialog_open`: тёмная левая панель + ≥2 синих | F85 да; F83 нет | ловит HTML гида; пергамент/квест-текст — слабо |
| HTML links | да, bbox синего | `extract_menu_items` | F85 6/6 | без текста; только LEFT_PANEL 0.05–0.37 × 0.20–0.65 |
| gold links | порог цвета есть | `GOLD_LINK` | UNKNOWN live как отдельный путь | F85 кликал blue |
| inventory contents | нет | — | — | только occupancy слота |
| quest state | нет | — | — | |
| quest counters | нет | — | — | |
| minimap | слот `radar` в JSON | координаты есть | occupancy не доказана | не карта |
| player position | нет live | sim `StepInfo.agent_xy` | sim only | |
| world coordinates | нет live | — | — | |
| orientation / yaw | попытка KLT/coarse | `calibration/klt_yaw.py` | F73–F79 | профиль не канон; H18: KLT dx≈0 ≠ стоит |
| optical flow | да | `NavigationEncoder`, `vision/flow.py` | F61–F72 | часто низкий; duplicate кадры |
| stuck detection | код энкодера | `stuck_detected` в live-motion JSON | live: везде false | не закрывает H17 |
| OCR | **нет** | — | — | |
| NPC text | **нет** | — | — | |
| quest text | **нет** | — | — | |
| window type | частично | `WindowManager.is_slot_occupied` rim/std | F86 на старом парке | трава давала FP до rim+body-std |
| universal UI detector | **нет** | слоты + HUD ROI | — | |
| F1–F3 ready | да | `slot_f*_ready` | F47 офлайн | затемнённый слот = not ready |
| chat log | **нет** | — | — | чат только как ввод `/target` |

Фиксированные эвристики: HUD norm_rect в `parallels_l2.json`; диалог `LEFT_PANEL`; клик разговора `(0.50, 0.48)`; слоты guest px.

---

# 7. World State / Memory

**Централизованной модели мира нет.** Поиск `WorldState` / `IN_WORLD` / `QUEST_` / persistent quest memory в `src/` — пусто.

Что есть вместо этого:

| Механизм | Где | Кто обновляет | Жизнь | Слой |
|---|---|---|---|---|
| `phase: str` (`idle/scan/roam/combat/loot`) | локальная переменная `run_integrated_spot` | сам зонд | один CLI-процесс | live combat |
| `payload: dict` | каждый live probe | тот же процесс | до записи JSON | live |
| `HUDParseResult` | на кадр | `HUDParser.parse` | один кадр (+ мост помнит last HP) | perception |
| `VisionTelemetryBridge` | last self/target HP, `_defeat_emitted` | `publish` | процесс зонда | perception |
| `TelemetryHub` | очередь событий | bridge / sim | процесс | mixed |
| `ShortTermMemory` | `BaselineController` | recovery на nav-sim | эпизод sim | OBSOLETE-FOR-LIVE |
| `Circuit._last_obs` | предыдущий Observation | `Circuit.step` | эпизод Circuit | Circuit mock |
| experiment store | JSONL сессии | Circuit recorder | диск | не игровой мир |
| `WindowManager` стек модалок | `ui_manager.py` | `open_modal` / Escape | процесс layout-slots | UI, не мир |

Состояний вида `IN_WORLD / NPC_DIALOG / QUEST_DIALOG / COMBAT` как enum **нет**.  
Представления текущей задачи / прогресса квеста **нет**.  
Recovery state live = `aborted` + Escape, не политика.  
Persistent memory между запусками CLI для персонажа **нет**.

---

# 8. Action / Skill primitives

Семантика — не CLI. `GameAction` в `io/actions.py`. Live зонды шлют их напрямую, минуя `IntentDecoder` (decoder — dry-run/sim).

| Skill | Implementation | Inputs | Completion condition | Failure detection | Live tested |
|---|---|---|---|---|---|
| press/hold key | `HoldKey` + CGEvent | key, duration_ms≤500 в S4 | keyUp | focus_lost, F12, watchdog | да, F43+ |
| short walk pulse | `HoldKey("w")` 450–500 мс | ms | time | H17 риск если ≥8 с непрерывно | да, F69–F72, F82 |
| rotate camera (arrow) | `HoldKey` left/right 450 мс | direction | time | yaw не измерен каноном | да, F55, F79, F82 roam |
| RMB drag yaw | `CameraRotate` / mouse drag | dx px | coarse/KLT | часто dx=0 (H18) | калибровка, не бой |
| target next | `SkillActivate` F1 | — | `target_locked` | scan timeout / roam_limit | F49, F82 |
| target by name | `target_by_name` | printable name ≤48 | HUD lock | `chat_target_failed` | F85 |
| attack | F2 в бою (`HOTBAR`) | — | HP drop / dead | combat_timeout 25 с, no-damage 8 с | F51–F53, F82 |
| approach (named NPC) | F2 после `/target` | — | dialog HTML или timeout | F83: лок без окна | F85; F83 fail |
| loot | F3 ×3 | — | time gaps; инвентарь не читают | нет проверки лута | F52, F82 |
| talk click | `GroundClick` 0.50/0.48 | norm xy | `is_dialog_open` | `dialog_timeout` | F85 |
| click HTML link | `GroundClick` центр bbox | px from parser | клик ушёл; текст не читают | `no_link` | F85 |
| close window | Escape | — | `is_dialog_open` false / slot free | F86 escape | F85, F86 |
| heal | F4 | — | — | **запрещён** в NPC; spot `no_heal=True` | не live |
| roam | стрелка + w pulses | counters | F1 lock | `roam_limit` 15 | F82 |
| peel / L1 unjam | стрелки 350 мс | flow static | resume combat | F82: 0 срабатываний | код есть, LIVE слабо |
| u-turn | 2 arrow + 3 walk | roam count | time | — | F82: 2 |
| aggro interrupt | drop self HP vs mean | window 5 | retarget | F82: 2 | да |
| Tab inventory | `HoldKey("tab")` | — | slot occupied | `reset_failed` на траве | F86 old park |
| type chat | `type_text` 25 мс/сим | ASCII | Enter | focus/F12 | F85 |
| emergency stop | `EmergencyStop` / F12 | — | release_all | — | unit + F42 watchdog |

**Reusable skills vs сценарий.** Настоящих библиотечных skills с контрактом `pre/post/fail` нет. Есть общие `_send` / `_hold_key_ms` / `_tap_escape`. Остальное зашито в один probe. F2 в бою = Attack, в NPC = approach (ADR-0074) — одно имя, разная семантика.

---

# 9. Combat

**Основной файл:** `src/l2_brain/live/spot_loop.py`  
**Entry:** `run_integrated_spot` (~строка 135), CLI `s4-integrated-spot`  
**Предшественник режимов:** `live/s4_probe.py` `run_s4_probe` (clean-target, engage-any, kill-and-loot, multi-kill≤3, verify-search, roam series)

**FSM:** строковая `phase`, не enum:

1. `idle` → settle  
2. `scan` — до 2× F1 за 1.2 с  
3. `roam` — 4 пульса `w` 450 мс + стрелка; после 3 неудач u-turn; лимит 15  
4. `combat` — F2, пока цель жива, ≤25 с; agro если своё HP упало  
5. `loot` — F3×3 с паузами  
6. повтор до `kills`≤10 или abort

**Начало боя:** `target_locked` и HP≥`ENGAGE_HP_MIN` (импорт из s4_probe).  
**Target acquisition:** F1 = `/targetnext` (профиль). Не клик по силуэту.  
**Атака:** F2.  
**Kill:** `target_dead` или vanish HP≤0.08 → `EntityDefeated`.  
**Loot:** F3, инвентарь не проверяют.  
**HP safety:** `SELF_HP_MIN=0.30` (не хил); abort `SELF_HP_ABORT=0.10`. F80 abort `self_hp_low`.  
**Healing:** выключен, `heal_sent=false`.  
**Movement:** только короткие импульсы; `assert WALK_MS <= 800` и `<= SEARCH_HOLD_MAX_MS` (500).  
**Camera:** клавиши стрелок, не RMB в бою.  
**Recovery:** Escape на combat_timeout; общего planner recovery нет.  
**Stop:** kill cap, roam_limit, self_hp_low, focus, F12, CaptureError.

**L1 в бою:** не Frozen. На стабильной серии F82 **не срабатывал**. Стабилизация 10/10 как раз при L1=0 (ADR-0070).

**Последний live evidence F82** (`docs/evidence/live-s4/spot-series-10-stable.json`):

- `ok=true`, `total_kills=10`, `kills_completed=10`, `timeout_s=null`, `aborted=null`
- `elapsed_time_sec≈150.035`, `avg_combat_duration_sec≈3.349`
- `roam_cycles=14`, `l1_triggers=0`, `aggro_triggers=2`, `u_turns=2`, `stuck_keys=0`
- `no_heal=true`, `farm=false`
- window_id 16372, target_pid 68342

**Не проверено live:** ночь/другая зона, другой моб, хил, группа, death персонажа, полный инвентарь, смена UI layout, бой + диалог в одной сессии, Circuit+HID.

---

# 10. NPC / Dialog / Quest

Код: `live/npc_dialog_probe.py`, `io/chat_commander.py`, `vision/dialog_parser.py`.  
Evidence: F83 fail; F84 нет; F85 success.

| Шаг | Статус | Код / evidence |
|---|---|---|
| target NPC | PARTIAL | имя заранее; `/target` F85. F5 без чата: лок без окна F83 |
| approach NPC | PARTIAL | F2 hold 40 мс + ждать 2 с; нет проверки дистанции |
| interact | PARTIAL | ЛКМ (0.50, 0.48) на кадр, не на bbox модели |
| opening dialog | PARTIAL | работает на Guide F85; не universal |
| detecting dialog | PARTIAL | тёмная панель + ≥2 blue links |
| detecting links/buttons | PARTIAL | цветные bbox, без подписи |
| clicking dialog entries | PARTIAL | все найденные синие сверху вниз, max 12 |
| closing dialog | PARTIAL | Escape после каждого пункта F85 |
| which dialog/menu | NOT IMPLEMENTED | нет классификации окон по тексту |
| reading text | NOT IMPLEMENTED | OCR нет |
| accepting quest | NOT IMPLEMENTED | клики не семантические |
| quest accepted | NOT IMPLEMENTED | |
| quest objective | NOT IMPLEMENTED | |
| quest counter | NOT IMPLEMENTED | |
| completion | NOT IMPLEMENTED | |
| return to NPC | NOT IMPLEMENTED | нет навигации назад |
| complete quest | NOT IMPLEMENTED | |

## Сценарий Newbie Guide (F85), по шагам

Источник: `run_npc_dialog_probe(..., via_chat=True, npc_name="Newbie Guide")` + `npc-menu-crawl.json`.

1. Dual flags, фокус Parallels, SCK start (timeout 4 с, рестарты до 24).  
2. `_ensure_dialog_closed` — Escape, пока HTML открыт. `dialog_was_closed=true`.  
3. `target_by_name`: Escape, Enter, type `/target Newbie Guide` (25 мс/сим), Enter; ждать `target_locked`.  
4. F2 (`SkillActivate` slot=2) — подбег. `FORBIDDEN_SLOTS={F1,F3,F4}`; F2 как слот таргета запрещён.  
5. Пауза `APPROACH_S=2.0`.  
6. ЛКМ в норме кадра (0.50, 0.48) → JSON `talk_click_xy=[1028,619]` на том окне.  
7. Ждать HTML `TALK_WAIT_S=1.5`. `dialog_detected=true`, `reason=html_links`, confidence 1.0.  
8. `extract_menu_items` — 6 центров. `false_target_markers=0` (нет ссылок правее x/width>0.42).  
9. Для каждого: клик bbox → пауза 0.60 → Escape → 0.40. 6/6.  
10. Не читает пункты, не принимает квест, не проверяет журнал.  
11. 36.67 с, `sck_crashes=7` (захват падал и поднимался), farm=false.

Имена пунктов меню в репозитории как распознанный текст **отсутствуют**.

---

# 11. UI layout

Источник истины для чисел: `config/window_profiles/parallels_l2.json` (прочитан 2026-09-18).

| Система | Значение в конфиге/коде | Тип |
|---|---|---|
| Профиль | `parallels_l2`, title `Windows 11`, owner `Parallels Desktop` | config |
| Host window expected | **2056×1290** | config `expected_size` |
| SCK capture | **4112×2580** | config `capture_size` (Retina scale 2) |
| Guest grid (слоты) | **2560×1600** | config `layout_slots.ref_window` (ADR-0077) |
| Overlay | масштабирует guest→host окно | `LayoutSlots.box_on_frame`, Swift overlay |
| HUD ROI | norm_rect, мерены 2026-09-17 на кадре 4112×2580 | calibration-based, один layout |
| Dialog LEFT_PANEL | `NormRect(0.05, 0.20, 0.37, 0.65)` | hardcoded |
| Talk click | `(0.50, 0.48)` | hardcoded |
| Slot A (dialog) | `[60,140,400,520]` guest | config, цель парковки |
| Slot B (modal) | `[2140,140,360,480]` guest | config цели; **не** F86 |
| F86 Slot B (evidence) | `[1592,650,342,307]` | live-proven old park |
| Hotbar slot | `[380,1564,520,32]` guest | config, не occupancy-live |
| Radar slot | `[2380,10,170,170]` | config only |
| Motion block | числа yaw/step есть, `peak_reliable=false`, `q5_gt_yaw=false` | **не канон** |

**Hardcoded:** диалог ROI, talk click, цвет HP/MP/CP/blue links, пороги occupancy (rim luma≥80, body std≥20).  
**Config:** HUD, sizes, slots, motion (motion не закрыт).  
**Calibration-based:** HUD F45–F47; motion попытки F56–F79.  
**Оператор руками:** видимое окно на столе, разрешение гостя, парковка окон в слоты, dual flags, PID, хоткеи F1–F3, remap F2 для гида.  
**Drift:** `window_id` не стабилен (проф. note); Retina 2×; host 2056 vs guest 2560; перетаскивание HUD; скрытый/off-screen стол не источник; смена 2560 без повторного F86.

Масштаб overlay: `sx = frame_w / ref_window_w`. Для SCK 4112 относительно 2560 sx≈1.606. Для host 2056 / 2560 ≈0.803. Путаница host/SCK/guest — основной риск кликов.

---

# 12. Navigation

## nav-sim

EXISTS + UNIT-TESTED + LIVE не применимо.

- Поза агента и цель есть в `StepInfo` / GT, **не** в Observation.  
- Каталог сцен: open_goal, dead_end, u_trap, long_fence, corridor, … (`sim/scenarios.py`, `sim/config.py` catalog).  
- `BaselineController` 52/60 Frozen.  
- Obstacle: Peel/Slide/Probe/hook — эвристики контроллера, AABB стенда.  
- `go_to` в метрах стенда = успех эпизода «дойти до цели», не API агента.  
- H15 отклонена, H16 не подтверждена.

## live navigation

| Вопрос | Ответ |
|---|---|
| Позиция игрока | нет |
| World coordinates | нет |
| Карта / локальная карта | нет |
| Minimap perception | слот есть, не читается как карта |
| Compass / orientation | нет канона |
| Yaw измеряется? | попытки KLT/coarse; профиль не принят (F79 `\|dx\|<50`) |
| Distance | нет |
| `go_to(X,Y)` | **нет** |
| `go_to_visual_target` | нет; F2 approach без измерения дистанции |
| Obstacle avoidance | только peel в combat при static flow; на F82 0 |
| Stuck recovery | encoder flag не срабатывал live; roam/u-turn эмпирические |
| Roam | да, в spot FSM |
| Memory navigation | нет live |
| Frozen 52/60 live | **нет** |

## Q5 / H17

**Q5 открыт** (`docs/open-questions.md`): семантика камеры и метры unknown. F79: один тап стрелки ≈40 px, 146/113 инлаеров, ratio≥0.70; профиль не писали. Мышь→px не константа (F78). GT yaw нет.

**H17 открыта:** непрерывный `w`≥8 с дважды совпал со срывом сессии (F65/F66/F68). Позже короткие и один 8 с (F72) без срыва. «Всегда рвёт» не доказано. ADR-0064: не слать непрерывный `w`≥8 с; импульсы ≤800 мс (в S4 фактически ≤500).

Код: `calibration/*`, `bench/live_motion_probe.py`, CLI `calibrate-motion`, `live-motion`. Evidence: `docs/evidence/live-s4/calib-loop/`, `l1-flow-validation*.json`, `docs/evidence/h17-report.md`.

---

# 13. Controllers / AI

| Controller | Type | Input | Output | Training | Used where | Live? |
|---|---|---|---|---|---|---|
| `ReactiveController` | пороги blob | `types.Observation` | `types.Action` | нет | `evaluate` SyntheticEnv | нет |
| `RecurrentController` | short hidden | то же | то же | нет | evaluate | нет |
| `SpikingController` (`controllers/snn.py`) | LIF на признаках стенда | то же | то же | нет | evaluate | нет |
| `FeatureController` | gain на EncodedVisual | `contracts.Observation` | `MotorIntent` | нет | Circuit mock/SCK-no-HID | нет |
| `BaselineController` `baseline_v1` | эвристика | contracts.Obs + nav | MotorIntent | нет | baseline-eval, bench | нет |
| `baseline_memory_v1` | то же + STM | то же | то же | нет | Frozen 52/60 | **нет** |
| `GRUController` `gru_v1` | NumPy GRU H=16 | 6 признаков nav-sim | MotorIntent | опц. ES | bench/suite | нет |
| `SNNController` `snn_v1` | LIF CPU Braitenberg | то же | MotorIntent | опц. R-STDP | bench/learn; **spot_agent L1** | нет |
| `MaleCNSController` | синтет. граф 208/616 | то же | MotorIntent | нет | malecns-eval | нет |
| `TacticalCombatController` | FSM | Obs + TelemetryHub | MotorIntent/GameAction dry | нет | combat-dry-run | нет |
| `SpotAutonomousAgent` | FSM + snn_v1 | то же | dry GameAction | нет | CLI `spot-loop` | нет |
| Live spot FSM | script | HUD + flow scalar | GameAction HID | нет | `s4-integrated-spot` | **да, это управляет** |
| Live NPC script | script | HUD + dialog bbox | GameAction HID | нет | `s4-npc-dialog` | **да, в том зонде** |
| Live layout script | script | occupancy | Tab/Escape | нет | `layout-slots` | да, узко |

**Код существует ≠ управляет персонажем.** Сейчас персонажем управляет только `CGEventInputBackend`, вызываемый из `live/*.py` сценариев.

---

# 14. MaleCNS / SNN

Проверено: `control/malecns/loader.py` `load_subgraph()` в этом venv → `n=208`, `e=616`, `source=synthetic_extract`, `biological_claim=False`.

| Вопрос | Факт |
|---|---|
| Что загружено | `synthetic_visuomotor_extract_v0` v0.1.0 |
| FlyEM / полный коннектом | **нет** (`full_connectome_loaded=False`) |
| Neurons / synapses | 208 узлов, 616 рёбер (F37) |
| Что исполняется | `MaleCNSController` на nav-sim `open_goal` и suite |
| Inputs | те же 6 визуальных признаков, что SNN, не пиксели игры |
| Outputs | `MotorIntent` |
| Learning | нет на этом графе; R-STDP живёт в `control/snn/plasticity.py` на другом контроллере |
| Live | **нет** |
| H | H11 не принята; H3/H4 не начаты; H6 отклонена |
| Результаты | F37: snn 61, bio 178, shuffle 191, ER timeout 200 на одном эпизоде. F38 suite: malecns_bio 4/5, stuck на `single_obstacle` |
| Чтобы стал реальным controller | отображение кадр→вход и спайки→live GameAction; прогон H3/H4/H11; сейчас запрещено утверждать «MaleCNS играет» |

Биологическая лексика ≠ качество управления (правило проекта, F5/F6).

SNN отдельно: `snn_core_v1` CPU, infer p50≈1.6–1.7 мс на open_goal (F30–F32). Не Frozen 60. Не live.

---

# 15. Evidence / experiments

Источники: `docs/assumptions.md`, `docs/decisions.md`, `docs/status.md`, `docs/roadmap.md`, `docs/vision.md`, JSON под `docs/evidence/`.

| ID | Claim | Status | Evidence | Still valid? |
|---|---|---|---|---|
| H1 | reactive ≥0.80 на 20× open_field | открыта | дым F9 8 эп. ≠ 20 | да, не закрыта |
| H2 | recurrent − reactive ≥0.25 на occluded×20 | открыта | нет канона 20 | да |
| H3 | SNN лучше recurrent на occluded | не начата | bench ≠ evaluate | да |
| H4 | SNN не хуже reactive на поле | не начата | то же | да |
| H5 | infer p95 < 0.20 loop p95 | формально не закрыта 20 эп. | принцип в отчётах | UNKNOWN как цифра 20 эп. |
| H6 | MPS чинит тик | **отклонена** | F36 | да |
| H7 | SCK полезен | **принята** | F40 | да, на **видимом** окне |
| H8 | p95 observe+infer+act ≤100 мс | **принята** | F57 2.19 мс n=100 | да; observe=очередь, не фотон; encode вне формулы |
| H9 | short memory хватает v1 | открыта | — | да |
| H10 | ранг стенда = ранг live | открыта | live бой ≠ таблица 3 контроллеров | да |
| H11 | MaleCNS полезная политика | не принята | F37 | да |
| H12 | «не застревает» | обещание запрещено | — | держать |
| H13 | v1 без карты | держится на стенде | нет waypoints в evaluate | live спот тоже без карты, но это не H1 |
| H14 | P/R≥0.60 на 100 размеченных кадрах | открыта | HUD ≠ размеченный детектор | да |
| H15 | encoder +15% vs blob | **отклонена** | F17 Δ=+0.033 | да |
| H16 | память чинит тупики | не подтверждена | F15 10/10=10/10 | да |
| H17 | w≥8 с рвёт Interlude | **открыта** | F65/F66/F68 vs F72 | да |
| H18 | KLT dx≈0 ≠ камера стоит | **принята** | F75 | да |
| F7 | «живой клиент и HID закрыты» | **STALE-DOC** | F49+ hid_sent=true | нет как утверждение |
| F29 | L1 frozen 52/60; «snn пакет ещё не создан» | частично STALE | пакет `control/snn` **есть** | freeze 52/60 да; фраза про пакет нет |
| F40 | H7 30 с окно 13745 | принят | JSON live-s2 | да для видимого окна |
| F57 | H8 | принят | h8-latency-report.json | да |
| F79 | Q5 не закрыт; arrow ≈40 px | открыт Q5 | calib-loop | да |
| F80 | 7/10 HP abort | факт | integrated-spot-series-10.json | да |
| F81 | 5/5 | факт | spot-aggro-validation.json | да |
| F82 | 10/10 150 с | факт | spot-series-10-stable.json | да, тот layout/хоткеи |
| F83 | F5 лок, диалога нет | факт | npc-dialog-probe.json | да |
| F84 | — | **нет факта** | прогон не стартовал | gap |
| F85 | Guide 6/6 | факт | npc-menu-crawl.json | да, тот UI |
| F86 | Tab/Escape | факт на старых px слота Б | layout-slots-validation.json | **частично**: координаты слота Б в JSON ≠ текущий профиль |

ADR, влияющие на следующий этап: 0030 (freeze L1), 0038 (не полный MaleCNS), 0043 (dual flag), 0049 (S4), 0064 (H17 pulses), 0067 (Q5), 0068 (live L1 ≠ Frozen), 0073–0077 (чат, F2, слоты, overlay, 2560).

Roadmap S4 «не делаем квесты/диалоги» — **расходится** с наличием `s4-npc-dialog` (операторская ветка после открытия S4). Vision.md «живой клиент не часть контура» — **STALE** относительно зондов; формально Circuit+LiveEnv всё ещё не контур.

---

# 16. Tests

Прогон этого аудита, HID не слался:

```text
cd /Users/apple/Desktop/L2_brain
.venv/bin/python -m pytest tests --tb=no -q
```

**Результат:** все собранные тесты зелёные; в выводе **336** точек, **0** failed, skip/xfail в summary не было. 1 warning: `test_mps_compatibility` / sparse MPS.  
Файлов `tests/test_*.py`: **44**. Строк тестов (wc): 6484.

| Область | Файлы | Покрытие |
|---|---|---|
| Circuit | `test_circuit.py` | mock loop |
| nav-sim / baseline | `test_baseline.py`, `test_sim_env.py`, `test_recovery_scenes.py`, `test_observability.py` | сильный |
| vision encoder | `test_vision.py` | сильный на синтетике |
| HUD | `test_hud_parser.py`, `test_calibrate_hud.py` | unit + PNG |
| dialog | `test_npc_dialog.py` | unit эвристик, не live Guide |
| layout | `test_layout_slots.py` | scale/occupancy fixtures |
| CGEvent | `test_cgevent_backend.py` | RecordingPoster, dual flags |
| chat | `test_chat_commander.py` | sanitize/sequence без HID |
| spot live FSM | `test_spot_loop.py` | agro/L1 predicates, не 150 с игра |
| s4 | `test_s4_probe.py` | режимы/лимиты |
| live blocked | `test_live_blocked.py` | заглушки Env/Actuator |
| SNN/GRU/MaleCNS | `test_snn_dynamics.py`, `test_gru_controller.py`, `test_malecns.py`, `test_plasticity.py` | численные |
| input dry | `test_input_backend.py` | hid_sent=false |

**Integration:** Circuit mock, sim episodes — да. Live HID integration — нет (намеренно).  
**FSM:** предикаты spot — да; полный live FSM — нет.  
**Critical live почти без автотестов:** реальный SCK «no frame», off-screen окно, координаты клика 0.50/0.48 на живом масштабе, семантика пунктов меню, лут в сумке, H17, парковка 2560.

---

# 17. CLI

| Command | Purpose | Simulation/Live | Current status |
|---|---|---|---|
| `mock` / `record` / `replay` / `inspect` | Circuit сессии | sim/mock | рабочий |
| `eval` | reactive/recurrent/snn | sim | рабочий; не H1-канон 20 |
| `doctor` | окружение | — | рабочий |
| `sim-eval` | nav-sim короткий | sim | рабочий |
| `baseline-eval` | Frozen каталог | sim | рабочий; не ретюнить |
| `bench` / `suite` / `learn` / `malecns-eval` | мини-сравнения | sim | рабочий, не 52/60 |
| `capture` | SCK list/permission/record | capture | рабочий |
| `vision bench/diag` | encoder | sim | рабочий |
| `input-dry-run` | MotorIntent лог | mock | рабочий |
| `focus-bench` | NSWorkspace | host | рабочий, без HID |
| `calibrate-hud` | ROI overlay | capture / PNG | рабочий |
| `calibrate-motion` | yaw/step | live opt | Q5 не закрыт |
| `live-motion` | непрерывный w+flow | live | H17 риск; ADR-0064 |
| `bench-h8` | латентность | live idle | F57 |
| `input-probe` | Notepad | live не игра | F43 |
| `combat-dry-run` | dummy бой | sim | F35 |
| `spot-loop` | dummy спот | sim | F39; **не** live spot |
| `profile` | стадии + MPS audit | sim | F36 |
| `s4-probe` | узкие боевые режимы | live | F49–F55; использовался в линейке S4 |
| `s4-integrated-spot` | серия фрагов | live | **F80–F82** последние боевые |
| `s4-npc-dialog` | NPC | live | **F83, F85**; `--via-chat` |
| `layout-grid` | PNG рамки | capture | без HID |
| `layout-overlay` | живые рамки | host overlay | ход 86b, без HID |
| `layout-slots` | Tab/Escape | live | **F86**; координаты слота Б устарели относительно профиля |

Последние live experiments фактически: `s4-integrated-spot`, `s4-npc-dialog --via-chat`, `layout-slots`, `layout-overlay`, батарея `calibrate-motion` / `live-motion` (Q5/H17).

---

# 18. Safety layer

Реализация: `io/cgevent_backend.py`, `io/safety.py` `InputWatchdog`, `io/focus.py`, `io/profile.py`, CLI флаги.

| Механизм | Где | Поведение |
|---|---|---|
| Dual flags | `CGEventInputBackend.__init__` | без `live_confirmed` и `live_danger_confirmed` → `LiveInputNotConfirmed` |
| CLI | `--live --danger-confirmed` | зонды не создают backend иначе |
| PID only | `target_pid >= 1`, `CGEventPostToPid` | не post в систему целиком на клавишах; мышь может hid_also |
| Focus | `is_allowed_frontmost(PARALLELS_BUNDLES)` | иначе `release_all`, `focus_lost` |
| F12 | `GameInputProfile.kill_switch="F12"` | `_kill_switch_down` → emergency |
| Watchdog | 250 мс без heartbeat при удержании | keyUp, `watchdog_timeout` |
| Max hold S4 | `SEARCH_HOLD_MAX_MS=500`; asserts ≤800 | ADR-0064 |
| Press default | `press_duration_ms=40` | |
| Mock/live split | `MockInputBackend`, `DryRunInputBackend`, `RecordingPoster` | |
| LiveEnv block | `env/live.py`, `actuators/live.py` | всё ещё NotImplemented — **не** путь зондов |
| Farm cap | kill≤10, multi-kill≤3 | код, не античит |
| Forbidden slots NPC | F1/F3/F4 | не слать как talk |

**Обходы общего слоя (из кода, не эксплойт):**

- Live зонды импортируют CGEvent напрямую; кто соберёт backend с флагами и RecordingPoster — тесты.  
- `type_text` и mouse path проверяют F12/focus, но это отдельные методы.  
- Overlay Swift не HID, но лежит поверх игры.  
- `prlctl` / гостевой ввод в этом пакете live-путём не используется (architecture запрещает во время live).  
- Заглушки `LiveClientEnv` можно обойти просто не вызывая их — так и сделано: live идёт мимо «официального» Env.  
- Длинный `w` можно запросить через `live-motion --hold-ms` (операторский риск H17), не через Circuit.

Античит/скрытие/инъекции — запрещены и не реализованы (ADR-0002).

---

# 19. Known bugs / instability

Только то, что зафиксировано в status/evidence/коде как повторяющееся.

| Problem | Frequency | Impact | Workaround | Root cause known? |
|---|---|---|---|---|
| SCK `no frame` / helper crash | F85: `sck_crashes=7` за 37 с; встречалось в зондах | abort или рестарт grabber | timeout 4 с + retry в grabber; рестарт helper | частично: очередь/окно |
| Окно off-screen / `on_screen=false` | F84 прогон не стартовал; overlay KeyError `shown` | нет кадра, нет live | вернуть окно на стол; скрытый стол запрещён | да: не тот Space / minimize |
| Непрерывный `w` ≥8 с | ≥2 срыва (F68) | клиент «мёртвый» до релога | импульсы ≤500–800 мс | H17 открыта; сокет не снимали |
| Stuck keys | на F82 = 0 | высокий если watchdog не успел | watchdog 250 мс, F12 | механизм есть |
| UI coordinate drift | после 2560 и перетаскивания | мимо слота/HUD | оператор + overlay; не автокалибровка | да: 3 системы координат |
| Dialog fail без клика по модели | F83 | лок есть, окна нет | F2+LMB F85 | да: F5 недостаточно |
| Focus не Parallels | любой live | hid не уходит | клик по окну | да |
| Inconsistent scaling host/guest/SCK | постоянно | клик/слот мимо | ручная сетка 2560, overlay | да, не решено автоматически |
| False HUD / grass occupancy | hod 86 первый abort | ложный occupied | rim+std; не сажать слот на траву | частично |
| KLT yaw alias | F74–F75 | ложный «не повернулись» | coarse_shift + глаза оператора | да, H18 |
| `duplicate` кадры SCK | F61–F67 часто | нулевой flow | copy T0/T1, settle 300 мс (ADR-0066) | буфер без копии |
| F2 dual meaning | архитектурно | атака vs подбег | ADR-0074, разные CLI | да, путаница имён |
| Layout-slots evidence vs config | после 86c | F86 не валидирует текущий слот Б | нужен новый прогон | да, координаты разъехались |

---

# 20. Architecture debt

Проверено по коду, не как вкусовщина.

| Разрыв | Есть? | Факт |
|---|---|---|
| Circuit и live probes раздельно | **да** | нет builder SCK+CGEvent; `Circuit.run` не live |
| Duplicate state machines | **да** | `spot_agent.SpotPhase` vs `spot_loop.phase`; `tactical.CombatPhase` vs s4 режимы |
| Hardcoded coordinates | **да** | LEFT_PANEL, 0.50/0.48, HUD norm, guest slots |
| Multiple Observation/Action | **да** | `types.*` vs `contracts.*` vs `GameAction` |
| Duplicated capture | **частично** | один `SCKFrameSource`, но обёртки `SCKGrabber` vs Circuit frames vs CLI capture |
| Duplicated safety | **частично** | общий CGEvent слой; зонды дублируют focus/abort |
| Sim ≠ live abstractions | **да** | pose/GT vs пиксели; `types.Action` vs клавиши; F2 разный |
| Контроллеры не взаимозаменяемы live | **да** | live не принимает `CircuitController` |
| Perception coupled to scenario | **да** | Guide crawl, HUD Interlude, слоты Talking Island |
| Docs vs code | **да** | README «клиент не подключён»; `safety.py` «закрыт до S4»; F7; architecture L3=ход 83; F29 «snn не создан»; vision.md п.6 |
| Нет World State | **да** | §7 |
| Нет skill interface | **да** | §8 |
| Git не хранит проект | **да** | весь `L2_brain` untracked на Desktop |

Не найдено как отдельный второй полный HID-стек. LiveHIDActuator мёртв, CGEvent — единственный живой путь.

---

# 21. Что мешает сделать "One Quest"

Критерий (задан, не реализован): персонаж сам проходит один простой квест от первого разговора до сдачи, под оператором, только зрение + легальный host input, **без** полного сценария координат.

| # | Способность | Статус | Комментарий |
|---|---|---|---|
| 1 | найти нужного NPC | частично | только если имя известно → `/target`; визуальный поиск нет |
| 2 | подойти | частично | F2 после лока; дистанция/препятствия unknown |
| 3 | открыть диалог | частично | F2+LMB центр; не любой NPC (F83) |
| 4 | диалог открылся | частично | HTML-эвристика, не все типы окон |
| 5 | понять варианты | **отсутствует** | нет OCR/семантики |
| 6 | выбрать quest option | **отсутствует** | F85 кликает **все** синие |
| 7 | acceptance | **отсутствует** | |
| 8 | понять objective | **отсутствует** | |
| 9 | выйти из деревни | **отсутствует** | нет позы/карты/go_to; Q5 открыт |
| 10 | найти quest target | **отсутствует** | F1 targetnext — любой моб спота, не квест |
| 11 | убить target | частично | спот 10/10 есть; привязки к квесту нет |
| 12 | progress | **отсутствует** | |
| 13 | completion condition | **отсутствует** | |
| 14 | вернуться к NPC | **отсутствует** | навигация назад нет |
| 15 | снова dialog | частично | код `reopen_dialog` в том же зонде; не после вылазки |
| 16 | выбрать completion | **отсутствует** | |
| 17 | reward/completion | **отсутствует** | |
| 18 | recovery на любом этапе | частично | Escape, abort, grabber restart; нет политики «с какого шага продолжить» |

Уже есть: легальный кадр+HID, HUD HP/lock, один путь к Guide, клик синих ссылок, узкий бой, Escape.

Частично: подход, детектор HTML, слоты UI, roam.

Отсутствует: понимание квеста, навигация между точками, идентификация цели квеста, прогресс, сдача, общий state.

Неизвестно: какой квест первый; стабильны ли HTML после принятия; нужен ли radar; можно ли OCR; хоткеи на других персонажах.

**Без заранее записанных координат** пункт 9–14 сейчас невыполним: нет метрики пространства.

---

# 22. Что является следующим настоящим архитектурным bottleneck

Не «слабый SNN» и не отсутствие планировщика на пустом месте.

Факты:

1. Live уже исполняет **две** длинные цепочки (бой ~150 с, меню ~37 с), но каждая хранит прогресс в локальном `payload`/`phase`. Склеить «поговорил → пошёл убить → вернулся» некуда: **нет session/world/task state**.  
2. Действия не skills: нет completion/fail, F2 перегружен, лут не проверяется. Планировщик над этим будет кликать вслепую.  
3. Perception не даёт objective/text/pose. Даже идеальный planner не узнает «принеси 10 зубов».  
4. Q5: нельзя честно `go_to` из деревни к мобам и назад. Roam спота — локальный поиск, не маршрут квеста.  
5. Circuit integration — отдельный долг; он **не** блокирует склейку зондов (зонды уже ходят в CGEvent). Склеивать через Circuit сейчас значило бы сначала написать отсутствующий live backend.  
6. Frozen L1 / MaleCNS не участвуют в live и не являются текущим ограничителем острова.

**Главный bottleneck:** отсутствие **явного состояния сессии + контракта навыка** при одновременно **дырявом восприятии задачи** (нет текста/прогресса) и **отсутствии метрической навигации**. Из трёх дыр склейка бой+диалог упирается сначала в state/skills (это уже проявилось: два CLI, F2 dual-use, F86 vs 2560). Выход из деревни упирается в Q5. Понимание квеста упирается в OCR/журнал — этого кода нет.

Если выбирать один ограничитель перехода «пробы → агент длинного горизонта»: **нет слоя World/Task state и reusable skills поверх существующих зондов**. Perception и navigation — следующие жёсткие стены на One Quest; planner без них преждевременен.

---

# 23. Минимальные возможные следующие milestones

Не реализация, только кандидаты. Не закрывают One Quest целиком.

### M1 — Единый live session state (без нового «мозга»)

**Доказать:** один процесс может переключать `SPOT | NPC_TALK | UI_RESET` с общим `payload` (HP, lock, dialog_open, last_abort) и одним CGEvent.  
**Компоненты:** новый тонкий оркестратор **или** расширение `live/` без Circuit; не трогать Frozen/`sim/`.  
**Зависимости:** текущие зонды.  
**Риск:** склеить скрипты в ещё больший скрипт; F2-семантика.  
**DONE:** один CLI, два уже доказанных навыка подряд (10 фрагов **или** Guide crawl + Escape), JSON с единым state dump; фарм нет.

### M2 — Повторная валидация слотов на 2560×1600

**Доказать:** occupancy Slot B `[2140,140,360,480]` после посадки оператором: free→Tab occupied→Escape free.  
**Компоненты:** профиль уже сменён; нужен live `layout-slots`, не правка эвристик «на всякий случай».  
**Зависимости:** оператор паркует окна; окно on-screen.  
**Риск:** drift масштаба SCK/host.  
**DONE:** новый JSON, SHA1, F86 не затирать; координаты в evidence = координаты профиля.

### M3 — Контракт skill: `TargetByName`, `OpenHtmlDialog`, `PulseWalk`

**Доказать:** три вызова с pre/post/fail, пригодные из двух сценариев.  
**Компоненты:** вынести из probe, не меняя HID safety.  
**Зависимости:** M1 желателен.  
**Риск:** форма без семантики квеста.  
**DONE:** unit + один live Guide open+close без обхода всех пунктов как «успех».

### M4 — Навигация без метров: «вид изменился после импульса»

**Доказать:** серия импульсов `w`/стрелка с критерием «кадр не duplicate / coarse dx знак»; стоп у стены по глазам+JSON, без 8 с hold.  
**Компоненты:** `calibrate-motion` / live-motion пороги; **не** писать фальшивый `go_to`.  
**Зависимости:** Q5 остаётся открытым; H17.  
**Риск:** принять KLT=0 за истину (H18).  
**DONE:** протокол импульсов + evidence «вышел из узкого двора» глазами оператора, без GT метров.

### M5 — Не делать сейчас как milestone архитектуры

Закрытие H1–H4 на 20 эп., подключение Frozen 52/60 в клиент, MaleCNS live, OCR-квест, Circuit+HID «чтобы было красиво» — каждое либо научный долг, либо запрещено правилами freeze, либо не имеет сенсора. Это развилки оператора (`docs/overview-2026-09-18.md`), не обязательный next step.

---

# 24. Ключевые исходники для следующего AI

```text
src/l2_brain/cli.py
Почему важен: все entrypoints.
Ключевые: main() ~18
Связан с: каждым live/sim модулем

src/l2_brain/live/spot_loop.py
Почему важен: фактический боевой агент.
Ключевые: run_integrated_spot(...) ~135; should_aggro_interrupt ~88; should_l1_unjam ~107
Связан с: s4_probe, HUDParser, CGEvent, NavigationEncoder (flow)

src/l2_brain/live/s4_probe.py
Почему важен: захват и примитивы HID live.
Ключевые: SCKGrabber ~140; run_s4_probe ~199; SEARCH_HOLD_MAX_MS=500; HOTBAR F1/F2/F3
Связан с: всеми live CLI

src/l2_brain/live/npc_dialog_probe.py
Почему важен: единственный NPC путь.
Ключевые: run_npc_dialog_probe(..., via_chat, npc_name) ~50; approach_and_talk ~302; crawl_menu ~345
Связан с: chat_commander, dialog_parser

src/l2_brain/io/cgevent_backend.py
Почему важен: единственный live актуатор.
Ключевые: __init__(target_pid, live_confirmed, live_danger_confirmed) ~166; send_action ~205; type_text ~226
Связан с: safety, focus, actions

src/l2_brain/io/chat_commander.py
Почему важен: /target.
Ключевые: target_by_name(...) ~26
Связан с: npc probe

src/l2_brain/io/actions.py
Почему важен: словарь действий.
Ключевые: GameAction union ~64
Связан с: decoder (sim) и live напрямую

src/l2_brain/vision/hud_parser.py
Почему важен: всё «зрение боя».
Ключевые: HUDParseResult ~73; HUDParser.parse
Связан с: telemetry.vision_bridge, spot, npc

src/l2_brain/vision/dialog_parser.py
Почему важен: диалог без OCR.
Ключевые: LEFT_PANEL; extract_menu_items ~40; is_dialog_open ~62; parse_dialog ~70
Связан с: npc_dialog_probe

src/l2_brain/vision/layout_slots.py
Почему важен: сетка 2560.
Ключевые: LayoutSlots.box_on_frame ~34
Связан с: ui_manager, overlay, layout_slots_probe

src/l2_brain/vision/ui_manager.py
Почему важен: occupancy.
Ключевые: WindowManager.is_slot_occupied; RIM_LUMA_MIN=80; BODY_STD_MIN=20
Связан с: layout-slots

src/l2_brain/vision/encoder.py
Почему важен: L1-признаки стенда и flow live.
Ключевые: NavigationEncoder.encode ~44
Связан с: Circuit, baseline, live-motion, spot flow

src/l2_brain/circuit/loop.py
Почему важен: показать, что единого контура с HID нет.
Ключевые: Circuit.step ~113; Circuit.run ~214
Связан с: capture/circuit.py MockInputBackend

src/l2_brain/capture/circuit.py
Почему важен: SCK без HID.
Ключевые: build_sck_circuit ~13
Связан с: Circuit

src/l2_brain/control/baseline.py
Почему важен: Frozen L1, не live.
Ключевые: BaselineController.step ~88
Связан с: sim, ADR-0030

src/l2_brain/control/spot_agent.py
Почему важен: не путать с live spot.
Ключевые: SpotAutonomousAgent; L1=snn_v1
Связан с: CLI spot-loop только sim

src/l2_brain/contracts.py
Почему важен: Observation/MotorIntent контура.
Ключевые: Observation ~98; MotorIntent ~120; PRIVILEGED_OBSERVATION_FIELDS
Связан с: encoder, Circuit, baseline

src/l2_brain/types.py
Почему важен: второй контракт стенда.
Ключевые: Observation, Action
Связан с: evaluate, controllers

config/window_profiles/parallels_l2.json
Почему важен: HUD, sizes, slots 2560, motion не-канон.
Связан с: все live

src/l2_brain/control/malecns/loader.py
Почему важен: что MaleCNS на самом деле синтетический.
Ключевые: EXTRACT_ID="synthetic_visuomotor_extract_v0"; Subgraph.biological_claim=False; load_subgraph()
Связан с: malecns-eval, F37, ADR-0038

src/l2_brain/io/safety.py
Почему важен: watchdog удержаний, не OS HID.
Ключевые: InputWatchdog (timeout 250 ms)
Связан с: CGEventInputBackend

src/l2_brain/env/live.py
Почему важен: официальный LiveClientEnv всё ещё NotImplementedError.
Ключевые: LiveClientEnv.reset/step
Связан с: test_live_blocked.py; НЕ путь зондов

docs/assumptions.md
Почему важен: канон F*/H*. F7 и часть F29 — STALE.
Связан с: decisions.md, status.md

docs/decisions.md
Почему важен: ADR-0030, 0043, 0064, 0068, 0073–0077.
Связан с: live probes

docs/evidence/live-s4/spot-series-10-stable.json
Почему важен: F82 10/10.
Связан с: spot_loop.py

docs/evidence/live-s4/npc-menu-crawl.json
Почему важен: F85 Guide 6/6.
Связан с: npc_dialog_probe.py

docs/evidence/live-s4/layout-slots-validation.json
Почему важен: F86; слот Б ≠ текущий профиль.
Связан с: parallels_l2.json layout_slots
```

### Critical snippets (без них схему легко перепутать)

`build_sck_circuit` намеренно без HID (`src/l2_brain/capture/circuit.py`):

```python
def build_sck_circuit(config: CircuitConfig, frames: SCKFrameSource) -> Circuit:
    return Circuit(
        ...
        controller=FeatureController(),
        backend=MockInputBackend(),
        ...
    )
```

Конструктор живого ввода (`src/l2_brain/io/cgevent_backend.py` ~166–181):

```python
def __init__(self, target_pid: int, live_confirmed: bool = False,
             *, live_danger_confirmed: bool = False, ...):
    if not live_confirmed or not live_danger_confirmed:
        raise LiveInputNotConfirmed(
            "CGEventInputBackend requires live_confirmed=True and live_danger_confirmed=True"
        )
```

Детектор диалога без OCR (`src/l2_brain/vision/dialog_parser.py` ~62–67):

```python
def is_dialog_open(frame: np.ndarray) -> bool:
    items = extract_menu_items(rgb)
    return _left_panel_dark(rgb) and len(items) >= HTML_ITEMS_MIN  # 2
```

STALE блок «живой клиент закрыт» всё ещё в `src/l2_brain/safety.py`, но S4-зонды его не вызывают.

---

# 25. Questions for next architect

На эти вопросы репозиторий **не** даёт достоверного ответа. Не заполнять догадкой.

1. Какой конкретный квест будет первым One Quest (если вообще квест, а не ещё один зонд)?
2. Нужно ли generalize NPC или достаточно одного Guide / одного квестодателя?
3. Допустим ли OCR (Tesseract/Vision) или только пиксельные эвристики?
4. Допустима ли ручная калибровка слотов/HUD на каждого оператора и каждый layout?
5. Какой UI обязателен: Classic HTML слева, системные окна, radar, journal?
6. Должен ли следующий этап склеивать live-зонды или сначала закрывать научный v1 (H1–H5, 20 эпизодов)?
7. Нужно ли когда-либо сажать Frozen `baseline_memory_v1` 52/60 в клиент, или live L1 навсегда отдельный?
8. Нужен ли `Circuit.run()` + CGEvent как единый runtime, или зонды остаются каноном live?
9. Можно ли считать успехом «оператор паркует окна + известное имя NPC», или это нарушает «без полного сценария координат»?
10. Какая сборка клиента (Q1)? Ломает ли другой UI pack текущие ROI?
11. Как оператор закрывает H17: запрет `w`≥8 с навсегда или новая проверка после релога?
12. Q5: нужен ли вообще метрический yaw, или достаточно визуального «кадр изменился»?
13. Разрешён ли выход за Talking Island / другой спот?
14. Нужен ли хил F4 когда-либо, или abort по HP остаётся политикой?
15. Должна ли система читать чат-лог (квест-сообщения) или это тоже OCR/запрещено?
16. Куда коммитить `L2_brain`? Сейчас каталог целиком untracked на Desktop git чужого проекта.
17. Имя/PID окна 16372 / 68342 стабильны только для той сессии; какой протокол резолва окна на следующий день?
18. Гостевое 2560×1600 — финальный канон или снова сменится?
19. Нужна ли посадка всех окон оператором как вход M2, или архитектура должна жить без фиксированных слотов?
20. MaleCNS: оставлять песочницей навсегда или есть отдельная научная ветка вне live?

---

# HANDOFF SUMMARY

## What works today

- Пакет `l2-brain` 0.7.0, `pytest` 336 passed / 0 failed (этот аудит, без HID).
- Nav-sim + Frozen L1 `baseline_memory_v1` **52/60** (не крутить).
- SCK видимого окна Parallels (H7/F40). CGEvent на PID хоста с dual flags, F12, focus, watchdog 250 ms (H8/F57 idle).
- HUD: свои CP/HP/MP, lock, HP цели, смерть цели, F1–F3 ready — на одном Interlude layout.
- Live бой: **10/10 за 150 с**, farm=false, heal=false, L1 triggers=0 (F82).
- Live NPC: `/target Newbie Guide` → F2 → ЛКМ (0.50, 0.48) → 6/6 синих ссылок (F85).
- Tab/Escape занимает и освобождает слот (F86) — на **старых** координатах инвентаря.
- Click-through overlay рамок; профиль слотов переведён на guest 2560×1600 (ходы 86b/86c, HID нет).

## What does not work today

- Единый замкнутый агент; `Circuit.run()` + CGEvent.
- Цель/квест/прогресс/OCR/журнал.
- `go_to(x,y)`, поза, карта, канонический yaw (Q5 открыт).
- Универсальный поиск NPC и понимание пунктов меню.
- Принятие и сдача квеста; выход из деревни и возврат.
- Frozen 52/60, SNN, GRU, MaleCNS как live-контроллеры.
- `LiveClientEnv` / `LiveHIDActuator` — по-прежнему `NotImplementedError`.
- Повторная валидация слота Б `[2140,140,360,480]` после смены сетки.
- F84 (чат-таргет live h) — прогон не стартовал.
- Официальные H1–H5 на 20 эпизодах; H10; H14.

## What is experimental

- `control/snn`, `control/gru`, `control/malecns` (синтетический 208/616, не FlyEM).
- R-STDP / ES (`learning/`).
- KLT/coarse yaw, `live-motion` ≥8 с (H17).
- Синтетические `TacticalCombatController` / `SpotAutonomousAgent`.
- Occupancy слотов и overlay до посадки окон оператором.
- Поле `motion` в `parallels_l2.json` (`peak_reliable=false`).

## What is currently controlling the live character

Только сценарии в `src/l2_brain/live/*.py`, которые шлют `GameAction` в `CGEventInputBackend` (PID Parallels). Не `Circuit`, не `BaselineController`, не SNN/MaleCNS. Между запусками CLI управления нет.

## Current autonomy level

Scripted live skills under operator supervision. Один заранее написанный сценарий за запуск (бой XOR меню XOR слоты). Нет planner, нет persistent task, нет recovery-политики после abort.

## Biggest architectural bottleneck

Нет слоя session/world/task state и reusable skills поверх зондов; параллельно нет текста квеста и метрической навигации. Склеивать планировщик или Circuit+HID раньше этих дыр не на чем.

## Closest meaningful milestone

Не One Quest. Ближе всего: **один процесс с явным session state**, который подряд вызывает уже доказанные навыки (spot и/или Guide open+Escape) с общим abort/focus; отдельно — **переснять F86 на слоте Б 2560×1600** после посадки окон. Это не квест и не `go_to`.

## Files the next AI should inspect first

1. `src/l2_brain/live/spot_loop.py`
2. `src/l2_brain/live/npc_dialog_probe.py`
3. `src/l2_brain/live/s4_probe.py`
4. `src/l2_brain/io/cgevent_backend.py`
5. `src/l2_brain/vision/hud_parser.py`
6. `src/l2_brain/vision/dialog_parser.py`
7. `config/window_profiles/parallels_l2.json`
8. `src/l2_brain/capture/circuit.py` (почему Circuit без HID)
9. `docs/assumptions.md` + `docs/decisions.md` (ADR-0064, 0068, 0073–0077)
10. Evidence: `spot-series-10-stable.json`, `npc-menu-crawl.json`, `layout-slots-validation.json`

## Unknowns requiring operator decision

Первый квест; OCR да/нет; generalize vs один NPC; склеивать зонды vs закрывать H1–H5; сажать ли Frozen L1 в клиент; нужен ли Circuit+HID; канон 2560×1600; куда коммитить репозиторий; политика H17.

## One-sentence project state

`L2_brain` — легальный host-контур кадра+клавиш и два узких доказанных live-сценария (спот 10/10 и меню Newbie Guide) без единого агента, без квеста, без позы и без `Circuit.run()` на клиенте.

END OF PROJECT STATE SNAPSHOT

