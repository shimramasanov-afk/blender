# Ход 28: InputBackend, только dry-run

Дата: 2026-09-17. Живой HID не отправляли. Инъекций нет. S2/S3 не открыты.
Контракты `contracts.py` и симулятор не меняли. Baseline не трогали.

## Что сделано

Пакет `src/l2_brain/io/`:

- `actions.py` — CameraRotate, GroundClick, TargetSelect, SkillActivate,
  HoldKey, EmergencyStop, лог `InputEvent`.
- `profile.py` — шаблон `mmorpg_template_v0`, не замер клиента.
- `decoder.py` — `MotorIntent` → действия.
- `backend.py` — `DryRunInputBackend`; `dry_run=False` не конструируется.
- `safety.py` — `InputWatchdog`, timeout 250 мс, `release_all`.

Q1/Q3/Q5 остаются unknown. Профиль не есть привязка L2.

## Прогоны

`pytest tests/test_input_backend.py` — 6 passed.

`l2-brain input-dry-run --out docs/evidence/hod28/dry-run.json` —
6 событий, `hid_sent=false`.

JSON: [hod28/dry-run.json](hod28/dry-run.json).
SHA1 `b5445c38b9c4eb98429e43ec50933df051182e3a`.
