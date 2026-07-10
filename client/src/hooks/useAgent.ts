/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useRef, useCallback } from "react";
import type {
	ChatEvent,
	ConfirmationRequest,
	Tool,
	SubAgentPane,
} from "../types";
import { handleSseEvent, type SseSetters } from "./sseHandler";
import { getWebSocketUrl } from "../utils/wsConfig";
import { readJson } from "../utils/http";

type ModelOption = {
	value: string;
	label: string;
};

type MonitorState = {
	running?: boolean;
	goal?: string;
	live_answer?: string;
	chat_history?: any[];
	operator_event_seq?: number;
};

function chatHistoryToEvents(chatHistory: any[]): ChatEvent[] {
	const events: ChatEvent[] = [];
	for (const item of chatHistory) {
		if (!item || !item.role) continue;
		if (item.role === "user") {
			events.push({
				type: "message",
				role: "user",
				content: item.content || "",
			});
			continue;
		}
		if (item.role === "assistant") {
			if (Array.isArray(item.plan) && item.plan.length > 0) {
				events.push({
					type: "message",
					role: "assistant",
					plan: item.plan,
				});
			}
			if (item.thought) {
				events.push({
					type: "thought",
					role: "assistant",
					thought: item.thought,
					step: 0,
				});
			}
			if (Array.isArray(item.actions)) {
				item.actions
					.filter((a: any) => a.action !== "finish_task")
					.sort((a: any, b: any) => (a.step || 0) - (b.step || 0))
					.forEach((action: any) => {
						if (action.thought) {
							events.push({
								type: "thought",
								role: "assistant",
								thought: action.thought,
								step: action.step || 0,
							});
						}
						events.push({
							type: "tool_result",
							role: "assistant",
							action: action.action,
							result: action.result,
							success: action.success,
							step: action.step || 0,
						});
					});
			}
			if (item.content) {
				events.push({
					type: "message",
					role: "assistant",
					content: item.content,
				});
			}
		}
	}
	return events;
}

function rawMessageMatches(left: any, right: any): boolean {
	if ((left?.role ?? "") !== (right?.role ?? "")) return false;
	if ((left?.content ?? "") !== (right?.content ?? "")) return false;
	const leftPlan = Array.isArray(left?.plan) ? left.plan : [];
	const rightPlan = Array.isArray(right?.plan) ? right.plan : [];
	return JSON.stringify(leftPlan) === JSON.stringify(rightPlan);
}

function rawChatHistoryContainsSequence(a: any[], b: any[]): boolean {
	if (b.length === 0 || a.length < b.length) return false;
	const firstPossible = Math.max(0, a.length - b.length - 6);
	for (let start = firstPossible; start <= a.length - b.length; start += 1) {
		let matches = true;
		for (let i = 0; i < b.length; i += 1) {
			if (!rawMessageMatches(a[start + i], b[i])) {
				matches = false;
				break;
			}
		}
		if (matches) return true;
	}
	return false;
}

export function useAgent() {
	const [events, setEvents] = useState<ChatEvent[]>([]);
	const [tools, setTools] = useState<Tool[]>([]);
	const [isRunning, setIsRunning] = useState(false);
	const [liveStatus, setLiveStatus] = useState("");
	const [currentAnswer, setCurrentAnswer] = useState("");
	const [confirmationRequest, setConfirmationRequest] =
		useState<ConfirmationRequest | null>(null);
	const [contextTokens, setContextTokens] = useState(0);
	const [contextLimit, setContextLimit] = useState(32768);
	const [selectedModel, setSelectedModel] = useState("");
	const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
	const [subAgentPanes, setSubAgentPanes] = useState<SubAgentPane[]>([]);
	const [liveThought, setLiveThought] = useState("");
	const sessionFinishedRef = useRef(false);
	const eventsRef = useRef<ChatEvent[]>([]);
	const historyRefreshInFlightRef = useRef(false);
	const operatorWsRef = useRef<WebSocket | null>(null);
	const operatorEventSeqRef = useRef(0);
	const currentAnswerRef = useRef("");

	const loadRuntimeConfig = useCallback(async () => {
		try {
			const response = await fetch("/api/runtime-config");
			if (!response.ok) return;
			const data = await readJson<{ num_ctx?: number }>(response, {});
			const limit = Number(data.num_ctx);
			if (Number.isFinite(limit) && limit > 0) {
				setContextLimit(limit);
			}
		} catch {
			// ignore runtime config errors
		}
	}, []);

	const loadModelConfig = useCallback(async () => {
		try {
			const [modelsResponse, availableResponse, ollamaResponse] =
				await Promise.all([
					fetch("/api/models"),
					fetch("/api/available-models"),
					fetch("/api/ollama-models"),
				]);

			const modelsData = modelsResponse.ok
				? await readJson<{
						default?: string;
						models?: Record<string, string>;
						custom_models?: string[];
					}>(modelsResponse, {})
				: {};
			const availableData = availableResponse.ok
				? await readJson<{ models?: string[] }>(availableResponse, {})
				: {};
			const ollamaData = ollamaResponse.ok
				? await readJson<{ models?: string[] }>(ollamaResponse, {})
				: {};

			const currentModel =
				modelsData.models?.operator?.trim() ||
				modelsData.default?.trim() ||
				"";
			setSelectedModel(currentModel);

			const allModels = Array.from(
				new Set(
					[
						...(modelsData.custom_models || []),
						...(availableData.models || []),
						...(ollamaData.models || []),
						currentModel,
					]
						.map((item) => item.trim())
						.filter(Boolean),
				),
			);
			setModelOptions(
				allModels.map((model) => ({
					value: model,
					label: model,
				})),
			);
		} catch {
			// ignore model config errors
		}
	}, []);

	const updatePane = useCallback(
		(id: string, patch: Partial<SubAgentPane>) => {
			setSubAgentPanes((prev) => {
				const idx = prev.findIndex((p) => p.id === id);
				if (idx === -1) return prev;
				const updated = [...prev];
				updated[idx] = { ...updated[idx], ...patch };
				return updated;
			});
		},
		[],
	);

	// Загрузка истории
	const loadHistory = useCallback(async () => {
		try {
			const [historyResponse, monitorResponse] = await Promise.all([
				fetch("/api/history"),
				fetch("/api/monitor/state"),
			]);
			if (!historyResponse.ok) {
				console.error("Не удалось загрузить историю с сервера");
				return;
			}
			const data = await readJson<{ chat_history?: any[] }>(
				historyResponse,
				{},
			);
			const monitorState = monitorResponse.ok
				? await readJson<MonitorState>(monitorResponse, {})
				: {};
			// operatorEventSeqRef НЕ продвигаем здесь до текущего "хвоста" сервера:
			// он используется как since_seq при последующей WS-подписке
			// (subscribe_operator), и преждевременное продвижение заставило бы
			// сервер пропустить replay уже случившихся sub_agent_step/tool_result
			// событий активного запуска — саб-агент выглядел бы "без действий"
			// после перезагрузки страницы, хотя реально уже прошёл несколько шагов.
			// Ref продвигается только по факту реально полученных событий (см. onmessage).

			const historyEvents: ChatEvent[] = [];

			if (Array.isArray(data.chat_history)) {
				historyEvents.push(...chatHistoryToEvents(data.chat_history));
			}

			if (
				monitorState.running &&
				Array.isArray(monitorState.chat_history)
			) {
				const liveMessages = monitorState.chat_history;
				const memoryRaw = Array.isArray(data.chat_history)
					? data.chat_history
					: [];
				const shouldAppendLive = !rawChatHistoryContainsSequence(
					memoryRaw,
					liveMessages,
				);
				if (shouldAppendLive) {
					historyEvents.push(...chatHistoryToEvents(liveMessages));
				}
				if (monitorState.live_answer?.trim()) {
					const liveAnswer = monitorState.live_answer;
					const liveNormalized = liveAnswer.trim();
					const lastAssistantIdx = historyEvents.findLastIndex(
						(event) =>
							event.type === "message" &&
							event.role === "assistant" &&
							Boolean(event.content),
					);
					const lastAssistant =
						lastAssistantIdx !== -1
							? historyEvents[lastAssistantIdx]
							: undefined;
					const lastContent = String(lastAssistant?.content || "");
					if (
						lastAssistant &&
						(liveNormalized.startsWith(lastContent.trim()) ||
							lastContent.trim().startsWith(liveNormalized))
					) {
						historyEvents[lastAssistantIdx] = {
							...lastAssistant,
							content:
								liveAnswer.length >= lastContent.length
									? liveAnswer
									: lastContent,
						};
						setCurrentAnswer("");
						currentAnswerRef.current = "";
					} else {
						setCurrentAnswer(liveAnswer);
						currentAnswerRef.current = liveAnswer;
					}
				} else {
					setCurrentAnswer("");
					currentAnswerRef.current = "";
				}
				setIsRunning(true);
				sessionFinishedRef.current = false;
				setLiveStatus(
					monitorState.live_answer?.trim()
						? "Формируется ответ..."
						: "Агент работает...",
				);
			} else if (!wsRef.current) {
				setCurrentAnswer("");
				currentAnswerRef.current = "";
				setIsRunning(false);
				sessionFinishedRef.current = true;
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
			const data = await readJson<{ tools?: any[] }>(response, {
				tools: [],
			});
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

	// Проверка активных запусков для восстановления состояния
	const checkActiveRuns = useCallback(async () => {
		try {
			const [runsResponse, monitorResponse] = await Promise.all([
				fetch("/api/runs"),
				fetch("/api/monitor/state"),
			]);
			const data = await readJson<{ runs?: any[] }>(runsResponse, {
				runs: [],
			});
			const monitorState = monitorResponse.ok
				? await readJson<MonitorState>(monitorResponse, {})
				: {};
			// См. комментарий в loadHistory: не продвигаем operatorEventSeqRef здесь,
			// иначе последующая WS-подписка (subscribe_operator) пропустит replay
			// шагов уже идущего запуска.
			const activeRuns = (data.runs ?? []).filter(
				(run: any) =>
					run.status === "running" ||
					run.status === "waiting_input" ||
					run.status === "waiting_user",
			);
			const hasActiveRuns =
				activeRuns.length > 0 || Boolean(monitorState.running);
			const hasLocalSession = Boolean(wsRef.current);

			// Если есть активные запуски, устанавливаем isRunning
			if (hasActiveRuns) {
				setIsRunning(true);
				if (!hasLocalSession) {
					setLiveStatus(
						monitorState.live_answer?.trim()
							? "Формируется ответ..."
							: "Восстановление сессии...",
					);
				}

				// Обновляем subAgentPanes из активных запусков
				const activePanes: SubAgentPane[] = activeRuns.map(
					(run: any) => ({
						id: `history:${run.agent_name}`,
						name: run.agent_name,
						displayName: run.agent_name,
						task: run.task ?? "",
						status: "running",
						steps: [],
						sessions: [],
						startedAt: run.created_at ?? Date.now(),
						model: run.model,
						result: run.result,
						errorMessage: run.error,
					}),
				);

				// ВАЖНО: только ДОБАВЛЯЕМ синтетическую панель для агентов, у которых
				// её ещё вообще нет (например сразу после reload, пока не пришли
				// живые sub_agent_* события) — и НИКОГДА не перезаписываем уже
				// существующую панель. Раньше здесь был merged.set(pane.name, pane)
				// БЕЗУСЛОВНО — это каждые 3 секунды (см. интервал ниже) стирало
				// реально накопленные шаги живой панели пустышкой (steps: []),
				// поэтому саб-агент выглядел "без действий" даже во время
				// собственного успешного выполнения, а не только после reload.
				setSubAgentPanes((prev) => {
					const existingNames = new Set(prev.map((p) => p.name));
					const additions = activePanes.filter(
						(pane) => !existingNames.has(pane.name),
					);
					if (additions.length === 0) return prev;
					return [...prev, ...additions];
				});
			} else if (!hasLocalSession) {
				// Если нет активных запусков, сбрасываем isRunning
				setIsRunning(false);
				setLiveStatus("");
				setCurrentAnswer("");
				sessionFinishedRef.current = true;
			}

			return hasActiveRuns;
		} catch (e) {
			console.error("Ошибка проверки активных запусков:", e);
			return false;
		}
	}, []);

	const clearHistory = useCallback(async () => {
		const response = await fetch("/api/history/clear", { method: "POST" });
		if (!response.ok) {
			throw new Error("Не удалось очистить историю");
		}
		setEvents([]);
		setCurrentAnswer("");
		setContextTokens(0);
		setSubAgentPanes([]);
		await loadHistory();
	}, [loadHistory]);

	const clearLogs = useCallback(async () => {
		const response = await fetch("/api/logs/clear", { method: "POST" });
		if (!response.ok) {
			throw new Error("Не удалось очистить логи");
		}
	}, []);

	// Очищает живое состояние панелей саб-агентов (subAgentPanes живёт здесь,
	// на уровне App, а не в AgentChatPage). Без этого AgentChatPage мог очистить
	// только историю на диске (/api/agents/*/clear) — buildPaneList всё равно
	// продолжал показывать уже накопленные в этом состоянии шаги/сессии, потому
	// что "живая" панель с реальным run_id побеждает в слиянии с исторической.
	// agentName не указан — очищаем всех.
	const clearSubAgentPanes = useCallback((agentName?: string) => {
		setSubAgentPanes((prev) =>
			agentName ? prev.filter((pane) => pane.name !== agentName) : [],
		);
	}, []);

	const updateSelectedModel = useCallback(
		async (model: string) => {
			try {
				const response = await fetch("/api/models");
				const modelsData = response.ok
					? await readJson<{
							models?: Record<string, string>;
							custom_models?: string[];
						}>(response, {})
					: {};
				const nextModels = {
					...(modelsData.models || {}),
					operator: model,
				};
				const saveResponse = await fetch("/api/models", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						models: nextModels,
						custom_models: modelsData.custom_models || [],
					}),
				});
				if (!saveResponse.ok) {
					throw new Error("Не удалось сохранить модель");
				}
				setSelectedModel(model);
				await loadModelConfig();
			} catch (error) {
				console.error("Не удалось обновить модель:", error);
			}
		},
		[loadModelConfig],
	);

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
			setLiveStatus(
				approved ? "Подтверждение отправлено" : "Команда отклонена",
			);
		},
		[confirmationRequest],
	);

	// Запуск задачи через WebSocket
	const wsRef = useRef<WebSocket | null>(null);

	const runTask = useCallback(
		async (task: string, images: string[] = []) => {
			if (!task.trim() && images.length === 0) return;

			// Закрываем предыдущее соединение
			if (wsRef.current) {
				wsRef.current.close();
				wsRef.current = null;
			}
			if (operatorWsRef.current) {
				operatorWsRef.current.close();
				operatorWsRef.current = null;
			}

			setIsRunning(true);
			sessionFinishedRef.current = false;
			setLiveStatus("Агент думает...");
			setCurrentAnswer("");
			setContextTokens(0);
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
					currentAnswerRef.current = lastAnswer;
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
				const wsUrl = getWebSocketUrl();
				const ws = new WebSocket(wsUrl);
				wsRef.current = ws;

				ws.onopen = () => {
					ws.send(
						JSON.stringify({
							action: "run",
							task,
							images: images.length > 0 ? images : undefined,
						}),
					);
				};

				ws.onmessage = (msg) => {
					try {
						const event = JSON.parse(msg.data);
						if (Number.isFinite(event?.seq)) {
							operatorEventSeqRef.current = Math.max(
								operatorEventSeqRef.current,
								Number(event.seq),
							);
						}
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
					setConfirmationRequest(null);
					void loadHistory();
					resolve();
				};
			});
		},
		[loadHistory, updatePane],
	);

	// Отмена текущего запроса
	const cancelTask = useCallback(async () => {
		if (wsRef.current) {
			wsRef.current.close();
			wsRef.current = null;
		}
		if (operatorWsRef.current) {
			operatorWsRef.current.close();
			operatorWsRef.current = null;
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
		const timer = window.setTimeout(() => {
			void loadRuntimeConfig();
			void loadModelConfig();
			void loadHistory();
			void loadTools();
			void checkActiveRuns();
		}, 0);
		return () => window.clearTimeout(timer);
	}, [
		loadHistory,
		loadModelConfig,
		loadRuntimeConfig,
		loadTools,
		checkActiveRuns,
	]);

	// Периодическое обновление при активных запусках
	useEffect(() => {
		if (!isRunning) return;

		const interval = window.setInterval(() => {
			void checkActiveRuns();
		}, 3000); // Проверяем каждые 3 секунды

		return () => window.clearInterval(interval);
	}, [isRunning, checkActiveRuns]);

	// После reload открываем новый WebSocket и подписываемся на текущий runtime.
	useEffect(() => {
		if (!isRunning || wsRef.current) return;

		if (operatorWsRef.current) return;

		const ws = new WebSocket(getWebSocketUrl());
		operatorWsRef.current = ws;
		const setters: SseSetters = {
			setEvents,
			setLiveThought,
			setLiveStatus,
			setCurrentAnswer: (v: any) => {
				currentAnswerRef.current =
					typeof v === "string" ? v : currentAnswerRef.current;
				setCurrentAnswer(v);
			},
			setIsRunning,
			setConfirmationRequest,
			setContextTokens,
			setSubAgentPanes,
			updatePane,
			getCurrentAnswer: () => currentAnswerRef.current,
			isSessionFinished: () => sessionFinishedRef.current,
			setSessionFinished: (value: boolean) => {
				sessionFinishedRef.current = value;
			},
		};

		ws.onopen = () => {
			ws.send(
				JSON.stringify({
					action: "subscribe_operator",
					since_seq: operatorEventSeqRef.current,
				}),
			);
		};
		ws.onmessage = (msg) => {
			try {
				const event = JSON.parse(msg.data);
				if (event?.event === "ping") {
					if (Number.isFinite(event?.seq)) {
						operatorEventSeqRef.current = Math.max(
							operatorEventSeqRef.current,
							Number(event.seq),
						);
					}
					return;
				}
				if (Number.isFinite(event?.seq)) {
					operatorEventSeqRef.current = Math.max(
						operatorEventSeqRef.current,
						Number(event.seq),
					);
				}
				handleSseEvent(event, setters);
			} catch (e) {
				console.error("[WS subscribe] Ошибка парсинга:", e, msg.data);
			}
		};
		ws.onerror = (err) => {
			console.error("[WS subscribe] Ошибка соединения:", err);
		};
		ws.onclose = () => {
			if (operatorWsRef.current === ws) {
				operatorWsRef.current = null;
			}
		};

		return () => {
			if (operatorWsRef.current === ws) {
				operatorWsRef.current = null;
			}
			ws.close();
		};
	}, [isRunning, updatePane]);

	// После перезагрузки страницы старого WebSocket уже нет, но серверный runtime
	// может продолжать работать. Polling остаётся fallback, если reattach-сокет упал.
	useEffect(() => {
		if (!isRunning || wsRef.current || operatorWsRef.current) return;

		const refresh = () => {
			if (historyRefreshInFlightRef.current) return;
			historyRefreshInFlightRef.current = true;
			void loadHistory().finally(() => {
				historyRefreshInFlightRef.current = false;
			});
		};

		refresh();
		const interval = window.setInterval(refresh, 1200);
		return () => window.clearInterval(interval);
	}, [isRunning, loadHistory]);

	return {
		events,
		tools,
		isRunning,
		liveStatus,
		currentAnswer,
		liveThought,
		confirmationRequest,
		contextTokens,
		contextLimit,
		selectedModel,
		modelOptions,
		updateSelectedModel,
		subAgentPanes,
		runTask,
		cancelTask,
		loadHistory,
		clearHistory,
		clearLogs,
		clearSubAgentPanes,
		respondToConfirmation,
	};
}
