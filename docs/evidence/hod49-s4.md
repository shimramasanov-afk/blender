# Ход 49: замер сдвига кадра

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Один импульс стрелки
и один шаг `w`. H8 не закрывали.

## Прогон

JSON: [motion-calibration.json](live-s4/motion-calibration.json)
SHA1 `826be412c12432da3f525ec6c944abef9435c475`.

Окно 13944, 1.81 с, ticks=3, stuck=0, watchdog=false.

| поле | значение |
|---|---|
| yaw_shift_px | **20.78** |
| yaw_peak | **0.023** |
| deg_per_sec | **0.758** (FOV 75° — допуск) |
| step_shift_px | **165.18** |
| step_dx / step_dy | 162.2 / 31.1 |
| step_peak | **0.034** |
| step_px_per_sec | **330.4** |
| step_scale | 1.0 |
| motion_detected | true |
| confidence | **low** |
| turn_90_duration_ms | null |
| h8_closed | **false** |

Шаги: I0 → right_arrow 500 мс → I1 → w 500 мс → I3.

Профиль: `config/window_profiles/parallels_l2.json` → `motion`.

## Что это не доказывает

Пик корреляции < 0.08: сдвиг может быть ложным. 0.76 °/с даёт поворот
на 90° порядка двух минут — это не похоже на стрелку Interlude.
Метры шага нет. H8 (p95 полной задержки) не измеряли.

ADR-0056. F56.
