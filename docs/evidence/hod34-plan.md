# План: ход 34 — H7 на видимом окне Parallels

Дата плана: 2026-09-17. Цифр замера здесь нет.

## Гипотеза / отклонение

На видимом окне Parallels (`Windows 11`, bundle `com.parallels.desktop.console`)
медиана интервала ≤ 50 мс, drop < 0.10, black < 0.05 за 30 с.

Отклоняем, если медиана > 80 мс, black ≥ 0.10, захват требует скрытого
стола, или нет кадра.

## Не делаем

Ввод, guest-софт, sim/, control/, Frozen 60, HUD-маски.

## Команда

```text
python -m l2_brain capture permission
python -m l2_brain capture list
python -m l2_brain capture record --window-id <id> --duration 30 --fps 30 \
  --profile config/window_profiles/parallels_l2.json \
  --out docs/evidence/live-s2/parallels-30s.json
```

Прогон выполнен: [hod34-h7.md](hod34-h7.md). H7 принята.
