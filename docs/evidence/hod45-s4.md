# Ход 45: смерть цели и импульс F3

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм-цикл не запускали.
Один моб, один зонд.

## Прогон

JSON: [kill-loot-probe.json](live-s4/kill-loot-probe.json)
SHA1 `241269a1639ed8961d9d3dd6431f8c30ef684c60`.

Окно 13944.

| поле | значение |
|---|---|
| ok | true |
| target_killed | **true** |
| entity_defeated | **true** |
| loot_pickup_sent | **true** |
| initial_hp | **0.444** |
| final_hp | **0.0** |
| first drop | 0.444 → 0.361 за 1632 мс |
| time_to_kill_ms | **6685** |
| F3 | hid_sent |
| Escape | hid_sent |
| session_ms | **9138** |
| ticks | **130** / 360 |
| stuck_keys_count | **0** |

Шаги: F1 → F2×2 → дельта HP → `target_dead` / `EntityDefeated` → F3 → Escape.

## Ограничения

F3 отправлен после смерти. Подбор предмета в инвентаре не читали:
это `loot_pickup_sent`, не факт GetItem. Не фарм. Не H8.

ADR-0052. F52.
