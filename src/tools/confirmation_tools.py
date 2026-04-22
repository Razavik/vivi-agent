from __future__ import annotations


def finish_task(args: dict[str, object]) -> dict[str, object]:
    summary = args.get("summary")
    if isinstance(summary, str) and summary.strip():
        return {"summary": summary.strip()}
    message = args.get("message")
    if isinstance(message, str) and message.strip():
        return {"summary": message.strip()}
    return {"summary": "Задача завершена"}


def send_message(args: dict[str, object]) -> dict[str, object]:
    message = args.get("message")
    if not isinstance(message, str) or not message.strip():
        return {"error": "Поле message не должно быть пустым"}
    return {"message": message.strip()}
