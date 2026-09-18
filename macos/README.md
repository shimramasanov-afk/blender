# ScreenCaptureKit helper

Минимум API: macOS 12.3 (`ScreenCaptureKit`). Проверялось на 27.0. Запрошенный FPS не гарантия.

Сборка:

```bash
python -c "from l2_brain.capture.helper import build_helper; print(build_helper())"
```

или `swiftc` всех файлов в `macos/CaptureProbe/` в `.build/capture-probe`.

Рамки парковки UI (без захвата, клики навылет):

```bash
python -m l2_brain layout-overlay --window-id 16372 --seconds 180
```

Сборка: `macos/LayoutOverlay/main.swift` → `.build/layout-overlay`.

Команды:

```bash
.build/capture-probe
.build/capture-probe --permission
.build/capture-probe --list-json
.build/capture-probe --stream --window-id <id> --fps 30
.build/capture-probe --self-test --max-frames 12 --fps 20 --resize
```

`--permission` только читает `CGPreflightScreenCaptureAccess`. Не вызывает `CGRequestScreenCaptureAccess`.

Транспорт потока — stdout, пакеты `L2F1` + JSON + RGB8. Shared memory нет.

Python:

```bash
python -m l2_brain capture permission
python -m l2_brain capture list
python -m l2_brain capture record --self-test --ticks 8 --out run/sck-demo
python -m l2_brain inspect run/sck-demo --tick 1
```

Профиль ROI/масок: `config/window_profiles/generic.json`. Координаты HUD конкретной игры туда не класть из общего модуля.
