# Ход 84: `/target` через чат

Дата: 2026-09-18. Frozen L1 и `sim/` не трогали. Фарм и F2 не слали.
ADR-0073. F84 нет.

## Что сделано в коде

`io/chat_commander.py` — `target_by_name`: Escape, Enter,
`/target Name` по 25 мс, Enter. Нет лока за 500 мс — Escape.
`cgevent_backend.py` — ЛКМ только `CGEventPostToPid`, координата
в пределах окна. `dialog_parser` — окно по ≥2 синим кластерам.
`s4-npc-dialog --via-chat --npc-name "Newbie Guide"`.

## Проверки

`pytest tests` — зелёный. Юнит: чат шлёт Escape/Enter/текст,
ложные золотые ники не окно, клик PID-only и кламп.

## Живой прогон h

Не выполнялся. Окно 16372 в каталоге SCK есть, `on_screen=false`.
Скрытый / чужой стол гостя не источник. HID не слали.

JSON `docs/evidence/live-s4/npc-chat-target-h.json` отсутствует.

Предыдущие живые факты того же дня (не h): f поймал уже открытый
чат гида; g был ложный SUCCESS по никам и в детекторе закрыт.
