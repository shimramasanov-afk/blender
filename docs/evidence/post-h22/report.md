# Post-H22 — кинематика забора и Frozen 60

Дата: 2026-09-17. Логику контроллера не меняли. F14/F15 не перезаписывались.

Команды и артефакты:

```text
# long_fence, frozen, seed=0, лимит 250 → docs/evidence/post-h22/long-fence-250.json
python -m l2_brain baseline-eval --seed 0 --suite frozen --max-steps 200 \
  --out docs/evidence/post-h22/frozen-post-h22.json
```

Контроллер: `baseline_memory_v1`. Энкодер: `navigation_v1`. Каналы: `all`.

## Шаг 1. `long_fence` при max_steps=250

Гипотеза «финиш v0 в 220–230» **отклонена**: training v0 закрывается на **244** тиках, col=0.
Прямая «acq + 4.47/0.12 ≈ 221» не учитывает доворот и выравнивание после захвата.

LOS/acq ниже — после шага, 1-based, порог детектора 0.12. На прогоне hod22 (лимит 200)
те же величины писались как 182/183 (сдвиг на 1 тик из-за момента выборки).
`wrap_tick` в JSON — первая защёлка `edge_seen` (v0: 111); фаза Post-Edge Wrap
на hod22 начиналась около 151 (align 8 + reslide 32).

| split | v | 200 тиков | 250 тиков | LOS / acq 0.12 | примечание |
|---|---|---|---|---|---|
| training | 0 | timeout 200, col=0 | **success 244**, col=0 | 183 / 184 | конец (10.76, 7.55), dist=0.74 |
| training | 1 | timeout 200, col=0 | **success 250**, col=0 | 185 / 186 | в самый край лимита, dist=0.73 |
| training | 2 | stuck 200, col=27 | stuck 250, col=77 | нет | срыв в ребро, не бюджет |
| validation | 3 | timeout 200, col=0 | timeout 250, col=0 | 197 / 198 | конец dist=1.30 |
| held_out | 4 | stuck 200, col=26 | stuck 250, col=76 | нет | held-out переворот, не бюджет |

На измеренной траектории v0 бюджет **200 — кинематический отсекатель**, не доказательство, что обход «не работает».
Варианты v2/v4 — отдельные сбои управления (коллизии, LOS нет).

## Шаг 2. Frozen 60, seed=0, 200 тиков

**46 / 60** успехов. train 29/36, val 9/12, held-out 8/12.

| Исход | post-h14 | post-h22 |
|---|---|---|
| success | 44 | **46** |
| oscillate | 11 | **0** |
| stuck | 3 | 7 |
| timeout | 2 | 7 |

Причины post-h22: none 46, control 10, mixed 3, vision 1.  
encode p50 3.92 мс, infer p50 0.047 мс.  
Recovery: GT-окон 2, детекций 4, TP 0, FP 4.

Это не замена F14 (23/60), H15 (24/60) и не «закрытый каталог».

### По сценам

| Сцена | post-h14 | post-h22 | провалы post-h22 |
|---|---|---|---|
| `open_goal` | 5/5 | **4/5** | held_out v4 timeout |
| `narrow_gate` | 5/5 | **4/5** | training v1 stuck |
| `corridor` | 5/5 | **4/5** | held_out v4 timeout |
| `u_trap` | 5/5 | 5/5 | — |
| `dead_end` | 5/5 | 5/5 | — |
| `vanishing_target` | 5/5 | **2/5** | train v0/v1, val v3 stuck |
| `camera_spin` | 5/5 | 5/5 | — |
| `latency_drops` | 5/5 | 5/5 | — |
| `moving_target` | 4/5 | 4/5 | held_out v4 stuck (как было) |
| `single_obstacle` | 0/5 | **3/5** | train v2, val v3 timeout |
| `weak_texture` | 0/5 | **5/5** | — |
| `long_fence` | 0/5 | 0/5 | 3 timeout, 2 stuck |

Δ к post-h14: **+8 / −6**, нетто **+2**.  
Прирост: weak 5 и box 3. Потери: vanish 3, open_goal / gate / corridor по одному.

Осцилляции у стены (11 на post-h14) сняты.

### 14 незакрытых на 200 тиках

Кинематика длинной траектории (timeout, col=0, на 250 v0/v1 финиш):

- `long_fence` training v0, v1
- `long_fence` validation v3 (на 250 всё ещё timeout, dist=1.30)

Сбой управления / геометрии варианта (не «просто мало тиков»):

- `long_fence` training v2, held_out v4 — stuck, коллизии, LOS нет
- `single_obstacle` training v2, validation v3 — timeout
- `vanishing_target` training v0/v1, validation v3 — stuck (регрессия к post-h14)
- `open_goal` held_out v4 — timeout
- `narrow_gate` training v1 — stuck
- `corridor` held_out v4 — timeout
- `moving_target` held_out v4 — stuck, как на post-h14
