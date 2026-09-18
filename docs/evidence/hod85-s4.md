# Ход 85: F2-подбег и обход меню гида

Дата: 2026-09-18. Frozen L1 и `sim/` не трогали. Фарм нет.
ADR-0074. F85.

## Что сделано в коде

`/target Newbie Guide` → импульс F2 → ЛКМ (0.50, 0.48).
`extract_menu_items` только в левой панели. Обход сверху вниз:
клик, 600 мс, Escape, 400 мс.

CLI: `l2-brain s4-npc-dialog --via-chat`.
JSON: [npc-menu-crawl.json](live-s4/npc-menu-crawl.json).
PNG: `run/npc_dialog_detected.png`.

## Проверки

Полный `pytest tests` — зелёный. Frozen L1 / `sim/` не трогали.

## Живой прогон

Окно 16372, PID 68342. Dual flags. **36.67 с**. `ok=true`.
SHA1 `ce2cec6a…`. `farm=false`. F1/F3/F4 нет. F2×2 (подбег и
реоткрытие после пункта 2).

| поле | факт |
|---|---|
| chat_target_success | true, hp 0 |
| f2_approach | true |
| dialog_opened_from_closed | true, `html_links`, 2.27 с |
| total_items_found | 6 |
| items_clicked | 6 |
| false_target_markers | 0 |
| sck_crashes | 7 (helper no frame, захват поднимали) |

Координаты центров (кадр 4112×2580), сверху вниз:

| k | px | py | nx | ny |
|---|---|---|---|---|
| 0 | 1037 | 888 | 0.252 | 0.344 |
| 1 | 1207 | 1249 | 0.294 | 0.484 |
| 2 | 1186 | 1348 | 0.288 | 0.522 |
| 3 | 1095 | 1551 | 0.266 | 0.601 |
| 4 | 1141 | 1617 | 0.277 | 0.627 |
| 5 | 1152 | 1702 | 0.280 | 0.660 |

Все nx ≤ 0.42. OCR названий нет: в кадре видны Ask for advice,
NPC Location, Blessing, teleport / Newbie Town, help, supplemental
magic; детектор снял 6 синих полос (переносы могли слиться).

F2: после лока пауза 2 с, один клик в центр — HTML слева открылся.
Персонаж уже стоял у монумента с прошлых проб. После пункта 2
окно закрылось; повтор F2+ЛКМ открыл снова. Q5 не закрыт.
