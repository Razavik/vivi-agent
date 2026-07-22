from __future__ import annotations

import threading
import time
from typing import Any, Callable


class SupervisorLoop:
    """Фоновый supervisor: периодически проверяет active runs и эмитит alerts.

    Эвристики:
    - hang_detected: running, но нет обновлений > hang_threshold секунд.
    - stale_paused: paused дольше stale_paused_threshold секунд.
    - waiting_timeout: waiting_input дольше hang_threshold*2 секунд.
    """

    def __init__(
        self,
        get_active_runs: Callable[[], list[dict[str, Any]]],
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
        tick_interval: float = 10.0,
        hang_threshold: float = 60.0,
        stale_paused_threshold: float = 300.0,
        alert_cooldown: float = 30.0,
        dependency_graph: Any | None = None,
    ) -> None:
        self._get_active_runs = get_active_runs
        self._event_sink = event_sink
        self._tick_interval = tick_interval
        self._hang_threshold = hang_threshold
        self._stale_paused_threshold = stale_paused_threshold
        self._alert_cooldown = alert_cooldown
        self._dependency_graph = dependency_graph

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_alert_time: dict[str, float] = {}
        self._last_deadlock_check: float = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="supervisor")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.wait(self._tick_interval):
            self._tick()

    def _tick(self) -> None:
        now = time.time()
        active_runs = self._get_active_runs()

        for run in active_runs:
            run_id = run.get("run_id", "")
            if not run_id:
                continue

            status = run.get("status", "")
            updated_at = run.get("updated_at") or 0
            created_at = run.get("created_at") or 0
            step = run.get("step", 0)
            idle_time = now - updated_at
            age = now - created_at

            # cooldown per run_id
            last_alert = self._last_alert_time.get(run_id, 0)
            if now - last_alert < self._alert_cooldown:
                continue

            alert: dict[str, Any] | None = None

            if status == "running" and idle_time > self._hang_threshold:
                alert = {
                    "type": "hang_detected",
                    "run_id": run_id,
                    "agent_name": run.get("agent_name", ""),
                    "task": run.get("task", ""),
                    "idle_seconds": round(idle_time, 1),
                    "step": step,
                    "age_seconds": round(age, 1),
                    "message": f"Run {run_id} ({run.get('agent_name', '')}) висит {round(idle_time)} сек на шаге {step}",
                }

            elif status == "paused" and idle_time > self._stale_paused_threshold:
                alert = {
                    "type": "stale_paused",
                    "run_id": run_id,
                    "agent_name": run.get("agent_name", ""),
                    "task": run.get("task", ""),
                    "idle_seconds": round(idle_time, 1),
                    "message": f"Run {run_id} ({run.get('agent_name', '')}) в паузе {round(idle_time)} сек",
                }

            elif status == "waiting_input" and idle_time > self._hang_threshold * 2:
                alert = {
                    "type": "waiting_timeout",
                    "run_id": run_id,
                    "agent_name": run.get("agent_name", ""),
                    "task": run.get("task", ""),
                    "idle_seconds": round(idle_time, 1),
                    "message": f"Run {run_id} ({run.get('agent_name', '')}) ждёт ввода {round(idle_time)} сек",
                }

            if alert is not None:
                self._last_alert_time[run_id] = now
                self._emit("supervisor_alert", alert)

        # Deadlock detection каждые 60 секунд
        if self._dependency_graph is not None and now - self._last_deadlock_check > 60.0:
            self._last_deadlock_check = now
            try:
                from src.safety.deadlock_detector import DeadlockDetector
                detector = DeadlockDetector(self._dependency_graph)
                report = detector.report()
                if report["deadlock_detected"]:
                    self._emit("supervisor_alert", {
                        "type": "deadlock_detected",
                        "cycles": report["cycles"],
                        "message": f"Обнаружен дедлок между run: {report['cycles']}",
                    })
            except Exception:
                pass

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            try:
                self._event_sink(event, payload)
            except Exception:
                pass
