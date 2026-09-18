# Ход 80: L1 encoder + L2 spot, кап 10 фрагов

Дата: 2026-09-18. Frozen L1 и `sim/` не трогали. Фарм не открывали.

## Что сделано в коде

`src/l2_brain/live/spot_loop.py` — живой зонд, не Circuit.

| слой | поведение |
|---|---|
| Зрение | каждый тик: `HUDParser` + `NavigationEncoder` |
| L1 | если движение ≥600 мс и `|expansion|<0.01` → peel 350 мс + slide `w` 450 мс |
| L2 SCAN | 2×F1; лок → COMBAT |
| L2 ROAM_SEARCH | стрелка 450 мс, 4×`w` 450 мс с паузой 50 мс; лимит 15 холостых |
| L2 COMBAT | двойной F2; нет урона 8 с → L1-проверка и повтор F2 |
| L2 LOOT | 3×F3 шаг 350 мс, пауза 400 мс, `kills+=1` |

Кап 10 `EntityDefeated` / 360 с. `w` ≤450 мс (≤800, ADR-0064).
CLI: `l2-brain s4-integrated-spot --kills 10 --timeout 360`.
Выход: `docs/evidence/live-s4/integrated-spot-series-10.json`.

`tactical.py` / `spot_agent.py` не меняли: это синтетический стек.

## Проверки

`pytest tests/test_spot_loop.py tests/test_s4_probe.py` — 27 зелёных.

Скриптованные факты (не клиент):

- 10 фрагов, 30×F3, `farm=false`, `stuck_keys=0`, F4 нет;
- roam → лок → килл;
- 15 холостых roam → `roam_limit`;
- в COMBAT при нулевом expansion срабатывают `l1_peel` / `l1_slide`.

## Живой прогон

JSON: [integrated-spot-series-10.json](live-s4/integrated-spot-series-10.json)
SHA1 `ed36f5eb…`. Окно 16372, PID 68342. Dual flags. 251.9 с.

`ok=false`, `aborted=self_hp_low`, **7/10** фрагов. `farm=false`.
`stuck_keys=0`, `watchdog_tripped=false`. Старт self HP 0.94.
Банки F4 не слали. Порог стопа self HP 0.15.

| kill | search_ms | combat_ms | loot_ms | L1 в этом бое |
|---|---|---|---|---|
| 1 | 395 | 2822 | 1533 | 0 |
| 2 | 340 | 1389 | 1842 | 0 |
| 3 | 253 | 2599 | 1845 | 1 |
| 4 | 346 | 12407 | 1824 | 3 |
| 5 | 1584 | 12004 | 1832 | 3 |
| 6 | 343 | 2667 | 1858 | 0 |
| 7 | 1483 | 14344 | 1750 | 3 |

Средний бой по семи фрагам ≈ **6.89 с**. Всего roam **24**, L1
срабатываний **60**. F1 58, F2 19, F3 21.

Поток: 1276 сэмплов, `|expansion|≥0.01` только у 16, mag>0.05 у 296,
пик mag 0.328. L1 часто ловит «stuck» на нулевом expansion (трава),
не только упор в стену.

Перцентили тика, мс:

| стадия | p50 | p95 |
|---|---|---|
| observe | 1.69 | 3.01 |
| parse | 13.08 | 14.90 |
| encode | 45.44 | 53.60 |
| infer | 0.015 | 0.042 |
| act | 0.49 | 485.2 |

`act` p95 ≈ 485 мс — в выборку попали удержания стрелки/`w`, не
пустой post. `e2e_p95_ms` 557 из этой суммы, это не H8.

F80. ADR-0068.
