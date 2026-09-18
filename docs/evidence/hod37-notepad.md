# Ход 37: live-probe в Блокнот, без L2.exe

Дата: 2026-09-17. `sim/` и политики не трогали. `L2.exe` в `tasklist`
не было. HID ушёл в хост-PID Parallels при фокусе `prl_client_app`.

## Прогон

`l2-brain input-probe --target-pid 68342 --live --live-confirmed`

JSON: [live-s3/notepad-probe.json](live-s3/notepad-probe.json)
SHA1 `a1d962a3fde15200abbebf5550fa0d5d56ea7d24`.

| метрика | значение |
|---|---|
| hid_sent | **true** |
| aborted | null |
| stuck_keys_count | **0** |
| watchdog_tripped | **true** |
| act_ms p50 / p95 | 215.6 / 244.1 |
| guest | notepad Console, без l2.exe |

Кадр окна после прогона: [live-s3/notepad-after.png](live-s3/notepad-after.png).
В открытом Notepad (файл `l2.log`, не клиент) строка начинается с `123`.
Это не пустой Untitled и не процесс `L2.exe`.

## Чего нет

S4. H8. Ввод в игровой процесс. Идеальная чистая серия `www` в пустом файле.
