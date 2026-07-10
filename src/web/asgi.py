from __future__ import annotations

import asyncio
import json
import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from src.web.context import ServerContext
from src.web.routes import Routes
from src.web.ws_server import broadcast_supervisor_alert


ctx = ServerContext()
routes = Routes(ctx)

app = FastAPI(title="Agent-1 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_DIST = Path(__file__).resolve().parents[2] / "client" / "dist"
CLIENT_ASSETS = CLIENT_DIST / "assets"
if CLIENT_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=CLIENT_ASSETS), name="assets")


def _json(result: Any, status_code: int = 200) -> JSONResponse:
    if isinstance(result, tuple):
        payload, status = result
        code = status.value if isinstance(status, HTTPStatus) else int(status)
        return JSONResponse(payload, status_code=code)
    return JSONResponse(result, status_code=status_code)


async def _body(request: Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


@app.get("/api/tools")
async def get_tools() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_tools))


@app.get("/api/runtime-config")
async def get_runtime_config() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_runtime_config))


@app.get("/api/history")
async def get_history() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_history))


@app.get("/api/monitor/state")
async def get_monitor_state() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_monitor_state))


@app.get("/api/runs")
async def get_runs() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_active_runs))


@app.get("/api/supervisor/alerts")
async def get_supervisor_alerts() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_supervisor_alerts))


@app.get("/api/bus")
async def get_bus() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_bus_history))


@app.get("/api/crashes")
async def get_crashes() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_crash_reports))


@app.get("/api/crashes/{filename:path}")
async def get_crash(filename: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_crash_report, filename))


@app.get("/api/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_run_artifacts, run_id))


@app.get("/api/runs/{run_id}/artifacts/{name:path}")
async def get_run_artifact(run_id: str, name: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_run_artifact, run_id, name))


@app.get("/api/artifact-image/{run_id}/{name:path}")
async def get_artifact_image(run_id: str, name: str):
    """Отдаёт артефакт как есть (сырые байты, правильный Content-Type) — для
    встраивания в markdown ![...](url) в тексте ответа. Отдельный от
    /api/runs/{run_id}/artifacts/{name} роут (тот возвращает JSON с hex для
    бинарных данных, не годится для <img src>)."""
    safe_run_id = Path(run_id).name
    safe_name = Path(name).name
    result = await run_in_threadpool(routes.ctx.read_artifact_bytes, safe_run_id, safe_name)
    if result is None:
        return _json({"error": "Артефакт не найден"}, 404)
    data, mime_type = result
    return Response(content=data, media_type=mime_type)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_run_by_id, run_id))


@app.get("/api/agents/history")
async def get_agents_history() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_agents_history))


@app.get("/api/models")
async def get_models() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_models))


@app.get("/api/app-settings")
async def get_app_settings() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_app_settings))


@app.get("/api/available-models")
async def get_available_models() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_available_models))


@app.get("/api/screenshots/{filename}")
async def get_screenshot_file(filename: str):
    safe_name = Path(filename).name
    file_path = Path("data") / "screenshots" / safe_name
    if not file_path.exists() or not file_path.is_file():
        return _json({"error": "Файл не найден"}, 404)
    return FileResponse(path=file_path, media_type="image/png")


@app.get("/api/ollama-models")
async def get_ollama_models() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_ollama_models))


@app.get("/api/tools-config")
async def get_tools_config() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_tools_config))


@app.get("/api/agents-config")
async def get_agents_config() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_agents_config))


@app.get("/api/user-profile")
async def get_user_profile() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_user_profile))


@app.get("/api/operator-skills")
async def get_operator_skills() -> JSONResponse:
    return _json(await run_in_threadpool(routes.get_operator_skills))


@app.post("/api/run")
async def run_task(request: Request):
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    task = payload.get("task")
    images = payload.get("images") or []
    if (not isinstance(task, str) or not task.strip()) and not images:
        return _json({"error": "Поле task должно быть непустой строкой"}, 400)

    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def write_sse(data: bytes) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, data)

    def run_blocking() -> None:
        try:
            routes.run_task((task or "").strip(), [], write_sse, images=images)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=run_blocking, daemon=True).start()

    async def stream():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/api/cancel")
async def cancel() -> JSONResponse:
    return _json(await run_in_threadpool(routes.cancel))


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.cancel_run, run_id))


@app.post("/api/runs/{run_id}/pause")
async def pause_run(run_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.pause_run, run_id))


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.resume_run, run_id))


@app.post("/api/runs/{run_id}/message")
async def message_run(run_id: str, request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "run id or body missing"}, 400)
    return _json(await run_in_threadpool(routes.message_run, run_id, payload))


@app.post("/api/runs/{run_id}/replace-task")
async def replace_task_run(run_id: str, request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "run id or body missing"}, 400)
    return _json(await run_in_threadpool(routes.replace_task_run, run_id, payload))


@app.post("/api/confirm")
async def confirm(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(_confirm_payload, payload))


def _confirm_payload(payload: dict[str, Any]) -> Any:
    request_id = payload.get("request_id")
    approved = payload.get("approved")
    if not isinstance(request_id, str) or not request_id.strip():
        return {"error": "Поле request_id должно быть непустой строкой"}, HTTPStatus.BAD_REQUEST
    if not isinstance(approved, bool):
        return {"error": "Поле approved должно быть bool"}, HTTPStatus.BAD_REQUEST
    return routes.confirm(request_id, approved)


@app.post("/api/history/clear")
async def clear_history() -> JSONResponse:
    return _json(await run_in_threadpool(routes.clear_history))


@app.post("/api/logs/clear")
async def clear_logs() -> JSONResponse:
    return _json(await run_in_threadpool(routes.clear_logs))


@app.post("/api/models")
async def set_models(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_models, payload))


@app.post("/api/app-settings")
async def set_app_settings(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_app_settings, payload))


@app.post("/api/tools-config")
async def set_tools_config(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_tools_config, payload))


@app.post("/api/agents-config")
async def set_agents_config(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_agents_config, payload))


@app.post("/api/user-profile")
async def set_user_profile(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_user_profile, payload))


@app.post("/api/operator-skills")
async def create_operator_skill(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.create_operator_skill, payload))


@app.post("/api/operator-skills/enabled")
async def set_operator_skill_enabled(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.set_operator_skill_enabled, payload))


@app.post("/api/operator-skills/install")
async def install_operator_market_skill(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.install_operator_market_skill, payload))


@app.post("/api/operator-skills/{skill_id}")
async def update_operator_skill(skill_id: str, request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.update_operator_skill, skill_id, payload))


@app.post("/api/operator-skills/{skill_id}/delete")
async def delete_operator_skill(skill_id: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.delete_operator_skill, skill_id))


@app.post("/api/open-path")
async def open_path(request: Request) -> JSONResponse:
    payload = await _body(request)
    if payload is None:
        return _json({"error": "Некорректный JSON"}, 400)
    return _json(await run_in_threadpool(routes.open_path, payload))


@app.post("/api/agents/clear/all")
async def clear_all_agents_memory() -> JSONResponse:
    return _json(await run_in_threadpool(routes.clear_all_agents_memory))


@app.post("/api/agents/{agent_name}/clear-runs")
async def clear_agent_runs(agent_name: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.clear_agent_runs, agent_name))


@app.post("/api/agents/{agent_name}/clear")
async def clear_agent_memory(agent_name: str) -> JSONResponse:
    return _json(await run_in_threadpool(routes.clear_agent_memory, agent_name))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
    except Exception:
        await websocket.close(code=1008, reason="Невалидный JSON")
        return

    action = msg.get("action")
    if action == "run":
        await _ws_run(websocket, msg)
    elif action == "subscribe_operator":
        await _ws_subscribe_operator(websocket, msg)
    elif action == "subscribe_supervisor":
        await _ws_subscribe_supervisor(websocket)
    elif action == "cancel":
        await websocket.send_json(await run_in_threadpool(routes.cancel))
    elif action == "cancel_run":
        run_id = str(msg.get("run_id", "")).strip()
        await websocket.send_json(await run_in_threadpool(routes.cancel_run, run_id))
    elif action == "confirm":
        result = await run_in_threadpool(_confirm_payload, msg)
        if isinstance(result, tuple):
            await websocket.send_json(result[0])
        else:
            await websocket.send_json(result)
    else:
        await websocket.send_json({"error": "Unknown action"})


async def _ws_run(websocket: WebSocket, msg: dict[str, Any]) -> None:
    task = str(msg.get("task", "")).strip()
    chat_history = msg.get("chat_history", [])
    images = msg.get("images") or []
    if not task and not images:
        await websocket.send_json({"event": "error", "payload": {"message": "Пустая задача"}})
        return

    send_queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def write_ws(data: bytes) -> None:
        text = data.decode("utf-8")
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                loop.call_soon_threadsafe(send_queue.put_nowait, line[6:])

    def run_blocking() -> None:
        try:
            routes.run_task(task, chat_history, write_ws, images=images)
        finally:
            loop.call_soon_threadsafe(send_queue.put_nowait, None)

    threading.Thread(target=run_blocking, daemon=True).start()

    while True:
        json_str = await send_queue.get()
        if json_str is None:
            break
        try:
            await websocket.send_text(json_str)
        except WebSocketDisconnect:
            break


async def _ws_subscribe_operator(websocket: WebSocket, msg: dict[str, Any]) -> None:
    try:
        since_seq = int(msg.get("since_seq", 0) or 0)
    except (TypeError, ValueError):
        since_seq = 0

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    loop = asyncio.get_running_loop()
    subscriber, replay = await run_in_threadpool(
        routes.ctx.add_operator_subscriber_with_replay,
        loop,
        queue,
        since_seq,
    )
    for event in replay:
        try:
            await websocket.send_json(event)
        except WebSocketDisconnect:
            routes.ctx.remove_operator_subscriber(subscriber)
            return

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "event": "ping",
                    "seq": routes.ctx.get_operator_event_seq(),
                })
    except WebSocketDisconnect:
        pass
    finally:
        routes.ctx.remove_operator_subscriber(subscriber)


async def _ws_subscribe_supervisor(websocket: WebSocket) -> None:
    existing = await run_in_threadpool(routes.get_supervisor_alerts, 20)
    for alert in existing.get("alerts", []):
        await websocket.send_json(alert)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50)
    loop = asyncio.get_running_loop()
    subscriber = (loop, queue)
    from src.web import ws_server

    with ws_server._supervisor_lock:
        ws_server._supervisor_subscribers.add(subscriber)
    try:
        while True:
            try:
                alert = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(alert)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        with ws_server._supervisor_lock:
            ws_server._supervisor_subscribers.discard(subscriber)


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_client_app(full_path: str):
    index_path = CLIENT_DIST / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>Client build not found</h1><p>Run npm run build in client.</p>",
        status_code=404,
    )


__all__ = ["app", "ctx", "routes", "broadcast_supervisor_alert"]
