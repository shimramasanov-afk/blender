# Ход 36: CGEvent backend и отказ слать в игру

Дата: 2026-09-17. `sim/`, Frozen L1 не трогали. Клиент не получал ввод.

## Механизм

- `CGEventInputBackend`: `CGEventCreateKeyboardEvent` / `CGEventPostToPid`.
  Конструктор требует `live_confirmed` и `live_danger_confirmed`.
- Фокус: bundle `com.parallels.desktop.console`, иначе `release_all`.
- Watchdog 250 мс вызывает keyUp всех удержаний.
- Kill-switch: состояние F12 в HID (`CGEventSourceKeyState`).
- CLI `input-probe --live --live-confirmed`. Без второго флага HID нет.

## Прогоны

`pytest tests/test_cgevent_backend.py tests/test_input_backend.py` — 14 passed.

Live: [live-s3/notepad-probe.json](live-s3/notepad-probe.json)
SHA1 `17c01f61a09506d5d92e194f9bdd12ff36ea617e`.
`aborted=game_process_present`, markers=`l2.exe`, `hid_sent=false`.

Dry harness (без Quartz): [live-s3/notepad-probe-dry.json](live-s3/notepad-probe-dry.json).
watchdog_tripped=true, stuck_keys_count=0, act_ms p50=0.018 / p95=0.034 мс
(это не задержка CGEvent в госте).

## Чего нет

Текст в Блокноте. S4. H8. SendInput в госте.
