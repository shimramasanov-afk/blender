# Заморозка L1 и готовность каркаса к `control/snn`

Дата: 2026-09-17. Контроллер не меняли. Цифры — уже снятый
[frozen-hod23.json](hod23/frozen-hod23.json). ADR-0030.

F14/F15 и post-h22 не перезаписывались
(`8f90a697f1a348dfea2547041e609e32fba4d265` /
`6b7644ee7163fed22e62cb82d3d924dff7ae5c19` /
`724b5d708e65c132b1b0c6d4e90dfd3999ed1e69`).

## Канон, который замораживаем

Frozen 60, seed=0, 200 тиков: **52/60**. Δ к post-h22: +6/−0.

Законсервированы: `long_fence` 0/5 (ADR-0028), `single_obstacle` train v2 и val v3,
`moving_target` held_out v4.

## Готовность каркаса (осмотр кода, не прогон SNN)

Готово:

- Контурный протокол `CircuitController` в `l2_brain.circuit.protocols`:
  `initialize` / `reset_state` / `reset_weights` /
  `step(Observation, now_ns, intent_ttl_ns) -> MotorIntent`.
- Тот же вход, что у baseline: `contracts.Observation` + `NavigationEncoder`.
- Второй контроллер в том же протоколе уже существует как диагностика:
  `OracleSeek` в `control/diag_abc.py`. Пакет `control/snn/` может появиться
  рядом, не внутри `baseline.py`.
- Стендовый `controllers/snn.py` (`SpikingController`, `types.Action`) — другой
  контур (`ControlLoop` / H1–H5). Его не удалять и не «улучшать» в L1-ядро.

Зазор, не блокер песочницы:

- `control/eval.run_episode` сейчас создаёт только `BaselineController`.
  Первый шаг SNN получит свой вызов или аргумент контроллера. Это не повод
  править замороженные веса baseline.
- Пакета `src/l2_brain/control/snn/` ещё нет — так и должно быть до явной
  реализации LIF.
- H3/H4 по-прежнему про `evaluate` на `open_field` / `occluded` (20 эпизодов).
  Канон 52/60 их не закрывает и не заменяет.

Не готово и не открыто этим осмотром: живой HID, SCK в петле, L2/L3, MaleCNS,
сравнение SNN с baseline на Frozen 60.

Порог `< 2.0 мс` для будущего SNN на `open_goal:training:v0` — отдельный замер.
У baseline на Frozen 60 infer p50 был 0.051 мс; это не цифра SNN.
