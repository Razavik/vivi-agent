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

1. Запустите бэкенд:

```bash
python -m src.web.server
```

2. В отдельном терминале запустите React-клиент:

```bash
cd client ; npm run dev
```

Обычно клиент будет доступен по адресу:

```text
http://localhost:5173
```
