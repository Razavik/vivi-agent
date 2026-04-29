from __future__ import annotations

from typing import Any

from src.infra.agent_ops import AgentOpsService
from src.infra.diagnostics import DiagnosticsService
from src.web.context import ServerContext


class OpsRoutes:
    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx

    @property
    def ops(self) -> AgentOpsService:
        return AgentOpsService(self.ctx.settings, self.ctx)

    def diagnostics(self) -> dict[str, Any]:
        return DiagnosticsService(self.ctx.settings).run(self.ctx)

    def preflight(self) -> dict[str, Any]:
        return self.ops.preflight()

    def post_run_reviews(self) -> dict[str, Any]:
        return self.ops.list_post_run_reviews()

    def scorecard(self) -> dict[str, Any]:
        return self.ops.scorecard()

    def memory_inspector(self) -> dict[str, Any]:
        return self.ops.memory_inspector()

    def task_templates(self) -> dict[str, Any]:
        return self.ops.task_templates()

    def run_replays(self) -> dict[str, Any]:
        return self.ops.run_replays()

    def tool_contract_tests(self) -> dict[str, Any]:
        return self.ops.tool_contract_tests()

    def maintenance(self) -> dict[str, Any]:
        return self.ops.maintenance()

    def command_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.ops.safe_command_preview(str(body.get("command", "")))
