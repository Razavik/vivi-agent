"""WebSocket-сервер для реал-тайм стриминга событий агента."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import websockets
from websockets.asyncio.server import serve, ServerConnection

from src.web.context import ServerContext
from src.web.routes import Routes

_supervisor_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
_supervisor_lock = threading.Lock()


def broadcast_supervisor_alert(alert: dict) -> None:
    """Вызывается из фонового потока SupervisorLoop → рассылает алерт всем WS-подписчикам."""
    with _supervisor_lock:
        subscribers = list(_supervisor_subscribers)
    for loop, q in subscribers:
        loop.call_soon_threadsafe(_put_alert_nowait, q, alert)


def _put_alert_nowait(q: asyncio.Queue, alert: dict) -> None:
    try:
        q.put_nowait(alert)
    except asyncio.QueueFull:
        pass


async def _handle_connection(ws: ServerConnection, routes: Routes) -> None:
    """Обрабатываем одно WS-соединение: получаем задачу, стримим события."""
    try:
        raw = await ws.recv()
        msg = json.loads(raw)
    except Exception:
        await ws.close(1008, "Невалидный JSON")
        return

    action = msg.get("action")

    if action == "run":
        task = msg.get("task", "").strip()
        chat_history = msg.get("chat_history", [])
        images: list[str] = msg.get("images") or []
        if not task and not images:
            await ws.send(json.dumps({"event": "error", "payload": {"message": "Пустая задача"}}, ensure_ascii=False))
            return

        # Очередь для передачи событий из потока агента в asyncio
        send_queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def write_ws(data: bytes) -> None:
            """Колбэк из потока агента — кладём JSON в очередь."""
            text = data.decode("utf-8")
            for line in text.strip().split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    json_str = line[6:]
                    loop.call_soon_threadsafe(send_queue.put_nowait, json_str)

        def run_blocking() -> None:
            try:
                routes.run_task(task, chat_history, write_ws, images=images)
            finally:
                loop.call_soon_threadsafe(send_queue.put_nowait, None)

        # Запускаем агента в отдельном потоке
        agent_thread = threading.Thread(target=run_blocking, daemon=True)
        agent_thread.start()

        # Читаем из очереди и отправляем в WS — каждое событие сразу
        while True:
            json_str = await send_queue.get()
            if json_str is None:
                break
            try:
                await ws.send(json_str)
            except websockets.exceptions.ConnectionClosed:
                break

        agent_thread.join(timeout=5)

    elif action == "subscribe_supervisor":
        # Клиент подписывается на supervisor-алерты — сразу отдаём накопленные, потом стримим новые
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        loop = asyncio.get_running_loop()
        existing = routes.get_supervisor_alerts(20)
        for alert in existing.get("alerts", []):
            await ws.send(json.dumps(alert, ensure_ascii=False))
        with _supervisor_lock:
            _supervisor_subscribers.add((loop, q))
        try:
            while True:
                try:
                    alert = await asyncio.wait_for(q.get(), timeout=30.0)
                    await ws.send(json.dumps(alert, ensure_ascii=False))
                except asyncio.TimeoutError:
                    try:
                        await ws.ping()
                    except websockets.exceptions.ConnectionClosed:
                        break
                except websockets.exceptions.ConnectionClosed:
                    break
        finally:
            with _supervisor_lock:
                _supervisor_subscribers.discard((loop, q))

    elif action == "cancel":
        result = routes.cancel()
        await ws.send(json.dumps(result, ensure_ascii=False))

    elif action == "cancel_run":
        run_id = str(msg.get("run_id", "")).strip()
        result = routes.cancel_run(run_id)
        await ws.send(json.dumps(result, ensure_ascii=False))

    elif action == "confirm":
        request_id = msg.get("request_id", "")
        approved = msg.get("approved", False)
        result = routes.confirm(request_id, approved)
        if isinstance(result, tuple):
            await ws.send(json.dumps(result[0], ensure_ascii=False))
        else:
            await ws.send(json.dumps(result, ensure_ascii=False))


async def start_ws_server(host: str = "127.0.0.1", port: int = 8001, routes: Routes | None = None) -> None:
    """Запускает WebSocket-сервер."""
    if routes is None:
        ctx = ServerContext()
        routes = Routes(ctx)

    async with serve(
        lambda ws: _handle_connection(ws, routes),
        host,
        port,
    ):
        print(f"WebSocket сервер запущен: ws://{host}:{port}")
        await asyncio.Future()  # Работаем вечно
