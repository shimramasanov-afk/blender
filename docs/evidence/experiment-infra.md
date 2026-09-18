# Проверка инфраструктуры экспериментов

Не оценка политики. Доказательства — `tests/test_experiment.py` и CLI на mock-контуре.

| Возможность | Статус | Доказательство |
|---|---|---|
| Запись кадра / выбранной последовательности | pass | `test_session_inspect_shows_frame_intent_command_timings`, `test_keep_every_other_frame` |
| Метки времени и признаки | pass | inspect JSON: `timestamps`, `features` |
| Телеметрия, intent, отправленная команда | pass | inspect: `telemetry`, `intent`, `command` |
| Награда | pass | поле есть, в mock `null` |
| Диагностика / config / seed / версии | pass | `manifest.json` + `diagnostics` |
| p50/p95/p99 и n по стадиям | pass | `test_timing_report_has_percentiles_and_count`, `timing.json` |
| GPU без sync ≠ compute | pass | `test_unsynced_gpu_is_not_compute_time` |
| Latency ≠ throughput | pass | `test_latency_and_throughput_are_separate` |
| Latest-only + учёт пропусков | pass | `test_latest_only_queue_prefers_fresh_frame` |
| Запись не блокирует close-flush | pass | `test_async_writer_does_not_lose_on_close` |
| Replay realtime/speed/step | pass | `test_step_and_speed_replay`, CLI `--mode speed --no-sleep` |
| Offline ≠ closed-loop | pass | CLI replay `closed_loop: false` |

Ограничение переноса: запись mock-контура. Успех offline replay не есть успех другой политики в среде.
