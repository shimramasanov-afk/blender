# Проверка ScreenCaptureKit-источника

Не оценка политики и не H7 на 30 с.

| Проверка | Статус | Доказательство |
|---|---|---|
| Обычный захват реального окна | pass | `run/sck-demo`, `inspect --tick 1` кадр 440×344×3 |
| Retina / scale | pass | scale=2 на self-test |
| Изменение размера | pass | `run/sck-resize` resizes=2 |
| Потеря источника | pass | `test_source_lost_is_explicit` (mock helper) |
| Медленный потребитель | pass | `test_slow_consumer_counts_drops` |
| Остановка | pass | `test_stop_is_idempotent`, `circuit.close` |
| Запись и replay | pass | `inspect` + `replay run/sck-demo` |
| Диагностика разрешения без запроса | pass | `capture permission`, `requested_permission: false` |
| HUD не вшит в модуль | pass | `test_profile_masks_do_not_hardcode_hud` |

Минимум API: ScreenCaptureKit 12.3. Прогон: macOS 27.0. Транспорт: stdout pipe. Shared memory не включали.

H7 оценена 2026-09-17 на видимом окне Parallels: медиана 33.76 мс,
drops 0, black 0, 30.13 с. Принята (F40, ADR-0041). Не HUD и не контур.
