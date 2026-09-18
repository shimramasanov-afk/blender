# Ход 50: H8 латентность и горизонт Q5

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. Автономный агент
не открыт. Игровые клавиши в бенче H8 не слали.

## H8 — 100 тиков

JSON: [h8-latency-report.json](live-s4/h8-latency-report.json)
SHA1 `bd9434b0f7272985b0e2137b2445db8a355faf3f`.

Окно 13944, PID 68342, 6.43 с, warmup 8 + 100, hid_sent=false,
stuck=0, watchdog=false, farm=false.

`observe_ms` — снятие последнего кадра SCK из очереди (копия, не
фотон). `act_ms` — `idle_act`: фокус, опрос F12, pump, пустой
`release_all`. Игровых keyDown нет.

| стадия | p50 | p90 | p95 | p99 |
|---|---|---|---|---|
| observe | 1.14 | 1.76 | **2.08** | 3.18 |
| parse | 13.03 | 14.02 | **15.13** | 15.37 |
| encode | 42.02 | 43.97 | **44.26** | 45.35 |
| infer | 0.059 | 0.071 | **0.077** | 0.088 |
| act | 0.045 | 0.161 | **0.191** | 0.214 |
| H8 observe+infer+act | 1.29 | 1.90 | **2.19** | 3.28 |
| pipeline +parse | 14.73 | 15.71 | **16.33** | 16.49 |

Производно от тех же 100 тиков, не отдельный прогон:
observe+encode+infer+act p95 **45.65** мс;
observe+parse+encode+infer+act p95 **59.30** мс.

Критерий: p95(observe+infer+act) ≤ 100. **H8 = true.**
Отклонение (>150) не сработало.

## Q5 — полоса горизонта

JSON: [motion-calibration-v2.json](live-s4/motion-calibration-v2.json)
SHA1 `2e4891c91ebc81be806d5583daae58385ab9862d`.

Кроп y 15–30%, x 25–75% (387×2056 на кадре 4112×2580).
Один `right_arrow` 500 мс, без `w`. hid_sent=true, stuck=0.

| поле | значение |
|---|---|
| yaw_shift_px | −203.99 |
| yaw_peak | **0.013** |
| deg_per_sec | −7.44 (FOV 75° — допуск) |
| peak_reliable | **false** (< 0.15) |
| q5_horizon_ok | false |
| q5_closed | **false** |

`parallels_l2.json` не обновляли: нужны peak ≥ 0.15 **и** H8 p95 ≤ 100.

## Что это не доказывает

`observe_ms` ≈ 1 мс — не задержка камеры. Encode ~44 мс в канон H8
не входит; даже с ним p95 < 100. Пик горизонта 0.013: сдвиг −204 px
и −7.44 °/с не константа маршрута. 75° FOV не измерен. 360° по
ориентиру нет. Метры шага нет.

ADR-0057. F57.
