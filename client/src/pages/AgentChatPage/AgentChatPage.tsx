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
import { formatModelLabel } from "../../utils/modelLabel";
import { ImageThumbGrid } from "../../components/ImageThumbGrid/ImageThumbGrid";
import { AgentList } from "./components/sidebar/AgentList";
import { PlanSidebar } from "./components/plan/PlanSidebar";

const SIDEBAR_MIN_WIDTH = 260;
const SIDEBAR_MAX_WIDTH = 560;
const SIDEBAR_DEFAULT_WIDTH = 330;
const SIDEBAR_WIDTH_STORAGE_KEY = "agentChatSidebarWidth";

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

function sessionsToPane(
	name: string,
	displayName: string,
	sessions: any[],
): SubAgentPane {
	const normalizedSessions: SubAgentSession[] = sessions.map((session) => ({
		task: session.task ?? "",
		model: session.model ?? "",
		result: session.result ?? "",
		steps: Array.isArray(session.steps)
			? session.steps.map((action: any) => ({
					step: action.step ?? 0,
					thought: action.thought,
					action: action.action,
					args: action.args,
					result: action.result,
					success: action.success,
				}))
			: [],
		plan: Array.isArray(session.plan)
			? session.plan.map((item: any) => ({
					id: item.id ?? "",
					content: item.content ?? "",
					status: item.status ?? "pending",
				}))
			: [],
	}));

	const lastSession = normalizedSessions[normalizedSessions.length - 1];
	const allSteps = normalizedSessions.flatMap((session) => session.steps);

	return {
		id: `history:${name}`,
		name,
		displayName,
		task: normalizedSessions[0]?.task ?? "",
		status: "done",
		steps: allSteps,
		result: lastSession?.result,
		model: lastSession?.model,
		plan: lastSession?.plan,
		sessions: normalizedSessions,
		startedAt: 0,
	};
}

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
	const activeByName = new Map(mergedActive.map((pane) => [pane.name, pane]));
	// historicPanes на вызове — это [...configuredPanes, ...реальнаяИстория]:
	// пустышки из конфига (task: "", status: "idle") идут первыми, поэтому
	// простой "первый встреченный побеждает" всегда оставлял бы пустышку,
	// даже если следом идёт настоящая история с сохранёнными сессиями агента —
	// сайдбар вечно показывал бы "Ещё не запускался". Вместо этого пропускаем
	// вперёд пустышку, если следующий pane с тем же именем реально содержит данные.
	const hasContent = (pane: SubAgentPane): boolean =>
		pane.steps.length > 0 ||
		(pane.sessions?.length ?? 0) > 0 ||
		Boolean(pane.result) ||
		Boolean(pane.task);
	const historicByName = new Map<string, SubAgentPane>();
	for (const pane of historicPanes) {
		const existing = historicByName.get(pane.name);
		if (!existing || (!hasContent(existing) && hasContent(pane))) {
			historicByName.set(pane.name, pane);
		}
	}

	// Порядок панелей фиксируем по historicPanes (который на вызове уже включает
	// стабильный конфиг агентов) — иначе агент, у которого только что появилось
	// live SSE-событие, раньше выпрыгивал в начало списка (порядок появления
	// событий непредсказуем), и панели визуально "менялись местами" при каждом
	// заходе на страницу в зависимости от того, что успело прийти к моменту рендера.
	const orderedNames: string[] = [];
	const seenNames = new Set<string>();
	for (const pane of historicPanes) {
		if (!seenNames.has(pane.name)) {
			seenNames.add(pane.name);
			orderedNames.push(pane.name);
		}
	}
	for (const pane of mergedActive) {
		if (!seenNames.has(pane.name)) {
			seenNames.add(pane.name);
			orderedNames.push(pane.name);
		}
	}

	return orderedNames.map((name) => {
		const active = activeByName.get(name);
		const historic = historicByName.get(name);
		if (!active) return historic as SubAgentPane;
		if (!historic) return active;

		// Предпочитаем активную (live SSE) панель, но только если в ней реально
		// есть данные. Живая панель может прийти пустой (steps/sessions), если
		// sub_agent_step-события не успели накопиться в состоянии до момента
		// рендера — тогда историческая панель с сохранённой памятью агента
		// полнее и должна победить, даже если её статус не idle.
		const activeHasContent =
			active.steps.length > 0 ||
			(active.sessions?.length ?? 0) > 0 ||
			Boolean(active.result);
		if (active.status === "idle" && historic.status !== "idle") {
			return historic;
		}
		if (!activeHasContent) {
			const hasHistoricContent =
				historic.steps.length > 0 ||
				(historic.sessions?.length ?? 0) > 0 ||
				Boolean(historic.result);
			if (hasHistoricContent) {
				return { ...historic, status: active.status };
			}
		}
		// Раньше здесь было `return active;` — как только у живой панели
		// появлялся хоть один шаг, historic.sessions (все ранее сохранённые
		// на диске сессии этого саб-агента) отбрасывались целиком, и в чате
		// оставалась видна только самая последняя делегированная задача —
		// выглядело так, будто чат "пересоздаётся" при каждой новой задаче,
		// хотя на диске (см. ChatMemoryStore.append_session) ничего не терялось.
		// historic.sessions — авторитетный источник (свежепрочитан с диска),
		// active.sessions добавляем поверх только то, чего там ещё нет —
		// на случай параллельной делегации той же саб-агенту, ещё не
		// успевшей записаться на диск к моменту последнего loadHistory().
		const sessionKey = (s: SubAgentSession) =>
			`${s.task}|${s.model}|${s.steps.length}|${s.result ?? ""}`;
		const historicSessions = historic.sessions ?? [];
		const historicKeys = new Set(historicSessions.map(sessionKey));
		const extraActiveSessions = (active.sessions ?? []).filter(
			(s) => !historicKeys.has(sessionKey(s)),
		);
		return {
			...active,
			sessions: [...historicSessions, ...extraActiveSessions],
		};
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
							модель: {formatModelLabel(session.model)}
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
							{formatModelLabel(session.model)}
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

export function AgentChatPage({
	panes,
	onClearSubAgentPanes,
}: AgentChatPageProps) {
	const { paneId } = useParams<{ paneId: string }>();
	const navigate = useNavigate();
	const [historicPanes, setHistoricPanes] = useState<SubAgentPane[]>([]);
	const [historyLoaded, setHistoryLoaded] = useState(false);
	const [configuredPanes, setConfiguredPanes] = useState<SubAgentPane[]>([]);
	const [telegramStyle, setTelegramStyle] = useState<string | null>(null);
	const [telegramStyleDraft, setTelegramStyleDraft] = useState("");
	const [telegramStyleSaving, setTelegramStyleSaving] = useState(false);
	const [telegramStyleError, setTelegramStyleError] = useState<string | null>(
		null,
	);
	const [telegramStyleOpen, setTelegramStyleOpen] = useState(false);

	const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
		const saved = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
		return Number.isFinite(saved) &&
			saved >= SIDEBAR_MIN_WIDTH &&
			saved <= SIDEBAR_MAX_WIDTH
			? saved
			: SIDEBAR_DEFAULT_WIDTH;
	});
	const pageBodyRef = useRef<HTMLDivElement>(null);
	const resizingRef = useRef(false);
	const [resizing, setResizing] = useState(false);

	useEffect(() => {
		const onMouseMove = (e: MouseEvent) => {
			if (!resizingRef.current || !pageBodyRef.current) return;
			const rect = pageBodyRef.current.getBoundingClientRect();
			const raw = rect.right - e.clientX;
			setSidebarWidth(
				Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, raw)),
			);
		};
		const onMouseUp = () => {
			if (!resizingRef.current) return;
			resizingRef.current = false;
			setResizing(false);
			document.body.style.cursor = "";
			document.body.style.userSelect = "";
		};
		window.addEventListener("mousemove", onMouseMove);
		window.addEventListener("mouseup", onMouseUp);
		return () => {
			window.removeEventListener("mousemove", onMouseMove);
			window.removeEventListener("mouseup", onMouseUp);
		};
	}, []);

	// Персистим ширину только по завершении перетаскивания, а не на каждый
	// mousemove — иначе тысячи записей в localStorage за один drag.
	useEffect(() => {
		if (resizing) return;
		localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
	}, [resizing, sidebarWidth]);

	const startResize = useCallback((e: React.MouseEvent) => {
		e.preventDefault();
		resizingRef.current = true;
		setResizing(true);
		document.body.style.cursor = "col-resize";
		document.body.style.userSelect = "none";
	}, []);

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
					Array.isArray(agent.sessions) && agent.sessions.length > 0
						? sessionsToPane(
								agent.name,
								AGENT_DISPLAY_NAMES[agent.name] ?? agent.name,
								agent.sessions,
							)
						: historyToPane(
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
		} finally {
			setHistoryLoaded(true);
		}
	}, []);

	const loadTelegramStyle = useCallback(async () => {
		try {
			const res = await fetch("/api/telegram-style");
			const data = await readJson<{ style_guide?: string | null }>(res, {
				style_guide: null,
			});
			const guide = data.style_guide ?? null;
			setTelegramStyle(guide);
			setTelegramStyleDraft(guide ?? "");
		} catch {
			// ignore — просто останется незаполненным
		}
	}, []);

	const saveTelegramStyle = useCallback(async () => {
		setTelegramStyleSaving(true);
		setTelegramStyleError(null);
		try {
			const res = await fetch("/api/telegram-style", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ style_guide: telegramStyleDraft }),
			});
			const data = await readJson<{
				style_guide?: string | null;
				error?: string;
			}>(res, {});
			if (!res.ok) {
				setTelegramStyleError(data.error || "Не удалось сохранить");
				return;
			}
			const guide = data.style_guide ?? null;
			setTelegramStyle(guide);
			setTelegramStyleDraft(guide ?? "");
		} catch {
			setTelegramStyleError("Не удалось сохранить — проверь соединение");
		} finally {
			setTelegramStyleSaving(false);
		}
	}, [telegramStyleDraft]);

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
			void loadTelegramStyle();
		}, 0);
		return () => window.clearTimeout(timer);
	}, [loadConfiguredAgents, loadHistory, loadTelegramStyle]);

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
	// configuredPanes идёт первым источником порядка: он всегда в одном и том же
	// порядке (data/agents.json), тогда как historicPanes отсортирован backend'ом
	// по алфавиту имени файла памяти (file/system/telegram/web) — другой порядок,
	// чем в конфиге. Если поставить historicPanes первым, список визуально
	// "прыгает" сразу после того, как история догружается (см. buildPaneList).
	const allPanes = buildPaneList(panes, [
		...configuredPanes,
		...historicPanes,
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
		// До завершения первого /api/agents/history запроса allPanes состоит
		// только из пустышек configuredPanes (id "config:*") — если редиректить
		// по ним, глубокая ссылка/reload на конкретного агента (id "history:*")
		// не совпадёт с пустышкой и нас уводит на первого агента ДО того, как
		// реальная история успела загрузиться. historyLoaded ждёт первого
		// завершённого запроса, чтобы редирект срабатывал только на самом деле
		// несуществующий id, а не на ещё не подгруженный.
		if (!historyLoaded || !allPanes.length) return;
		if (!paneId || !allPanes.find((pane) => pane.id === paneId)) {
			navigate(`/agents/${allPanes[0].id}`, { replace: true });
		}
	}, [paneId, allPanes, navigate, historyLoaded]);

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
				<div className={styles.pageBody} ref={pageBodyRef}>
					<div className={styles.mainColumn}>
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
							<>
								<AgentChat pane={activePane} />
								<div className={styles.readonlyBar}>
									Только просмотр — писать агентам нельзя
								</div>
							</>
						)}
					</div>
					<div
						className={`${styles.resizeHandle} ${resizing ? styles.resizing : ""}`}
						onMouseDown={startResize}
					/>
					<PlanSidebar
						pane={activePane}
						width={sidebarWidth}
						telegramStyle={
							activePane.name === "telegram"
								? {
										draft: telegramStyleDraft,
										current: telegramStyle,
										saving: telegramStyleSaving,
										error: telegramStyleError,
										open: telegramStyleOpen,
										onToggleOpen: () =>
											setTelegramStyleOpen((v) => !v),
										onDraftChange: setTelegramStyleDraft,
										onSave: () => void saveTelegramStyle(),
									}
								: undefined
						}
					/>
				</div>
			</div>
		</div>
	);
}
