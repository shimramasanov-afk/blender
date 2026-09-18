# Снимок Prompt 7.5 — live validation LiveRuntime (R1 / R2)

Дата: 2026-09-18. Frozen L1 / `sim/` не менялись. Evidence F82/F85/F86
не переписывались. Prompt 8 не начинали. `Circuit.run` не live-путь.

Это не снимок после Prompt 6–7. Тот — код без HID:
[live-runtime-after-prompt7.md](live-runtime-after-prompt7.md).

7.5 = минимальная live-серия на том же контуре: NPC и короткий combat
через `LiveRuntime`, новые JSON, старый канон F82/F85 не трогать.

## Короткий вердикт

**По флагу `--runtime-validation`: R1 PASS, R2 PASS.
Оба JSON пишут `architecture=LiveRuntime`, `runtime_used=true`.**

Это не доказательство квестов, фарма, навигации Q5, Frozen 52/60
или «агент готов». Общий ярлык «agent LIVE-PROVEN» не используем.
Loot SUCCESS = последовательность F3, не инвентарь.

```text
LiveRuntime execution path = LIVE-VALIDATED
Long-horizon Agent/Task layer = NOT YET LIVE-VALIDATED
```

Канон R1/R2 JSON не переписывать. Критерии PASS в
`runtime_validation.py` не менять задним числом.

## Где лежат факты

| Что | Путь |
|---|---|
| Этот снимок | `docs/live-runtime-after-prompt7.5.md` |
| Короткий вердикт серии | [live-agent-runtime-validation.md](live-agent-runtime-validation.md) |
| Каталог JSON | [evidence/live-agent-runtime/](evidence/live-agent-runtime/) |
| R1 канон | `docs/evidence/live-agent-runtime/R1-runtime-npc.json` |
| R2 канон | `docs/evidence/live-agent-runtime/R2-runtime-combat.json` |
| Критерий PASS/FAIL | `src/l2_brain/live/runtime_validation.py` |
| ADR серии | ADR-0080; дальше 0081–0084 — почему R2 сначала не шёл |

Окно всех живых попыток: **18733** (`Windows 11`), PID **68342**.
Сервер: Interlude / BotEbaniy / говорящий остров (Q6).

## Что обещали в 7.5 и что вышло

| Обещание | Код | Live |
|---|---|---|
| Флаг `--runtime-validation`, default CLI без флага | да | да, оба прогона с флагом |
| Новые пути evidence, не F82/F85/F86 | да | да |
| R1: `/target` → F2 → диалог → один пункт → Escape | да | **PASS** 14.67 с |
| R2: `--kills 3`, без фарма, без хила | да | **PASS** 113.0 с, 3 килла |
| Dual flags + F12 + `release_all` | да | `focus_lost=false`, `release_all_called=true` |
| Cursor сам не жмёт live | да (ADR-0080) | live только по «го» |
| Prompt 8 / GuideInteractionTask | **нет** | — |
| `LIVE-PROVEN` на агента | запрещено до серии | серия по флагу закрыта; ярлык не ставим |

## Критерий, которым мерили (не ощущение)

**R1 PASS** если: runtime; цель; `OpenNpcDialog` SUCCESS; диалог виден;
≥1 пункт; клик; talk-click **или** F2 открыл HTML; close; диалог закрыт;
нет `focus_lost`; `release_all`; `aborted` пуст.

На каноне R1: `talk_click_sent=false`, `f2_approach=true`, диалог
открылся после F2 без центрального talk-click. Это заложено в
критерии (не дыра). `capture_recovery_used=true` (SCK restart 6) —
это success с восстановлением захвата, не чистый непрерывный кадр.

**R2 PASS** если: `kills_completed≥1`; `attack_skill_success≥1`;
`loot_skill_runs≥1`; `stuck_keys=0`; нет `focus_lost`; `release_all`;
не farm; не heal; `aborted` пуст; Frozen/SNN/MaleCNS/Circuit не
использовались.

На каноне R2: киллов **3** (порог был ≥1). `attack_skill_success=1`
при 8 запусках атаки: часть боёв ушла в aggro / blind, не в
`AttackTarget` SUCCESS.

## R1 — NPC

Файл: `R1-runtime-npc.json`. SHA1 `062760c2…`.

| поле | значение |
|---|---|
| `validation_result` | PASS |
| `elapsed_sec` | 14.67 |
| команда | `/target Newbie Guide` |
| `chat_target_success` | true |
| `open_dialog_skill_status` | success |
| `dialog_detected` | true (html_links, conf 0.74) |
| `talk_click_sent` | false |
| `f2_approach` | true |
| пункты / клик | 2 найдено, 1 клик (1261, 1171) |
| `dialog_closed` | true (Escape) |
| SCK restart | 6 / 6 |
| Frozen / SNN / MaleCNS / Circuit | false |

Попытка 1: `R1-runtime-npc-attempt1.json` — FAIL `chat_target_failed`.
Канон — повтор, не первая попытка.

## R2 — combat

Файл: `R2-runtime-combat.json`. SHA1 `be12db2b…`.

| поле | значение |
|---|---|
| `validation_result` | PASS |
| `elapsed_sec` | 113.0 |
| `kills_completed` | 3 |
| `f2_input_count` | 18 |
| `loot_skill_runs` / F3 taps | 7 / 21 |
| `loot_pickup_sent` | true |
| self HP старт / мин / конец | 1.0 / 0.97 / 1.0 |
| roam / L1 / aggro / u-turn | 4 / 3 / 2 / 1 |
| `stuck_keys` | 0 |
| `focus_lost` / `capture_lost` | false / false |
| farm / heal | false / false |

Фраги из JSON:

| # | search_ms | combat_ms | loot_ms | HP | как в логе |
|---|---|---|---|---|---|
| 1 | 11494 | 262 | 3308 | 1.0→0.0 | lock → aggro → F2 → `target_dead` → F3 |
| 2 | 2969 | **0.03** | 3338 | **0→0** | `blind_engage` → `target_dead` сразу |
| 3 | 75562 | 6243 | 3254 | 1.0→0.0 | roam, снова lock, aggro, F2, F3 |

Килл 2 не доказывает отдельный удар: пластина уже была «мертвая».
Киллы 1 и 3 — живой lock 1.0→0.0 и F3 после смерти.

Пока бродил без лока, F3 шёл ещё и `via=after_f2` (ADR-0083): лут
после слепого F2, без кредита килла.

### Почему R2 сразу не прошёл

Канон перезаписывали. Старые FAIL лежат как attempt1–6:

| файл | abort | с | F2 | киллы |
|---|---|---|---|---|
| attempt1 | `self_hp_low` | 0.8 | 0 | 0 |
| attempt2 | `SourceLost` | 4.0 | 0 | 0 |
| attempt3 | `capture_lost` | 147.4 | 0 | 0 |
| attempt4 | `capture_lost` | 105.3 | 0 | 0 |
| attempt5 | `roam_limit` | 411.8 | 55 | 0 |
| attempt6 | `self_hp_low` | 173.7 | 22 | 0 |

Разбор по ходам, не «магия архитектуры»:

- F1 подсвечивал моба, парсер не видел пластину → F2=0 (Ход 90–91,
  ADR-0081: слепой F2).
- Ложная мёртвая пластина / свой HP как цель → сидели 25 с, килл 0
  (Ход 92–93, ADR-0082).
- Лут только после засчитанного килла → F3=0 при живых трупах
  (Ход 95, ADR-0083).
- Свои полосы увеличены оператором; старый ROI смотрел в землю;
  канон R2 после переразметки (Ход 95, ADR-0084, кадр
  `client-reference-hod95.png`, self HP 31,151,582,155).

## Что 7.5 не доказал

- Инвентарь / факт лута (F3 sent ≠ GetItem).
- Каждый волк в мире = строка в JSON (килл 2 сомнительный).
- Q5 (метры, yaw). Профиль motion по-прежнему weak.
- Непрерывный захват без SCK restart (R1: 6 рестартов).
- F5-путь NPC (канон R1 — via_chat / F2).
- `s4-probe` и `layout-slots` (не мигрированы на LiveRuntime).
- Prompt 8, квесты, OCR, Task layer.
- Перенос F82 10/10: другой CLI, другой канон, не переписывали.

## Кто чем владел в этих прогонах

```text
evaluate / Circuit / Frozen L1     не вызывались (флаги false)

s4-npc-dialog --runtime-validation     → R1
s4-integrated-spot --runtime-validation --kills 3 --no-timeout --no-heal
        ↓
   FSM зонда (payload, PNG, фазы, roam)
        ↓
   LiveRuntime.run_skill → один Skill.tick
        ↓
   CGEvent  (dual flags, окно 18733, PID 68342)
```

## Тесты

Prep (Ход 89): 363 passed, без live.
После HUD/лута (Ход 95): зелёные `test_hud_parser`,
`test_spot_loop`, `test_live_runtime`, `test_runtime_validation`.
Полный suite в том ходе один раз оборвали по «стоп»; на канон R1/R2
это не ссылается.

## Следующее решение оператора

7.5 по своему критерию закрыт.

Не следует из этого автоматически Prompt 8. Если нужен Task layer —
отдельная команда. Если нужна ещё серия (F5-гид, 10 фрагов, другой
спот) — тоже отдельное «го», не этот JSON.
