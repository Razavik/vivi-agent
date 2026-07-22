from __future__ import annotations

from threading import Event

from src.agent.lifecycle.run_control import RunController


def _make_controller() -> RunController:
    return RunController(run_id="r1", cancel_event=Event(), pause_event=Event())


def test_cancel_invokes_registered_callback() -> None:
    calls: list[str] = []
    controller = _make_controller()
    controller.register_cancel_callback(lambda: calls.append("aborted"))

    controller.cancel()

    assert calls == ["aborted"]
    assert controller.is_cancelled() is True


def test_register_after_cancel_fires_immediately() -> None:
    """Если cancel() уже произошёл (гонка потоков), поздняя регистрация должна
    сработать немедленно, а не потеряться навсегда."""
    calls: list[str] = []
    controller = _make_controller()
    controller.cancel()

    controller.register_cancel_callback(lambda: calls.append("late"))

    assert calls == ["late"]


def test_callback_exception_does_not_break_cancel() -> None:
    controller = _make_controller()

    def boom() -> None:
        raise RuntimeError("network error while closing")

    controller.register_cancel_callback(boom)
    controller.cancel()  # не должно бросать исключение

    assert controller.is_cancelled() is True


def test_multiple_callbacks_all_invoked() -> None:
    calls: list[int] = []
    controller = _make_controller()
    controller.register_cancel_callback(lambda: calls.append(1))
    controller.register_cancel_callback(lambda: calls.append(2))

    controller.cancel()

    assert sorted(calls) == [1, 2]
