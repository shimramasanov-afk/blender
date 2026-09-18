# Ход 42: первый S4-зонд на живом окне

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм не запускали.
Ходьбы не было.

Оператор: Q6 уже закрыт (F48); явная команда «S4 открыт» / «давай допуск».

## Прогон

JSON: [first-combat-probe.json](live-s4/first-combat-probe.json)
SHA1 `54c3b54311fb6f4cc80ecffcd27e09b4b74c7f2b`.

Окно `Windows 11` id **13944**, PID Parallels **68342**.
`live_confirmed` + `live_danger_confirmed`. Маски HUD на захвате выключены.

| поле | значение |
|---|---|
| ok | true |
| aborted | нет |
| hid_sent | true |
| session_ms | **5430** |
| ticks | **76** / 300 |
| start_self_hp | **0.943** |
| target_locked | true (подложка) |
| initial / final target_hp | **0.444 / 0.444** |
| damage_detected | **false** |
| F1 → lock | **116** мс |
| F2 → HP drop | нет |
| stuck_keys_count | **0** |
| watchdog_tripped | false |

Шаги: capture → self bars → F1 → lock → F2 → 4 с наблюдения HP → Escape → `release_all`.

События ввода: `TargetSelect`, `SkillActivate(F2)`, `escape` down/up, `release_all`.

## Что это не доказывает

Lock за 116 мс при HP 0.444 совпадает с кадром F45 (Gremlin).
Цель, скорее всего, уже висела до F1 — это не доказательство нового
выбора. Полоска за 4 с после F2 не сдвинулась: дистанции/попадания нет
(подхода не было, Q5 не измерен). Это не килл и не 95% готовности.

ADR-0049. F49.
