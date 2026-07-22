import { useState, useCallback, useRef } from "react";
import { useEffect } from "react";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { PanelLeft } from "lucide-react";
import { useAgent } from "./hooks/useAgent";
import { useSupervisorAlerts } from "./hooks/useSupervisorAlerts";
import { NavBar, type NavPage } from "./components/NavBar/NavBar";
import { ChatThread } from "./components/ChatThread/ChatThread";
import { Composer } from "./components/Composer/Composer";
import { PlanGraph } from "./components/PlanGraph/PlanGraph";
import { ConfirmationPrompt } from "./components/ConfirmationPrompt/ConfirmationPrompt";
import { SupervisorAlerts } from "./components/SupervisorAlerts/SupervisorAlerts";
import { ToolsPage } from "./pages/ToolsPage/ToolsPage";
import { ModelsPage } from "./pages/ModelsPage/ModelsPage";
import { SkillsPage } from "./pages/SkillsPage/SkillsPage";
import { AgentChatPage } from "./pages/AgentChatPage/AgentChatPage";
import { SettingsPage } from "./pages/SettingsPage/SettingsPage";
import { WatchPage } from "./pages/WatchPage/WatchPage";
import "./index.css";
import { fetchJson } from "./utils/http";
import { prefetchAllPages } from "./prefetch";

function pathToPage(pathname: string): NavPage {
	if (pathname === "/") return "chat";
	if (pathname.startsWith("/agents")) return "agents";
	if (pathname.startsWith("/tools")) return "tools";
	if (pathname.startsWith("/models")) return "models";
	if (pathname.startsWith("/skills")) return "skills";
	if (pathname.startsWith("/settings")) return "settings";
	return "chat";
}

const PAGE_TO_PATH: Record<NavPage, string> = {
	chat: "/",
	agents: "/agents",
	tools: "/tools",
	models: "/models",
	skills: "/skills",
	settings: "/settings",
};

const SIDEBAR_MIN_WIDTH = 300;
const SIDEBAR_MAX_WIDTH = 900;
const SIDEBAR_DEFAULT_WIDTH = 320;

interface AgentConfigEntry {
	display_name?: string;
}

interface SubAgentOption {
	name: string;
	displayName: string;
}

function App() {
	const supervisorAlerts = useSupervisorAlerts();
	const [task, setTask] = useState("");
	const [images, setImages] = useState<string[]>([]);
	const [sidebarVisible, setSidebarVisible] = useState(true);
	const [pcControlMode, setPcControlMode] = useState(false);
	const [showMonitor, setShowMonitor] = useState(true);
	const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
	const [isSidebarResizing, setIsSidebarResizing] = useState(false);
	const sidebarResizeStartRef = useRef({
		x: 0,
		width: SIDEBAR_DEFAULT_WIDTH,
	});
	// Приоритетные саб-агенты — мягкая подсказка оператору, живёт на всю
	// сессию (пока пользователь сам не отожмёт кнопку), не персистится между
	// перезагрузками страницы намеренно: это разовое усиление на текущий разговор.
	const [preferredAgents, setPreferredAgents] = useState<string[]>([]);
	const [subAgentOptions, setSubAgentOptions] = useState<SubAgentOption[]>(
		[],
	);
	const location = useLocation();
	const navigate = useNavigate();
	useEffect(() => {
		void fetchJson<{ pc_control_mode?: boolean; show_monitor?: boolean }>(
			"/api/app-settings",
			{
				pc_control_mode: false,
				show_monitor: true,
			},
		).then((data) => {
			setPcControlMode(Boolean(data.pc_control_mode));
			setShowMonitor(data.show_monitor !== false);
		});
	}, []);
	useEffect(() => {
		void fetchJson<{ config?: Record<string, AgentConfigEntry> }>(
			"/api/agents-config",
			{ config: {} },
		).then((data) => {
			const config = data.config ?? {};
			const options = Object.entries(config)
				.filter(([name]) => name !== "operator")
				.map(([name, cfg]) => ({
					name,
					displayName: cfg.display_name || name,
				}));
			setSubAgentOptions(options);
		});
	}, []);
	// Прогреваем кэш React Query для всех остальных страниц сразу при старте,
	// параллельно с чатом — без этого при первом заходе на "Модели"/
	// "Настройки"/"Инструменты"/... был виден лоадер, хотя данные там почти
	// не меняются между сессиями (см. client/src/prefetch.ts).
	useEffect(() => {
		prefetchAllPages();
	}, []);
	// Общий персист pc_control_mode на сервер — используется и переключателем
	// режима ПК, и выбором приоритетного саб-агента (см. togglePreferredAgent):
	// оба места должны одинаково держать клиент и сервер в синхроне.
	const persistPcControlMode = useCallback((enabled: boolean) => {
		setPcControlMode(enabled);
		void fetchJson("/api/app-settings", null, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ pc_control_mode: enabled }),
		});
	}, []);
	const togglePreferredAgent = useCallback(
		(name: string) => {
			const isAdding = !preferredAgents.includes(name);
			setPreferredAgents((prev) =>
				prev.includes(name)
					? prev.filter((n) => n !== name)
					: [...prev, name],
			);
			// Симметрично handlePcControlModeChange: выбор приоритета имеет смысл
			// только когда доступно делегирование, поэтому включение приоритета
			// само выключает режим ПК (в нём delegate_task недоступен оператору).
			if (isAdding && pcControlMode) persistPcControlMode(false);
		},
		[preferredAgents, pcControlMode, persistPcControlMode],
	);

	const {
		events,
		tools,
		isRunning,
		liveStatus,
		currentAnswer,
		liveThought,
		confirmationRequest,
		contextTokens,
		contextLimit,
		modelSupportsVision,
		selectedModel,
		modelOptions,
		updateSelectedModel,
		subAgentPanes,
		runTask,
		cancelTask,
		clearHistory,
		clearLogs,
		compressMemory,
		clearSubAgentPanes,
		respondToConfirmation,
	} = useAgent();

	const activePage: NavPage = pathToPage(location.pathname);
	const isWatchPage = location.pathname.startsWith("/watch");

	const handleNavigate = (page: NavPage) => navigate(PAGE_TO_PATH[page]);
	const handlePcControlModeChange = (enabled: boolean) => {
		// В режиме управления ПК оператор теряет delegate_task/delegate_parallel
		// (см. _OPERATOR_ORCHESTRATION_TOOLS в app_factory.py) — делегировать
		// вообще некому, поэтому приоритет саб-агентов в этом режиме бессмыслен
		// и сбрасывается автоматически.
		if (enabled) setPreferredAgents([]);
		persistPcControlMode(enabled);
	};
	const handleShowMonitorChange = (enabled: boolean) => {
		setShowMonitor(enabled);
		void fetchJson("/api/app-settings", null, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ show_monitor: enabled }),
		});
	};

	const [isDragging, setIsDragging] = useState(false);

	const readFilesAsBase64 = useCallback(
		(files: File[]): Promise<string[]> => {
			const imageFiles = files.filter((f) => f.type.startsWith("image/"));
			return Promise.all(
				imageFiles.map(
					(file) =>
						new Promise<string>((resolve) => {
							const reader = new FileReader();
							reader.onload = () =>
								resolve(
									(reader.result as string).split(",")[1],
								);
							reader.readAsDataURL(file);
						}),
				),
			);
		},
		[],
	);

	const handleDragOver = (e: React.DragEvent) => {
		e.preventDefault();
		if (!isDragging) setIsDragging(true);
	};

	const handleDragLeave = (e: React.DragEvent) => {
		if (!e.currentTarget.contains(e.relatedTarget as Node)) {
			setIsDragging(false);
		}
	};

	const handleDrop = (e: React.DragEvent) => {
		e.preventDefault();
		setIsDragging(false);
		readFilesAsBase64(Array.from(e.dataTransfer.files)).then((b64s) => {
			if (b64s.length > 0) setImages((prev) => [...prev, ...b64s]);
		});
	};

	const handleRun = async () => {
		if (!task.trim() && images.length === 0) return;
		const currentTask = task;
		const currentImages = images;
		setTask("");
		setImages([]);
		await runTask(currentTask, currentImages, preferredAgents);
	};

	const handleClearHistory = () => void clearHistory().catch(console.error);
	const handleClearLogs = () => void clearLogs().catch(console.error);
	const handleApprove = () =>
		void respondToConfirmation(true).catch(console.error);
	const handleReject = () =>
		void respondToConfirmation(false).catch(console.error);

	const handleSidebarResizeStart = (
		event: React.MouseEvent<HTMLDivElement>,
	) => {
		event.preventDefault();
		sidebarResizeStartRef.current = {
			x: event.clientX,
			width: sidebarWidth,
		};

		const handleMouseMove = (moveEvent: MouseEvent) => {
			const delta = sidebarResizeStartRef.current.x - moveEvent.clientX;
			const nextWidth = Math.min(
				SIDEBAR_MAX_WIDTH,
				Math.max(
					SIDEBAR_MIN_WIDTH,
					sidebarResizeStartRef.current.width + delta,
				),
			);
			setSidebarWidth(nextWidth);
		};

		const handleMouseUp = () => {
			setIsSidebarResizing(false);
			document.body.classList.remove("sidebar-resizing");
			window.removeEventListener("mousemove", handleMouseMove);
			window.removeEventListener("mouseup", handleMouseUp);
		};

		setIsSidebarResizing(true);
		document.body.classList.add("sidebar-resizing");
		window.addEventListener("mousemove", handleMouseMove);
		window.addEventListener("mouseup", handleMouseUp);
	};

	const hasActiveAgents = subAgentPanes.some(
		(p) =>
			p.status === "running" ||
			p.status === "paused" ||
			p.status === "interrupted",
	);

	// Извлекаем последний план из событий
	const plan = events.findLast((e) => e.plan)?.plan ?? [];

	return (
		<>
			<div className="app-shell">
				{!isWatchPage && (
					<NavBar
						activePage={activePage}
						onNavigate={handleNavigate}
						hasActiveAgents={hasActiveAgents}
						alertCount={supervisorAlerts.alerts.length}
						pcControlMode={pcControlMode}
					/>
				)}

				<div className="app-frame">
					<main className="main-panel">
						<Routes>
							<Route path="/watch" element={<WatchPage />} />
							<Route
								path="/"
								element={
									<section
										className="chat-shell"
										onDragOver={handleDragOver}
										onDragLeave={handleDragLeave}
										onDrop={handleDrop}
									>
										{isDragging && (
											<div className="drag-overlay">
												<div className="drag-overlay-box">
													<svg
														width="40"
														height="40"
														viewBox="0 0 24 24"
														fill="none"
														stroke="currentColor"
														strokeWidth="1.5"
														strokeLinecap="round"
														strokeLinejoin="round"
													>
														<rect
															x="3"
															y="3"
															width="18"
															height="18"
															rx="2"
														/>
														<circle
															cx="8.5"
															cy="8.5"
															r="1.5"
														/>
														<polyline points="21 15 16 10 5 21" />
													</svg>
													<span>
														Отпустите для загрузки
													</span>
												</div>
											</div>
										)}
										<div className="chat-layout">
											<div className="chat-main">
												<ChatThread
													events={events}
													currentAnswer={
														currentAnswer
													}
													liveThought={liveThought}
												/>
												{confirmationRequest && (
													<ConfirmationPrompt
														request={
															confirmationRequest
														}
														onApprove={
															handleApprove
														}
														onReject={handleReject}
													/>
												)}
												<Composer
													task={task}
													images={images}
													contextTokens={
														contextTokens
													}
													contextLimit={contextLimit}
													modelSupportsVision={
														modelSupportsVision
													}
													selectedModel={
														selectedModel
													}
													modelOptions={modelOptions}
													onModelChange={
														updateSelectedModel
													}
													onTaskChange={setTask}
													onImagesChange={setImages}
													onRun={handleRun}
													onStop={cancelTask}
													isRunning={isRunning}
													liveStatus={liveStatus}
													pcControlMode={
														pcControlMode
													}
													onPcControlModeChange={
														handlePcControlModeChange
													}
													subAgentOptions={
														subAgentOptions
													}
													preferredAgents={
														preferredAgents
													}
													onTogglePreferredAgent={
															togglePreferredAgent
														}
														onClearHistory={handleClearHistory}
														onClearLogs={handleClearLogs}
														onCompressMemory={
															compressMemory
														}
														/>
											</div>
											{plan.length > 0 && (
												<>
													<div
														className={`chat-sidebar-placeholder ${!sidebarVisible ? "hidden" : ""} ${isSidebarResizing ? "resizing" : ""}`}
														style={{
															width: sidebarWidth,
														}}
													/>
													<div
														className={`chat-sidebar ${!sidebarVisible ? "hidden" : ""}`}
														style={{
															width: sidebarWidth,
														}}
													>
														<div
															className="chat-sidebar-resize-handle"
															onMouseDown={
																handleSidebarResizeStart
															}
														/>
														<PlanGraph
															plan={plan}
															title="План оркестратора"
															compact
														/>
													</div>
												</>
											)}
											{plan.length > 0 && (
												<button
													className={`sidebar-toggle-btn ${sidebarVisible ? "active" : ""}`}
													onClick={() =>
														setSidebarVisible(
															(value) => !value,
														)
													}
													title={
														sidebarVisible
															? "Скрыть план"
															: "Показать план"
													}
												>
													<PanelLeft size={16} />
												</button>
											)}
										</div>
									</section>
								}
							/>
							<Route
								path="/agents"
								element={
									pcControlMode ? (
										<></>
									) : (
										<AgentChatPage
											panes={subAgentPanes}
											onClearSubAgentPanes={clearSubAgentPanes}
										/>
									)
								}
							/>
							<Route
								path="/agents/:paneId"
								element={
									pcControlMode ? (
										<></>
									) : (
										<AgentChatPage
											panes={subAgentPanes}
											onClearSubAgentPanes={clearSubAgentPanes}
										/>
									)
								}
							/>
							<Route
								path="/tools"
								element={
									pcControlMode ? (
										<></>
									) : (
										<ToolsPage tools={tools} />
									)
								}
							/>
							<Route path="/models" element={<ModelsPage />} />
							<Route path="/skills" element={<SkillsPage />} />
							<Route
								path="/settings"
								element={
									<SettingsPage
										pcControlMode={pcControlMode}
										showMonitor={showMonitor}
										onPcControlModeChange={
											handlePcControlModeChange
										}
										onShowMonitorChange={
											handleShowMonitorChange
										}
									/>
								}
							/>
							<Route path="*" element={<></>} />
						</Routes>
					</main>
				</div>
			</div>
			<SupervisorAlerts
				alerts={supervisorAlerts.alerts}
				onDismiss={supervisorAlerts.dismiss}
				onDismissAll={supervisorAlerts.dismissAll}
			/>
		</>
	);
}

export default App;
