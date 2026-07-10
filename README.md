# agent-computer-control

## Перед запуском

- Python 3.11+
- Ollama
- Python-зависимости:

```bash
pip install -r requirements.txt
```

- React-клиент:

```bash
cd client
npm install
```

## Запуск

### Быстрый запуск

```bash
start.bat
```

`start.bat` запускает приложение через Electron (`npm run app`) без упаковки `dist`.
`start-exe.bat` запускает собранный `dist-app\Vivi\Vivi.exe`.

### Сборка EXE

```bash
build.bat
```

Готовое приложение появится в `dist-app\Vivi\Vivi.exe`.

### Ручной запуск

Backend:

```bash
uvicorn src.web.asgi:app --host 127.0.0.1 --port 8000 --reload
```

Или через Python-лаунчер:

```bash
python start_server.py
```

Frontend:

```bash
cd client
npm run dev
```

Адреса:

```text
Backend:  http://127.0.0.1:8000
WebSocket: ws://127.0.0.1:8000/ws
Frontend: http://localhost:5500
```
