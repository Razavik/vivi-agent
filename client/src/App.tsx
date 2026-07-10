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
import { RunsDashboardPage } from "./pages/RunsDashboardPage/RunsDashboardPage";
import { BusPage } from "./pages/BusPage/BusPage";
import { CrashesPage } from "./pages/CrashesPage/CrashesPage";
import { WatchPage } from "./pages/WatchPage/WatchPage";
import "./index.css";
import { fetchJson } from "./utils/http";

function pathToPage(pathname: string): NavPage {
	if (pathname === "/") return "chat";
	if (pathname.startsWith("/agents")) return "agents";
	if (pathname.startsWith("/tools")) return "tools";
	if (pathname.startsWith("/models")) return "models";
	if (pathname.startsWith("/skills")) return "skills";
	if (pathname.startsWith("/settings")) return "settings";
	if (pathname.startsWith("/runs")) return "runs";
	if (pathname.startsWith("/bus")) return "bus";
	if (pathname.startsWith("/crashes")) return "crashes";
	return "chat";
}

const PAGE_TO_PATH: Record<NavPage, string> = {
	chat: "/",
	agents: "/agents",
	tools: "/tools",
	models: "/models",
	skills: "/skills",
	settings: "/settings",
	runs: "/runs",
	bus: "/bus",
	crashes: "/crashes",
};

const SIDEBAR_MIN_WIDTH = 300;
const SIDEBAR_MAX_WIDTH = 900;
const SIDEBAR_DEFAULT_WIDTH = 320;

function App() {
	const supervisorAlerts = useSupervisorAlerts();
	const [task, setTask] = useState("");
	const [images, setImages] = useState<string[]>([]);
	const [developerMode, setDeveloperMode] = useState(
		() => localStorage.getItem("agent1.developerMode") === "true",
	);
	const [sidebarVisible, setSidebarVisible] = useState(true);
	const [pcControlMode, setPcControlMode] = useState(false);
	const [showMonitor, setShowMonitor] = useState(true);
	const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
	const [isSidebarResizing, setIsSidebarResizing] = useState(false);
	const sidebarResizeStartRef = useRef({
		x: 0,
		width: SIDEBAR_DEFAULT_WIDTH,
	});
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
		selectedModel,
		modelOptions,
		updateSelectedModel,
		subAgentPanes,
		runTask,
		cancelTask,
		clearHistory,
		clearLogs,
		clearSubAgentPanes,
		respondToConfirmation,
	} = useAgent();

	const activePage: NavPage = pathToPage(location.pathname);
	const isWatchPage = location.pathname.startsWith("/watch");

	const handleNavigate = (page: NavPage) => navigate(PAGE_TO_PATH[page]);
	const handleDeveloperModeChange = (enabled: boolean) => {
		if (document.activeElement instanceof HTMLElement) {
			document.activeElement.blur();
		}
		localStorage.setItem("agent1.developerMode", String(enabled));
		setDeveloperMode(enabled);
	};
	const handlePcControlModeChange = (enabled: boolean) => {
		setPcControlMode(enabled);
		void fetchJson("/api/app-settings", null, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ pc_control_mode: enabled }),
		});
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
		await runTask(currentTask, currentImages);
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
						developerMode={developerMode}
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
													selectedModel={
														selectedModel
													}
													modelOptions={modelOptions}
													onClearHistory={
														handleClearHistory
													}
													onClearLogs={
														handleClearLogs
													}
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
										developerMode={developerMode}
										pcControlMode={pcControlMode}
										showMonitor={showMonitor}
										onDeveloperModeChange={
											handleDeveloperModeChange
										}
										onPcControlModeChange={
											handlePcControlModeChange
										}
										onShowMonitorChange={
											handleShowMonitorChange
										}
									/>
								}
							/>
							<Route
								path="/runs"
								element={
									developerMode ? (
										<RunsDashboardPage />
									) : (
										<></>
									)
								}
							/>
							<Route
								path="/bus"
								element={developerMode ? <BusPage /> : <></>}
							/>
							<Route
								path="/crashes"
								element={
									developerMode ? <CrashesPage /> : <></>
								}
							/>
							<Route path="*" element={<></>} />
						</Routes>
					</main>
				</div>
			</div>
			{developerMode && (
				<SupervisorAlerts
					alerts={supervisorAlerts.alerts}
					onDismiss={supervisorAlerts.dismiss}
					onDismissAll={supervisorAlerts.dismissAll}
				/>
			)}
		</>
	);
}

export default App;
