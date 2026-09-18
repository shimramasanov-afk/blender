# Проверка VisualEncoder (navigation_v1)

Не оценка политики и не перенос в MMORPG. Контур контроллера с этим энкодером не гоняли.

Эталон: CPU block-matching (SAD) + отдельный поиск масштаба. Модель распознавания объектов не подключена.

## Стартовая конфигурация

Выбрана **48×32**, сетка секторов 5×3, поток 8×6, поиск ±8, нижняя полоса `near_y0=0.45`.

Основание — `l2-brain vision bench --repeats 8` → [vision-bench.json](vision-bench.json):

| Рабочий кадр | encode p50 / p95, мс | сдвиг/зум 6 пар | sim: поворот ≠ подход |
|---|---|---|---|
| 32×24 | 8.11 / 10.36 | 6/6 | нет |
| **48×32** | **36.57 / 36.91** | **6/6** | **да** |
| 64×48 | 89.86 / 90.98 | 5/6 | нет |

32×24 дешевле, но на перспективном стенде не отделяет приближение к стене от поворота камеры. 64×48 дороже и хуже на синтетике. 36 мс на кадр — измерение, не обещание бюджета живого тика.

## Проверки преобразований

| Случай | Ожидание | Статус |
|---|---|---|
| Неподвижная сцена | `duplicate` или низкая уверенность | `test_static_scene_has_near_zero_motion` |
| Горизонтальный сдвиг | `camera_turn` | `test_horizontal_shift_is_camera_like` |
| Масштабирование | `approach`, expansion > 0.04 | `test_zoom_is_approach_like` |
| Поворот камеры | `camera_turn` на `camera_spin` | `test_sim_turn_vs_approach` |
| Приближение к препятствию | `approach` или `uncertain`, expansion больше, чем у поворота | `test_sim_turn_vs_approach` |
| Резкая смена кадра | `abrupt_cut` / `low_confidence` | `test_abrupt_cut_marks_low_confidence` |
| Низкая текстура | `low_confidence`, нет «свободный путь» | `test_low_texture_is_not_a_clear_path` |
| Пропуск / stale | `validity_mask.stale`, `low_confidence` | `test_duplicate_and_dropped_frame` |
| Освещение | не `approach`/`camera_turn` как движение | `test_lighting_change_is_not_treated_as_flow` |
| HUD из профиля | статический верх не ломает сдвиг | `test_hud_mask_excludes_static_overlay` |
| Команда ≠ измерение | `command_is_not_measurement` | `test_command_is_not_treated_as_measurement` |

Диагностика: `run/vision-diag.ppm` (векторы, сектора, слабая текстура, цель, уверенность, метка). Не вход политики.

## Ограничения

- Нет потока ≠ свободный путь (`flow_absent_is_not_clear`).
- История команд — только prior гипотезы, не замена потока.
- Цель — красное пятно, не детектор объектов.
- Запись живого окна этим энкодером не гоняли.
- `pytest` на момент записи evidence: 73 passed.
