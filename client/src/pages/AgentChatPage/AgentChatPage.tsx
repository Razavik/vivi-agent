import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./AgentChatPage.module.css";
import type { PlanItem, SubAgentPane, SubAgentSession, SubAgentStep } from "../../types";

interface AgentChatPageProps {
	panes: SubAgentPane[];
}

const AGENT_DISPLAY_NAMES: Record<string, string> = {
	file: "Файловый агент",
	system: "Системный агент",
	telegram: "Telegram-агент",
	web: "Веб-агент",
};

const ALL_AGENTS: Pick<SubAgentPane, "name" | "displayName">[] = [
	{ name: "file", displayName: AGENT_DISPLAY_NAMES.file },
	{ name: "system", displayName: AGENT_DISPLAY_NAMES.system },
	{ name: "telegram", displayName: AGENT_DISPLAY_NAMES.telegram },
	{ name: "web", displayName: AGENT_DISPLAY_NAMES.web },
];

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
				for (const a of msg.actions) {
					steps.push({
						step: a.step ?? steps.length + 1,
						thought: a.thought,
						action: a.action,
						args: a.args,
						result: a.result,
						success: a.success,
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
	const allSteps = sessions.flatMap((s) => s.steps);

	return {
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
	return ALL_AGENTS.map((agent) => {
		const active = activePanes.find((p) => p.name === agent.name);
		if (active) return active;
		const historic = historicPanes.find((p) => p.name === agent.name);
		return (
			historic ?? {
				name: agent.name,
				displayName: agent.displayName,
				task: "",
				status: "idle",
				steps: [],
				startedAt: 0,
			}
		);
	});
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

function StepBlock({ s }: { s: SubAgentStep }) {
	const hasResult = s.result !== undefined;
	const st = hasResult ? (s.success ? "success" : "fail") : "pending";
	const argsStr = s.args ? fmt(s.args) : "";
	const resultStr = hasResult ? fmt(s.result) : "";

	return (
		<div className={`${styles.stepBlock} ${styles[st]}`}>
			<div className={styles.stepHeader}>
				<span className={styles.stepNum}>#{s.step}</span>
				{s.action && (
					<span className={`${styles.stepAction} ${styles[st]}`}>{s.action}</span>
				)}
				{hasResult && (
					<span className={`${styles.stepBadge} ${styles[st]}`}>
						{s.success ? "ok" : "fail"}
					</span>
				)}
			</div>
			{s.thought && <div className={styles.stepThought}>{s.thought}</div>}
			{argsStr && !hasResult && (
				<div className={styles.stepArgs}>
					<pre className={styles.stepArgsPre}>{argsStr}</pre>
				</div>
			)}
			{s.streamLines && s.streamLines.length > 0 && (
				<div className={styles.stepStream}>
					<pre className={styles.stepStreamPre}>{s.streamLines.join("\n")}</pre>
				</div>
			)}
			{hasResult && resultStr && (
				<div className={styles.stepResult}>
					<pre className={styles.resultPre}>{resultStr}</pre>
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
	const done = plan.filter((i) => i.status === "completed").length;
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
			{session.steps.map((s, i) => (
				<StepBlock key={i} s={s} />
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

	// Текущая активная сессия — показываем если есть незавершённые шаги вне sessions
	const sessionsStepCount = (pane.sessions ?? []).reduce((n, s) => n + s.steps.length, 0);
	const hasUnsavedSteps = pane.steps.length > sessionsStepCount;
	const activeSession: SubAgentSession | null =
		hasUnsavedSteps || pane.status === "running"
			? { task: pane.task, model: pane.model || "", steps: pane.steps, plan: pane.plan ?? [] }
			: null;

	// Все сессии: история + активная (если есть)
	const allSessions: SubAgentSession[] = [
		...(pane.sessions ?? []),
		...(activeSession ? [activeSession] : []),
	];

	return (
		<div className={styles.agentChat}>
			{allSessions.map((session, i) => (
				<SessionBlock key={i} session={session} index={i} allSessions={allSessions} />
			))}

			{pane.question && (
				<div className={styles.questionBlock}>
					<div className={styles.questionLabel}>Вопрос директору</div>
					<div className={styles.questionText}>{pane.question}</div>
				</div>
			)}

			{pane.answer && (
				<div className={styles.answerBlock}>
					<div className={styles.answerLabel}>Ответ директора</div>
					<div className={styles.answerText}>{pane.answer}</div>
				</div>
			)}

			<div ref={bottomRef} />
		</div>
	);
}

export function AgentChatPage({ panes }: AgentChatPageProps) {
	const { agentName } = useParams<{ agentName: string }>();
	const navigate = useNavigate();
	const [historicPanes, setHistoricPanes] = useState<SubAgentPane[]>([]);

	const loadHistory = useCallback(async () => {
		try {
			const res = await fetch("/api/agents/history");
			const data = await res.json();
			const loaded: SubAgentPane[] = (data.agents ?? []).map((a: any) =>
				historyToPane(a.name, AGENT_DISPLAY_NAMES[a.name] ?? a.name, a.chat_history ?? []),
			);
			setHistoricPanes(loaded);
		} catch {}
	}, []);

	const clearAgent = useCallback(
		async (agentName: string) => {
			await fetch(`/api/agents/${agentName}/clear`, { method: "POST" });
			await loadHistory();
		},
		[loadHistory],
	);

	const clearAll = useCallback(async () => {
		await fetch("/api/agents/clear/all", { method: "POST" });
		await loadHistory();
	}, [loadHistory]);

	useEffect(() => {
		void loadHistory();
	}, [loadHistory]);

	useEffect(() => {
		const hasDone = panes.some((p) => p.status === "done" || p.status === "error");
		if (hasDone) void loadHistory();
	}, [panes, loadHistory]);

	const allPanes = buildPaneList(panes, historicPanes);

	const selected =
		agentName && allPanes.find((p) => p.name === agentName) ? agentName : allPanes[0].name;

	useEffect(() => {
		if (!agentName || !allPanes.find((p) => p.name === agentName)) {
			navigate(`/agents/${allPanes[0].name}`, { replace: true });
		}
	}, [agentName, allPanes, navigate]);

	const activePane = allPanes.find((p) => p.name === selected) ?? allPanes[0];

	return (
		<div className={styles.page}>
			{/* ── Левая панель — список агентов ── */}
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
							key={pane.name}
							className={`${styles.agentCard} ${agentName === pane.name ? styles.selected : ""}`}
							onClick={() => navigate(`/agents/${pane.name}`)}
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
								{(pane.status === "done" || pane.status === "error") && (
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
								)}
							</div>
						</div>
					))}
				</div>
			</aside>

			{/* ── Правая панель — чат ── */}
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
				</div>

				{activePane.status === "idle" ? (
					<div className={styles.chatEmpty}>
						<div className={styles.chatEmptyIcon}>◎</div>
						<div>Агент ещё не запускался</div>
						<div style={{ fontSize: 12, opacity: 0.6 }}>
							Дай директору задачу — здесь появится лог
						</div>
					</div>
				) : (
					<>
						<AgentChat pane={activePane} />
						<div className={styles.readonlyBar}>
							Только просмотр — писать агентам нельзя
						</div>
					</>
				)}
			</div>
		</div>
	);
}
