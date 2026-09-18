# Ход 47: поисковый маневр при пустом /targetnext

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Фарм и повторное
блуждание не запускали. Один шаг `w` ≤ 400 мс.

## Прогон

Канон: [search-maneuver-probe.json](live-s4/search-maneuver-probe.json)
SHA1 `0231f3004cac84172944be56564cef48bb3aa2e6`.

Первый такой же исход: [search-maneuver-probe-no-target.json](live-s4/search-maneuver-probe-no-target.json)
SHA1 `b87599a0475cf2a805a474b240ce49676362ce5a`.

Окно 13944, PID 68342. Стол сначала скрыт, затем Control+Right.

| поле | значение |
|---|---|
| ok | false |
| aborted | **search_no_target** |
| search_maneuver_executed | **true** |
| rotation_sent | **true** |
| walk_step_sent | **true** |
| target_acquired_after_search | **false** |
| damage_detected | false |
| target_killed | false |
| loot_pickup_sent | false |
| stuck_keys_count | **0** |
| watchdog_tripped | **false** |
| total_session_ms | **7685.5** |
| ticks | **102** / 500 |

## Шаги (канон)

| t_ms | шаг |
|---|---|
| 1361 | F1 miss #1 |
| 2882 | F1 miss #2 |
| 4408 | `search_maneuver_triggered` |
| 4408 | CameraRotate dx=150 hid_sent |
| 4833 | HoldKey `w` 400 мс, затем up (~425 мс по логу) |
| 5172 | F1 #3 after_search |
| 7685 | abort `search_no_target`, Escape |

F2 и F3 не слали. Четвёртого шага `w` нет.

Повтор через ~8 с дал ту же цепочку. Второй импульс поиска в одной
сессии не добавляли.

## Ограничения

Ветка пустого скана отработала и остановилась. Это не захват после
маневра и не килл. Q5: HID дошёл, метры/градусы неизвестны. H8 не
закрыта. F3/лут не проверяли.

ADR-0054. F54.
