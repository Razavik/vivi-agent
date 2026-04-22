import type { ChatEvent, ConfirmationRequest, SubAgentPane } from "../types";

const AGENT_DISPLAY_NAMES: Record<string, string> = {
	telegram: "Telegram",
	file: "Файлы",
	system: "Система",
	web: "Веб",
};

export interface SseSetters {
	setEvents: React.Dispatch<React.SetStateAction<ChatEvent[]>>;
	setLiveThought: React.Dispatch<React.SetStateAction<string>>;
	setLiveStatus: React.Dispatch<React.SetStateAction<string>>;
	setCurrentAnswer: React.Dispatch<React.SetStateAction<string>>;
	setIsRunning: React.Dispatch<React.SetStateAction<boolean>>;
	setConfirmationRequest: React.Dispatch<React.SetStateAction<ConfirmationRequest | null>>;
	setContextTokens: React.Dispatch<React.SetStateAction<number>>;
	setSubAgentPanes: React.Dispatch<React.SetStateAction<SubAgentPane[]>>;
	updatePane: (name: string, patch: Partial<SubAgentPane>) => void;
	getCurrentAnswer: () => string;
	isSessionFinished: () => boolean;
	setSessionFinished: (value: boolean) => void;
}

// --- Парсинг SSE-потока ---

export interface ParseResult {
	remaining: string;
	events: any[];
}

export function parseSseBuffer(buffer: string): ParseResult {
	buffer = buffer.replace(/\r\n/g, "\n");
	const events: any[] = [];
	let idx = buffer.indexOf("\n\n");
	while (idx !== -1) {
		const raw = buffer.slice(0, idx);
		buffer = buffer.slice(idx + 2);

		const data = raw
			.split("\n")
			.filter((l) => l.startsWith("data:"))
			.map((l) => l.slice(5).trimStart())
			.join("\n");

		if (data) {
			try {
				events.push(JSON.parse(data));
			} catch {
				// невалидный JSON — пропускаем
			}
		}
		idx = buffer.indexOf("\n\n");
	}
	return { remaining: buffer, events };
}

// --- Обработка одного SSE-события ---

export function handleSseEvent(event: any, s: SseSetters): void {
	const p = event.payload;
	console.log("[SSE handler]", event.event);
	switch (event.event) {
		case "thought_stream":
			if (s.isSessionFinished()) break;
			s.setLiveThought(p?.thought || "");
			break;

		case "llm_step": {
			const { thought, action, args, step } = p;
			s.setSessionFinished(false);
			s.setLiveThought("");
			s.setEvents((prev) => {
				const next = [...prev];
				if (thought) next.push({ type: "thought", role: "assistant", thought, step });
				if (action && action !== "finish_task") {
					next.push({ type: "tool_use", role: "assistant", action, result: args, step });
					s.setLiveStatus(`Агент использует: ${action}`);
				}
				return next;
			});
			break;
		}

		case "assistant_stream":
			if (s.isSessionFinished()) break;
			s.setCurrentAnswer(p?.content || "");
			s.setLiveStatus("Формируется ответ...");
			break;

		case "sub_agent_plan_updated": {
			const { agent, plan } = p;
			s.updatePane(agent, { plan: Array.isArray(plan) ? plan : [] });
			break;
		}

		case "tool_result": {
			const { action, result, success, step } = p;
			if (action !== "finish_task") {
				s.setEvents((prev) => {
					const i = prev.findLastIndex(
						(e) => e.type === "tool_use" && e.action === action && e.step === step,
					);
					if (i !== -1) {
						const u = [...prev];
						u[i] = {
							type: "tool_result",
							role: "assistant",
							action,
							result,
							success,
							step,
						};
						return u;
					}
					return [
						...prev,
						{ type: "tool_result", role: "assistant", action, result, success, step },
					];
				});
				s.setLiveStatus(`Выполнено: ${action}`);
			} else {
				s.setLiveStatus("Формируется ответ...");
			}
			break;
		}

		case "agent_error": {
			const { step, message } = p;
			s.setEvents((prev) => {
				const i = prev.findLastIndex((e) => e.type === "tool_use" && e.step === step);
				if (i !== -1) {
					const u = [...prev];
					u[i] = {
						type: "tool_result",
						role: "assistant",
						action: u[i].action!,
						result: { error: message },
						success: false,
						step,
					};
					return u;
				}
				return [
					...prev,
					{ type: "message", role: "assistant", content: `Ошибка: ${message}` },
				];
			});
			s.setLiveStatus("Произошла ошибка");
			break;
		}

		case "session_finished": {
			const { summary } = p;
			if (summary) {
				s.setSessionFinished(true);
				s.setLiveThought("");
				s.setEvents((prev) => [
					...prev,
					{ type: "message", role: "assistant", content: summary },
				]);
				s.setCurrentAnswer("");
				s.setLiveStatus("");
				s.setIsRunning(false);
			}
			break;
		}

		case "plan_updated": {
			const plan = Array.isArray(p?.plan) ? p.plan : [];
			s.setEvents((prev) => {
				const next = [...prev];
				const lastPlanIdx = next.findLastIndex(
					(e) => e.plan && !e.content && !e.action && !e.thought,
				);
				const planEvent = {
					type: "message" as const,
					role: "assistant" as const,
					plan,
					step: p?.step,
				};
				if (lastPlanIdx !== -1) {
					next[lastPlanIdx] = planEvent;
					return next;
				}
				return [...next, planEvent];
			});
			break;
		}

		case "confirmation_requested":
			s.setConfirmationRequest({
				requestId: p?.request_id || "",
				message: p?.message || "Требуется подтверждение",
				tool: p?.tool,
				args: p?.args,
				step: p?.step,
			});
			s.setLiveStatus("Требуется подтверждение");
			break;

		case "__final__":
			s.setSessionFinished(true);
			s.setLiveThought("");
			s.setLiveStatus("");
			s.setCurrentAnswer("");
			s.setConfirmationRequest(null);
			s.setIsRunning(false);
			break;

		case "intermediate_message":
			s.setEvents((prev) => [
				...prev,
				{ type: "message", role: p?.role || "assistant", content: p?.content || "" },
			]);
			break;

		case "context_tokens":
			if (p?.agent) {
				s.updatePane(p.agent, { contextTokens: p.count || 0 });
			} else {
				s.setContextTokens(p?.count || 0);
			}
			break;

		case "sub_agent_started": {
			const { agent, task: t, model: m } = p;
			s.setSubAgentPanes((prev) => {
				const exists = prev.find((x) => x.name === agent);
				if (exists) {
					return prev.map((x) => {
						if (x.name !== agent) return x;
						// Сохраняем текущую сессию в историю
						const prevSessions = x.sessions ?? [];
						const currentSession = {
							task: x.task,
							model: x.model || "",
							steps: x.steps,
							plan: x.plan ?? [],
							result: x.result,
						};
						const hasContent = x.steps.length > 0 || x.result || x.task;
						return {
							...x,
							task: t,
							model: m || x.model,
							status: "running",
							steps: [],
							plan: [],
							result: undefined,
							question: undefined,
							answer: undefined,
							startedAt: Date.now(),
							sessions: hasContent ? [...prevSessions, currentSession] : prevSessions,
						};
					});
				}
				return [
					...prev,
					{
						name: agent,
						displayName: AGENT_DISPLAY_NAMES[agent] || agent,
						task: t,
						model: m || "",
						status: "running",
						steps: [],
						plan: [],
						startedAt: Date.now(),
						sessions: [],
					},
				];
			});
			break;
		}

		case "sub_agent_step": {
			const { agent, step, thought, action, args } = p;
			s.setSubAgentPanes((prev) =>
				prev.map((x) => {
					if (x.name !== agent) return x;
					const i = x.steps.findIndex((s) => s.step === step);
					const newSteps =
						i !== -1
							? x.steps.map((s, idx) =>
									idx === i ? { ...s, thought, action, args } : s,
								)
							: [...x.steps, { step, thought, action, args }];
					return { ...x, steps: newSteps };
				}),
			);
			break;
		}

		case "powershell_output": {
			const { agent: a, line, stream } = p;
			if (stream !== "stdout") break;
			s.setSubAgentPanes((prev) =>
				prev.map((x) => {
					if (x.name !== a) return x;
					const steps = [...x.steps];
					const last = steps.length - 1;
					if (last < 0) return x;
					steps[last] = {
						...steps[last],
						streamLines: [...(steps[last].streamLines ?? []), line],
					};
					return { ...x, steps };
				}),
			);
			break;
		}

		case "sub_agent_tool_result": {
			const { agent: a, step, action: act, result: res, success } = p;
			s.setSubAgentPanes((prev) =>
				prev.map((x) => {
					if (x.name !== a) return x;
					const i = x.steps.findIndex((s) => s.step === step && s.action === act);
					if (i === -1) return x;
					const newSteps = x.steps.map((s, idx) =>
						idx === i ? { ...s, result: res, success } : s,
					);
					return { ...x, steps: newSteps };
				}),
			);
			break;
		}

		case "sub_agent_finished": {
			const { agent, result: r, success } = p;
			const resultStr = String(r ?? "");
			s.setSubAgentPanes((prev) =>
				prev.map((x) => {
					if (x.name !== agent) return x;
					// Добавляем завершённую активную сессию в историю
					const finishedSession = {
						task: x.task,
						model: x.model || "",
						steps: x.steps,
						plan: x.plan ?? [],
						result: resultStr,
					};
					const sessions = [...(x.sessions ?? []), finishedSession];
					return {
						...x,
						status: success ? "done" : "error",
						result: resultStr,
						sessions,
					};
				}),
			);
			break;
		}

		case "sub_agent_error":
			s.updatePane(p?.agent ?? "", { status: "error" });
			break;

		case "sub_agent_question": {
			const { question } = p;
			s.setSubAgentPanes((prev) => {
				const ri = [...prev].reverse().findIndex((x) => x.status === "running");
				if (ri === -1) return prev;
				const i = prev.length - 1 - ri;
				const u = [...prev];
				u[i] = { ...u[i], question };
				return u;
			});
			break;
		}

		case "sub_agent_answer": {
			const { question, answer } = p;
			s.setSubAgentPanes((prev) =>
				prev.map((x) => (x.question === question ? { ...x, answer } : x)),
			);
			break;
		}
	}
}
