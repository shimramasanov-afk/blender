# Ход 46: три цикла боя и лута

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Бесконечный фарм не
запускали. Потолок: 3 убийства или 45 с.

## Прогон

JSON: [multi-kill-probe.json](live-s4/multi-kill-probe.json)
SHA1 `5319157e2b86f858c82f7c6eb47dca067fafcfac`.

Окно 13944, PID Parallels 68342. Сначала `on_screen=false` (соседний
Space), затем Control+Right, окно на текущем столе.

| поле | значение |
|---|---|
| ok | true |
| kills_completed | **3** |
| loot_actions_sent | **3** |
| total_session_ms | **27334.6** |
| ticks | **397** / 900 |
| watchdog_tripped | **false** |
| stuck_keys_count | **0** |
| farm | false |
| CameraRotate | не понадобился |

## Фраги

| цикл | t_ms | lock HP | time_to_kill_ms | F3 |
|---|---|---|---|---|
| 1 | 11332 | 0.444 | 8339 | hid_sent |
| 2 | 18102 | 0.444 | 4638 | hid_sent |
| 3 | 27334 | 0.444 | 7118 | hid_sent |

Все три: `EntityDefeated`, финальный HP 0.0. Первая дельта сессии
0.444 → 0.375 за 883 мс (цикл 1).

Шаги каждого цикла: SCAN F1 → lock → F2×2 → `target_dead` → F3 → Escape.

После третьего RESET сессия остановилась. Четвёртого F1 нет.

## Ограничения

Три раза подряд полоска стартовала с 0.444: это заполнение бара, не
три доказанных разных `entity_id`. F3 — факт клавиши, не GetItem.
H8 не закрыта. Это не фарм-петля.

ADR-0053. F53.
