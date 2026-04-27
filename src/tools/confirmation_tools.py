from __future__ import annotations


def finish_task(args: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}

    summary = args.get("summary")
    if isinstance(summary, str) and summary.strip():
        result["summary"] = summary.strip()
    else:
        message = args.get("message")
        result["summary"] = message.strip() if isinstance(message, str) and message.strip() else "Задача завершена"

    status = args.get("status")
    if isinstance(status, str) and status.strip():
        result["status"] = status.strip()

    needs_user_input = args.get("needs_user_input")
    if isinstance(needs_user_input, bool):
        result["needs_user_input"] = needs_user_input

    question = args.get("question")
    if isinstance(question, str) and question.strip():
        result["question"] = question.strip()

    for field in ("changed_files", "created_artifacts", "verification", "risks"):
        value = args.get(field)
        if isinstance(value, list):
            result[field] = [str(item) for item in value if str(item).strip()]

    return result


def send_message(args: dict[str, object]) -> dict[str, object]:
    message = args.get("message")
    if not isinstance(message, str) or not message.strip():
        return {"error": "Поле message не должно быть пустым"}
    return {"message": message.strip()}
