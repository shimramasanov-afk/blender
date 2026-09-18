# Biomimetic L2 Agent

Непрерывный контур **наблюдение → рекуррентный контроллер → моторное действие → новое наблюдение**.

Это исследовательский репозиторий, не готовый игровой бот. Первая рабочая поверхность — **локальный синтетический стенд**. Живой клиент MMORPG в контур не подключён.

## Документы

- [Цель и границы](docs/vision.md)
- [Архитектура и интерфейсы](docs/architecture.md)
- [Факты и гипотезы](docs/assumptions.md)
- [Этапы](docs/roadmap.md)
- [Журнал решений](docs/decisions.md)
- [Отчёт о работе](docs/work-report.md)

Операционные инструкции агента (`AGENTS.md` и подобные) человек пишет сам. Репозиторий их не подменяет.

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m l2_brain mock --ticks 16 --seed 0 --record run/mock-session.jsonl
python -m l2_brain doctor
python -m l2_brain eval --controller reactive --scenario open_field --episodes 8
python -m l2_brain sim-eval --seed 0 --split training --max-steps 4 --out run/nav-suite.json
python -m l2_brain record --ticks 16 --seed 0 --out run/exp-demo --log-level ERROR
python -m l2_brain inspect run/exp-demo --tick 2
python -m l2_brain replay run/exp-demo --mode speed --speed 0 --no-sleep
python -m l2_brain capture permission
python -m l2_brain capture record --self-test --ticks 8 --out run/sck-demo
python -m l2_brain inspect run/sck-demo --tick 1
python -m l2_brain vision bench --repeats 8 --out docs/evidence/vision-bench.json
python -m l2_brain vision diag --out run/vision-diag.ppm
python -m l2_brain baseline-eval --seed 0 --out docs/evidence/baseline-nav.json
```

## Что есть в коде

- прозрачный `BaselineController` (без обучения) и CLI `baseline-eval`;
- `NavigationEncoder`: сектора, эталонный поток, расширение, пеленг, уверенности (не детектор объектов);
- ScreenCaptureKit → `SCKFrameSource` (pipe RGB, не клиент игры);
- `HUDParser` + `calibrate-hud --from-png`: ROI Interlude; TargetLost ≠ победа; слоты F1–F3 (F47);
- `s4-probe`: один 15с живой зонд (F49), не фарм;
- запись эксперимента: кадры, признаки, телеметрия, intent, команда, стадии задержки (p50/p95/p99);
- replay offline / realtime / speed / step и `inspect` одного тика;
- headless навигационный стенд `l2_brain.sim` (12 сцен, перспективная камера, GT отдельно);
- контур `FrameSource → Encoder → Controller → Decoder → InputBackend` на mock-кадрах;
- CLI: `mock`, `record`, `replay`, `inspect`, `eval`, `doctor`, `sim-eval`, `capture`, `vision`, `baseline-eval`, `s4-probe`;
- три стендовых контроллера: `reactive`, `recurrent`, `snn`;
- синтетическая среда с эгоцентрическим кадром;
- helper ScreenCaptureKit в `macos/`; в контур входит только через `SCKFrameSource`.

## Чего нет в первой версии

Квесты, диалоги, торговля, инвентарь, многочасовые маршруты, произвольные классы, полный MaleCNS как зависимость, ручные карты, обход античита, скрытие ввода, инъекции и перехват учётных данных.
