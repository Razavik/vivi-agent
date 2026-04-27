# Статус доработок агента

Легенда: ✅ Выполнено · 🔄 Выполняется следующим · ⏳ Ожидает

---

## Этап A — Срочные исправления фундамента

| #   | Кейс                                                                                         | Статус |
| --- | -------------------------------------------------------------------------------------------- | ------ |
| A-1 | `run_id` в каждом запуске саб-агента                                                         | ✅     |
| A-2 | Переделать `delegate_parallel` — возвращает список по `run_id`, а не словарь по `agent_name` | ✅     |
| A-3 | Исправить UI-корреляцию событий: все панели маппятся по `run_id`                             | ✅     |
| A-4 | Потокобезопасная память (`ChatMemoryStore`): file lock + atomic write через `os.replace`     | ✅     |
| A-5 | Нормализовать event schema: `event_type`, `run_id`, `agent_name`, `payload`                  | ✅     |
| A-6 | Усилить валидатор аргументов инструментов                                                    | ✅     |

---

## Этап B — Управляемые run

| #   | Кейс                                                                               | Статус |
| --- | ---------------------------------------------------------------------------------- | ------ |
| B-1 | `RunRegistry` — центральный реестр активных и завершённых run                      | ✅     |
| B-2 | `RunController` — cancel / pause / resume / inbox для каждого run                  | ✅     |
| B-3 | Backend API: `POST /runs/:id/cancel`, `pause`, `resume`, `message`, `replace-task` | ✅     |
| B-4 | Frontend: run-центричная модель, кнопки управления в AgentChatPage                 | ✅     |
| B-5 | Persist runs при рестарте сервера (`RunStateStore`)                                | ✅     |
| B-6 | Восстановление interrupted run при старте                                          | ✅     |
| B-7 | `GET /runs/:id` — детальная карточка одного run                                    | ✅     |

---

## Этап C — Двустороннее управление

| #   | Кейс                                                                              | Статус |
| --- | --------------------------------------------------------------------------------- | ------ |
| C-1 | inbox/outbox в `RunController`                                                    | ✅     |
| C-2 | `post_message` директора в саб-агент                                              | ✅     |
| C-3 | `replace_task` во время выполнения                                                | ✅     |
| C-4 | Interruption points в `SubAgent.run()` — проверка cancel/pause/inbox между шагами | ✅     |
| C-5 | `ask_director` — саб-агент задаёт вопрос директору и ждёт ответ                   | ✅     |
| C-6 | MessageBus — формальная шина с типами, correlation id, логированием               | ✅     |
| C-7 | outbox саб-агента → директор (произвольные сообщения, не только вопросы)          | ✅     |

---

## Этап D — Настоящий supervisor

| #    | Кейс                                                                                                                         | Статус |
| ---- | ---------------------------------------------------------------------------------------------------------------------------- | ------ |
| D-1  | `SupervisorLoop` — фоновый мониторинг зависших run                                                                           | ✅     |
| D-2  | Алерты `hang_detected`, `stale_paused`, `waiting_timeout`                                                                    | ✅     |
| D-3  | WS-стриминг `supervisor_alert` в UI в реальном времени                                                                       | ✅     |
| D-4  | `GET /api/supervisor/alerts` — polling fallback                                                                              | ✅     |
| D-5  | UI-компонент алертов: fixed overlay, badge-счётчик в NavBar                                                                  | ✅     |
| D-6  | `supervisor_observations` в prompt директора                                                                                 | ✅     |
| D-7  | Директор-инструменты управления run: `view_runs`, `cancel_run`, `pause_run`, `resume_run`, `message_run`, `replace_task_run` | ✅     |
| D-8  | Автономный шаг директора по триггеру от supervisor (без нового сообщения юзера)                                              | ✅     |
| D-9  | `WorldState` — структурированное состояние системы для директора                                                             | ✅     |
| D-10 | `reprioritize_run` — смена приоритета активного run                                                                          | ✅     |
| D-11 | `wait_for_event` — директор блокируется до события                                                                           | ✅     |

---

## Этап E — Граф задач и артефакты

| #   | Кейс                                                                                  | Статус |
| --- | ------------------------------------------------------------------------------------- | ------ |
| E-1 | `ArtifactStore` — потокобезопасное хранилище артефактов на диске                      | ✅     |
| E-2 | `ArtifactTools` для саб-агентов: `create_artifact`, `read_artifact`, `list_artifacts` | ✅     |
| E-3 | `GET /api/runs/:id/artifacts`, `GET /api/runs/:id/artifacts/:name`                    | ✅     |
| E-4 | UI артефакт-браузер в AgentChatPage (вкладка «Артефакты»)                             | ✅     |
| E-5 | Артефакты видны в `AgentRun.artifacts` (реестр)                                       | ✅     |
| E-6 | Dependency graph между run: `wait_for_artifact`, `mark_artifact_ready`                | ✅     |
| E-7 | `handoff_run` — передача результата одного run как входа другому                      | ✅     |
| E-8 | `dependency_ready` event — автоматический запуск ждущего run                          | ✅     |
| E-9 | GC-политика артефактов (TTL или ручная очистка)                                       | ✅     |

---

## Этап F — Стабилизация платформы

| #   | Кейс                                                                             | Статус |
| --- | -------------------------------------------------------------------------------- | ------ |
| F-1 | Atomic write в памяти саб-агентов                                                | ✅     |
| F-2 | Защита от битого JSON в `ChatMemoryStore`                                        | ✅     |
| F-3 | Crash diagnostics / export логов сессии                                          | ✅     |
| F-4 | Replay/debug mode — воспроизведение сессии по event log                          | ⏳     |
| F-5 | Миграция на SQLite (sessions, runs, messages, events, artifacts, agent_memory)   | ⏳     |
| F-6 | `schema_version` + retention policy в памяти                                     | ✅     |
| F-7 | Recovery незавершённых run при рестарте (сейчас — `interrupted`, нет авто-retry) | ✅     |
| F-8 | Сохранение pending confirmations при рестарте                                    | ✅     |

---

## Наблюдаемость (раздел 2.12)

| #   | Кейс                                                                 | Статус |
| --- | -------------------------------------------------------------------- | ------ |
| O-1 | Event log саб-агентов (`sub_agent_started`, `step`, `finished`, ...) | ✅     |
| O-2 | Supervisor dashboard: алерты, badge в NavBar                         | ✅     |
| O-3 | Latency tool call / LLM call в метриках run                          | ⏳     |
| O-4 | Число retries и interrupts в `AgentRun`                              | ✅     |
| O-5 | Timeline событий в UI                                                | ⏳     |
| O-6 | Inbox/outbox просмотр в UI                                           | ⏳     |

---

## Безопасность и policy (раздел 2.9)

| #   | Кейс                                                               | Статус |
| --- | ------------------------------------------------------------------ | ------ |
| S-1 | Базовый `SafetyPolicy` — риск-уровни инструментов                  | ✅     |
| S-2 | User confirmation для опасных инструментов                         | ✅     |
| S-3 | `PathGuard` — ограничение файловых путей                           | ✅     |
| S-4 | Проверка типов аргументов инструментов                             | ✅     |
| S-5 | Run-level permissions (read-only / file-write / destructive / ...) | ✅     |
| S-6 | Квоты: max_steps, max_tool_calls, runtime, внешние запросы         | ✅     |
| S-7 | Orchestration loop detection                                       | ✅     |
| S-8 | Deadlock detection                                                 | ✅     |

---

## Тесты (раздел 2.15)

| #    | Кейс                                                        | Статус |
| ---- | ----------------------------------------------------------- | ------ |
| T-1  | Unit: `RunRegistry` (upsert, update, list_active, snapshot) | ✅     |
| T-2  | Unit: `SubAgent` cancel / pause / resume / replace_task     | ✅     |
| T-3  | Unit: `ArtifactStore` CRUD                                  | ✅     |
| T-4  | Unit: `ChatMemoryStore` atomic write, thread safety         | ✅     |
| T-5  | Unit: `ActionValidator` типы и схемы аргументов             | ✅     |
| T-6  | Integration: директор + один саб-агент                      | ⏳     |
| T-7  | Integration: pause/resume/cancel/replace-task               | ⏳     |
| T-8  | Integration: саб-агент задаёт вопрос директору              | ⏳     |
| T-9  | Integration: handoff между агентами                         | ⏳     |
| T-10 | Concurrency: параллельная запись памяти                     | ✅     |
| T-11 | Concurrency: несколько run одного агента                    | ✅     |
| T-12 | Failure injection: битый JSON, падение LLM, обрыв WS        | ✅     |

---

## Промпты и поведение моделей (раздел 2.11)

| #   | Кейс                                                            | Статус |
| --- | --------------------------------------------------------------- | ------ |
| P-1 | Директор: инструкции по реакции на `supervisor_observations`    | ✅     |
| P-2 | Директор: видит список активных run                             | ✅     |
| P-3 | Директор: не ждёт завершения одного run перед запуском другого  | ✅     |
| P-4 | Саб-агенты: progress updates, heartbeat, blocked-состояние      | ✅     |
| P-5 | Межагентное общение: structured output вместо свободного текста | ✅     |

---

## Итого

| Статус                   | Кол-во |
| ------------------------ | ------ |
| ✅ Выполнено             | 65     |
| 🔄 Выполняется следующим | 0      |
| ⏳ Ожидает               | 11     |
