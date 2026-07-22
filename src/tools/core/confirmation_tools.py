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

    # attach_images — просто маркер для runtime (AgentRuntime/SubAgent): finish_task
    # сам не знает, какие картинки видел агент за этот run — это состояние уровня
    # runtime, а не этой чистой функции. Runtime встраивает markdown-картинки в
    # summary ПОСЛЕ вызова этого обработчика, см. _execute_step.
    attach_images = args.get("attach_images")
    if isinstance(attach_images, bool):
        result["attach_images"] = attach_images

    return result
