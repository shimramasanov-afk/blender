# Ход 83: зонд диалога NPC

Дата: 2026-09-18. Frozen L1 и `sim/` не трогали. Фарм и F2 не слали.
ADR-0071.

## Что сделано в коде

`vision/dialog_parser.py` — `is_dialog_open` / `parse_dialog`.
`live/npc_dialog_probe.py` — F5 → лок → повтор F5 → окно → клик → Escape.

CLI: `l2-brain s4-npc-dialog --slot F5`.
JSON: `docs/evidence/live-s4/npc-dialog-probe.json`.
PNG: `run/npc_dialog_detected.png`.

## Проверки

`pytest tests/test_npc_dialog.py` — 5 зелёных. F2 в скрипте нет.

## Живой прогон

JSON: [npc-dialog-probe.json](live-s4/npc-dialog-probe.json)
SHA1 `d016a14a…`. Окно 16372, PID 68342. Dual flags. 9.48 с.

`ok=false`, abort `dialog_timeout`. `farm=false`. F2/F3/F4 нет.
`stuck_keys=0`.

| поле | факт |
|---|---|
| target_acquired | true, после F5 за 1.37 с, `target_hp=0.0` |
| approach_time_sec | 8.11 (до стопа, окно не открылось) |
| dialog_detected | false |
| click_dispatched | false |
| parse_dialog p95 | 99.0 мс (n=63) |

Лок HUD есть. Детектор окна за 8 с не сработал: либо F5 не
открыл HTML, либо кадр не похож на пергамент/контрастную панель.
PNG нет. Квестные ветки не читались.

Повтор (оператор «го»): [npc-dialog-probe-b.json](live-s4/npc-dialog-probe-b.json)
SHA1 `684b00cc…`. Снова `target_acquired=true` (hp 0),
`dialog_timeout` 8.01 с, клика нет. F2 нет.

F83. ADR-0071.
