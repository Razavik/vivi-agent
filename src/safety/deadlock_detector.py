"""DeadlockDetector — обнаружение дедлоков между run-ами через зависимости артефактов.

Дедлок: run A ждёт артефакт от run B, а run B ждёт артефакт от run A
(или любой цикл в графе зависимостей).

Использует DFS для поиска циклов в графе ожидания.
"""
from __future__ import annotations

from typing import Any


class DeadlockDetector:
    def __init__(self, dependency_graph: Any) -> None:
        self._graph = dependency_graph

    def detect(self) -> list[list[str]]:
        """Возвращает список циклов (каждый цикл — список run_id). Пустой список — дедлоков нет."""
        snap = self._graph.snapshot()
        # Строим граф ожидания: run_id → список run_id, которых он ждёт
        wait_graph: dict[str, set[str]] = {}
        for key, waiters in snap["waiters"].items():
            # key = "provider_run_id::artifact_name"
            parts = key.split("::", 1)
            if len(parts) != 2:
                continue
            provider_run_id = parts[0]
            for waiter in waiters:
                wait_graph.setdefault(waiter, set()).add(provider_run_id)

        cycles = []
        visited: set[str] = set()
        path: list[str] = []
        in_path: set[str] = set()

        def dfs(node: str) -> None:
            if node in in_path:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            in_path.add(node)
            path.append(node)
            for neighbor in wait_graph.get(node, set()):
                dfs(neighbor)
            path.pop()
            in_path.discard(node)

        for node in list(wait_graph.keys()):
            if node not in visited:
                dfs(node)

        return cycles

    def has_deadlock(self) -> bool:
        return bool(self.detect())

    def report(self) -> dict[str, Any]:
        cycles = self.detect()
        return {
            "deadlock_detected": bool(cycles),
            "cycles": cycles,
            "cycle_count": len(cycles),
        }
