# Ход 71: coarse live, кадр не скопировали

Дата: 2026-09-18. Профиль не писали. Frozen L1 не трогали.

JSON: [motion-calibration-wall-coarse.json](live-s4/motion-calibration-wall-coarse.json)
SHA1 `4d79becf20861ca09db1c653e5806f03715a9814`.

PNG (копии, канон перезаписан ходом 72): [hod71-coarse/](live-s4/hod71-coarse/).

Окно 16372, 6.91 с. RMB +480 / 24×25 мс, затем 10 тапов стрелки.
`grab()` отдавал тот же буфер SCK: T0 и T1 RMB визуально те же,
`coarse_peak` 0.966, `pixel_diff` 0.15. Стрелка: diff 6.84.
`physical=false`. Q5 не закрыт.

F76. ADR-0066.
