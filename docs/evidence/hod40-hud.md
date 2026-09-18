# Ход 40: рамка цели отдельно от полоски HP

Дата: 2026-09-17. `sim/` и Frozen L1 не трогали. HID не слали.
S4 не открыт. Кадры только уже записанные F45 / F44.

## Зачем

После хода 39 `target_locked` был равен «есть красные пиксели».
Пустая полоска (смерть, рамка ещё висит) выглядела как «цели нет».
FSM не отличал победу от сброса.

## Кадры

F45 [interlude-target-active.png](live-s4/interlude-target-active.png)
JSON [calibrate-hud-hod40.json](live-s4/calibrate-hud-hod40.json)
SHA1 `6ccf7c1988e4e6963be032cb7e9a4128c62dd1a4`.

| поле | значение |
|---|---|
| `target_locked` | **true** |
| `target_hp_ratio` | **0.444** |
| `target_dead` | **false** |
| `hid_sent` | **false** |

F44 [client-reference.png](live-s4/client-reference.png)
JSON [calibrate-hud-hod40-f44.json](live-s4/calibrate-hud-hod40-f44.json)
SHA1 `178f956fb5b73baf1b3b86037c93d30c5fa161e9`.

| поле | значение |
|---|---|
| `target_locked` | **false** |
| `target_hp_ratio` | **null** |
| `target_dead` | **false** |

CLI: `l2-brain calibrate-hud --from-png <png> --tag hod40`.

## Правило

`detect_target_plate`: тёмно-коричневая подложка Classic / канавка
пустой полосы / красная заливка. Контраст камня (F44) не проходит:
brown 0.005 против 0.69 на виджете Gremlin.

Если рамка есть — `locked=true`, HP читается отдельно и может быть 0.0
(`target_dead=true`). Если рамки нет — `locked=false`, `target_hp=None`.

Синтетика: пустая подложка → locked + hp 0.0.
Тот же кадр F45 без красных пикселей в `target_hp` → locked + dead.

## Шина

`VisionTelemetryBridge` шлёт `EntityDefeated(is_target=True, source=ui_vision)`
один раз, когда раньше было locked и hp>0, а теперь:

- рамка есть и hp=0, или
- рамка пропала.

`entity_id=0` (с пикселей id нет). `xp_gained=0`.
Повтор на том же трупе не публикуется.

Ограничение: ручной сброс цели (Escape) после живой рамки выглядит
как `EntityDefeated`. Отдельного признака «снял сам» нет.

## Тесты

`tests/test_target_lifecycle.py`. `pytest` зелёный.
Замкнутый контур / S4 не гоняли.

## Чего нет

S4. H8. H14. Живой ввод. Поиск виджета при перетаскивании.
Хотбар. Q6.
