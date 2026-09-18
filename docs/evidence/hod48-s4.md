# Ход 48: поворот камеры стрелкой

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Мышиный драг камеры
не слали. Фарм не открывали.

## Прогон

Канон: [keyboard-search-probe.json](live-s4/keyboard-search-probe.json)
SHA1 `d9500b6281c659e2591dde8631f7c3afae3655ec`.

Окно 13944. Предыдущие попытки: сразу lock без стрелки
([keyboard-search-probe-not-empty.json](live-s4/keyboard-search-probe-not-empty.json));
затем `capture_lost`
([keyboard-search-probe-capture-lost.json](live-s4/keyboard-search-probe-capture-lost.json)).

| поле | значение |
|---|---|
| ok | true |
| rotation_type | **keyboard_arrow** |
| rotation_sent | **true** |
| walk_step_sent | false |
| target_acquired_after_search | false |
| target_killed | **true** |
| loot_pickup_sent | **true** |
| stuck_keys_count | **0** |
| watchdog_tripped | false |
| total_session_ms | **9260** |
| ticks | **125** / 600 |

## Шаги

| t_ms | шаг |
|---|---|
| 1347 | F1, lock HP 0.444 (`before_search`) |
| 2031 | `right_arrow` 450 мс, hid_sent, up в логе |
| 2032 / 2244 | F2×2 |
| 4556 | HP 0.444 → 0.258 |
| 8308 | `target_dead` 0.0, 5864 мс |
| 8712 | F3 |
| 9260 | Escape, done |

В `events` только `HoldKey right_arrow` down/up. `CameraRotate` нет.
`w` не слали: радиус `/targetnext` не был пустым.

## Камера глазами

Этот агент окно игры глазами не видел. Факт: клавиша 0x7C ушла в PID
Parallels. Угол yaw и факт разворота картинки не измерены.

ADR-0055. F55.
