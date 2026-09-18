# Факты и гипотезы

Разделение жёсткое. Факт можно цитировать в решении. Гипотезу — только вместе со способом отвергнуть.

## Проверенные факты этого репозитория

| ID | Формулировка | Основание |
|---|---|---|
| F1 | Каталог `L2_brain` на 2026-09-16 был пуст: не было кода, документов и инструкций агента. | Листинг каталога при старте |
| F2 | Первая целевая машина — Apple M4 Max, arm64, Darwin. | `uname -m`, `sysctl machdep.cpu.brand_string` |
| F3 | На машине есть Python 3.14 и Swift 6.3. | `python3 --version`, `swift --version` |
| F4 | Системный Python 3.14 не содержит numpy и pytest. Стенд идёт из локального `.venv`. | `import numpy` на системном интерпретаторе |
| F5 | MaleCNS — коннектом ЦНС самца дрозофилы (~1.7×10⁵ тел в публикации FlyEM), не игровая политика MMORPG. | Описание датасета FlyEM Male CNS; пакет `natverse/malecns` |
| F6 | Известные замкнутые прогоны полного MaleCNS используют аналитическое зрение (пеленг и угловой размер), не пиксели камеры игры. | Описание runtime Fly.exe / NeuroMechFly: нет camera pixels в контуре |
| F7 | Живой клиент и HID по-прежнему закрыты. Старый `ScreenCaptureKitSource.start()` на Observation-API поднимает `NotImplementedError`. Контурный `SCKFrameSource` пишет кадры реального окна в `Frame`. | `tests/test_live_blocked.py`, `run/sck-demo` |
| F8 | `macos/CaptureProbe` собирается Swift 6.3 и получает список видимых окон через ScreenCaptureKit (на прогоне 2026-09-16: 1 дисплей, 21–22 окна). | Запуск `.build/capture-probe` |
| F9 | На 8 эпизодах `open_field` (`--seed 0`) `reactive` и `recurrent` дали success=1.00; это дымовой прогон S0, не приёмка H1. | `python -m l2_brain.evaluate` |
| F10 | Headless стенд `l2_brain.sim` воспроизводит кадр и позу по seed; `AgentView` не несёт GT; успех = достижение цели. Это не перенос в MMORPG. | `tests/test_sim_env.py`, `sim-eval` |
| F11 | Сессию mock-контура можно записать и открыть тик: кадр, признаки, намерение, команда, задержки p50/p95/p99. Offline replay не closed-loop. | `tests/test_experiment.py`, `l2-brain inspect` |
| F12 | Self-test окно ScreenCaptureKit: 12 тиков, scale 2, медиана интервала 49.6 мс при запросе 20 FPS, 2 resize, rgb8 pipe. Это не H7 и не клиент MMORPG. | `docs/evidence/sck-self-test.json` |
| F13 | `NavigationEncoder` на 48×32 отличает синтетический сдвиг от зума (6/6) и поворот камеры от подхода на стенде; 32×24 это разделение на стенде не даёт. encode p50≈36.6 мс. Детектора объектов нет. | `docs/evidence/vision-bench.json`, `tests/test_vision.py` |
| F14 | `BaselineController` на полном каталоге seed=0: 23/60 успехов (train 14/36, val 5/12, held-out 4/12). Провалы: vision 20, control 17, oscillate 0. Не перенос и не H15. | `docs/evidence/baseline-nav.json` |
| F15 | `baseline_memory_v1` на том же каталоге seed=0: 23/60, ловушки 10/10 ticks_p50=117.5, простые 13/15 — как F14. GT-окон застревания 0, восстановлений 0, ложных срабатываний 0. Улучшение ловушек не подтверждено. Не биология и не H15. | `docs/evidence/baseline-memory-nav.json` |
| F16 | После `repair-20260917` снимок `baseline_memory_v1` + `navigation_v1` на frozen seed=0: 24/60 (train 15/36, val 5/12, held-out 4/12). Не замена F14: другие метрики и контроллер. | `docs/evidence/h15/all.json` |
| F17 | H15 на том же каталоге: blob 22, target 22, flow 21, expansion 20, all 24. Δ all−blob = +0.033 < 0.15, гипотеза отклонена. | `docs/evidence/h15/summary.json` |
| F18 | Векторизация SAD: `reference_flow` 22.0 → 1.67 мс, поля совпали с цикловым эталоном. encode p50 на `all` = 3.82 мс. Не Metal. | `docs/evidence/vision-flow-vectorize.md` |
| F19 | Ход 14, seed=0, 8 сцен × 5 вариантов: 39/40. `narrow_gate` 5/5 (v0 84 тика), `corridor` 5/5 (v0 94), `latency_drops` 5/5 (v0 76), `open_goal`/`dead_end`/`u_trap` 5/5. Не замена F14/F15. | `docs/evidence/hod14-nav.json`, `docs/evidence/hod14-report.md` |
| F20 | Post-h14 Frozen 60, seed=0, до обхода: 44/60 (success 44, oscillate 11, stuck 3, timeout 2). Стена/забор/weak 0/15. Не замена F14. | `docs/evidence/post-h14/frozen-baseline.json` |
| F21 | На спавне `brake_risk≈0.43` у `dead_end` и у стены: unknown/нет prev-frame, это не «нос в барьер». `steer`/`expansion` на тике 0 тоже низкие у обеих. Стенд не скользит по AABB: любой заступ радиуса 0.28 отменяет весь шаг. | прогон сенсоров 2026-09-17; `environment._integrate` |
| F22 | Счётчик свободного хода до первого фронта (`steer≥0.18` или `expansion≥0.03`) разделяет тупик и барьер без имён сцен: `dead_end`/`u_trap` probe=9/2 shallow, стена/забор/weak 46/36/55 deep. `dead_end` success 147. LOS у стены после глубокого Probe + Peel 26 + Slide не открылся. | [hod18-probe-gate.md](evidence/hod18-probe-gate.md) |
| F23 | Конечный Slide 22 + hook `-sign` открывает LOS на компактном боксе (seen 118) и даёт финиш: `single_obstacle` 190, `weak_texture` 191. `dead_end` 147 без hook. `long_fence` без LOS — грани 8.4 м бюджет Slide не закрывает. | [hod19-corner-hook.md](evidence/hod19-corner-hook.md) |
| F24 | После Peel 120° боковой pressure во время Slide не отличает бокс от забора (стена вне FOV). Inward hook с фронтом после 26 тиков — рабочий признак длинной кромки. `single_obstacle` 193, `weak_texture` 190, `dead_end` 147. `long_fence` доходит южнее торца (`min_y=3.11`), LOS нет. | [hod20-edge-loss.md](evidence/hod20-edge-loss.md) |
| F25 | Capped wrap + вынос + seek после `edge_seen` открывает LOS на `long_fence` (seen 185, acq 186, col=0). Финиша в 200 тиках нет (timeout, dist=5.12). Контрольные без регрессии: `dead_end` 147, `single_obstacle` 193, `weak_texture` 190. | [hod21-post-edge-wrap.md](evidence/hod21-post-edge-wrap.md) |
| F26 | Разгон Probe до 0.75 ломает компактный бокс: expansion 0.08 на подходе неотличим от контакта тупика. Обрезка только wrap-пути (reslide 32, clear 8, sprint 1.0) даёт `long_fence` acq 183 / dist=4.47, timeout 200. Контрольные 147 / 193 / 190. | [hod22-budget-trim.md](evidence/hod22-budget-trim.md) |
| F27 | post-h22 Frozen 60 seed=0: 46/60 (post-h14 было 44/60). `long_fence` training v0 при 250 тиках — success 244, col=0, LOS 183, acq 184; на каноне 200 — timeout. Ожидание финиша 220–230 и счёта 50–54 отклонены. | [post-h22/frozen-post-h22.json](evidence/post-h22/frozen-post-h22.json), [post-h22/long-fence-250.json](evidence/post-h22/long-fence-250.json), [post-h22/report.md](evidence/post-h22/report.md) |
| F28 | hod23 Frozen 60 seed=0: 52/60. Ровно +6 к post-h22, новых провалов нет. vanish / open_goal / gate / corridor 5/5. Забор на 200 без изменений (v0 timeout col=0). | [hod23/frozen-hod23.json](evidence/hod23/frozen-hod23.json), [hod23-course-hold.md](evidence/hod23-course-hold.md) |
| F29 | Эвристический L1 (`baseline_memory_v1`) заморожен на каноне 52/60. Восемь незакрытых эпизодов законсервированы. Пакет `control/snn` ещё не создан. Протокол `CircuitController` уже есть. Это не закрытие H3/H4 и не S2. | ADR-0030, [hod23-l1-freeze.md](evidence/hod23-l1-freeze.md) |
| F30 | `snn_core_v1` на CPU: 6 тестов LIF зелёные. `open_goal:training:v0` timeout 200, infer_ms_p50=1.653 (<2), средняя частота 52.2 Гц. Не Frozen 60, не H3/H4. | [hod24/open-goal-training-v0.json](evidence/hod24/open-goal-training-v0.json), [hod24-snn-sandbox.md](evidence/hod24-snn-sandbox.md) |
| F31 | Жёсткий Брайтенберг без STDP: `open_goal:training:v0` success 61, col=0, infer_ms_p50=1.704. Физиология 9/9. Не Frozen 60. | [hod25/open-goal-training-v0.json](evidence/hod25/open-goal-training-v0.json), [hod25-braitenberg.md](evidence/hod25-braitenberg.md) |
| F32 | Мини-бенч n=1 `open_goal:training:v0:s0`: baseline 72, GRU 162, SNN 61, все success, col=0. GRU H=16, 1186 весов, K=1, infer p50=0.070 мс. SNN 4480 stored, state 128, K=50, infer p50=1.627 мс. Не Frozen 60, не H3/H4. | [hod26/open-goal-training-v0.json](evidence/hod26/open-goal-training-v0.json), [hod26-gru-bench.md](evidence/hod26-gru-bench.md) |
| F33 | R-STDP на `w_in` + привилегированный `RewardEngine`. 10 численных тестов зелёные. Шумный контроль `open_goal` v0: 59 тиков; eval после 8 эпизодов: 58. Δ=1, n=1, не каталог. Observation без дистанции. | [hod27/open-goal-rstdp.json](evidence/hod27/open-goal-rstdp.json), [hod27-rstdp.md](evidence/hod27-rstdp.md) |
| F34 | `l2_brain.io` dry-run: 6 тестов зелёные. Лог MotorIntent→GameAction без HID (`hid_sent=false`). `dry_run=False` не конструируется. Не S2/S3 и не живой клиент. | [hod28/dry-run.json](evidence/hod28/dry-run.json), [hod28-input-dry-run.md](evidence/hod28-input-dry-run.md) |
| F35 | Синтетический бой `combat_dummy_v0`: success 80 тиков, урон 100, FSM SEEK→VICTORY. Атака без лока и вне 1.8 м урона не даёт. Observation без дистанции. HID нет. Не клиент. | [hod29/combat-dummy-v0.json](evidence/hod29/combat-dummy-v0.json), [hod29-combat.md](evidence/hod29-combat.md) |
| F36 | Профиль 100 тиков: encode p50≈3.8 мс, SNN infer p95=1.70 мс, GRU 0.096 мс. MPS GEMM N=64 B=1: 0.156 vs CPU 0.003 мс. H6 отклонена. `numpy_cpu`. | [hod30/profiling-m4.json](evidence/hod30/profiling-m4.json), [hod30-profiling.md](evidence/hod30-profiling.md) |
| F37 | Синтетический экстракт N=208 E=616 на `open_goal:training:v0:s0`: snn 61, bio 178, shuffle 191, ER timeout 200. Полный MaleCNS не загружался. H11 не принята. | [hod31/malecns-comparison.json](evidence/hod31/malecns-comparison.json), [hod31-malecns.md](evidence/hod31-malecns.md) |
| F38 | Мини-сводка 5×5, seed=0: baseline 5/5, snn_v1 4/5, snn_rstdp 4/5, malecns_bio 4/5, gru 3/5. Нейросети stuck на `single_obstacle`. Не Frozen 60. | [hod32/final-comparison.json](evidence/hod32/final-comparison.json), [hod32-suite.md](evidence/hod32-suite.md) |
| F39 | Спот `multi_dummy_arena_v0`, 250 тиков, seed=0: 4 фрага, 4 лута, серия 4, FSM полная, HID нет. Watchdog сбрасывает недосягаемую цель. | [hod33/spot-loop.json](evidence/hod33/spot-loop.json), [hod33-spot-loop.md](evidence/hod33-spot-loop.md) |
| F40 | 30.13 с видимого окна Parallels `Windows 11` (id 13745, 4112×2580, scale 2): медиана интервала 33.76 мс, 29.62 FPS, drops 0, black 0, latency p50/p95 10.97/12.73 мс. H7 принята. HID нет. | [live-s2/parallels-30s.json](evidence/live-s2/parallels-30s.json), [hod34-h7.md](evidence/hod34-h7.md) |
| F41 | Синтетический HUD-парсер: ratio полос 100/50/0% в пределах ±2%; рамка цели есть/нет; чёрный кадр `valid=False`; шина `source=ui_vision`. Живой Classic UI не размечали. GT стенда не снимали. | [hod35-hud.md](evidence/hod35-hud.md), `tests/test_hud_parser.py` |
| F42 | `CGEventInputBackend` без двух флагов не конструируется. Live-probe 2026-09-17 aborted: в госте `l2.exe`, `hid_sent=false`. Watchdog keyUp проверен на RecordingPoster, stuck=0. Клавиши в Блокноте не подтверждены. | [hod36-cgevent.md](evidence/hod36-cgevent.md) |
| F43 | Повторный live-probe: `L2.exe` нет, Notepad Console есть. `hid_sent=true`, stuck=0, watchdog keyUp `w`. act_ms p50/p95 215.6/244.1 мс. Кадр окна: в Notepad строка начинается с `123`. | [live-s3/notepad-probe.json](evidence/live-s3/notepad-probe.json), [hod37-notepad.md](evidence/hod37-notepad.md) |
| F44 | Фокус NSWorkspace p50/p95 0.0047/0.0055 мс; контроль osascript p50 175.9 мс. act_ms RecordingPoster 0.016 мс, hid_sent=false. SCK 4112×2580 окна 13944: оконный Interlude, плейсхолдеры HUD мимо полос. | [hod38/focus-bench.json](evidence/hod38/focus-bench.json), [live-s4/calibrate-hud.json](evidence/live-s4/calibrate-hud.json), [hod38-prep.md](evidence/hod38-prep.md) |
| F45 | Офлайн Interlude 4112×2580 с целью Gremlin: self CP/HP/MP 0.962/0.943/0.952 при тексте 50/50, 126/126, 38/38; target_locked=true, target_hp=0.444 (без текста). F44 на этих ROI — нули и нет замка. HID нет. | [live-s4/calibrate-hud-hod39.json](evidence/live-s4/calibrate-hud-hod39.json), [hod39-hud.md](evidence/hod39-hud.md) |
| F46 | После разделения рамки и HP: F45 locked=true hp=0.444 dead=false; F44 locked=false hp=None. Пустая подложка и F45 без красных пикселей → locked+dead. `EntityDefeated` с `ui_vision` на переходе живой→0/пропажа. HID нет. | [live-s4/calibrate-hud-hod40.json](evidence/live-s4/calibrate-hud-hod40.json), [hod40-hud.md](evidence/hod40-hud.md) |
| F47 | Drop при HP 0.44: нет `EntityDefeated`, есть `TargetState(locked=false)`. Победа — HP=0 на рамке или пропажа при HP≤0.08. F45: F1/F2/F3 ready. Затемнённый слот не ready. HID нет. | [live-s4/calibrate-hud-hod41.json](evidence/live-s4/calibrate-hud-hod41.json), [hod41-hud.md](evidence/hod41-hud.md) |
| F48 | Оператор 2026-09-17 подтвердил: уже в мире на этом стенде. Чат F44: `LineageII Interlude Server`. Персонаж BotEbaniy. Говорящий остров / цель Gremlin (F45). Q6 этой сессии закрыт. Это не локальный L2J, не сборка клиента и не открытие S4. | [q6-admission.md](evidence/q6-admission.md), [hod38-prep.md](evidence/hod38-prep.md), [hod39-hud.md](evidence/hod39-hud.md) |
| F49 | S4-зонд 2026-09-17 окно 13944: 5.43 с, 76 тиков, hid_sent=true, self_hp 0.943, lock hp 0.444 за 116 мс, F2 без дельты HP, Escape, stuck=0, watchdog=false. Не килл. Не H8. | [live-s4/first-combat-probe.json](evidence/live-s4/first-combat-probe.json), [hod42-s4.md](evidence/hod42-s4.md) |
| F50 | clean-target 2026-09-17 окно 13944: сброс (dead plate), F1×3 все HP 0.444, abort `clean_hp_low`, F2 нет, damage=false, 4.61 с, 64 тика, stuck=0. Не новый моб. Не 95%. | [live-s4/second-combat-probe.json](evidence/live-s4/second-combat-probe.json), [hod43-s4.md](evidence/hod43-s4.md) |
| F51 | engage-any 2026-09-17 окно 13944: F1 lock 0.444, F2×2, HP 0.444→0.366, damage=true, f2_to_hp_drop 1031 мс, 2.58 с, 34 тика, stuck=0. Не килл. | [live-s4/combat-damage-probe.json](evidence/live-s4/combat-damage-probe.json), [hod44-s4.md](evidence/hod44-s4.md) |
| F52 | kill-and-loot 2026-09-17 окно 13944: 0.444→0.0, EntityDefeated, time_to_kill 6685 мс, F3 hid_sent, 9.14 с, 130 тиков, stuck=0. Лут в инвентаре не читали. | [live-s4/kill-loot-probe.json](evidence/live-s4/kill-loot-probe.json), [hod45-s4.md](evidence/hod45-s4.md) |
| F53 | multi-kill 2026-09-17 окно 13944: 3 фрага, 3 F3, 27.33 с, 397 тиков, stuck=0, watchdog=false, farm=false. Каждый цикл 0.444→0.0. Лут в инвентаре не читали. | [live-s4/multi-kill-probe.json](evidence/live-s4/multi-kill-probe.json), [hod46-s4.md](evidence/hod46-s4.md) |
| F54 | verify-search 2026-09-17 окно 13944: F1×2 miss, CameraRotate dx=150, w 400 мс (up ~425 мс), F1, abort search_no_target, 7.69 с, stuck=0, watchdog=false. Лока и килла нет. | [live-s4/search-maneuver-probe.json](evidence/live-s4/search-maneuver-probe.json), [hod47-s4.md](evidence/hod47-s4.md) |
| F55 | keyboard-search 2026-09-17 окно 13944: F1 lock 0.444, right_arrow 450 мс hid_sent, без мыши, 0.444→0.0 за 5864 мс, F3, 9.26 с, stuck=0. walk нет. Yaw не измерен. | [live-s4/keyboard-search-probe.json](evidence/live-s4/keyboard-search-probe.json), [hod48-s4.md](evidence/hod48-s4.md) |
| F56 | calibrate-motion 2026-09-17 окно 13944: right_arrow+w по 500 мс, yaw_shift 20.8 px peak 0.023, step 165 px peak 0.034, deg_per_sec 0.76 при FOV 75° (допуск), 1.81 с, stuck=0. confidence=low. Не H8. | [live-s4/motion-calibration.json](evidence/live-s4/motion-calibration.json), [hod49-s4.md](evidence/hod49-s4.md) |
| F57 | bench-h8 2026-09-17 окно 13944: n=100, p95 observe+infer+act **2.19** мс, pipeline+parse **16.33** мс, encode p95 **44.26** мс, hid_sent=false, stuck=0. Горизонт 15–30% × 25–75%: peak **0.013**, yaw −204 px, −7.44 °/с (FOV 75° допуск), unreliable. Профиль не писали. | [live-s4/h8-latency-report.json](evidence/live-s4/h8-latency-report.json), [live-s4/motion-calibration-v2.json](evidence/live-s4/motion-calibration-v2.json), [hod50-s4.md](evidence/hod50-s4.md) |
| F58 | KLT yaw 2026-09-17 окно 13944: OpenCV PyrLK, right/left 450 мс, features 43/39, inliers **22/25** (<30), ratio 0.815/0.926, median_dx −2.09 / 0.00, deg/s −0.085 / 0, stuck=0. reliable=false. Профиль не писали. | [live-s4/motion-calibration-klt.json](evidence/live-s4/motion-calibration-klt.json), [hod51-s4.md](evidence/hod51-s4.md) |
| F59 | motion v3 2026-09-17 окно 13944: RMB Drag +150 px (5×10 мс) и 10 тапов right_arrow. OpenCV PyrLK, features 55/62, inliers **39/39**, ratio 0.830/0.780, median_dx −0.001 / +0.004, hid_sent=true, stuck=0. physical=false. Профиль не писали. | [live-s4/motion-calibration-v3.json](evidence/live-s4/motion-calibration-v3.json), [hod52-s4.md](evidence/hod52-s4.md) |
| F60 | sync-diag 2026-09-17 окно 13944: T0/T1 `.copy()`, settle 300 мс, unique ts. RMB hold +200 px: diff_mean **7.05**, Δt **371** мс, inliers 41, median_dx −0.007. Arrow 600 мс: diff **7.81**, Δt **984** мс, dx −0.002. `unique_frame=true`, `shares_memory=false`, `identical_frames_error=false`, `sck_desync=false`. hid_sent=true, stuck=0. Профиль не писали. | [live-s4/motion-sync-diag.json](evidence/live-s4/motion-sync-diag.json), [live-s4/calibration_t0.png](evidence/live-s4/calibration_t0.png), [live-s4/calibration_t1.png](evidence/live-s4/calibration_t1.png), [hod53-s4.md](evidence/hod53-s4.md) |
| F61 | live-motion 2026-09-17 окно 13944: 10+3 тика `w` 600 мс, hid_sent=true, stuck=0, 8.66 с. `flow_magnitude` 0/0, `expansion` 0/0, `motion_confidence` 0.399/0.404, encode p50 **47.4** мс p95 **48.0** мс, `stuck_detected=false`. Frozen L1 не меняли. | [live-s4/l1-flow-validation.json](evidence/live-s4/l1-flow-validation.json), [hod54-s4.md](evidence/hod54-s4.md) |
| F62 | live-motion 2026-09-17 окно 13944 у ворот деревни: 10+3 тика `w` 600 мс, hid_sent=true, stuck=0, 8.66 с. `flow_magnitude` 0.0089/0 (два тика 0.045/0.043), `expansion` 0/0, `motion_confidence` 0.513/0.530, encode p50 **46.8** мс p95 **50.1** мс, `flow_ratio` ∞, `stuck_detected=false`. Frozen L1 не меняли. Артефакт F61 не перезаписывали. | [live-s4/l1-flow-validation-village.json](evidence/live-s4/l1-flow-validation-village.json), [hod55-s4.md](evidence/hod55-s4.md) |
| F63 | live-motion 2026-09-17 окно 13944 у стены: 10+3 тика `w` 600 мс, hid_sent=true, stuck=0, 8.67 с. `flow_magnitude` 0.0137/0 (три тика 0.043/0.043/0.050), `expansion` 0/0, `motion_confidence` 0.452/0.161, encode p50 **47.0** мс p95 **48.4** мс. blocked[1..2]: `duplicate=true`, confidence 0. `flow_ratio` ∞, `stuck_detected=false`. Frozen L1 не меняли. | [live-s4/l1-flow-validation-wall.json](evidence/live-s4/l1-flow-validation-wall.json), [hod56-s4.md](evidence/hod56-s4.md) |
| F64 | live-motion 2026-09-17 окно 13944 подход+упор: 10+3 тика `w` 600 мс, hid_sent=true, stuck=0, 8.65 с. `flow_magnitude` 0.0139/0 (пик free[1] **0.095**), `expansion` 0/0. free[5..9] и все blocked: `duplicate=true`, confidence 0. encode p50 **43.3** мс p95 **47.7** мс. `stuck_detected=false`. Frozen L1 не меняли. | [live-s4/l1-flow-validation-approach.json](evidence/live-s4/l1-flow-validation-approach.json), [hod57-s4.md](evidence/hod57-s4.md) |
| F65 | live-motion 2026-09-17 окно 13944 непрерывный `w`: 2 события HoldKey, stuck_keys=0, watchdog=false, 8.34 с. `flow_magnitude` 0.0048/0 (пик free[4] 0.048), `expansion` 0/0. С free[6] `duplicate=true`, confidence 0. encode p50 **44.7** мс p95 **48.4** мс. `stuck_detected=false`. Frozen L1 не меняли. | [live-s4/l1-flow-validation-hold.json](evidence/live-s4/l1-flow-validation-hold.json), [hod59-s4.md](evidence/hod59-s4.md) |
| F66 | live-motion 2026-09-18 окно **16372** PID 68342, непрерывный `w`, 8.32 с, stuck_keys=0. `flow_magnitude` **0.0436**/0, пик free[9] **0.231**, free[1] label `approach`, expansion_free **0.004**. blocked[1..2] `duplicate=true`. encode p50 **47.4** мс p95 **48.8** мс. `stuck_detected=false`. Frozen L1 не меняли. | [live-s4/l1-flow-validation-restart.json](evidence/live-s4/l1-flow-validation-restart.json), [hod61-s4.md](evidence/hod61-s4.md) |
| F67 | nudge 2026-09-18 окно 16372: 3 сэмпла `w` 500 мс, hid_sent=true, 2 HoldKey, stuck_keys=0, 1.92 с. Все тики `duplicate=true`, confidence 0, flow 0. Кадр не менялся. Сеть не измеряли. | [live-s4/l1-nudge-after-stall.json](evidence/live-s4/l1-nudge-after-stall.json), [hod62-s4.md](evidence/hod62-s4.md) |
| F68 | Два срыва сессии Interlude сразу после непрерывного `live-motion` ≥8 с: вечером 2026-09-17 после F65; утром 2026-09-18 после F66 (клик рисует метку, шага нет, F67 кадр мёртвый). Пульс F61–F64 той же сессии 17-го без такого отчёта. Сокет не снимали. `L2.exe` 8852 снят `taskkill` 2026-09-18. | [hod63-s4.md](evidence/hod63-s4.md) |
| F69 | nudge 2026-09-18 окно 16372 после нового `L2.exe` 3840: 3×500 мс, 1.93 с, hid_sent=true, stuck_keys=0, stall_risk=false. `duplicate` 0/3, flow 0 / 0.048 / 0.056, среднее **0.034**, confidence ≈ 0.31. Кадр менялся. | [live-s4/l1-nudge-h17.json](evidence/live-s4/l1-nudge-h17.json), [hod64-s4.md](evidence/hod64-s4.md) |
| F70 | nudge-b 2026-09-18 окно 16372: 3×500 мс, 2.19 с, hid_sent=true, stuck_keys=0. `duplicate` 0/3, flow 0/0/0, confidence 0.34/0.32/0.31. Кадр не замер. 8 с не слали. | [live-s4/l1-nudge-h17-b.json](evidence/live-s4/l1-nudge-h17-b.json), [hod65-s4.md](evidence/hod65-s4.md) |
| F71 | live-motion 2026-09-18 окно 16372, 10+3 × 600 мс, 8.66 с, hid_sent=true, stuck_keys=0. flow 0.014/0, пик free[5] 0.095. С free[7] `duplicate=true`. blocked[2] Δt **961** мс. `stuck_detected=false`. | [live-s4/l1-flow-validation-8s-h17.json](evidence/live-s4/l1-flow-validation-8s-h17.json), [hod66-s4.md](evidence/hod66-s4.md) |
| F72 | live-motion 2026-09-18 окно 16372 «основной»: 8.39 с, hid_sent=true, stuck_keys=0. flow 0.014/0, пик free[5] **0.136**. `duplicate` 0/13. `stuck_detected=false`. Оператор после F71 ходил сам. | [live-s4/l1-flow-validation-main.json](evidence/live-s4/l1-flow-validation-main.json), [hod67-s4.md](evidence/hod67-s4.md) |
| F73 | yaw v3 2026-09-18 окно 16372 у стены: RMB +150 и arrow pulse. KLT 39/39 и 40/37, ratio 1.00/0.93, median_dx **0** / −0.0005, physical=false, 1.85 с. Профиль не писали. Q5 не закрыт. | [live-s4/motion-calibration-wall.json](evidence/live-s4/motion-calibration-wall.json), [hod68-s4.md](evidence/hod68-s4.md) |
| F74 | yaw hard 2026-09-18 окно 16372: RMB +480 / 24×25 мс, 24 тапа стрелки, hold 800 мс. KLT 40/40 / 38 / 37, median_dx 0 / 0.003 / −0.004, physical=false, 3.63 с. Профиль не писали. Q5 не закрыт. KLT dx=0 ≠ «камера не ехала» (F75). | [live-s4/motion-calibration-wall-hard.json](evidence/live-s4/motion-calibration-wall-hard.json), [hod69-s4.md](evidence/hod69-s4.md) |
| F75 | 2026-09-18 оператор: на F74 камера развернулась ≈45°. KLT SEARCH=40 px; 45°/75° на 4112 px ≈ 2467 px, трекер алиасит стену в dx≈0. `coarse_shift` на roll 80 px даёт ≈81 px при KLT \|dx\|<20. Q5 не закрыт. Живого coarse JSON нет. | [hod70-s4.md](evidence/hod70-s4.md), `tests/test_klt_yaw.py` |
| F76 | yaw v3 2026-09-18 окно 16372: RMB +480 и 10 тапов. HID ушёл. T0≡T1 (буфер SCK без копии), coarse_peak 0.966, pixel_diff 0.15 / 6.84, physical=false, 6.91 с. Профиль не писали. | [live-s4/motion-calibration-wall-coarse.json](evidence/live-s4/motion-calibration-wall-coarse.json), [hod71-s4.md](evidence/hod71-s4.md) |
| F77 | yaw v3 2026-09-18 окно 16372: RMB +800 / 40×20 мс, 3.28 с. T0 стена, T1 площадь. coarse_dx **1313**, peak 0.093, pixel_diff 14.33, assumed_yaw_deg 23.9 (FOV 75°). KLT 2/37, median_dx 53.7, unreliable. physical=true (coarse). q5_closed=false. Стрелку не слали. Профиль не писали. | [live-s4/motion-calibration-wall-harder.json](evidence/live-s4/motion-calibration-wall-harder.json), [hod72-s4.md](evidence/hod72-s4.md) |

| F78 | Калибровка 2026-09-18, 30+ live, окно 16372. RMB ≤120 у стены часто dx=0; +150 скачок. corner-m50: coarse 54 / KLT 55, 2 инлаера. Крыша +40: coarse −270/−288. Площадь: KLT/coarse близки (44/36, 101/90), до 11 инлаеров. walk 66 и 34 px / 500 мс. Короткий flow 0.116, пик **0.238**. sync unique, desync нет. Q5 не закрыт. | [hod73-s4.md](evidence/hod73-s4.md), [live-s4/calib-loop/](evidence/live-s4/calib-loop/) |
| F79 | Калибровка 2026-09-18, 89 live JSON, окно 16372. `arrow_pulse` 1 тап: KLT −41.6 / 146 / 0.73 и −39.5 / 113 / 0.71. Код `q5_closed=true`, профиль нет (`|dx|<50`). RMB `pixel_diff≥12` часто помечает physical и режет fallback стрелки. 7 коротких `live-motion`: `stuck_detected=false`. Оператор: в этой батарее нигде не застревал. 8 с `w` не слали. H17 не закрыта. | [hod74-s4.md](evidence/hod74-s4.md), [live-s4/calib-loop/py2-2--45/](evidence/live-s4/calib-loop/py2-2--45/), [live-s4/calib-loop/py2-3-45/](evidence/live-s4/calib-loop/py2-3-45/) |
| F80 | Живой `s4-integrated-spot` 2026-09-18 окно 16372: 251.9 с, **7/10** фрагов, abort `self_hp_low`. roam 24, L1 60, F3 21, stuck_keys 0, farm false. encode p95 53.6 мс. SHA1 `ed36f5eb…`. Frozen L1 не меняли. | [hod80-s4.md](evidence/hod80-s4.md), [live-s4/integrated-spot-series-10.json](evidence/live-s4/integrated-spot-series-10.json) |
| F81 | Живой `s4-integrated-spot` 2026-09-18 окно 16372: **94.6 с**, **5/5**, `timeout_s=null`, abort нет. L1 0, агро 0, разворот 1, roam 11, F3 15, stuck_keys 0, farm false. Бои 2.2–4.3 с. SHA1 `63a421ac…`. Frozen L1 не меняли. | [hod81-s4.md](evidence/hod81-s4.md), [live-s4/spot-aggro-validation.json](evidence/live-s4/spot-aggro-validation.json) |
| F82 | Живой `s4-integrated-spot` 2026-09-18 окно 16372: **150.0 с**, **10/10**, `timeout_s=null`. L1 0, агро 2, разворот 2, roam 14, средний бой 3.35 с, stuck_keys 0, farm false. SHA1 `388921ec…`. Frozen L1 не меняли. | [hod82-s4.md](evidence/hod82-s4.md), [live-s4/spot-series-10-stable.json](evidence/live-s4/spot-series-10-stable.json) |
| F83 | Живой `s4-npc-dialog` 2026-09-18 окно 16372: 9.48 с, F5×2, `target_acquired=true` (hp 0), `dialog_detected=false`, клик нет, abort `dialog_timeout`. parse_dialog p95 99 мс. farm false. SHA1 `d016a14a…`. Frozen L1 не меняли. | [hod83-s4.md](evidence/hod83-s4.md), [live-s4/npc-dialog-probe.json](evidence/live-s4/npc-dialog-probe.json) |
| F85 | Живой `s4-npc-dialog --via-chat` 2026-09-18 окно 16372: 36.67 с, `/target` + F2 + ЛКМ (0.50, 0.48), HTML слева, **6/6** пунктов, `false_target_markers=0`, farm false. SHA1 `ce2cec6a…`. Frozen L1 не меняли. | [hod85-s4.md](evidence/hod85-s4.md), [live-s4/npc-menu-crawl.json](evidence/live-s4/npc-menu-crawl.json) |
| F86 | Живой `layout-slots` 2026-09-18 окно 16372: 1.330 с, чистый слот Б → Tab → занят → Escape → свободен. Слот А `[60, 140, 400, 520]`, слот Б `[1592, 650, 342, 307]`. farm false. SHA1 `1ac0f4eb…`. Frozen L1 не меняли. | [hod86-s4.md](evidence/hod86-s4.md), [live-s4/layout-slots-validation.json](evidence/live-s4/layout-slots-validation.json) |

F1–F7, F10–F83, F85–F86 — факты этого репозитория. F8–F9 — прогоны, не приёмка гипотез. H7 принята на F40. H8 принята на F57. H18 принята на F75.

## Внешние заметки, ещё не факты L2_brain

Записи соседнего проекта на этой машине. Для решений v1 они **не** являются измерениями.

| ID | Утверждение | Почему это ещё не факт отсюда |
|---|---|---|
| N1 | ScreenCaptureKit на скрытом окне Parallels даёт ошибку −3811. | Замер был в другом дереве, зонд этого репо его не повторил |
| N2 | `prlctl capture` занимал 0.45–0.7 с на кадр. | То же |
| N3 | Поток ScreenCaptureKit около 30 FPS достижим на видимом окне при drop-if-busy. | Снято здесь как F40; скрытый стол по-прежнему не путь |
| N4 | Игра шла в Parallels Desktop + Windows 11 ARM, не в CrossOver. | Конфигурация пользователя; этот репозиторий клиент не запускает |
| N5 | CrossOver / D3D9→OpenGL давал около 10 FPS и был признан тупиком. | Не воспроизводилось здесь |
| N6 | Курсовой угол персонажа не равен углу камеры. | Наблюдение другого контура |
| N7 | В чужом разборе присутствовал GameGuardQuery. | Сетевой разбор этому проекту запрещён как метод работы |
| N8 | Ручные маршруты и автомат фарма не дали устойчивого живого цикла. | Полезно как осторожность, не как метрика этого стенда |

Пока зонд в `macos/` не запишет свой файл в `docs/evidence/`, N1–N3 нельзя ставить в критерии приёмки.

## Как читать гипотезы

У каждой гипотезы четыре поля. Если нет метрики или нет условия отклонения — гипотеза нерабочая и в roadmap не попадает.

Сравнение контроллеров всегда на одном сиде, одном бюджете тиков и одном извлечении признаков.

---

## H1 — реактивный контроллер закрывает открытое поле

**Формулировка.** `reactive` достигает доли успеха ≥ 0.80 на 20 эпизодах `open_field` при бюджете 200 тиков.

**Проверка.**  
`python -m l2_brain.evaluate --controller reactive --scenario open_field --episodes 20 --seed 0`

**Метрика.** `success_rate`.

**Отклоняем, если** `success_rate < 0.80`. Тогда либо стенд непригоден как учебная задача, либо входной кадр не несёт пеленга.

## H2 — короткая память помогает при окклюзии

**Формулировка.** На 20 эпизодах `occluded` разность `success_rate(recurrent) − success_rate(reactive)` ≥ 0.25.

**Проверка.** Тот же `evaluate` для `recurrent` и `reactive`, сценарий `occluded`, одинаковый `--seed`.

**Метрика.** Δ успеха.

**Отклоняем, если** Δ < 0.25. Тогда рекуррентный базовый контроллер не даёт заявленного выигрыша, и память этой реализации не считается полезной на этой задаче.

## H3 — SNN лучше рекуррентного базового на окклюзии

**Статус.** Не начата. Канон 52/60 — это `baseline_memory_v1`, не SNN.
Песочница `control/snn` и мини-бенч `l2-brain bench` (ADR-0033) эту
гипотезу не закрывают.

**Формулировка.** На тех же 20 эпизодах `occluded` `success_rate(snn) − success_rate(recurrent)` ≥ 0.10.

**Проверка.** Таблица из одного прогона трёх контроллеров.

**Метрика.** Δ успеха относительно `recurrent`.

**Отклоняем, если** выигрыш < 0.10. Спайковый контроллер тогда не получает статуса основного. Это ожидаемый исход для v1, не провал проекта.

## H4 — SNN не хуже реактивного на открытом поле

**Статус.** Не начата. То же ограничение, что у H3: `evaluate` на
`open_field`, не Frozen 60 и не один эпизод `l2-brain bench`.

**Формулировка.** На `open_field` `success_rate(snn) ≥ success_rate(reactive) − 0.10`.

**Проверка.** 20 эпизодов, `--seed 0`.

**Метрика.** Успех SNN относительно реактивного.

**Отклоняем, если** SNN ниже реактивного больше чем на 0.10. Тогда спайковый контур ломает уже решённую задачу и не допускается в следующие этапы как кандидат политики.

## H5 — время сети не есть время контура

**Формулировка.** На стенде p95 `infer_ms` < 0.20 × p95 `loop_ms` для каждого из трёх контроллеров.

**Проверка.** Поля `infer_ms` / `loop_ms` в `EpisodeReport`, агрегат по 20 эпизодам `open_field`.

**Метрика.** Отношение p95.

**Отклоняем, если** для любого контроллера отношение ≥ 0.20. Тогда узкое место — сам контроллер, и разговор про MPS/Metal становится уместен. Если гипотеза держится, ускорять сеть бессмысленно, пока не измерен захват.

## H6 — MPS или Metal уменьшают infer достаточно, чтобы это меняло тик

**Формулировка.** Один и тот же контроллер на MPS или Metal даёт p95 `infer_ms` ≤ 0.70 от numpy-CPU, и абсолютный p95 CPU при этом ≥ 2 мс.

**Статус.** Отклонена (ход 30). Пути MPS в контроллерах нет. Микробенч
torch 2.14: на N=64 B=1 CPU быстрее; SNN infer p95=1.70 мс < 2 мс.

**Проверка.** `l2-brain profile` + `tests/test_mps_compatibility.py`.

**Метрика.** Speedup и абсолютный p95 CPU.

**Отклоняем, если** ускорение < 1.3× **или** CPU уже < 2 мс. В обоих случаях бэкенд остаётся `numpy_cpu`.

## H7 — ScreenCaptureKit даёт полезный поток на M4 Max

**Формулировка.** На видимом окне-источнике медиана интервала кадров ≤ 50 мс, доля чёрных/пустых кадров < 0.05, доля дропов < 0.10 на окне 30 с.

**Проверка.** `macos/CaptureProbe` пишет JSON в `docs/evidence/`. Источник — видимое окно, не скрытое.

**Метрика.** `median_frame_interval_ms`, `black_frame_rate`, `drop_rate`.

**Статус.** Принята 2026-09-17 на видимом окне Parallels (F40, ADR-0041).

**Отклоняем, если** медиана > 80 мс, либо black ≥ 0.10, либо поток требует скрытого окна. Тогда захват не принимается как сенсор контура, пока не найден другой легальный источник кадра.

## H8 — полная задержка управления пригодна для короткого зрительного навыка

**Формулировка.** p95 (`observe_ms + infer_ms + act_ms`) на живой связке захват+ввод ≤ 100 мс.

**Проверка.** Только после S2 и S3. Стендовый `loop_ms` эту гипотезу не закрывает.

**Метрика.** p95 полной задержки, не `infer_ms`.

**Статус.** Принята 2026-09-17 на живом окне 13944 (F57, ADR-0057):
p95(`observe+infer+act`) = 2.19 мс, n=100. `observe` — очередь SCK,
не фотон. encode p95 44.26 мс в формулу не входит; с encode p95
45.65 мс. act — idle-gate, не 100 игровых клавиш.

**Отклоняем, если** p95 > 150 мс. Тогда не утверждаем управление боем в реальном времени; остаётся медленный исследовательский контур.

## H9 — короткой памяти достаточно для v1

**Формулировка.** Рекуррентный контроллер с скрытым состоянием размерности ≤ 8 закрывает критерий H2 **или** юнит-пробу `memory_probe` с долей ≥ 0.80 на 20 эпизодах.

**Проверка.** `evaluate --controller recurrent --scenario memory_probe --episodes 20` и/или H2.

**Метрика.** Успех `memory_probe` и/или Δ на `occluded`.

**Отклоняем, если** оба теста провалены. Тогда либо задаче нужна карта, либо другая память — и это отдельное решение, не «добавим waypoints по умолчанию».

## H10 — стенд предсказывает порядок контроллеров вживую

**Формулировка.** Ранги успеха (`reactive`, `recurrent`, `snn`) на стенде совпадают с рангами на первом живом зрительном задании из 20 коротких эпизодов.

**Проверка.** Невозможна до этапа S4. До него гипотеза числится открытой, не истинной.

**Метрика.** Совпадение рангов (Kendall τ = 1 на трёх точках).

**Отклоняем, если** на живом задании есть инверсия ранга. Стенд тогда остаётся учебным, не прокси политики.

## H11 — фрагмент MaleCNS полезен как игровая политика

**Формулировка.** Контроллер, построенный из MaleCNS, проходит H4 и бьёт `recurrent` по правилу H3, а его p95 `infer_ms` на M4 Max < 10 мс.

**Проверка.** Тот же `evaluate`, отдельное имя контроллера. Ход 31 дал
синтетический экстракт на одном `open_goal`, без FlyEM и без H4/H3. H11
по-прежнему **не принята**.

**Метрика.** Успех и `infer_ms` p95.

**Отклоняем, если** любой из порогов не выполнен, либо нет отображения кадр→вход / спайки→`Action`. До такой проверки утверждение «MaleCNS уже играет» запрещено. Базово гипотеза **не принята**.

## H12 — биомиметический контур не застревает

**Формулировка, которую проект не принимает.** «Агент не застревает».

**Проверка.** Любая публикация такого обещания сверяется с `stuck_rate`.

**Метрика.** `stuck_rate` на объявленном наборе сценариев.

**Отклоняем обещание, если** `stuck_rate > 0.05`. Само наличие ненулевых застреваний не закрывает проект — закрывает только бездоказательное обещание.

## H13 — v1 обходится без ручной карты

**Формулировка.** Критерии H1 и приёмка стенда выполняются без waypoint-графа и без заранее записанного маршрута.

**Проверка.** В репозитории нет модуля маршрута, который читает оценка. Поиск по дереву: нет `waypoints`, нет `route graph` в `evaluate`.

**Метрика.** Бинарно: оценка зелёная и карта не подключена.

**Отклоняем, если** чтобы закрыть H1, в официальную оценку приходится добавить человеческий граф. Тогда меняется видение, не «временно положим yaml со спотом».

## H14 — кадра окна достаточно, чтобы видеть цель живого навыка

**Формулировка.** На размеченных 100 кадрах выбранного живого окна детектор целевого признака (модель или цвет) даёт precision ≥ 0.60 и recall ≥ 0.60.

**Проверка.** Только после рабочего захвата. Разметка — отдельный пакет в `docs/evidence/`.

**Метрика.** Precision, recall.

**Отклоняем, если** хотя бы одна величина < 0.60. Тогда пиксельный контур на этом окне не ставится, пока не изменены разрешение, ROI или признак. Сетевой разбор как замена кадра не является запасным путём этого проекта.

## H15 — каналы NavigationEncoder повышают успех политики

**Формулировка.** На одном наборе навигационных эпизодов контроллер с `Observation.navigation` даёт Δ success ≥ 0.15 против того же контроллера с одним color-blob.

**Проверка.** План `docs/evidence/h15/plan.md`, одинаковые seed и бюджет. База этой проверки — `color_blob` на том же коде, не F14.

**Метрика.** Δ `success_rate`.

**Отклоняем, если** Δ < 0.15. Сами по себе метки `approach`/`camera_turn` на синтетике и наличие `NavigationEncoder` эту гипотезу не закрывают.

**Статус.** Отклонена. `all` 24/60 против `blob` 22/60, Δ = +0.033. Поток или расширение по отдельности не лучше базы.

## H16 — явная память улучшает тупики и U-ловушки

**Формулировка.** `baseline_memory_v1` на seed=0 даёт выше успех или ниже `ticks_p50` на `u_trap`+`dead_end`, чем `baseline_v1`, и не теряет больше 2 успехов на `open_goal`+`camera_spin`+`moving_target`.

**Проверка.** `baseline-eval --seed 0 --compare docs/evidence/baseline-nav.json`.

**Метрика.** Успех и `ticks_p50` ловушек; успех простых сцен; отдельно recall/FP/время восстановления/успех восстановления/retrap.

**Отклоняем улучшение, если** Δ успеха ловушек = 0 и Δ `ticks_p50` = 0. Регрессию отклоняем отдельно, если успех ловушек падает или простые сцены падают больше чем на 2.

**Статус.** На прогоне F15 улучшение **не подтверждено** (10/10 vs 10/10, ticks 117.5 vs 117.5). Регрессии нет. Recall не определён: GT-окон неподвижности на каталоге 0.

## H17 — непрерывный `live-motion` рвёт сессию Interlude

**Формулировка.** Непрерывный `w` ≥8 с через `CGEventPostToPid` совпадает со срывом хода: клик рисует метку, персонаж не едет, пока не перезапустить `L2.exe`.

**Проверка.** После входа оператор ходит сам. Затем один короткий `w` ≤2 с. Затем один длинный ≥8 с. После каждого — клик в землю. Сессию не альттабить в момент замера, если проверяем только HID.

**Метрика.** Шаг после клика (да/нет) глазами оператора; `duplicate` на nudge.

**Отклоняем, если** длинный прогон не даёт срыва в 3 сессиях подряд, а короткий и длинный ведут себя одинаково. Принимаем, если срыв только после длинного, ≥2 раза.

**Статус.** Открыта. Сводка: [h17-report.md](evidence/h17-report.md).
Срыв F65/F66/F68. После релога короткие живые (F69/F70). После F71
оператор ходил. F72: 8 с без `duplicate`. F79: короткие yaw/`w`
500 мс, оператор не видел застревания. «Всегда рвёт сессию» не
подтверждено. Сокет не измеряли.

## H18 — KLT `|dx|≈0` не значит, что камера стоит

**Формулировка.** При `SEARCH=40` локальный KLT на периодичной стене
может дать median_dx≈0 при реальном yaw в десятки градусов.

**Проверка.** Оператор видит поворот; `coarse_shift` / `pixel_diff_mean`
на T0/T1; PNG. Синтетика: roll больше `SEARCH`.

**Метрика.** Согласие знака/порядка грубого dx с глазами; KLT
`|median_dx| < 2` при `|coarse_dx| ≥ 30` или `pixel_diff ≥ 12`.

**Отклоняем, если** на живых T0/T1 PNG нет видимого поворота, а
оператор подтверждает, что камера не ехала.

**Статус.** Принята 2026-09-18 (F75, ADR-0065). F74 остаётся
замером KLT, не доказательством нулевого yaw.
