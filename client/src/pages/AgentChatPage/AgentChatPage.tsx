import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./AgentChatPage.module.css";
import type { PlanItem, SubAgentPane, SubAgentSession, SubAgentStep } from "../../types";

interface ArtifactMeta {
	name: string;
	mime_type: string;
	size: number;
	created_at?: number;
}

interface ArtifactContent extends ArtifactMeta {
	content: string;
}

function ArtifactsPanel({ runId }: { runId: string }) {
	const [artifacts, setArtifacts] = useState<ArtifactMeta[]>([]);
	const [selected, setSelected] = useState<ArtifactContent | null>(null);
	const [loading, setLoading] = useState(false);

	const reload = useCallback(async () => {
		try {
			const res = await fetch(`/api/runs/${runId}/artifacts`);
			const data = await res.json();
			setArtifacts(data.artifacts ?? []);
		} catch {
			// ignore
		}
	}, [runId]);

	useEffect(() => {
		void reload();
		const timer = setInterval(() => void reload(), 5000);
		return () => clearInterval(timer);
	}, [reload]);

	const openArtifact = async (name: string) => {
		setLoading(true);
		try {
			const res = await fetch(`/api/runs/${runId}/artifacts/${encodeURIComponent(name)}`);
			const data = await res.json();
			setSelected(data);
		} catch {
			// ignore
		} finally {
			setLoading(false);
		}
	};

	if (!artifacts.length) {
		return <div className={styles.artifactsEmpty}>Нет артефактов</div>;
	}

	return (
		<div className={styles.artifactsPanel}>
			<div className={styles.artifactsList}>
				{artifacts.map((a) => (
					<div
						key={a.name}
						className={`${styles.artifactItem} ${selected?.name === a.name ? styles.artifactSelected : ""}`}
						onClick={() => void openArtifact(a.name)}
					>
						<div className={styles.artifactName}>{a.name}</div>
						<div className={styles.artifactMeta}>
							<span>{a.mime_type}</span>
							<span>{(a.size / 1024).toFixed(1)} KB</span>
						</div>
					</div>
				))}
			</div>
			{selected && (
				<div className={styles.artifactViewer}>
					<div className={styles.artifactViewerHeader}>
						<span>{selected.name}</span>
						<span className={styles.artifactViewerMime}>{selected.mime_type}</span>
						<button
							className={styles.artifactCloseBtn}
							onClick={() => setSelected(null)}
						>
							✕
						</button>
					</div>
					{loading ? (
						<div className={styles.artifactLoading}>Загрузка…</div>
					) : selected.mime_type.startsWith("text/") ? (
						<pre className={styles.artifactContent}>{selected.content}</pre>
					) : (
						<div className={styles.artifactContent}>
							<span className={styles.artifactBinary}>
								[binary: {selected.content.length / 2} bytes]
							</span>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

interface AgentChatPageProps {
	panes: SubAgentPane[];
}

const AGENT_DISPLAY_NAMES: Record<string, string> = {
	file: "Файловый агент",
	system: "Системный агент",
	telegram: "Telegram-агент",
	web: "Веб-агент",
};

function historyToPane(name: string, displayName: string, chatHistory: any[]): SubAgentPane {
	const sessions: SubAgentSession[] = [];
	let pendingTask = "";

	for (const msg of chatHistory) {
		if (msg.role === "user") {
			pendingTask = msg.content ?? "";
		}
		if (msg.role === "assistant") {
			const steps: SubAgentStep[] = [];
			const plan: PlanItem[] = Array.isArray(msg.plan) ? msg.plan : [];
			if (Array.isArray(msg.actions)) {
				for (const action of msg.actions) {
					steps.push({
						step: action.step ?? steps.length + 1,
						thought: action.thought,
						action: action.action,
						args: action.args,
						result: action.result,
						success: action.success,
					});
				}
			}
			sessions.push({
				task: pendingTask,
				model: msg.model ?? "",
				steps,
				result: msg.content ?? "",
				plan,
			});
			pendingTask = "";
		}
	}

	if (sessions.length === 0) {
		return {
			id: `history:${name}`,
			name,
			displayName,
			task: "",
			status: "idle",
			steps: [],
			sessions: [],
			startedAt: 0,
		};
	}

	const lastSession = sessions[sessions.length - 1];
	const allSteps = sessions.flatMap((session) => session.steps);

	return {
		id: `history:${name}`,
		name,
		displayName,
		task: sessions[0]?.task ?? "",
		status: "done",
		steps: allSteps,
		result: lastSession?.result,
		model: lastSession?.model,
		plan: lastSession?.plan,
		sessions,
		startedAt: 0,
	};
}

function buildPaneList(activePanes: SubAgentPane[], historicPanes: SubAgentPane[]): SubAgentPane[] {
	// Группируем активные panes по name — оставляем только последний запуск,
	// предыдущие запуски складываем в sessions
	const grouped = new Map<string, SubAgentPane>();
	for (const pane of activePanes) {
		const existing = grouped.get(pane.name);
		if (!existing || pane.startedAt > existing.startedAt) {
			if (existing) {
				// Предыдущий запуск → в sessions нового
				const prevSession = {
					task: existing.task,
					model: existing.model || "",
					steps: existing.steps,
					plan: existing.plan ?? [],
					result: existing.result,
				};
				const merged = {
					...pane,
					sessions: [...(pane.sessions ?? []), ...(existing.sessions ?? []), prevSession],
				};
				grouped.set(pane.name, merged);
			} else {
				grouped.set(pane.name, pane);
			}
		} else {
			// Текущий pane старше — добавить как session
			const prevSession = {
				task: pane.task,
				model: pane.model || "",
				steps: pane.steps,
				plan: pane.plan ?? [],
				result: pane.result,
			};
			grouped.set(pane.name, {
				...existing,
				sessions: [...(existing.sessions ?? []), ...(pane.sessions ?? []), prevSession],
			});
		}
	}
	const mergedActive = Array.from(grouped.values());
	const activeNames = new Set(mergedActive.map((pane) => pane.name));
	return [...mergedActive, ...historicPanes.filter((pane) => !activeNames.has(pane.name))];
}

function fmt(value: unknown): string {
	if (value === undefined || value === null) return "";
	if (typeof value === "string") return value;
	try {
		return JSON.stringify(value, null, 2);
	} catch {
		return String(value);
	}
}

function StepBlock({ step }: { step: SubAgentStep }) {
	const [expanded, setExpanded] = useState(false);
	const hasResult = step.result !== undefined;
	const st = hasResult ? (step.success ? "success" : "fail") : "pending";
	const resultStr = hasResult ? fmt(step.result) : "";
	const hasDetails = !!(
		step.thought ||
		resultStr ||
		(step.streamLines && step.streamLines.length > 0)
	);

	return (
		<div className={`${styles.stepBlock} ${styles[st]} ${expanded ? styles.stepExpanded : ""}`}>
			<div
				className={styles.stepHeader}
				onClick={() => hasDetails && setExpanded(!expanded)}
				style={{ cursor: hasDetails ? "pointer" : "default" }}
			>
				<span className={`${styles.stepDot} ${styles[st]}`} />
				{step.action && (
					<span className={`${styles.stepAction} ${styles[st]}`}>{step.action}</span>
				)}
				{hasResult && (
					<span className={`${styles.stepBadge} ${styles[st]}`}>
						{step.success ? "ok" : "fail"}
					</span>
				)}
				{!hasResult && <span className={styles.stepSpinner} />}
				{hasDetails && (
					<span
						className={`${styles.stepChevron} ${expanded ? styles.stepChevronOpen : ""}`}
					>
						<svg
							width="10"
							height="10"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2.5"
						>
							<path d="M9 18l6-6-6-6" />
						</svg>
					</span>
				)}
			</div>
			{expanded && (
				<div className={styles.stepBody}>
					{step.thought && <div className={styles.stepThought}>{step.thought}</div>}
					{step.streamLines && step.streamLines.length > 0 && (
						<pre className={styles.stepStreamPre}>{step.streamLines.join("\n")}</pre>
					)}
					{hasResult && resultStr && <pre className={styles.resultPre}>{resultStr}</pre>}
				</div>
			)}
		</div>
	);
}

const PLAN_ICONS: Record<string, string> = {
	completed: "✓",
	in_progress: "◌",
	pending: "○",
};

function PlanBlock({ plan }: { plan: PlanItem[] }) {
	if (!plan.length) return null;
	const done = plan.filter((item) => item.status === "completed").length;
	return (
		<div className={styles.planBlock}>
			<div className={styles.planHeader}>
				<span className={styles.planLabel}>План</span>
				<span className={styles.planCounter}>
					{done} / {plan.length} tasks done
				</span>
			</div>
			<div className={styles.planList}>
				{plan.map((item) => (
					<div key={item.id} className={`${styles.planItem} ${styles[item.status]}`}>
						<span className={styles.planIcon}>{PLAN_ICONS[item.status] ?? "○"}</span>
						<span className={styles.planContent}>{item.content}</span>
					</div>
				))}
			</div>
		</div>
	);
}

function SessionBlock({
	session,
	index,
	allSessions,
}: {
	session: SubAgentSession;
	index: number;
	allSessions: SubAgentSession[];
}) {
	const prevModel = index > 0 ? allSessions[index - 1].model : null;
	const modelChanged = index > 0 && session.model && session.model !== prevModel;
	return (
		<div>
			{index > 0 && (
				<div className={styles.sessionDivider}>
					<span className={styles.sessionDividerLine} />
					{modelChanged && (
						<span className={styles.sessionDividerLabel}>модель: {session.model}</span>
					)}
					<span className={styles.sessionDividerLine} />
				</div>
			)}
			<div className={styles.taskBanner}>
				<div className={styles.taskBannerRow}>
					<div>
						<div className={styles.taskLabel}>Задача</div>
						<ReactMarkdown remarkPlugins={[remarkGfm]}>{session.task}</ReactMarkdown>
					</div>
					{session.model && <span className={styles.modelBadge}>{session.model}</span>}
				</div>
			</div>
			<PlanBlock plan={session.plan ?? []} />
			{session.steps.map((step, i) => (
				<StepBlock key={i} step={step} />
			))}
			{session.result && (
				<div className={`${styles.resultBanner} ${styles.success}`}>
					<div className={styles.resultBannerLabel}>Результат</div>
					<ReactMarkdown remarkPlugins={[remarkGfm]}>{session.result}</ReactMarkdown>
				</div>
			)}
		</div>
	);
}

function AgentChat({ pane }: { pane: SubAgentPane }) {
	const bottomRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		bottomRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [pane.steps.length, pane.result]);

	const sessionsStepCount = (pane.sessions ?? []).reduce(
		(n, session) => n + session.steps.length,
		0,
	);
	const hasUnsavedSteps = pane.steps.length > sessionsStepCount;
	const activeSession: SubAgentSession | null =
		hasUnsavedSteps || pane.status === "running"
			? { task: pane.task, model: pane.model || "", steps: pane.steps, plan: pane.plan ?? [] }
			: null;

	const allSessions: SubAgentSession[] = [
		...(pane.sessions ?? []),
		...(activeSession ? [activeSession] : []),
	];

	return (
		<div className={styles.agentChat}>
			{allSessions.map((session, i) => (
				<SessionBlock key={i} session={session} index={i} allSessions={allSessions} />
			))}

			<div ref={bottomRef} />
		</div>
	);
}

type ChatTab = "log" | "artifacts" | "timeline";

interface TimelineEvent {
	time: string;
	kind: string;
	label: string;
	detail?: string;
}

function buildTimeline(pane: SubAgentPane): TimelineEvent[] {
	const events: TimelineEvent[] = [];
	const fmt = (ts: number) =>
		new Date(ts).toLocaleTimeString("ru-RU", {
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});

	if (pane.startedAt) {
		events.push({
			time: fmt(pane.startedAt),
			kind: "start",
			label: "Запущен",
			detail: pane.task,
		});
	}

	const allSessions = pane.sessions ?? [];
	for (const session of allSessions) {
		for (const step of session.steps) {
			if (step.action === "ask_director") {
				events.push({
					time: "",
					kind: "question",
					label: "Вопрос директору",
					detail: step.args ? JSON.stringify(step.args) : "",
				});
			} else if (step.action === "finish_task") {
				events.push({
					time: "",
					kind: "finish",
					label: "Завершён",
					detail: String(step.args?.summary ?? ""),
				});
			} else if (step.action) {
				events.push({
					time: "",
					kind: step.success === false ? "fail" : "step",
					label: step.action,
					detail: step.thought,
				});
			}
		}
	}

	const liveSteps = pane.steps.filter((s) => !allSessions.flatMap((ss) => ss.steps).includes(s));
	for (const step of liveSteps) {
		events.push({
			time: "",
			kind: step.success === false ? "fail" : step.result !== undefined ? "step" : "pending",
			label: step.action ?? "…",
			detail: step.thought,
		});
	}

	if (pane.question) {
		events.push({
			time: "",
			kind: "question",
			label: "Вопрос директору",
			detail: pane.question,
		});
	}
	if (pane.status === "paused") {
		events.push({ time: "", kind: "pause", label: "На паузе" });
	}
	if (pane.result && pane.status === "done") {
		events.push({
			time: "",
			kind: "finish",
			label: "Готово",
			detail: pane.result.slice(0, 120),
		});
	}
	if (pane.status === "error") {
		events.push({ time: "", kind: "error", label: "Ошибка", detail: pane.errorMessage });
	}

	return events;
}

const TL_COLORS: Record<string, string> = {
	start: "var(--accent)",
	step: "rgba(255,255,255,0.2)",
	fail: "var(--err)",
	finish: "var(--ok)",
	question: "var(--warn)",
	pause: "var(--warn)",
	error: "var(--err)",
	pending: "#7eb0ff",
};

function TimelinePanel({ pane }: { pane: SubAgentPane }) {
	const events = buildTimeline(pane);
	if (!events.length) {
		return (
			<div className={styles.chatEmpty}>
				<div>Нет событий</div>
			</div>
		);
	}
	return (
		<div className={styles.timeline}>
			{events.map((ev, i) => (
				<div key={i} className={styles.tlRow}>
					<div className={styles.tlLeft}>
						{ev.time && <span className={styles.tlTime}>{ev.time}</span>}
						<span
							className={styles.tlDot}
							style={{ background: TL_COLORS[ev.kind] ?? "var(--border)" }}
						/>
						{i < events.length - 1 && <span className={styles.tlLine} />}
					</div>
					<div className={styles.tlContent}>
						<span
							className={styles.tlLabel}
							style={{ color: TL_COLORS[ev.kind] ?? "var(--text-muted)" }}
						>
							{ev.label}
						</span>
						{ev.detail && <span className={styles.tlDetail}>{ev.detail}</span>}
					</div>
				</div>
			))}
		</div>
	);
}

export function AgentChatPage({ panes }: AgentChatPageProps) {
	const { paneId } = useParams<{ paneId: string }>();
	const navigate = useNavigate();
	const [historicPanes, setHistoricPanes] = useState<SubAgentPane[]>([]);
	const [activeTab, setActiveTab] = useState<ChatTab>("log");

	const loadHistory = useCallback(async () => {
		try {
			const res = await fetch("/api/agents/history");
			const data = await res.json();
			const loaded: SubAgentPane[] = (data.agents ?? []).map((agent: any) =>
				historyToPane(
					agent.name,
					AGENT_DISPLAY_NAMES[agent.name] ?? agent.name,
					agent.chat_history ?? [],
				),
			);
			setHistoricPanes(loaded);
		} catch {
			// ignore history load errors
		}
	}, []);

	const clearAgent = useCallback(
		async (agentName: string) => {
			await fetch(`/api/agents/${agentName}/clear`, { method: "POST" });
			await loadHistory();
		},
		[loadHistory],
	);

	const clearAgentRuns = useCallback(
		async (agentName: string) => {
			await fetch(`/api/agents/${agentName}/clear-runs`, { method: "POST" });
			await loadHistory();
		},
		[loadHistory],
	);

	const clearAll = useCallback(async () => {
		await fetch("/api/agents/clear/all", { method: "POST" });
		await loadHistory();
	}, [loadHistory]);

	const cancelSelectedRun = useCallback(async (runId: string) => {
		await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
	}, []);

	const pauseSelectedRun = useCallback(async (runId: string) => {
		await fetch(`/api/runs/${runId}/pause`, { method: "POST" });
	}, []);

	const resumeSelectedRun = useCallback(async (runId: string) => {
		await fetch(`/api/runs/${runId}/resume`, { method: "POST" });
	}, []);

	useEffect(() => {
		void loadHistory();
	}, [loadHistory]);

	useEffect(() => {
		const hasDone = panes.some((pane) => pane.status === "done" || pane.status === "error");
		if (hasDone) void loadHistory();
	}, [panes, loadHistory]);

	const allPanes = buildPaneList(panes, historicPanes);
	const selectedId =
		paneId && allPanes.find((pane) => pane.id === paneId) ? paneId : allPanes[0]?.id;

	useEffect(() => {
		if (!allPanes.length) return;
		if (!paneId || !allPanes.find((pane) => pane.id === paneId)) {
			navigate(`/agents/${allPanes[0].id}`, { replace: true });
		}
	}, [paneId, allPanes, navigate]);

	if (!allPanes.length) {
		return <div className={styles.chatEmpty}>Нет данных по агентам</div>;
	}

	const activePane = allPanes.find((pane) => pane.id === selectedId) ?? allPanes[0];

	return (
		<div className={styles.page}>
			<aside className={styles.sidebar}>
				<div className={styles.sidebarHeader}>
					<span>Агенты</span>
					<button
						className={styles.clearAllBtn}
						onClick={clearAll}
						title="Очистить память всех агентов"
					>
						Очистить все
					</button>
				</div>
				<div className={styles.agentList}>
					{allPanes.map((pane) => (
						<div
							key={pane.id}
							className={`${styles.agentCard} ${selectedId === pane.id ? styles.selected : ""}`}
							onClick={() => navigate(`/agents/${pane.id}`)}
						>
							<span className={`${styles.cardDot} ${styles[pane.status]}`} />
							<div className={styles.cardInfo}>
								<div className={styles.cardName}>{pane.displayName}</div>
								<div className={styles.cardTask}>
									{pane.task || "Ещё не запускался"}
								</div>
							</div>
							<div className={styles.cardActions}>
								{pane.steps.length > 0 && (
									<span className={styles.cardSteps}>{pane.steps.length}</span>
								)}
								{pane.id.startsWith("history:") &&
									(pane.status === "done" || pane.status === "error") && (
										<>
											<button
												className={styles.clearCardBtn}
												title="Очистить runs"
												onClick={(e) => {
													e.stopPropagation();
													void clearAgentRuns(pane.name);
												}}
											>
												🗑
											</button>
											<button
												className={styles.clearCardBtn}
												title="Очистить память агента"
												onClick={(e) => {
													e.stopPropagation();
													void clearAgent(pane.name);
												}}
											>
												✕
											</button>
										</>
									)}
							</div>
						</div>
					))}
				</div>
			</aside>

			<div className={styles.chatArea}>
				<div className={styles.chatHeader}>
					<span className={`${styles.chatHeaderDot} ${styles[activePane.status]}`} />
					<span className={styles.chatHeaderName}>{activePane.displayName}</span>
					{activePane.steps.length > 0 && (
						<span className={styles.chatHeaderSteps}>
							{activePane.steps.length} шагов
						</span>
					)}
					{activePane.model && (
						<span className={styles.chatHeaderModel}>{activePane.model}</span>
					)}
					{activePane.contextTokens != null && activePane.contextTokens > 0 && (
						<span className={styles.chatHeaderTokens} title="Заполненность контекста">
							{activePane.contextTokens.toLocaleString()} tk
						</span>
					)}
					{!activePane.id.startsWith("history:") && (
						<>
							{activePane.status === "running" && (
								<button
									className={styles.pauseRunBtn}
									onClick={() => void pauseSelectedRun(activePane.id)}
									title="Приостановить запуск"
								>
									Пауза
								</button>
							)}
							{activePane.status === "paused" && (
								<button
									className={styles.resumeRunBtn}
									onClick={() => void resumeSelectedRun(activePane.id)}
									title="Продолжить запуск"
								>
									Продолжить
								</button>
							)}
							{(activePane.status === "running" ||
								activePane.status === "paused") && (
								<button
									className={styles.stopRunBtn}
									onClick={() => void cancelSelectedRun(activePane.id)}
									title="Остановить текущий запуск"
								>
									Остановить
								</button>
							)}
						</>
					)}
				</div>

				<div className={styles.tabBar}>
					<button
						className={`${styles.tabBtn} ${activeTab === "log" ? styles.tabActive : ""}`}
						onClick={() => setActiveTab("log")}
					>
						Лог
					</button>
					<button
						className={`${styles.tabBtn} ${activeTab === "artifacts" ? styles.tabActive : ""}`}
						onClick={() => setActiveTab("artifacts")}
					>
						Артефакты
					</button>
					<button
						className={`${styles.tabBtn} ${activeTab === "timeline" ? styles.tabActive : ""}`}
						onClick={() => setActiveTab("timeline")}
					>
						Timeline
					</button>
				</div>

				{activeTab === "timeline" ? (
					<TimelinePanel pane={activePane} />
				) : activeTab === "log" && activePane.status === "idle" ? (
					<div className={styles.chatEmpty}>
						<div className={styles.chatEmptyIcon}>◍</div>
						<div>Агент ещё не запускался</div>
						<div style={{ fontSize: 12, opacity: 0.6 }}>
							Дай директору задачу, и здесь появится лог
						</div>
					</div>
				) : activeTab === "log" ? (
					<>
						<AgentChat pane={activePane} />
						<div className={styles.readonlyBar}>
							Только просмотр — писать агентам нельзя
						</div>
					</>
				) : (
					<ArtifactsPanel runId={activePane.id} />
				)}
			</div>
		</div>
	);
}
