import { useState, useCallback } from "react";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { useAgent } from "./hooks/useAgent";
import { NavBar, type NavPage } from "./components/NavBar/NavBar";
import { ChatHeader } from "./components/ChatHeader/ChatHeader";
import { ChatThread } from "./components/ChatThread/ChatThread";
import { Composer } from "./components/Composer/Composer";
import { ConfirmationPrompt } from "./components/ConfirmationPrompt/ConfirmationPrompt";
import { ToolsPage } from "./pages/ToolsPage/ToolsPage";
import { AgentChatPage } from "./pages/AgentChatPage/AgentChatPage";
import { SettingsPage } from "./pages/SettingsPage/SettingsPage";
import "./index.css";

function pathToPage(pathname: string): NavPage {
	if (pathname === "/") return "chat";
	if (pathname.startsWith("/agents")) return "agents";
	if (pathname.startsWith("/tools")) return "tools";
	if (pathname.startsWith("/settings")) return "settings";
	return "chat";
}

const PAGE_TO_PATH: Record<NavPage, string> = {
	chat: "/",
	agents: "/agents",
	tools: "/tools",
	settings: "/settings",
};

function App() {
	const [task, setTask] = useState("");
	const [images, setImages] = useState<string[]>([]);
	const location = useLocation();
	const navigate = useNavigate();

	const {
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
		clearHistory,
		clearLogs,
		respondToConfirmation,
	} = useAgent();

	const activePage: NavPage = pathToPage(location.pathname);

	const handleNavigate = (page: NavPage) => navigate(PAGE_TO_PATH[page]);

	const [isDragging, setIsDragging] = useState(false);

	const readFilesAsBase64 = useCallback((files: File[]): Promise<string[]> => {
		const imageFiles = files.filter((f) => f.type.startsWith("image/"));
		return Promise.all(
			imageFiles.map(
				(file) =>
					new Promise<string>((resolve) => {
						const reader = new FileReader();
						reader.onload = () => resolve((reader.result as string).split(",")[1]);
						reader.readAsDataURL(file);
					}),
			),
		);
	}, []);

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
	const handleApprove = () => void respondToConfirmation(true).catch(console.error);
	const handleReject = () => void respondToConfirmation(false).catch(console.error);

	const hasActiveAgents = subAgentPanes.some((p) => p.status === "running");

	return (
		<div className="wrap">
			<div className="grid">
				<NavBar
					activePage={activePage}
					onNavigate={handleNavigate}
					hasActiveAgents={hasActiveAgents}
				/>

				<Routes>
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
												<rect x="3" y="3" width="18" height="18" rx="2" />
												<circle cx="8.5" cy="8.5" r="1.5" />
												<polyline points="21 15 16 10 5 21" />
											</svg>
											<span>Отпустите для загрузки</span>
										</div>
									</div>
								)}
								<ChatHeader
									onClearHistory={handleClearHistory}
									onClearLogs={handleClearLogs}
									isBusy={isRunning}
									contextTokens={contextTokens}
								/>
								<ChatThread
									events={events}
									currentAnswer={currentAnswer}
									liveThought={liveThought}
								/>
								{confirmationRequest && (
									<ConfirmationPrompt
										request={confirmationRequest}
										onApprove={handleApprove}
										onReject={handleReject}
									/>
								)}
								<Composer
									task={task}
									images={images}
									onTaskChange={setTask}
									onImagesChange={setImages}
									onRun={handleRun}
									onStop={cancelTask}
									isRunning={isRunning}
									liveStatus={liveStatus}
								/>
							</section>
						}
					/>
					<Route
						path="/agents"
						element={
							<section className="page-shell">
								<AgentChatPage panes={subAgentPanes} />
							</section>
						}
					/>
					<Route
						path="/agents/:paneId"
						element={
							<section className="page-shell">
								<AgentChatPage panes={subAgentPanes} />
							</section>
						}
					/>
					<Route
						path="/tools"
						element={
							<section className="page-shell">
								<ToolsPage tools={tools} />
							</section>
						}
					/>
					<Route
						path="/settings"
						element={
							<section className="page-shell">
								<SettingsPage />
							</section>
						}
					/>
					<Route path="*" element={<></>} />
				</Routes>
			</div>
		</div>
	);
}

export default App;
