# Снимок после Prompt 6–7 — оба сценария на LiveRuntime, live ещё нет

Дата: 2026-09-18. Live HID не запускался. Frozen L1 / `sim/` не менялись.
Evidence JSON (F82/F85/F86) не переписывались. Prompt 8 не начинали.

Оператор просил остановиться здесь: это самая опасная точка рефакторинга.
На бумаге архитектура может делать «то же самое», а в Lineage не добежать
до гида.

## Короткий вердикт

**Оба старых live-сценария оркеструют один LiveRuntime. Тесты зелёные.
Нового live-прогона нет. Победы в игре нет.**

- `s4-npc-dialog` и `s4-integrated-spot` больше не шлют HID сами через
  `_send` / `rotate_camera_keyboard` / `_hold_key_ms`.
- Они создают `LiveRuntime` и вызывают `run_skill(...)`.
- CLI те же. Dual flags те же. Квестов, OCR, Frozen, SNN, MaleCNS нет.
- F82/F85 остаются каноном **старых** живых прогонов. Этот слой ими
  не доказан.

## Контрольная точка

| Обещание | Есть в коде? | Доказано live? |
|---|---|---|
| NPC probe на Skill API | да | нет |
| Spot FSM на Skill → LiveRuntime → CGEvent | да | нет |
| Наблюдаемые тесты F5 / via_chat / 5–10 фрагов / roam / L1 / aggro | да (unit) | нет |
| Новый live-прогон после миграции | **нет** | — |
| GuideInteractionTask (Prompt 8) | **нет** | — |

## Кто чем владеет сейчас

```text
evaluate / Circuit / Frozen L1     без изменений, не live

s4-npc-dialog / s4-integrated-spot
        ↓
   FSM / сценарий (payload, PNG, restart, фазы)
        ↓
   LiveRuntime.run_skill → один Skill.tick
        ↓
   CGEvent     ← unit на RecordingPoster; live после миграции нет

layout-slots / s4-probe            не мигрированы, не этот снимок
```

## Как проверить, что это не rename

Тест `test_npc_and_spot_orchestrate_via_runtime`:

- `run_npc_dialog_probe` содержит `LiveRuntime`, `run_skill`,
  `open_npc_dialog`, `talk_click`, `tap_hotkey`, `click_dialog_item`.
- `run_integrated_spot` содержит `LiveRuntime`, `run_skill`,
  `attack_target`, `loot_target`, `walk_pulse`, `target_next`.
- В spot нет `BaselineController` / `SNNController` / `MaleCNSController`
  / `Circuit`.

`inspect.getsource(LiveRuntime)` по-прежнему не содержит `run_*_probe`.
Runtime не знает про 10 фрагов и обход 6 пунктов гида.

## Честные швы, где поведение могли сломать

Именно их надо смотреть перед live validation:

1. **F5 ≠ OpenNpcDialog.** `OpenNpcDialog` шлёт F2. F5-путь:
   `tap_hotkey F5` → lock → `talk_click` 0.50/0.48 (или skip, если
   HTML уже открыт) → `click_dialog_item` → `close_dialog`.
   Тест `test_probe_lock_dialog_click` запрещает F1/F2/F3.
2. **via_chat = OpenNpcDialog.** `/target` → F2 → talk click → crawl
   `click_dialog_item` + `close_dialog`. Тест F85-контракта зелёный.
3. **Capture restart.** LiveRuntime по умолчанию абортит `capture_lost`.
   NPC probe передаёт `recover_capture` (старый restart, MAX 24).
   Spot по-прежнему абортит потерю кадра.
4. **Spot FSM остался.** Фазы idle/scan/roam/combat/loot. HID только
   через skills. L1 peel сидит в `AttackTarget.tick` (иначе нельзя
   вторым skill во время боя). Aggro: `on_tick` → cancel → Escape +
   F1 + F2, затем loot если цель уже мертва.
5. **TargetByName** всё ещё блокирует на `chat_commander.target_by_name`.

## Тесты

- После Prompt 5: 357 passed.
- После Prompt 6–7: **358 passed**, 0 failed.
- Новый: `test_npc_and_spot_orchestrate_via_runtime`.
- Старые F5 / chat / five / ten / roam / roam_limit / L1 / aggro
  остались зелёными.

## Git

Инициализирован только `/Users/apple/Desktop/L2_brain/.git`.
Desktop не трогали. Коммита не делали. Live HID не слали.

## Что смотреть глазами

1. `src/l2_brain/live/npc_dialog_probe.py` — `LiveRuntime(...)`, `play()`.
2. `src/l2_brain/live/spot_loop.py` — `play("walk_pulse")`,
   `run_skill("attack_target")`, `play("loot_target")`.
3. `src/l2_brain/live/runtime.py` — `run_skill`, `recover_capture`.
4. `src/l2_brain/live/skills/npc.py` — `TalkClick`; F2 только в
   `OpenNpcDialog`.
5. Evidence F82/F85 — старые файлы, не новый прогон.

## Следующее решение оператора

Сделано отдельно как Prompt 7.5: live R1/R2.
Снимок: [live-runtime-after-prompt7.5.md](live-runtime-after-prompt7.5.md).
Этот файл (6–7) по-прежнему про код без тогдашнего HID.
