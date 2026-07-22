/* eslint-disable @typescript-eslint/no-explicit-any */
import type { ChatEvent, ConfirmationRequest, SubAgentPane } from "../types";

const AGENT_DISPLAY_NAMES: Record<string, string> = {
	telegram: "Telegram",
	file: "Файлы",
	system: "Система",
	web: "Веб",
};

function normalizeContent(value: unknown): string {
	return String(value ?? "").trim();
}

function appendAssistantMessageOnce(
	prev: ChatEvent[],
	content: string,
): ChatEvent[] {
	const normalized = normalizeContent(content);
	const lastMessage = [...prev]
		.reverse()
		.find(
			(event) => event.type === "message" && event.role === "assistant",
		);
	if (lastMessage && normalizeContent(lastMessage.content) === normalized) {
		return prev;
	}
	return [...prev, { type: "message", role: "assistant", content }];
}

export interface SseSetters {
	setEvents: React.Dispatch<React.SetStateAction<ChatEvent[]>>;
	setLiveThought: React.Dispatch<React.SetStateAction<string>>;
	setLiveStatus: React.Dispatch<React.SetStateAction<string>>;
	setCurrentAnswer: React.Dispatch<React.SetStateAction<string>>;
	setIsRunning: React.Dispatch<React.SetStateAction<boolean>>;
	setConfirmationRequest: React.Dispatch<
		React.SetStateAction<ConfirmationRequest | null>
	>;
	setContextTokens: React.Dispatch<React.SetStateAction<number>>;
	setSubAgentPanes: React.Dispatch<React.SetStateAction<SubAgentPane[]>>;
	updatePane: (id: string, patch: Partial<SubAgentPane>) => void;
	getCurrentAnswer: () => string;
	isSessionFinished: () => boolean;
	setSessionFinished: (value: boolean) => void;
}

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
				// ignore malformed event
			}
		}
		idx = buffer.indexOf("\n\n");
	}
	return { remaining: buffer, events };
}

export function handleSseEvent(event: any, s: SseSetters): void {
	const p = event.payload;
	switch (event.event) {
		case "thought_stream":
			if (s.isSessionFinished()) break;
			s.setLiveThought(p?.thought || "");
			break;

		case "llm_step": {
			// Сервер может дослать шаг старого retry через replay WebSocket уже
			// после завершения или ручной очистки чата. Не даём ему снова
			// пометить завершённую сессию как активную и вернуть старые события.
			if (s.isSessionFinished()) break;
			const { thought, action, args, step } = p;
			s.setSessionFinished(false);
			s.setLiveThought("");
			s.setEvents((prev) => {
				const next = [...prev];
				// thought_source "native" — из отдельного reasoning-канала модели;
				// "self" — модель без такого канала сама вернула поле thought в
				// JSON-ответе (см. src/agent/core/runtime.py). Оба показываем.
				if (thought)
					next.push({
						type: "thought",
						role: "assistant",
						thought,
						step,
					});
				if (action && action !== "finish_task") {
					next.push({
						type: "tool_use",
						role: "assistant",
						action,
						result: args,
						step,
					});
					s.setLiveStatus(`Агент использует: ${action}`);
				}
				return next;
			});
			break;
		}

		case "assistant_stream":
			if (s.isSessionFinished()) break;
			{
				const content = String(p?.content || "");
				const normalized = normalizeContent(content);
				s.setEvents((prev) => {
					const lastMessageIdx = prev.findLastIndex(
						(event) =>
							event.type === "message" &&
							event.role === "assistant" &&
							Boolean(event.content),
					);
					if (lastMessageIdx === -1 || !normalized) {
						s.setCurrentAnswer(content);
						return prev;
					}
					const last = prev[lastMessageIdx];
					const lastContent = String(last.content || "");
					if (
						normalized.startsWith(normalizeContent(lastContent)) ||
						normalizeContent(lastContent).startsWith(normalized)
					) {
						const updated = [...prev];
						updated[lastMessageIdx] = {
							...last,
							content:
								content.length >= lastContent.length
									? content
									: lastContent,
						};
						s.setCurrentAnswer("");
						return updated;
					}
					s.setCurrentAnswer(content);
					return prev;
				});
			}
			s.setLiveStatus("Формируется ответ...");
			break;

		case "sub_agent_plan_updated":
			if (p?.run_id) {
				s.updatePane(p.run_id, {
					plan: Array.isArray(p.plan) ? p.plan : [],
				});
			}
			break;

		case "tool_result": {
			const { action, result, success, step } = p;
			if (action !== "finish_task") {
				s.setEvents((prev) => {
					const i = prev.findLastIndex(
						(e) =>
							e.type === "tool_use" &&
							e.action === action &&
							e.step === step,
					);
					if (i !== -1) {
						const updated = [...prev];
						updated[i] = {
							type: "tool_result",
							role: "assistant",
							action,
							result,
							success,
							step,
						};
						return updated;
					}
					return [
						...prev,
						{
							type: "tool_result",
							role: "assistant",
							action,
							result,
							success,
							step,
						},
					];
				});
				s.setLiveStatus(`Выполнено: ${action}`);
			} else {
				s.setLiveStatus("Формируется ответ...");
			}
			break;
		}

		case "agent_warning": {
			if (s.isSessionFinished()) break;
			console.warn("[agent_warning]", p?.message);
			s.setEvents((prev) => [
				...prev,
				{
					type: "message",
					role: "assistant",
					content: `⚠ ${p?.message || "Предупреждение"}`,
				},
			]);
			break;
		}

		case "agent_error": {
			if (s.isSessionFinished()) break;
			const { step, message } = p;
			s.setEvents((prev) => {
				const i = prev.findLastIndex(
					(e) => e.type === "tool_use" && e.step === step,
				);
				if (i !== -1) {
					const updated = [...prev];
					updated[i] = {
						type: "tool_result",
						role: "assistant",
						action: updated[i].action!,
						result: { error: message },
						success: false,
						step,
					};
					return updated;
				}
				return [
					...prev,
					{
						type: "message",
						role: "assistant",
						content: `Ошибка: ${message}`,
					},
				];
			});
			s.setLiveStatus("Произошла ошибка");
			break;
		}

		case "cancelled": {
			s.setSessionFinished(true);
			s.setLiveThought("");
			s.setCurrentAnswer("");
			s.setConfirmationRequest(null);
			s.setIsRunning(false);
			s.setLiveStatus("");
			break;
		}

		case "session_finished": {
			const { summary } = p;
			if (summary) {
				s.setSessionFinished(true);
				s.setLiveThought("");
				s.setEvents((prev) =>
					appendAssistantMessageOnce(prev, summary),
				);
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
			if (!p?.summary && !p?.error) {
				break;
			}
			s.setSessionFinished(true);
			s.setLiveThought("");
			s.setCurrentAnswer("");
			s.setConfirmationRequest(null);
			s.setIsRunning(false);
			if (p?.error) {
				s.setLiveStatus("");
				s.setEvents((prev) => [
					...prev,
					{
						type: "message",
						role: "assistant",
						content: `⚠️ Ошибка: ${p.error}`,
					},
				]);
			} else {
				s.setLiveStatus("");
			}
			break;

		case "context_tokens":
			if (p?.run_id) {
				s.updatePane(p.run_id, { contextTokens: p.count || 0 });
			} else {
				s.setContextTokens(p?.count || 0);
			}
			break;

		case "sub_agent_started": {
			const { agent, run_id, task, model } = p;
			if (!run_id) break;
			s.setSubAgentPanes((prev) => {
				const existing = prev.find((pane) => pane.id === run_id);
				if (existing) {
					return prev.map((pane) =>
						pane.id === run_id
							? {
									...pane,
									task,
									model: model || pane.model,
									status: "running",
									steps: [],
									plan: [],
									result: undefined,
									question: undefined,
									answer: undefined,
									startedAt: Date.now(),
								}
							: pane,
					);
				}
				return [
					...prev,
					{
						id: run_id,
						name: agent,
						displayName: AGENT_DISPLAY_NAMES[agent] || agent,
						task,
						model: model || "",
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
			const { run_id, step, thought, action, args } = p;
			if (!run_id) break;
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== run_id) return pane;
					const i = pane.steps.findIndex(
						(item) => item.step === step,
					);
					const newStep = { step, thought, action, args };
					const steps =
						i !== -1
							? pane.steps.map((item, idx) =>
									idx === i ? { ...item, ...newStep } : item,
								)
							: [...pane.steps, newStep];
					return { ...pane, steps };
				}),
			);
			break;
		}

		case "powershell_output": {
			const { run_id, line, stream } = p;
			if (!run_id || stream !== "stdout") break;
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== run_id) return pane;
					const steps = [...pane.steps];
					const last = steps.length - 1;
					if (last < 0) return pane;
					steps[last] = {
						...steps[last],
						streamLines: [...(steps[last].streamLines ?? []), line],
					};
					return { ...pane, steps };
				}),
			);
			break;
		}

		case "sub_agent_tool_result": {
			const { run_id, step, action, result, success } = p;
			if (!run_id) break;
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== run_id) return pane;
					const i = pane.steps.findIndex(
						(item) => item.step === step && item.action === action,
					);
					if (i === -1) return pane;
					const steps = pane.steps.map((item, idx) =>
						idx === i ? { ...item, result, success } : item,
					);
					return { ...pane, steps };
				}),
			);
			break;
		}

		case "sub_agent_finished": {
			const { run_id, result, summary, success, cancelled } = p;
			if (!run_id) break;
			const resultStr = String(result ?? summary ?? "");
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== run_id) return pane;
					const finalPlan =
						success && !cancelled && pane.plan
							? pane.plan.map((item) =>
									item.status === "in_progress"
										? {
												...item,
												status: "completed" as const,
											}
										: item,
								)
							: (pane.plan ?? []);
					const finishedSession = {
						task: pane.task,
						model: pane.model || "",
						steps: pane.steps,
						plan: finalPlan,
						result: resultStr,
					};
					return {
						...pane,
						status: cancelled
							? "cancelled"
							: success
								? "done"
								: "error",
						plan: finalPlan,
						result: resultStr,
						errorMessage:
							!success && !cancelled
								? pane.errorMessage || resultStr
								: pane.errorMessage,
						sessions: [...(pane.sessions ?? []), finishedSession],
					};
				}),
			);
			break;
		}

		case "sub_agent_paused":
			if (p?.run_id) s.updatePane(p.run_id, { status: "paused" });
			break;

		case "sub_agent_task_replaced":
			if (p?.run_id) s.updatePane(p.run_id, { task: p.task ?? "" });
			break;

		case "sub_agent_resumed":
			if (p?.run_id) s.updatePane(p.run_id, { status: "running" });
			break;

		case "sub_agent_error": {
			if (!p?.run_id) break;
			const errMsg = p?.message || "Неизвестная ошибка";
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== p.run_id) return pane;
					const errStep = {
						step: p.step ?? pane.steps.length + 1,
						action: "error",
						result: { error: errMsg },
						success: false,
					};
					return {
						...pane,
						errorMessage: errMsg,
						steps: [...pane.steps, errStep],
					};
				}),
			);
			break;
		}

		case "sub_agent_warning": {
			console.warn("[sub_agent_warning]", p?.message);
			if (!p?.run_id) break;
			const warnMsg = p?.message || "Предупреждение";
			s.setSubAgentPanes((prev) =>
				prev.map((pane) => {
					if (pane.id !== p.run_id) return pane;
					const warnStep = {
						step: p.step ?? pane.steps.length + 1,
						action: "warning",
						result: { warning: warnMsg },
						success: true,
					};
					return { ...pane, steps: [...pane.steps, warnStep] };
				}),
			);
			break;
		}

		case "sub_agent_question":
			if (p?.run_id) {
				s.updatePane(p.run_id, { question: p.question });
				s.setSubAgentPanes((prev) =>
					prev.map((pane) => {
						if (pane.id !== p.run_id) return pane;
						const qStep = {
							step: pane.steps.length + 1,
							action: "ask_operator_question",
							result: { question: p.question },
							success: true,
						};
						return { ...pane, steps: [...pane.steps, qStep] };
					}),
				);
			}
			break;

		case "sub_agent_answer":
			if (p?.run_id) {
				s.updatePane(p.run_id, { answer: p.answer });
				s.setSubAgentPanes((prev) =>
					prev.map((pane) => {
						if (pane.id !== p.run_id) return pane;
						const aStep = {
							step: pane.steps.length + 1,
							action: "operator_answer",
							result: { answer: p.answer },
							success: true,
						};
						return { ...pane, steps: [...pane.steps, aStep] };
					}),
				);
			}
			break;
	}
}
