/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./AgentChatPage.module.css";
import type {
	PlanItem,
	SubAgentPane,
	SubAgentSession,
	SubAgentStep,
} from "../../types";
import { readJson } from "../../utils/http";
import { extractMarkdownImages } from "../../utils/renderText";
import { ImageThumbGrid } from "../../components/ImageThumbGrid/ImageThumbGrid";
import { AgentList } from "./components/sidebar/AgentList";
import { PlanSidebar } from "./components/plan/PlanSidebar";

interface AgentChatPageProps {
	panes: SubAgentPane[];
	onClearSubAgentPanes?: (agentName?: string) => void;
}

interface AgentConfigEntry {
	display_name?: string;
	description?: string;
	capabilities?: string[];
	when_to_use?: string;
	limits?: string[];
}

const AGENT_DISPLAY_NAMES: Record<string, string> = {
	file: "Файловый агент",
	system: "Системный агент",
	telegram: "Telegram-агент",
	web: "Веб-агент",
};

function historyToPane(
	name: string,
	displayName: string,
	chatHistory: any[],
): SubAgentPane {
	const sessions: SubAgentSession[] = [];
	let pendingTask = "";

	for (const msg of chatHistory) {
		if (msg.role === "user") {
			pendingTask = msg.content ?? "";
		}
		if (
			msg.role === "assistant" &&
			(Boolean(msg.content) ||
				(Array.isArray(msg.plan) && msg.plan.length > 0) ||
				Array.isArray(msg.actions))
		) {
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

function buildPaneList(
	activePanes: SubAgentPane[],
	historicPanes: SubAgentPane[],
): SubAgentPane[] {
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
					sessions: [
						...(pane.sessions ?? []),
						...(existing.sessions ?? []),
						prevSession,
					],
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
				sessions: [
					...(existing.sessions ?? []),
					...(pane.sessions ?? []),
					prevSession,
				],
			});
		}
	}
	const mergedActive = Array.from(grouped.values());

	// Теперь объединяем с историческими панелями
	const finalGrouped = new Map<string, SubAgentPane>();
	for (const pane of mergedActive) {
		finalGrouped.set(pane.name, pane);
	}
	for (const pane of historicPanes) {
		const existing = finalGrouped.get(pane.name);
		if (!existing) {
			// Если нет активной панели с таким именем, добавляем историческую
			finalGrouped.set(pane.name, pane);
			continue;
		}
		// Предпочитаем активную (live SSE) панель, но только если в ней реально
		// есть данные. Живая панель может прийти пустой (steps/sessions), если
		// sub_agent_step-события не успели накопиться в состоянии до момента
		// рендера — тогда историческая панель с сохранённой памятью агента
		// полнее и должна победить, даже если её статус не idle.
		const existingHasContent =
			existing.steps.length > 0 ||
			(existing.sessions?.length ?? 0) > 0 ||
			Boolean(existing.result);
		if (existing.status === "idle" && pane.status !== "idle") {
			finalGrouped.set(pane.name, pane);
			continue;
		}
		if (!existingHasContent) {
			const hasHistoricContent =
				pane.steps.length > 0 ||
				(pane.sessions?.length ?? 0) > 0 ||
				Boolean(pane.result);
			if (hasHistoricContent) {
				finalGrouped.set(pane.name, { ...pane, status: existing.status });
			}
		}
	}

	return Array.from(finalGrouped.values());
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
		<div
			className={`${styles.stepBlock} ${styles[st]} ${expanded ? styles.stepExpanded : ""}`}
		>
			<div
				className={styles.stepHeader}
				onClick={() => hasDetails && setExpanded(!expanded)}
				style={{ cursor: hasDetails ? "pointer" : "default" }}
			>
				<span className={`${styles.stepDot} ${styles[st]}`} />
				{step.action && (
					<span className={`${styles.stepAction} ${styles[st]}`}>
						{step.action}
					</span>
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
					{step.thought && (
						<div className={styles.stepThought}>{step.thought}</div>
					)}
					{step.streamLines && step.streamLines.length > 0 && (
						<pre className={styles.stepStreamPre}>
							{step.streamLines.join("\n")}
						</pre>
					)}
					{hasResult && resultStr && (
						<pre className={styles.resultPre}>{resultStr}</pre>
					)}
				</div>
			)}
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
	const modelChanged =
		index > 0 && session.model && session.model !== prevModel;
	const { text: taskText, images: taskImages } = extractMarkdownImages(
		session.task || "",
	);
	const { text: resultText, images: resultImages } = extractMarkdownImages(
		session.result || "",
	);
	return (
		<div>
			{index > 0 && (
				<div className={styles.sessionDivider}>
					<span className={styles.sessionDividerLine} />
					{modelChanged && (
						<span className={styles.sessionDividerLabel}>
							модель: {session.model}
						</span>
					)}
					<span className={styles.sessionDividerLine} />
				</div>
			)}
			<div className={styles.taskBanner}>
				<div className={styles.taskBannerRow}>
					<div>
						<div className={styles.taskLabel}>Задача</div>
						<ReactMarkdown remarkPlugins={[remarkGfm]}>
							{taskText}
						</ReactMarkdown>
						<ImageThumbGrid images={taskImages} />
					</div>
					{session.model && (
						<span className={styles.modelBadge}>
							{session.model}
						</span>
					)}
				</div>
			</div>
			{session.steps.map((step, i) => (
				<StepBlock key={i} step={step} />
			))}
			{session.result && (
				<div className={`${styles.resultBanner} ${styles.success}`}>
					<div className={styles.resultBannerLabel}>Результат</div>
					<ReactMarkdown remarkPlugins={[remarkGfm]}>
						{resultText}
					</ReactMarkdown>
					<ImageThumbGrid images={resultImages} />
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
			? {
					task: pane.task,
					model: pane.model || "",
					steps: pane.steps,
					plan: pane.plan ?? [],
				}
			: null;

	const allSessions: SubAgentSession[] = [
		...(pane.sessions ?? []),
		...(activeSession ? [activeSession] : []),
	];

	return (
		<div className={styles.agentChat}>
			{allSessions.map((session, i) => (
				<SessionBlock
					key={i}
					session={session}
					index={i}
					allSessions={allSessions}
				/>
			))}

			<div ref={bottomRef} />
		</div>
	);
}

export function AgentChatPage({ panes, onClearSubAgentPanes }: AgentChatPageProps) {
	const { paneId } = useParams<{ paneId: string }>();
	const navigate = useNavigate();
	const [historicPanes, setHistoricPanes] = useState<SubAgentPane[]>([]);
	const [configuredPanes, setConfiguredPanes] = useState<SubAgentPane[]>([]);

	const loadConfiguredAgents = useCallback(async () => {
		try {
			const res = await fetch("/api/agents-config");
			const data = await readJson<{
				config?: Record<string, AgentConfigEntry>;
			}>(res, {
				config: {},
			});
			const config = (data.config ?? {}) as Record<
				string,
				AgentConfigEntry
			>;
			const loaded = Object.entries(config)
				.filter(([name]) => name !== "operator")
				.map(([name, cfg]) => ({
					id: `config:${name}`,
					name,
					displayName:
						cfg.display_name || AGENT_DISPLAY_NAMES[name] || name,
					description: cfg.description,
					capabilities: cfg.capabilities ?? [],
					whenToUse: cfg.when_to_use,
					limits: cfg.limits ?? [],
					task: "",
					status: "idle" as const,
					steps: [],
					sessions: [],
					startedAt: 0,
				}));
			setConfiguredPanes(loaded);
		} catch {
			// ignore config load errors
		}
	}, []);

	// Преобразует активный запуск агента в SubAgentPane
	function activeRunToPane(run: any): SubAgentPane {
		return {
			id: `history:${run.agent_name}`,
			name: run.agent_name,
			displayName: AGENT_DISPLAY_NAMES[run.agent_name] ?? run.agent_name,
			task: run.task ?? "",
			status: run.status === "running" ? "running" : "idle",
			steps: [],
			sessions: [],
			startedAt: run.created_at ?? Date.now(),
			model: run.model,
			result: run.result,
			errorMessage: run.error,
		};
	}

	const loadHistory = useCallback(async () => {
		try {
			// Загружаем историю агентов
			const historyRes = await fetch("/api/agents/history");
			const historyData = await readJson<{ agents?: any[] }>(historyRes, {
				agents: [],
			});
			const historyPanes: SubAgentPane[] = (historyData.agents ?? []).map(
				(agent: any) =>
					historyToPane(
						agent.name,
						AGENT_DISPLAY_NAMES[agent.name] ?? agent.name,
						agent.chat_history ?? [],
					),
			);

			// Загружаем активные запуски
			const runsRes = await fetch("/api/runs");
			const runsData = await readJson<{ runs?: any[] }>(runsRes, {
				runs: [],
			});
			const activeRuns: SubAgentPane[] = (runsData.runs ?? []).map(
				(run: any) => activeRunToPane(run),
			);

			// Объединяем: активный запуск даёт актуальный статус, но не должен
			// затирать уже накопленные шаги/сессии из истории — activeRunToPane
			// всегда возвращает пустые steps/sessions (в процессе запуска они ещё
			// не записаны на диск), поэтому наложение статуса не должно стирать
			// то, что уже было загружено из /api/agents/history.
			const merged = new Map<string, SubAgentPane>();
			for (const pane of historyPanes) {
				merged.set(pane.name, pane);
			}
			for (const pane of activeRuns) {
				const existing = merged.get(pane.name);
				merged.set(pane.name, {
					...pane,
					status: "running",
					steps: existing?.steps ?? pane.steps,
					sessions: existing?.sessions ?? pane.sessions,
				});
			}

			setHistoricPanes(Array.from(merged.values()));
		} catch {
			// ignore history load errors
		}
	}, []);

	const clearAgent = useCallback(
		async (agentName: string) => {
			await fetch(`/api/agents/${agentName}/clear`, { method: "POST" });
			// Очищаем сохранённую на диске историю И живое состояние панели
			// (subAgentPanes на уровне App) — иначе buildPaneList продолжит
			// показывать уже накопленные в памяти шаги, т.к. "живая" панель с
			// реальным run_id побеждает историческую при слиянии.
			onClearSubAgentPanes?.(agentName);
			await loadHistory();
		},
		[loadHistory, onClearSubAgentPanes],
	);

	const clearAll = useCallback(async () => {
		await fetch("/api/agents/clear/all", { method: "POST" });
		onClearSubAgentPanes?.();
		await loadHistory();
		// Сбросить selectedId после очистки или выбрать первый доступный
		if (paneId) {
			navigate("/agents");
		}
	}, [loadHistory, navigate, onClearSubAgentPanes, paneId]);

	useEffect(() => {
		const timer = window.setTimeout(() => {
			void loadConfiguredAgents();
			void loadHistory();
		}, 0);
		return () => window.clearTimeout(timer);
	}, [loadConfiguredAgents, loadHistory]);

	useEffect(() => {
		const hasDone = panes.some(
			(pane) => pane.status === "done" || pane.status === "error",
		);
		if (!hasDone) return;
		const timer = window.setTimeout(() => void loadHistory(), 0);
		return () => window.clearTimeout(timer);
	}, [panes, loadHistory]);

	// Периодическое обновление статуса активных агентов
	useEffect(() => {
		const hasRunning = panes.some((pane) => pane.status === "running");
		if (!hasRunning) return;

		const interval = window.setInterval(() => {
			void loadHistory();
		}, 2000); // Обновляем каждые 2 секунды

		return () => window.clearInterval(interval);
	}, [panes, loadHistory]);

	const configByName = new Map(
		configuredPanes.map((pane) => [pane.name, pane]),
	);
	const allPanes = buildPaneList(panes, [
		...historicPanes,
		...configuredPanes,
	]).map((pane) => {
		const meta = configByName.get(pane.name);
		if (!meta) return pane;
		return {
			...pane,
			description: pane.description ?? meta.description,
			capabilities: pane.capabilities ?? meta.capabilities,
			whenToUse: pane.whenToUse ?? meta.whenToUse,
			limits: pane.limits ?? meta.limits,
		};
	});
	const selectedId =
		paneId && allPanes.find((pane) => pane.id === paneId)
			? paneId
			: allPanes[0]?.id;

	useEffect(() => {
		if (!allPanes.length) return;
		if (!paneId || !allPanes.find((pane) => pane.id === paneId)) {
			navigate(`/agents/${allPanes[0].id}`, { replace: true });
		}
	}, [paneId, allPanes, navigate]);

	if (!allPanes.length) {
		return <div className={styles.chatEmpty}>Нет данных по агентам</div>;
	}

	const activePane =
		allPanes.find((pane) => pane.id === selectedId) ?? allPanes[0];

	return (
		<div className={styles.page}>
			<AgentList
				panes={allPanes}
				selectedId={selectedId}
				onSelect={(id) => navigate(`/agents/${id}`)}
				onClearAgent={clearAgent}
				onClearAll={clearAll}
			/>

			<div className={styles.chatArea}>
				{activePane.status === "idle" ? (
					<div className={styles.agentProfile}>
						<div className={styles.profileHeader}>
							<div>
								<h2>{activePane.displayName}</h2>
								<p>
									{activePane.description ||
										"Агент настроен, но еще не запускался."}
								</p>
							</div>
						</div>
						<div className={styles.profileGrid}>
							<section>
								<h3>Возможности</h3>
								<div className={styles.profileTags}>
									{(activePane.capabilities?.length
										? activePane.capabilities
										: ["ожидание задачи"]
									).map((item) => (
										<span key={item}>{item}</span>
									))}
								</div>
							</section>
							<section>
								<h3>Ограничения</h3>
								<ul>
									{(activePane.limits?.length
										? activePane.limits
										: [
												"Действует только через доступные инструменты",
											]
									).map((item) => (
										<li key={item}>{item}</li>
									))}
								</ul>
							</section>
						</div>
					</div>
				) : (
					<div className={styles.logLayout}>
						<div className={styles.logMain}>
							<AgentChat pane={activePane} />
							<div className={styles.readonlyBar}>
								Только просмотр — писать агентам нельзя
							</div>
						</div>
						<PlanSidebar pane={activePane} />
					</div>
				)}
			</div>
		</div>
	);
}
