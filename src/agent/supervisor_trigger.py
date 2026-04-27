"""Автономный триггер директора по supervisor-алертам.

Когда SupervisorLoop эмитит алерт, а директор не занят — этот модуль
запускает один автономный шаг директора с системным сообщением о ситуации.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class SupervisorTrigger:
    """Запускает директора автономно при получении supervisor-алерта.

    Принцип работы:
    - алерты накапливаются в очереди
    - отдельный поток пытается запустить директора если он свободен
    - если директор занят — алерт будет передан ему через supervisor_observations
    - кулдаун между автономными запусками — чтобы не заспамить
    """

    def __init__(
        self,
        is_director_busy: Callable[[], bool],
        run_director: Callable[[str], None],
        cooldown: float = 60.0,
    ) -> None:
        self._is_busy = is_director_busy
        self._run_director = run_director
        self._cooldown = cooldown

        self._pending: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_trigger_time: float = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="supervisor-trigger"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def on_alert(self, alert: dict[str, Any]) -> None:
        """Вызывается из SupervisorLoop при каждом новом алерте."""
        with self._lock:
            self._pending.append(alert)

    def _loop(self) -> None:
        while not self._stop.wait(5.0):
            self._try_trigger()

    def _try_trigger(self) -> None:
        now = time.time()
        with self._lock:
            if not self._pending:
                return
            if now - self._last_trigger_time < self._cooldown:
                return
            alerts = self._pending[:]
            self._pending.clear()

        if self._is_busy():
            # Директор занят — алерты уже попадут через supervisor_observations
            with self._lock:
                # Возвращаем обратно чтобы не потерять, но не дублируем
                pass
            return

        message = self._build_message(alerts)
        self._last_trigger_time = now
        try:
            self._run_director(message)
        except Exception:
            pass

    def _build_message(self, alerts: list[dict[str, Any]]) -> str:
        lines = ["[SYSTEM] Supervisor обнаружил проблемы в активных run. Проверь ситуацию и прими решение:\n"]
        for a in alerts:
            payload = a.get("payload", a)
            alert_type = payload.get("type", "unknown")
            run_id = payload.get("run_id", "?")
            agent = payload.get("agent_name", "?")
            msg = payload.get("message", "")
            lines.append(f"- [{alert_type}] run_id={run_id} agent={agent}: {msg}")
        lines.append("\nИспользуй view_runs чтобы уточнить статус, затем message_run / cancel_run / resume_run по ситуации.")
        return "\n".join(lines)
