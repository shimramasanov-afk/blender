# Live Agent Refactor

## Baseline

- Дата: 2026-09-18.
- Каталог: `/Users/apple/Desktop/L2_brain`.
- Собственный git: инициализирован только здесь (не Desktop).
- `pytest tests --tb=no -q` до рефакторинга: **336 passed, 0 failed** (один warning MPS sparse).
- Live HID в этом рефакторинге не запускался.
- Evidence JSON не переписывались.
- Frozen `baseline_memory_v1` / `sim/` / SNN / GRU / MaleCNS не менялись.

## Constraints

- simulation не рефакторим;
- Frozen 52/60 не меняем;
- MaleCNS/SNN не подключаем live на этом этапе;
- planner/quests/OCR/navigation не реализуем;
- live HID нельзя запускать автоматически;
- существующие probes должны продолжать работать во время миграции;
- второй HID backend запрещён: только `CGEventInputBackend`;
- непрерывный `w` ≥8 с не вводить (ADR-0064, импульс ≤500 мс);
- `Circuit.run()` не становится live-путём на этом этапе.

## Architecture target

```text
SCK / FrameProvider
        ↓
PerceptionHub.observe()     (нет HID)
        ↓
WorldState                  (что видно)
        ↓
LiveRuntime                 (один skill, AgentMode)
        ↓
Skill.start/tick/cancel     (не probe-while на десятки секунд)
        ↓
CGEventInputBackend         (dual flags, F12, focus, watchdog)
```

CLI probes остаются. После Prompt 6–7 `s4-npc-dialog` и
`s4-integrated-spot` оркеструют `LiveRuntime`. `s4-probe` и
`layout-slots` не мигрированы. Prompt 8 не начинали.

## Migration status

Остановлено после **Prompt 7.5** (R1/R2). Prompt 8 ещё не в этом checkpoint.

```text
PRE_TASK_LAYER_TESTS = 378 passed, 0 failed
LiveRuntime execution path = LIVE-VALIDATED
Long-horizon Agent/Task layer = NOT YET LIVE-VALIDATED
```

Полный `pytest tests` 2026-09-18 перед Task layer. Не ярлык «agent LIVE-PROVEN».

| Шаг | Сделано? | Честно ли это runtime, а не rename? |
|---|---|---|
| P0 git + baseline 336 | да | `L2_brain/.git` есть; Desktop не трогали |
| P1 Skill + movement/target/ui | да | `WalkPulse` шлёт `HoldKey` down, в `tick` ждёт, затем up. Не вызывает probe |
| P2 WorldState + PerceptionHub | да | агрегирует `HUDParser` / `dialog_parser`; **нет** импорта input backend |
| P3 registry + combat/npc skills | да | `AttackTarget` остаётся RUNNING, пока `WorldState` не скажет dead; `LootTarget` SUCCESS = sequence, не инвентарь; `OpenNpcDialog` шагает по тикам F85-пути |
| P4 LiveRuntime | да | `observe/start_skill/tick/cancel/shutdown`; один skill; abort → `release_all`. Тест: исходник не содержит `run_*_probe` |
| P5 `agent-live` | да | observe-only без `--skill`; HID skill без dual flags → `live_flags_required` |
| P6 migrate NPC probe | да | CLI тот же; HID через `tap_hotkey` / `talk_click` / `open_npc_dialog` / `click_dialog_item` / `close_dialog` |
| P7 migrate spot | да | FSM на месте; HID через `target_next` / `attack_target` / `loot_target` / `walk_pulse` / rotate / `u_turn` |
| P7.5 live validation | да (код + R1/R2 JSON) | R1 PASS, R2 PASS по флагу; не LIVE-PROVEN на агента |
| P8 GuideInteractionTask | **нет** | 7.5 по критерию закрыт; Prompt 8 только по отдельной команде |

**Что сейчас управляет живым персонажем:** FSM зондов + `LiveRuntime`.
Канон **этой** серии — R1/R2 в `docs/evidence/live-agent-runtime/`.
F82/F85 — старый канон до миграции, не переписывали.

**pytest после P6–7:** 358 passed, 0 failed (тогда без live).

Снимок кода 6–7: [live-runtime-after-prompt7.md](live-runtime-after-prompt7.md).  
Снимок 7.5 live: [live-runtime-after-prompt7.5.md](live-runtime-after-prompt7.5.md).

Новые модули:

```text
src/l2_brain/live/world_state.py
src/l2_brain/live/perception.py
src/l2_brain/live/runtime.py
src/l2_brain/live/agent_cli.py
src/l2_brain/live/skills/{base,result,dispatch,movement,targeting,ui,combat,npc,context,registry}.py
```

