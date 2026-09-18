# Ход 35: парсер HUD и шина `ui_vision`

Дата: 2026-09-17. `sim/`, Frozen L1 и HID не трогали.
Записанных кадров Classic UI в репозитории нет: живая разметка
пропущена, не имитировалась.

## Что есть

- `HUDParser` / `extract_bar_ratio`: доля заполнения по непрерывному
  горизонтальному профилю цветовой маски (слева направо).
- ROI только в `config/window_profiles/parallels_l2.json` (`hud.*`).
  Это типичная раскладка Classic, не замер этого клиента (Q1).
- `VisionTelemetryBridge` → `HealthUpdate` / `TargetState`,
  `source="ui_vision"`. Повтор с дельтой HP < 0.5 не публикуется.
- Чёрный кадр: `valid=False`, событий нет.
- `TelemetryHub.is_stale` 300 мс без изменения порога.

## Прогон

`pytest tests/test_hud_parser.py` — 9 passed.

Синтетика: полосы 100 / 50 / 0% в пределах ±2%; рамка цели есть/нет.

## Чего нет

Живой HUD. Снятие `sim_ground_truth` со стенда. Кадр в политике.
Дальность с пикселей. OCR. pcap.
