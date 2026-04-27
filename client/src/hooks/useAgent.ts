import { useState, useEffect, useRef, useCallback } from "react";
import type { ChatEvent, ConfirmationRequest, Tool, SubAgentPane } from "../types";
import { handleSseEvent, type SseSetters } from "./sseHandler";

export function useAgent() {
	const [events, setEvents] = useState<ChatEvent[]>([]);
	const [tools, setTools] = useState<Tool[]>([]);
	const [isRunning, setIsRunning] = useState(false);
	const [liveStatus, setLiveStatus] = useState("");
	const [currentAnswer, setCurrentAnswer] = useState("");
	const [confirmationRequest, setConfirmationRequest] = useState<ConfirmationRequest | null>(
		null,
	);
	const [contextTokens, setContextTokens] = useState(0);
	const [subAgentPanes, setSubAgentPanes] = useState<SubAgentPane[]>([]);
	const [liveThought, setLiveThought] = useState("");
	const sessionFinishedRef = useRef(false);
	const eventsRef = useRef<ChatEvent[]>([]);

	const updatePane = useCallback((id: string, patch: Partial<SubAgentPane>) => {
		setSubAgentPanes((prev) => {
			const idx = prev.findIndex((p) => p.id === id);
			if (idx === -1) return prev;
			const updated = [...prev];
			updated[idx] = { ...updated[idx], ...patch };
			return updated;
		});
	}, []);

	// Загрузка истории
	const loadHistory = useCallback(async () => {
		try {
			const response = await fetch("/api/history");
			if (!response.ok) {
				console.error("Не удалось загрузить историю с сервера");
				return;
			}
			const data = await response.json();

			const historyEvents: ChatEvent[] = [];

			if (Array.isArray(data.chat_history)) {
				data.chat_history.forEach((item: any) => {
					if (item && item.role && item.content) {
						// Сообщение пользователя
						if (item.role === "user") {
							historyEvents.push({
								type: "message",
								role: item.role,
								content: item.content,
							});
						} else if (item.role === "assistant") {
							if (Array.isArray(item.plan) && item.plan.length > 0) {
								historyEvents.push({
									type: "message",
									role: "assistant",
									plan: item.plan,
								});
							}
							// Сначала thought из assistant сообщения (размышление перед ответом)
							if (item.thought) {
								historyEvents.push({
									type: "thought",
									role: "assistant",
									thought: item.thought,
									step: 0,
								});
							}

							// Thoughts и tool results из actions в порядке step
							if (Array.isArray(item.actions)) {
								item.actions
									.filter((a: any) => a.action !== "finish_task")
									.sort((a: any, b: any) => (a.step || 0) - (b.step || 0))
									.forEach((action: any) => {
										// Сначала thought (размышление перед действием)
										if (action.thought) {
											historyEvents.push({
												type: "thought",
												role: "assistant",
												thought: action.thought,
												step: action.step || 0,
											});
										}
										// Затем tool_result (результат действия)
										historyEvents.push({
											type: "tool_result",
											role: "assistant",
											action: action.action,
											result: action.result,
											success: action.success,
											step: action.step || 0,
										});
									});
							}

							// Затем сообщение ассистента (финальный ответ)
							historyEvents.push({
								type: "message",
								role: item.role,
								content: item.content,
							});
						}
					}
				});
			}
			eventsRef.current = historyEvents;
			setEvents(historyEvents);
		} catch (e) {
			console.error("Ошибка загрузки истории:", e);
		}
	}, []);

	// Загрузка инструментов
	const loadTools = useCallback(async () => {
		try {
			const response = await fetch("/api/tools");
			const data = await response.json();
			const toolList = (data.tools || []).map((tool: any) => ({
				name: tool.name,
				description: tool.description,
				risk_level: tool.risk_level,
				args_schema: tool.args_schema,
				agent: tool.agent,
			}));
			setTools(toolList);
		} catch (e) {
			console.error("Ошибка загрузки инструментов:", e);
		}
	}, []);

	const clearHistory = useCallback(async () => {
		const response = await fetch("/api/history/clear", { method: "POST" });
		if (!response.ok) {
			throw new Error("Не удалось очистить историю");
		}
		setEvents([]);
		setCurrentAnswer("");
		setSubAgentPanes([]);
		await loadHistory();
	}, [loadHistory]);

	const clearLogs = useCallback(async () => {
		const response = await fetch("/api/logs/clear", { method: "POST" });
		if (!response.ok) {
			throw new Error("Не удалось очистить логи");
		}
	}, []);

	const respondToConfirmation = useCallback(
		async (approved: boolean) => {
			if (!confirmationRequest) return;
			const response = await fetch("/api/confirm", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					request_id: confirmationRequest.requestId,
					approved,
				}),
			});
			if (!response.ok) {
				throw new Error("Не удалось отправить подтверждение");
			}
			setConfirmationRequest(null);
			setLiveStatus(approved ? "Подтверждение отправлено" : "Команда отклонена");
		},
		[confirmationRequest],
	);

	// Запуск задачи через WebSocket
	const wsRef = useRef<WebSocket | null>(null);

	const runTask = useCallback(async (task: string, images: string[] = []) => {
		if (!task.trim() && images.length === 0) return;

		// Закрываем предыдущее соединение
		if (wsRef.current) {
			wsRef.current.close();
			wsRef.current = null;
		}

		setIsRunning(true);
		sessionFinishedRef.current = false;
		setLiveStatus("Агент думает...");
		setCurrentAnswer("");
		setSubAgentPanes([]);
		const userMsg: ChatEvent = {
			type: "message",
			role: "user",
			content: task,
			images: images.length > 0 ? images : undefined,
		};
		setEvents((prev) => {
			const next = [...prev, userMsg];
			eventsRef.current = next;
			return next;
		});

		let lastAnswer = "";
		const setters: SseSetters = {
			setEvents,
			setLiveThought,
			setLiveStatus,
			setCurrentAnswer: (v: any) => {
				lastAnswer = typeof v === "string" ? v : lastAnswer;
				setCurrentAnswer(v);
			},
			setIsRunning,
			setConfirmationRequest,
			setContextTokens,
			setSubAgentPanes,
			updatePane,
			getCurrentAnswer: () => lastAnswer,
			isSessionFinished: () => sessionFinishedRef.current,
			setSessionFinished: (value: boolean) => {
				sessionFinishedRef.current = value;
			},
		};

		return new Promise<void>((resolve) => {
			// В dev — напрямую на WS-сервер, в prod — через тот же хост
			const wsUrl = import.meta.env.DEV
				? "ws://127.0.0.1:8001"
				: `ws://${window.location.host}/ws`;
			const ws = new WebSocket(wsUrl);
			wsRef.current = ws;

			ws.onopen = () => {
				const allMsgs = eventsRef.current.filter((e) => e.type === "message");
				const historyToSend = allMsgs
					.slice(0, -1)
					.map((e) => ({ role: e.role, content: e.content }));
				ws.send(
					JSON.stringify({
						action: "run",
						task,
						images: images.length > 0 ? images : undefined,
						chat_history: historyToSend,
					}),
				);
			};

			ws.onmessage = (msg) => {
				try {
					const event = JSON.parse(msg.data);
					handleSseEvent(event, setters);
				} catch (e) {
					console.error("[WS] Ошибка парсинга:", e, msg.data);
				}
			};

			ws.onerror = (err) => {
				console.error("[WS] Ошибка соединения:", err);
				setEvents((prev) => [
					...prev,
					{
						type: "message",
						role: "assistant",
						content: "Ошибка соединения с сервером",
					},
				]);
				setIsRunning(false);
				setLiveStatus("");
				resolve();
			};

			ws.onclose = () => {
				wsRef.current = null;
				setIsRunning(false);
				setLiveStatus("");
				setConfirmationRequest(null);
				resolve();
			};
		});
	}, []);

	// Отмена текущего запроса
	const cancelTask = useCallback(async () => {
		if (wsRef.current) {
			wsRef.current.close();
			wsRef.current = null;
		}
		// Отправляем сигнал отмены на сервер
		try {
			await fetch("/api/cancel", { method: "POST" });
		} catch (e) {
			console.error("Не удалось отправить сигнал отмены на сервер:", e);
		}
		setIsRunning(false);
		setLiveStatus("");
	}, []);

	// Инициализация при монтировании
	useEffect(() => {
		loadHistory();
		loadTools();
	}, [loadHistory, loadTools]);

	return {
		events,
		tools,
		isRunning,
		liveStatus,
		currentAnswer,
		liveThought,
		confirmationRequest,
		contextTokens,
		subAgentPanes,
		runTask,
		cancelTask,
		loadHistory,
		clearHistory,
		clearLogs,
		respondToConfirmation,
	};
}
