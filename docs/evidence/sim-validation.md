# Проверка навигационного стенда

Не оценка политики и не перенос в MMORPG. Статусы — корректность среды. Доказательства — тесты в `tests/test_sim_env.py` (38 в общем прогоне вместе с остальным пакетом; этот файл не содержит цифр успеха агента).

| Сценарий | Статус | Доказательство |
|---|---|---|
| open_goal | pass | `test_all_scenarios_reset_and_step`, `test_success_is_reaching_goal_not_a_pulse` |
| single_obstacle | pass | reset/step + `test_collision_stops_inside_wall` |
| narrow_gate | pass | reset/step |
| corridor | pass | reset/step |
| long_fence | pass | reset/step |
| u_trap | pass | reset/step |
| dead_end | pass | reset/step |
| weak_texture | pass | reset/step |
| moving_target | pass | reset/step |
| vanishing_target | pass | reset/step |
| camera_spin | pass | `test_camera_spin_does_not_move_body` |
| latency_drops | pass | `test_dropped_frame_changes_time_and_flags` |

Воспроизводимость: `test_same_seed_reproduces_frames_and_truth`.  
Разделение observation / ground truth: `test_agent_view_has_no_privileged_state`.  
Машинный отчёт: `l2-brain sim-eval` пишет JSON с seed и config каждого эпизода.

Ограничения переноса: перспективный синтетический рендер, цветная цилиндрическая цель, нет HUD, нет латентности клиента. Успех на стенде не доказывает работу в MMORPG.
