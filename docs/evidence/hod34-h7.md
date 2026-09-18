# Ход 34: H7 на видимом окне Parallels

Дата: 2026-09-17. Симулятор, политики и Frozen 60 не трогали.
Ввод не слали (`hid_sent=false`, `dry_run=true`). Guest-софт не писали.
Скрытый стол не был источником принятого замера.

Окно: id **13745**, title `Windows 11`, owner `Parallels Desktop`,
bundle `com.parallels.desktop.console`. Точки 2056×1290, захват
4112×2580, scale 2. Профиль
[parallels_l2.json](../../config/window_profiles/parallels_l2.json).
Маски HUD пустые.

## 30 с, запрошено 30 FPS

JSON: [live-s2/parallels-30s.json](live-s2/parallels-30s.json).
SHA1 `8a8c6c24e99fd0e616906f6453859a069a1f5355`.

| метрика | значение |
|---|---|
| elapsed | 30.13 с |
| frames (latest) | 676 |
| median_interval_ms | **33.76** |
| achieved_fps | **29.62** |
| drops_ratio | **0.0** |
| black_frames_ratio | **0.0** |
| capture_latency_ms p50/p95 | 10.97 / 12.73 |
| mean_luma_p50 | 76.08 |
| resizes | 0 |
| transport | stdout_pipe, 4 копии |
| h7_30s_window | true |
| h7_status | **accepted** |

`pytest tests/test_h7_probe.py tests/test_sck.py` — 13 passed.

Это не ≤3 мс render→NumPy, не HUD, не живой HID и не клиент в контуре.
`evaluate` по умолчанию SCK не включает.
