# Снимок после Prompt 5 — это LiveRuntime или rename?

Дата: 2026-09-18. Live HID не запускался. Frozen L1 / `sim/` не менялись.

Оператор просил остановиться здесь и проверить, не объявили ли
обёртку над `run_npc_dialog_probe` / `run_integrated_spot` «архитектурной победой».

## Короткий вердикт

**Каркас настоящий. Победы в игре нет.**

- Есть отдельные типы и tick-цикл, которых в probes не было.
- LiveRuntime **не** вызывает старые `run_*_probe`.
- Старые probes **не** переведены и по-прежнему единственный путь,
  который когда-либо убивал мобов / открывал гида (F82/F85).
- Если запустить `s4-integrated-spot` или `s4-npc-dialog`, персонажем
  по-прежнему рулит старый while-сценарий, не `LiveRuntime`.

## Что должно было появиться к Prompt 5

| Обещание плана | Есть в коде? | Доказано live? |
|---|---|---|
| `Skill` start/tick/cancel + статусы | да | нет |
| `WorldState` без quest/XY | да | нет |
| `PerceptionHub` без HID | да | нет |
| `LiveRuntime` один skill | да | нет |
| `agent-live` observe-only | да | нет |
| Миграция NPC/spot probes | **нет** (это Prompt 6–7) | — |

## Как отличить runtime от rename

Проверено тестом `test_runtime_is_not_a_probe_rename`:

- `inspect.getsource(LiveRuntime)` не содержит `run_npc_dialog_probe`,
  `run_integrated_spot`, `run_s4_probe`.
- `WalkPulse.start` шлёт `HoldKey` down; `tick` возвращает RUNNING,
  пока не истечёт импульс; затем up. Это не `run_integrated_spot()`.
- `AttackTarget.tick` смотрит `WorldState.target_dead`; не крутит
  25-секундный while внутри `start`.
- `OpenNpcDialog` после `start` остаётся RUNNING (ещё не «диалог открыт»).
- `LootTarget` SUCCESS reason = `loot_input_sequence_completed`,
  `inventory_confirmed=False`.
- `PerceptionHub` не импортирует input backend.
- `TargetByName` вызывает существующий `chat_commander.target_by_name`
  (тот же объект функции), не копирует набор клавиш.

Честные оговорки, где ещё тонко:

- `TargetByName.start` **блокирует** на время `target_by_name` (lock wait).
  Это старый helper, не новый скрытый бой-loop.
- `AttackTarget.start` шлёт два F2 с паузой `ENGAGE_F2_GAP_S` — как F82.
- `agent-live --skill` без injected runtime на реальной машине
  соберёт SCK+CGEvent только при dual flags + window + pid.
  Этого пути мы в этом ходе **не гоняли**.

## Кто чем владеет сейчас

```text
evaluate / Circuit / Frozen L1     без изменений, не live

s4-integrated-spot / s4-npc-dialog / layout-slots
        ↓
   старый probe while
        ↓
   CGEvent     ← ЭТО всё ещё канон живого персонажа

agent-live / LiveRuntime
        ↓
   PerceptionHub → WorldState → один Skill.tick
        ↓
   CGEvent     ← есть в коде, unit на RecordingPoster, live нет
```

## Тесты

- До рефакторинга: 336 passed.
- После Prompt 5: **357 passed**, 0 failed.
- Новые: `test_live_skills.py`, `test_perception_hub.py`,
  `test_live_runtime.py`, `test_agent_live_cli.py`.

## Git

Инициализирован только `/Users/apple/Desktop/L2_brain/.git`.
Desktop-репозиторий не трогали. Коммита не делали.

## Что смотреть глазами

1. `src/l2_brain/live/runtime.py` — `start_skill` / `tick` / `_abort`.
2. `src/l2_brain/live/skills/movement.py` — импульс, не hold на 8 с.
3. `src/l2_brain/live/skills/combat.py` — бой по WorldState.
4. `src/l2_brain/live/skills/npc.py` — шаги F85, SUCCESS = `dialog_open`.
5. `src/l2_brain/live/perception.py` — нет input backend.
6. `src/l2_brain/live/npc_dialog_probe.py` и `spot_loop.py` —
   **не** импортируют LiveRuntime. Значит миграции не было.

## Если бы это был rename

Ожидалось бы примерно:

```python
def start_skill(self, name):
    return run_integrated_spot(...)
```

Этого нет. Вместо этого runtime не знает про 10 фрагов, roam и
обход 6 пунктов гида. Он умеет только один skill за раз.

## Что ещё не сделано (намеренно)

Prompt 6+: probes на skills. Без этого LiveRuntime — каркас,
который персонажем в записанных evidence не управлял.
