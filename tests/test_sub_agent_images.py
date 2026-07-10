from __future__ import annotations

from src.agent.schemas import ActionStep
from src.agent.sub_agent import SubAgent
from src.infra.chat_memory import ChatMemoryStore
from src.tools.registry import ToolSpec


class _StubClient:
    """Заглушка OllamaClient: выдаёт заранее заданную последовательность шагов и
    записывает, какие images были переданы в каждый вызов plan_next_step."""

    model = "stub-model"
    num_ctx = 4096

    def __init__(self, steps: list[ActionStep]) -> None:
        self._steps = steps
        self._i = 0
        self.seen_images: list[list[str] | None] = []

    def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
        user_message = next(m for m in messages if m["role"] == "user")
        self.seen_images.append(user_message.get("images"))
        step = self._steps[min(self._i, len(self._steps) - 1)]
        self._i += 1
        return step


def _make_sub_agent(tmp_path, client, tools: list[ToolSpec], prompt_vars: dict[str, str] | None = None) -> SubAgent:
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
        prompt_vars=prompt_vars,
    )


def test_tool_returned_image_flows_to_next_step(tmp_path) -> None:
    """Регрессия: инструмент, вернувший {_type: 'image', image: b64}, должен
    появиться в images СЛЕДУЮЩЕГО вызова LLM — иначе саб-агент не может увидеть
    картинку, даже если инструмент технически её скачал."""
    image_tool = ToolSpec(
        "read_chat_image",
        "скачать фото",
        0,
        lambda args: {"image": "ZmFrZS1iYXNlNjQ=", "format": "image/jpeg", "_type": "image", "caption": "hi"},
        {"chat_id": "str?", "message_id": "str?"},
    )
    client = _StubClient([
        ActionStep(action="read_chat_image", args={}, done=False),
        ActionStep(action="finish_task", args={"summary": "видел фото"}, done=True),
    ])
    agent = _make_sub_agent(tmp_path, client, [image_tool])

    agent.run("посмотри фото", run_id="r1")

    assert client.seen_images[0] is None, "на первом шаге изображений ещё нет"
    assert client.seen_images[1] == ["ZmFrZS1iYXNlNjQ="], "картинка от инструмента должна попасть в следующий шаг"


def test_image_cleared_after_being_sent_once(tmp_path) -> None:
    """Картинка не должна дублироваться в КАЖДОМ последующем сообщении — только
    в том шаге, что идёт сразу после её получения."""
    image_tool = ToolSpec(
        "read_chat_image", "скачать фото", 0,
        lambda args: {"image": "AAAA", "format": "image/png", "_type": "image"},
        {},
    )
    noop_tool = ToolSpec("noop", "ничего не делает", 0, lambda args: {"ok": True}, {})
    client = _StubClient([
        ActionStep(action="read_chat_image", args={}, done=False),
        ActionStep(action="noop", args={}, done=False),
        ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
    ])
    agent = _make_sub_agent(tmp_path, client, [image_tool, noop_tool])

    agent.run("задача", run_id="r1")

    assert client.seen_images == [None, ["AAAA"], None]


def test_operator_supplied_images_reach_first_step(tmp_path) -> None:
    """Изображения, переданные оператором при delegate_task(images=[...]),
    должны попасть уже в ПЕРВЫЙ вызов LLM саб-агента."""
    client = _StubClient([
        ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
    ])
    agent = _make_sub_agent(tmp_path, client, [])

    agent.run("посмотри скриншот", run_id="r1", images=["operator-image-b64"])

    assert client.seen_images[0] == ["operator-image-b64"]


def test_image_redacted_from_persisted_observation(tmp_path) -> None:
    """base64 картинки не должен попадать в chat_history/observations — иначе
    память саб-агента раздувается на каждый просмотренный кадр."""
    image_tool = ToolSpec(
        "read_chat_image", "скачать фото", 0,
        lambda args: {"image": "SECRET_BASE64", "format": "image/png", "_type": "image", "caption": "cat"},
        {},
    )
    client = _StubClient([
        ActionStep(action="read_chat_image", args={}, done=False),
        ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
    ])
    agent = _make_sub_agent(tmp_path, client, [image_tool])

    result = agent.run("задача", run_id="r1")

    mem = agent.memory_store.load()
    serialized = str(mem)
    assert "SECRET_BASE64" not in serialized
    assert result["success"] is True


def test_prompt_vars_substituted_into_system_prompt(tmp_path) -> None:
    client = _StubClient([ActionStep(action="finish_task", args={"summary": "ok"}, done=True)])
    prompt = tmp_path / "agent.txt"
    prompt.write_text("Профиль: @{tg_username} ({tg_display_name})", encoding="utf-8")
    agent = SubAgent(
        name="telegram", display_name="Telegram", prompt_path=str(prompt), tools=[],
        client=client, memory_store=ChatMemoryStore(tmp_path / "mem.json"),
        prompt_vars={"tg_username": "myhandle", "tg_display_name": "Иван Иванов"},
    )

    agent.run("любая задача", run_id="r1")

    # Проверяем через сообщение, что подстановка реально произошла — достаём system prompt
    # из последнего вызова LLM: используем отдельный клиент, фиксирующий messages целиком.
    class _CapturingClient(_StubClient):
        def __init__(self, steps):
            super().__init__(steps)
            self.system_prompts: list[str] = []

        def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
            self.system_prompts.append(next(m for m in messages if m["role"] == "system")["content"])
            return super().plan_next_step(messages, on_retry_error)

    capturing = _CapturingClient([ActionStep(action="finish_task", args={"summary": "ok"}, done=True)])
    agent2 = SubAgent(
        name="telegram", display_name="Telegram", prompt_path=str(prompt), tools=[],
        client=capturing, memory_store=ChatMemoryStore(tmp_path / "mem2.json"),
        prompt_vars={"tg_username": "myhandle", "tg_display_name": "Иван Иванов"},
    )
    agent2.run("любая задача", run_id="r2")

    assert "@myhandle" in capturing.system_prompts[0]
    assert "Иван Иванов" in capturing.system_prompts[0]
