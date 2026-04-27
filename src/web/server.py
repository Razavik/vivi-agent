from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.web.context import ServerContext
from src.web.routes import Routes


class AgentWebHandler(BaseHTTPRequestHandler):
    """Тонкий HTTP-handler: только роутинг и I/O. Вся логика в Routes."""

    # Отключаем буферизацию wfile — иначе SSE-события не идут в реальном времени
    wbufsize = 0

    def setup(self) -> None:
        super().setup()
        import socket
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Разделяемый контекст (устанавливается при запуске сервера)
    _ctx: ServerContext | None = None
    _routes: Routes | None = None

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    def do_GET(self) -> None:
        routes = self._get_routes()
        if self.path == "/api/tools":
            self._send_json(routes.get_tools())
        elif self.path == "/api/history":
            self._send_json(routes.get_history())
        elif self.path == "/api/runs":
            self._send_json(routes.get_active_runs())
        elif self.path == "/api/supervisor/alerts":
            self._send_json(routes.get_supervisor_alerts())
        elif self.path.startswith("/api/bus"):
            self._send_json(routes.get_bus_history())
        elif self.path == "/api/crashes":
            self._send_json(routes.get_crash_reports())
        elif self.path.startswith("/api/crashes/"):
            fname = self.path[len("/api/crashes/"):]
            self._send_json(routes.get_crash_report(fname))
        elif self.path.startswith("/api/runs/") and "/artifacts" in self.path:
            self._handle_artifacts_get(routes)
        elif self.path.startswith("/api/runs/") and self.path != "/api/runs/":
            run_id = self.path[len("/api/runs/"):].strip("/")
            self._send_json(routes.get_run_by_id(run_id))
        elif self.path == "/api/agents/history":
            self._send_json(routes.get_agents_history())
        elif self.path == "/api/models":
            self._send_json(routes.get_models())
        elif self.path == "/api/available-models":
            self._send_json(routes.get_available_models())
        elif self.path == "/api/ollama-models":
            self._send_json(routes.get_ollama_models())
        elif self.path == "/api/tools-config":
            self._send_json(routes.get_tools_config())
        elif self.path == "/api/agents-config":
            self._send_json(routes.get_agents_config())
        elif self.path == "/api/user-profile":
            self._send_json(routes.get_user_profile())
        else:
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        routes = self._get_routes()
        if self.path == "/api/run":
            self._handle_run(routes)
        elif self.path == "/api/cancel":
            self._send_json(routes.cancel())
        elif self.path.startswith("/api/runs/") and self.path.endswith("/cancel"):
            run_id = self.path[len("/api/runs/"):-len("/cancel")]
            if run_id:
                self._send_json(routes.cancel_run(run_id.strip("/")))
            else:
                self._send_json({"error": "run id missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/runs/") and self.path.endswith("/pause"):
            run_id = self.path[len("/api/runs/"):-len("/pause")]
            if run_id:
                self._send_json(routes.pause_run(run_id.strip("/")))
            else:
                self._send_json({"error": "run id missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/runs/") and self.path.endswith("/resume"):
            run_id = self.path[len("/api/runs/"):-len("/resume")]
            if run_id:
                self._send_json(routes.resume_run(run_id.strip("/")))
            else:
                self._send_json({"error": "run id missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/runs/") and self.path.endswith("/message"):
            run_id = self.path[len("/api/runs/"):-len("/message")]
            payload = self._read_json_body()
            if run_id and payload is not None:
                self._send_json(routes.message_run(run_id.strip("/"), payload))
            else:
                self._send_json({"error": "run id or body missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/runs/") and self.path.endswith("/replace-task"):
            run_id = self.path[len("/api/runs/"):-len("/replace-task")]
            payload = self._read_json_body()
            if run_id and payload is not None:
                self._send_json(routes.replace_task_run(run_id.strip("/"), payload))
            else:
                self._send_json({"error": "run id or body missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path == "/api/confirm":
            self._handle_confirm(routes)
        elif self.path == "/api/history/clear":
            self._send_json(routes.clear_history())
        elif self.path == "/api/logs/clear":
            self._send_json(routes.clear_logs())
        elif self.path == "/api/models":
            payload = self._read_json_body()
            if payload is not None:
                self._send_json(routes.set_models(payload))
        elif self.path == "/api/tools-config":
            payload = self._read_json_body()
            if payload is not None:
                result = routes.set_tools_config(payload)
                if isinstance(result, tuple):
                    self._send_json(result[0], status=result[1])
                else:
                    self._send_json(result)
        elif self.path == "/api/agents-config":
            payload = self._read_json_body()
            if payload is not None:
                result = routes.set_agents_config(payload)
                if isinstance(result, tuple):
                    self._send_json(result[0], status=result[1])
                else:
                    self._send_json(result)
        elif self.path == "/api/user-profile":
            payload = self._read_json_body()
            if payload is not None:
                result = routes.set_user_profile(payload)
                if isinstance(result, tuple):
                    self._send_json(result[0], status=result[1])
                else:
                    self._send_json(result)
        elif self.path == "/api/open-path":
            payload = self._read_json_body()
            if payload is not None:
                self._send_json(routes.open_path(payload))
        elif self.path == "/api/agents/clear/all":
            self._send_json(routes.clear_all_agents_memory())
        elif self.path.startswith("/api/agents/") and self.path.endswith("/clear-runs"):
            agent_name = self.path[len("/api/agents/"):-len("/clear-runs")]
            if agent_name:
                self._send_json(routes.clear_agent_runs(agent_name))
            else:
                self._send_json({"error": "agent name missing"}, status=HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/agents/") and self.path.endswith("/clear"):
            agent_name = self.path[len("/api/agents/"):-len("/clear")]
            if agent_name:
                self._send_json(routes.clear_agent_memory(agent_name))
            else:
                self._send_json({"error": "agent name missing"}, status=HTTPStatus.BAD_REQUEST)
        else:
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    # --- Приватные обработчики ---

    def _handle_artifacts_get(self, routes: Routes) -> None:
        # /api/runs/{run_id}/artifacts            — список артефактов
        # /api/runs/{run_id}/artifacts/{name}     — конкретный артефакт
        path = self.path[len("/api/runs/"):]  # "run_id/artifacts" или "run_id/artifacts/name"
        parts = path.split("/artifacts", 1)
        run_id = parts[0].strip("/")
        rest = parts[1].strip("/") if len(parts) > 1 else ""
        if not run_id:
            self._send_json({"error": "run_id missing"}, status=HTTPStatus.BAD_REQUEST)
            return
        if rest:
            self._send_json(routes.get_run_artifact(run_id, rest))
        else:
            self._send_json(routes.get_run_artifacts(run_id))

    def _handle_run(self, routes: Routes) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        task = payload.get("task")
        if not isinstance(task, str) or not task.strip():
            self._send_json({"error": "Поле task должно быть непустой строкой"}, status=HTTPStatus.BAD_REQUEST)
            return
        chat_history = payload.get("chat_history", [])
        if not isinstance(chat_history, list):
            self._send_json({"error": "Поле chat_history должно быть массивом"}, status=HTTPStatus.BAD_REQUEST)
            return

        # SSE-заголовки
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def write_sse(data: bytes) -> None:
            try:
                self.wfile.write(data)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        routes.run_task(task.strip(), chat_history, write_sse)

    def _handle_confirm(self, routes: Routes) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        request_id = payload.get("request_id")
        approved = payload.get("approved")
        if not isinstance(request_id, str) or not request_id.strip():
            self._send_json({"error": "Поле request_id должно быть непустой строкой"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(approved, bool):
            self._send_json({"error": "Поле approved должно быть bool"}, status=HTTPStatus.BAD_REQUEST)
            return
        result = routes.confirm(request_id, approved)
        if isinstance(result, tuple):
            self._send_json(result[0], status=result[1])
        else:
            self._send_json(result)

    # --- Утилиты ---

    def _get_routes(self) -> Routes:
        if self._routes is None:
            raise RuntimeError("ServerContext не инициализирован")
        return self._routes

    def log_message(self, format: str, *args: object) -> None:
        return  # Подавляем стандартный лог HTTP-сервера

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._send_json({"error": "Отсутствует Content-Length"}, status=HTTPStatus.BAD_REQUEST)
            return None
        raw = self.rfile.read(int(content_length))
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "Некорректный JSON"}, status=HTTPStatus.BAD_REQUEST)
            return None

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def start_server(host: str = "127.0.0.1", port: int = 8000, ws_port: int = 8001) -> None:
    import asyncio
    import threading
    from src.web.ws_server import start_ws_server

    ctx = ServerContext()
    routes = Routes(ctx)
    AgentWebHandler._ctx = ctx
    AgentWebHandler._routes = routes

    # WebSocket-сервер в отдельном потоке
    def run_ws() -> None:
        asyncio.run(start_ws_server(host, ws_port, routes))

    ws_thread = threading.Thread(target=run_ws, daemon=True)
    ws_thread.start()

    # HTTP-сервер в основном потоке
    server = ThreadingHTTPServer((host, port), AgentWebHandler)
    print(f"HTTP сервер: http://{host}:{port}")
    print(f"WS сервер:   ws://{host}:{ws_port}")
    server.serve_forever()


if __name__ == "__main__":
    start_server()
