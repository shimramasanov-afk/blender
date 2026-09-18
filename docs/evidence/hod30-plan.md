# План: ход 30 — профиль контура и аудит MPS

Дата плана: 2026-09-17. Цифр задержек здесь нет.

## Гипотеза / отклонение

На M4 Max при B=1 и текущих размерах (GRU H=16, SNN n=64) синхронизированный
GEMM на MPS не быстрее CPU, а p95 `infer` SNN уже < 2 мс. Тогда H6
отклоняется и бэкенд остаётся `numpy_cpu`.

Отклоняем «оставить CPU», если после sync MPS p50 < CPU p50 на N=64 B=1
**и** это меняет бюджет тика (infer p95 CPU ≥ 2 мс). Иначе CPU остаётся.

## База

Текущий контур: NumPy CPU, `accel.BACKEND=numpy_cpu`. Модели не менять.

## Независимые переменные

Устройство (cpu / mps) только в микробенче GEMM. Контроллер контура — имя
политики. Сцена: `open_goal:training:v0`, 10 warmup + 100 тиков.

## Метрики

Стадии: encode, infer, tactical, decode. p50/p95/p99/max в мс и мкс.
MPS: sparse/scatter/gather support, GEMM N=64/128, rtol=1e-4.

## Команда

```text
pytest tests/test_mps_compatibility.py tests/test_profiler.py -q
l2-brain profile --ticks 100 --out docs/evidence/hod30/profiling-m4.json
```

Оптимизаций и Metal-ядер в этом ходе нет.
