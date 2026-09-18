# Кинематический отсекатель long_fence и срез Frozen 60

Дата: 2026-09-17. Контроллер не меняли. Порог 0.12 не снижали. F14/F15 SHA без изменений
(`8f90a697f1a348dfea2547041e609e32fba4d265` / `6b7644ee7163fed22e62cb82d3d924dff7ae5c19`).

Полная таблица: [post-h22/report.md](post-h22/report.md).
Frozen: [post-h22/frozen-post-h22.json](post-h22/frozen-post-h22.json).
Забор 250: [post-h22/long-fence-250.json](post-h22/long-fence-250.json). ADR-0028.

## long_fence training v0, seed=0

На 200 тиках: timeout, LOS 182, acq 183, dist 4.47 (hod22).  
На 250 тиках: **success 244**, col=0, LOS 183, acq 184, конец dist=0.74.
Ожидание 220–230 не подтвердилось.

## Frozen 60, seed=0, 200 тиков

**46/60** (post-h14 было 44/60). oscillate 11→0. weak 0/5→5/5. box 0/5→3/5.  
Забор на каноне 200: 0/5. Регрессии: vanish 5/5→2/5; по одному на open_goal, gate, corridor.
