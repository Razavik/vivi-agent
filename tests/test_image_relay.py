from __future__ import annotations

import base64

from src.agent.core.runtime import AgentRuntime
from src.agent.core.schemas import ActionStep, SubAgentResult
from src.agent.core.state import SessionState
from src.agent.core.sub_agent import SubAgent
from src.agent.lifecycle.agent_registry import AgentRegistry
from src.infra.artifact_store import ArtifactStore
from src.infra.chat_memory import ChatMemoryStore
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.agent_ops.delegate_tools import DelegateTools
from src.tools.core.registry import ToolRegistry, ToolSpec


class _FakeServerContext:
    """Достаточно ServerContext-подобия для save_image_artifact: create_artifact."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def create_artifact(self, run_id, name, content, mime_type):  # noqa: ANN001
        return self._store.create(run_id, name, content, mime_type)


class _StubClient:
    model = "stub-model"
    num_ctx = 4096

    def __init__(self, steps: list[ActionStep]) -> None:
        self._steps = steps
        self._i = 0

    def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
        step = self._steps[min(self._i, len(self._steps) - 1)]
        self._i += 1
        return step


def _image_tool_spec(b64: str = "ZmFrZS1pbWFnZQ==") -> ToolSpec:
    return ToolSpec(
        "read_chat_image",
        "скачать фото",
        0,
        lambda args: {"image": b64, "format": "image/png", "_type": "image", "caption": "cat"},
        {},
    )


def _make_sub_agent(tmp_path, client, tools, server_context=None) -> SubAgent:
    prompt = tmp_path / "agent.txt"
    prompt.write_text("# Тестовый агент\nДелай задачу.", encoding="utf-8")
    return SubAgent(
        name="telegram",
        display_name="Telegram",
        prompt_path=str(prompt),
        tools=tools,
        client=client,
        memory_store=ChatMemoryStore(tmp_path / "mem.json"),
        max_steps=5,
        server_context=server_context,
    )


class TestSubAgentImageArtifacts:
    def test_image_tool_saved_as_artifact_and_url_tracked(self, tmp_path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        ctx = _FakeServerContext(store)
        client = _StubClient([
            ActionStep(action="read_chat_image", args={}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
        ])
        agent = _make_sub_agent(tmp_path, client, [_image_tool_spec()], server_context=ctx)

        result = agent.run("посмотри фото", run_id="r1")

        assert result["image_urls"], "image_urls должен содержать URL сохранённого артефакта"
        url = result["image_urls"][0]
        assert url.startswith("/api/artifact-image/r1/")

    def test_no_server_context_still_works_without_urls(self, tmp_path) -> None:
        """Без server_context (например автономный запуск) картинка всё ещё
        видна модели (extracted_images), просто без публичного URL."""
        client = _StubClient([
            ActionStep(action="read_chat_image", args={}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
        ])
        agent = _make_sub_agent(tmp_path, client, [_image_tool_spec()], server_context=None)

        result = agent.run("посмотри фото", run_id="r1")

        assert result["success"] is True
        assert result["image_urls"] == []

    def test_finish_task_attach_images_embeds_markdown(self, tmp_path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        ctx = _FakeServerContext(store)
        client = _StubClient([
            ActionStep(action="read_chat_image", args={}, done=False),
            ActionStep(action="finish_task", args={"summary": "вот фото", "attach_images": True}, done=True),
        ])
        agent = _make_sub_agent(tmp_path, client, [_image_tool_spec()], server_context=ctx)

        result = agent.run("посмотри и пришли фото", run_id="r1")

        assert "![image](" in result["summary"]
        assert result["image_urls"][0] in result["summary"]

    def test_finish_task_without_attach_images_no_markdown(self, tmp_path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        ctx = _FakeServerContext(store)
        client = _StubClient([
            ActionStep(action="read_chat_image", args={}, done=False),
            ActionStep(action="finish_task", args={"summary": "вот фото"}, done=True),
        ])
        agent = _make_sub_agent(tmp_path, client, [_image_tool_spec()], server_context=ctx)

        result = agent.run("посмотри фото", run_id="r1")

        assert "![image](" not in result["summary"]
        # но URL всё равно доступен оператору отдельно
        assert result["image_urls"]

    def test_base64_never_leaks_into_persisted_memory(self, tmp_path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        ctx = _FakeServerContext(store)
        client = _StubClient([
            ActionStep(action="read_chat_image", args={}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово", "attach_images": True}, done=True),
        ])
        agent = _make_sub_agent(tmp_path, client, [_image_tool_spec("SUPER_SECRET_B64")], server_context=ctx)

        agent.run("задача", run_id="r1")

        mem = str(agent.memory_store.load())
        assert "SUPER_SECRET_B64" not in mem


class TestDelegateToolsImagePropagation:
    def test_normalize_result_propagates_image_urls(self) -> None:
        dt = DelegateTools(AgentRegistry())
        raw = {
            "run_id": "r1",
            "agent_name": "telegram",
            "success": True,
            "status": "done",
            "summary": "готово",
            "image_urls": ["/api/artifact-image/r1/image-abc.png"],
        }
        compact = dt._normalize_result(raw)
        assert compact["image_urls"] == ["/api/artifact-image/r1/image-abc.png"]

    def test_normalize_result_omits_empty_image_urls(self) -> None:
        dt = DelegateTools(AgentRegistry())
        compact = dt._normalize_result({"run_id": "r1", "agent_name": "telegram", "success": True})
        assert "image_urls" not in compact


class _NullLogger:
    def write(self, event, payload):  # noqa: ANN001
        pass


def _make_runtime(server_context=None, tools: list[ToolSpec] | None = None) -> AgentRuntime:
    registry = ToolRegistry()
    for spec in tools or []:
        registry.register(spec)
    from src.tools.core.confirmation_tools import finish_task

    registry.register(ToolSpec(
        "finish_task", "завершить", 0, finish_task,
        {"summary": "str?", "status": "str?", "attach_images": "bool?"},
    ))
    return AgentRuntime(
        client=None,  # не используется напрямую _execute_step
        registry=registry,
        validator=ActionValidator(registry),
        policy=SafetyPolicy(),
        logger=_NullLogger(),
        memory_store=None,
        confirm=lambda msg: True,
        max_steps=10,
        max_consecutive_errors=2,
        workspace_root=".",
        server_context=server_context,
    )


class TestAgentRuntimeImageRelay:
    def test_extract_delegated_image_urls_direct(self) -> None:
        result = {"image_urls": ["/api/artifact-image/r1/a.png", 123, ""]}
        urls = AgentRuntime._extract_delegated_image_urls(result)
        assert urls == ["/api/artifact-image/r1/a.png"]

    def test_extract_delegated_image_urls_nested_parallel(self) -> None:
        result = {
            "results": [
                {"image_urls": ["/api/artifact-image/r1/a.png"]},
                {"image_urls": ["/api/artifact-image/r2/b.png"]},
                {"no_images": True},
            ]
        }
        urls = AgentRuntime._extract_delegated_image_urls(result)
        assert urls == ["/api/artifact-image/r1/a.png", "/api/artifact-image/r2/b.png"]

    def test_extract_delegated_image_urls_empty_when_absent(self) -> None:
        assert AgentRuntime._extract_delegated_image_urls({"summary": "ok"}) == []

    def test_own_tool_image_saved_and_accumulated(self, tmp_path) -> None:
        store = ArtifactStore(tmp_path / "artifacts")
        ctx = _FakeServerContext(store)
        image_tool = _image_tool_spec()
        runtime = _make_runtime(server_context=ctx, tools=[image_tool])
        state = SessionState(user_goal="test")
        step = ActionStep(action="read_chat_image", args={}, done=False)

        image_urls: list[str] = []
        result = runtime._execute_step(step, 1, state, [], image_urls, "op-run-1")

        assert result is None  # не финальный шаг
        assert len(image_urls) == 1
        assert image_urls[0].startswith("/api/artifact-image/op-run-1/")

    def test_delegate_task_image_urls_propagate_to_operator(self, tmp_path) -> None:
        runtime = _make_runtime(server_context=None)
        state = SessionState(user_goal="test")
        step = ActionStep(action="finish_task", args={"summary": "ok"}, done=True)
        # Симулируем: finish_task ещё не вызван, а delegate_task уже был —
        # напрямую тестируем что _execute_step подхватывает image_urls из
        # результата delegate_task-подобного инструмента.
        delegate_spec = ToolSpec(
            "delegate_task", "делегировать", 0,
            lambda args: {"success": True, "image_urls": ["/api/artifact-image/sub1/x.png"]},
            {"agent_name": "str", "task": "str"},
        )
        runtime.registry.register(delegate_spec)
        delegate_step = ActionStep(action="delegate_task", args={"agent_name": "telegram", "task": "x"}, done=False)

        image_urls: list[str] = []
        runtime._execute_step(delegate_step, 1, state, [], image_urls, "op-run-1")

        assert image_urls == ["/api/artifact-image/sub1/x.png"]

    def test_finish_task_attach_images_embeds_markdown(self, tmp_path) -> None:
        runtime = _make_runtime(server_context=None)
        state = SessionState(user_goal="test")
        step = ActionStep(action="finish_task", args={"summary": "вот результат", "attach_images": True}, done=True)

        image_urls = ["/api/artifact-image/r1/a.png"]
        result = runtime._execute_step(step, 1, state, [], image_urls, "op-run-1")

        assert result is not None
        assert "![image](/api/artifact-image/r1/a.png)" in result

    def test_finish_task_without_attach_images_flag_stays_plain(self) -> None:
        runtime = _make_runtime(server_context=None)
        state = SessionState(user_goal="test")
        step = ActionStep(action="finish_task", args={"summary": "вот результат"}, done=True)

        result = runtime._execute_step(step, 1, state, [], ["/api/artifact-image/r1/a.png"], "op-run-1")

        assert result == "вот результат"


class TestSubAgentResultImageUrls:
    def test_from_raw_reads_top_level_image_urls(self) -> None:
        result = SubAgentResult.from_raw({
            "run_id": "r1", "agent_name": "web", "success": True,
            "image_urls": ["/api/artifact-image/r1/a.png", ""],
        })
        assert result.image_urls == ["/api/artifact-image/r1/a.png"]

    def test_from_raw_defaults_to_empty_list(self) -> None:
        result = SubAgentResult.from_raw({"run_id": "r1", "agent_name": "web", "success": True})
        assert result.image_urls == []
