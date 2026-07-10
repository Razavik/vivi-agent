import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./ToolsPage.module.css";
import type { Tool } from "../../types";
import { Select } from "../../components/Select/Select";
import { fetchJson } from "../../utils/http";

interface ToolsPageProps {
	tools: Tool[];
}

const AGENT_COLORS: Record<string, string> = {
	operator: "#c084fc",
	file: "#7eb0ff",
	system: "#f6d365",
	web: "#f0abfc",
	telegram: "#5ba4cf",
};

const COLOR_PALETTE = [
	"#a78bfa",
	"#f87171",
	"#fb923c",
	"#ec4899",
	"#60a5fa",
	"#f472b6",
	"#facc15",
];

function getAgentColor(name: string, index: number): string {
	return AGENT_COLORS[name] ?? COLOR_PALETTE[index % COLOR_PALETTE.length];
}

interface AgentCfg {
	display_name?: string;
	prompt_path?: string;
	tools?: (string | ToolEntry)[];
}

function getRiskLabel(level: number): string {
	if (level === 0) return "read-only";
	if (level === 1) return "safe-write";
	if (level === 2) return "confirm";
	return "blocked";
}

function getRiskClass(level: number): string {
	if (level === 0) return "riskSafe";
	if (level === 1) return "riskMedium";
	if (level === 2) return "riskHigh";
	return "riskCritical";
}

type AgentsConfig = Record<string, AgentCfg>;
type ToolStatusFilter = "all" | "enabled" | "disabled";

interface ToolEntry {
	name: string;
	enabled: boolean;
	required?: boolean;
}

type ToolsPageQueryData = {
	agentsData?: { config?: AgentsConfig };
	modelsData?: {
		models?: Record<string, string>;
		default?: string;
		custom_models?: string[];
	};
	availData?: { models?: string[] };
	ollamaData?: { models?: string[] };
	appSettings?: { pc_control_mode?: boolean };
};

const ORCHESTRATOR_TOOL_NAMES = new Set([
	"delegate_task",
	"delegate_parallel",
	"get_agent_memory",
	"view_runs",
	"cancel_run",
	"pause_run",
	"resume_run",
	"message_run",
	"replace_task_run",
	"reprioritize_run",
	"get_world_state",
	"wait_for_event",
]);

const RUN_TOOL_NAMES = new Set([
	"view_runs",
	"cancel_run",
	"pause_run",
	"resume_run",
	"message_run",
	"replace_task_run",
	"reprioritize_run",
	"get_world_state",
	"wait_for_event",
]);

const PC_TOOL_NAMES = new Set([
	"get_screen_info",
	"take_screenshot",
	"read_image",
	"system_mouse_move",
	"system_mouse_nudge",
	"system_mouse_click",
	"system_mouse_double_click",
	"system_mouse_scroll",
	"system_mouse_drag",
	"system_type_text",
	"system_key_press",
	"list_ui_elements",
	"click_ui_element",
	"focus_ui_element",
]);

export function ToolsPage({ tools }: ToolsPageProps) {
	const queryClient = useQueryClient();
	const [search, setSearch] = useState("");
	const [selectedAgent, setSelectedAgent] = useState<string>("operator");
	const [showAddAgent, setShowAddAgent] = useState(false);
	const [newAgentName, setNewAgentName] = useState("");
	const [newAgentDisplay, setNewAgentDisplay] = useState("");
	const [newAgentPrompt, setNewAgentPrompt] = useState("");
	const [statusFilter, setStatusFilter] = useState<ToolStatusFilter>("all");

	const { data, isLoading } = useQuery({
		queryKey: ["tools-page"],
		queryFn: async () => {
			const [agentsData, modelsData, availData, ollamaData, appSettings] =
				await Promise.all([
					fetchJson<{ config?: AgentsConfig }>("/api/agents-config", {
						config: {},
					}),
					fetchJson<{
						models?: Record<string, string>;
						default?: string;
						custom_models?: string[];
					}>("/api/models", {
						models: {},
						default: "",
						custom_models: [],
					}),
					fetchJson<{ models?: string[] }>("/api/available-models", {
						models: [],
					}),
					fetchJson<{ models?: string[] }>("/api/ollama-models", {
						models: [],
					}),
					fetchJson<{ pc_control_mode?: boolean }>(
						"/api/app-settings",
						{ pc_control_mode: false },
					),
				]);
			return {
				agentsData,
				modelsData,
				availData,
				ollamaData,
				appSettings,
			};
		},
	});

	const agentsConfig = useMemo(
		() => data?.agentsData.config ?? {},
		[data?.agentsData.config],
	);
	const models = useMemo(
		() => data?.modelsData.models ?? {},
		[data?.modelsData.models],
	);
	const defaultModel = data?.modelsData.default ?? "";
	const customModels = useMemo(
		() => data?.modelsData.custom_models ?? [],
		[data?.modelsData.custom_models],
	);
	const pcControlMode = Boolean(data?.appSettings.pc_control_mode);
	const availableModels = useMemo(
		() => data?.availData.models ?? [],
		[data?.availData.models],
	);
	const downloadedModels = useMemo(
		() => data?.ollamaData.models ?? [],
		[data?.ollamaData.models],
	);

	const saveAgentsConfig = useMutation({
		mutationFn: (config: AgentsConfig) =>
			fetchJson<unknown>("/api/agents-config", null, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ config }),
			}),
		onMutate: async (config) => {
			await queryClient.cancelQueries({ queryKey: ["tools-page"] });
			const previous = queryClient.getQueryData<ToolsPageQueryData>([
				"tools-page",
			]);
			queryClient.setQueryData<ToolsPageQueryData>(
				["tools-page"],
				(current) => {
					if (!current) return current;
					return {
						...current,
						agentsData: {
							...(current.agentsData ?? {}),
							config,
						},
					};
				},
			);
			return { previous };
		},
		onError: (_error, _config, context) => {
			if (context?.previous) {
				queryClient.setQueryData(["tools-page"], context.previous);
			}
		},
		onSettled: () => {
			void queryClient.invalidateQueries({ queryKey: ["tools-page"] });
		},
	});

	const saveModels = useMutation({
		mutationFn: (updated: Record<string, string>) =>
			fetchJson<unknown>("/api/models", null, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					models: updated,
					custom_models: data?.modelsData.custom_models ?? [],
				}),
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["tools-page"] });
		},
	});

	const availableAgents = useMemo(() => {
		const fromConfig = Object.keys(agentsConfig);
		const fromTools = tools.map((t) => t.agent).filter(Boolean) as string[];
		return [...new Set([...fromConfig, ...fromTools])];
	}, [agentsConfig, tools]);

	const getLabel = (key: string) => agentsConfig[key]?.display_name || key;
	const getColor = (key: string) =>
		getAgentColor(key, availableAgents.indexOf(key));
	const downloadedSet = useMemo(
		() => new Set(downloadedModels),
		[downloadedModels],
	);
	const getToolEntry = (
		agent: string,
		toolName: string,
	): ToolEntry | string | undefined => {
		const toolsList = agentsConfig[agent]?.tools || [];
		return toolsList.find((t) =>
			typeof t === "string"
				? t === toolName
				: (t as ToolEntry).name === toolName,
		);
	};
	const getToolEnabled = (agent: string, toolName: string): boolean => {
		const entry = getToolEntry(agent, toolName);
		if (entry === undefined || typeof entry === "string") return true;
		return Boolean(entry.required) || entry.enabled !== false;
	};
	const hiddenToolNames =
		selectedAgent === "operator"
			? pcControlMode
				? ORCHESTRATOR_TOOL_NAMES
				: PC_TOOL_NAMES
			: null;

	const modelOptions = useMemo(
		() => [
			{ value: "", label: `по умолчанию (${defaultModel})` },
			...Array.from(
				new Set(
					[
						...downloadedModels,
						...availableModels,
						...customModels,
						...Object.values(models).filter(Boolean),
						defaultModel,
					].filter(Boolean),
				),
			).map((m) => ({
				value: m,
				label: downloadedSet.has(m) ? `${m} · скачана` : m,
				dot: downloadedSet.has(m) ? "#22c55e" : undefined,
			})),
		],
		[
			availableModels,
			customModels,
			defaultModel,
			downloadedModels,
			downloadedSet,
			models,
		],
	);

	const allAgentTools = useMemo(() => {
		const byName = new Map<string, Tool>();
		for (const tool of tools) {
			if (tool.agent === selectedAgent) {
				if (
					selectedAgent === "operator" &&
					RUN_TOOL_NAMES.has(tool.name)
				)
					continue;
				if (
					selectedAgent === "operator" &&
					hiddenToolNames?.has(tool.name)
				)
					continue;
				byName.set(tool.name, tool);
			}
		}
		const configuredTools = agentsConfig[selectedAgent]?.tools || [];
		for (const entry of configuredTools) {
			const name = typeof entry === "string" ? entry : entry.name;
			if (selectedAgent === "operator" && RUN_TOOL_NAMES.has(name))
				continue;
			if (
				!name ||
				(selectedAgent === "operator" && hiddenToolNames?.has(name))
			)
				continue;
			if (!name || byName.has(name)) continue;
			byName.set(name, {
				name,
				description:
					"Инструмент отключён и не передаётся оркестратору.",
				agent: selectedAgent,
			});
		}
		return Array.from(byName.values()).sort((a, b) => {
			const aIndex = configuredTools.findIndex((entry) =>
				typeof entry === "string"
					? entry === a.name
					: entry.name === a.name,
			);
			const bIndex = configuredTools.findIndex((entry) =>
				typeof entry === "string"
					? entry === b.name
					: entry.name === b.name,
			);
			if (aIndex === -1 && bIndex === -1)
				return a.name.localeCompare(b.name);
			if (aIndex === -1) return 1;
			if (bIndex === -1) return -1;
			return aIndex - bIndex;
		});
	}, [agentsConfig, hiddenToolNames, selectedAgent, tools]);

	const toolStats = useMemo(() => {
		let enabled = 0;
		let disabled = 0;
		for (const tool of allAgentTools) {
			if (getToolEnabled(selectedAgent, tool.name)) {
				enabled += 1;
			} else {
				disabled += 1;
			}
		}
		return { enabled, disabled, total: allAgentTools.length };
	}, [allAgentTools, selectedAgent]);

	const agentTools = useMemo(() => {
		const q = search.toLowerCase();
		return allAgentTools.filter((t) => {
			const enabled = getToolEnabled(selectedAgent, t.name);
			if (statusFilter === "enabled" && !enabled) return false;
			if (statusFilter === "disabled" && enabled) return false;
			if (
				q &&
				!t.name.toLowerCase().includes(q) &&
				!t.description.toLowerCase().includes(q)
			) {
				return false;
			}
			return true;
		});
	}, [allAgentTools, selectedAgent, search, statusFilter]);

	const saveConfig = (config: AgentsConfig) => {
		saveAgentsConfig.mutate(config);
	};

	const setAgentModel = (agent: string, model: string) => {
		const updated = { ...models, [agent]: model };
		saveModels.mutate(updated);
	};

	const addAgent = async () => {
		const key = newAgentName.trim().toLowerCase().replace(/\s+/g, "_");
		if (!key) return;
		const updated: AgentsConfig = {
			...agentsConfig,
			[key]: {
				display_name: newAgentDisplay.trim() || key,
				prompt_path:
					newAgentPrompt.trim() || `prompts/agents/${key}.txt`,
				tools: [],
			},
		};
		saveConfig(updated);
		setSelectedAgent(key);
		setShowAddAgent(false);
		setNewAgentName("");
		setNewAgentDisplay("");
		setNewAgentPrompt("");
	};

	const toggleTool = (agent: string, toolName: string) => {
		const cfg = agentsConfig[agent] || {};
		const entries: ToolEntry[] = (cfg.tools || []).map((t) =>
			typeof t === "string"
				? { name: t, enabled: true }
				: (t as ToolEntry),
		);
		const updated = entries.map((t) =>
			t.name === toolName ? { ...t, enabled: !t.enabled } : t,
		);
		saveConfig({ ...agentsConfig, [agent]: { ...cfg, tools: updated } });
	};

	const enableAll = () => {
		const cfg = agentsConfig[selectedAgent] || {};
		const entries: ToolEntry[] = (cfg.tools || []).map((t) =>
			typeof t === "string"
				? { name: t, enabled: true }
				: { ...(t as ToolEntry), enabled: true },
		);
		saveConfig({
			...agentsConfig,
			[selectedAgent]: { ...cfg, tools: entries },
		});
	};

	const disableAll = () => {
		const cfg = agentsConfig[selectedAgent] || {};
		const entries: ToolEntry[] = (cfg.tools || []).map((t) =>
			typeof t === "string"
				? { name: t, enabled: false }
				: { ...(t as ToolEntry), enabled: false },
		);
		saveConfig({
			...agentsConfig,
			[selectedAgent]: { ...cfg, tools: entries },
		});
	};

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<h1 className={styles.title}>Редактор инструментов</h1>
				<p className={styles.subtitle}>
					Выберите агента и управляйте доступными ему инструментами
				</p>
				<div className={styles.controls}>
					<div className={styles.selectWrapper}>
						<label className={styles.label}>Агент:</label>
						<Select
							value={selectedAgent}
							onChange={setSelectedAgent}
							options={availableAgents.map((key) => ({
								value: key,
								label: getLabel(key),
								dot: getColor(key),
							}))}
						/>
					</div>
					<button
						className={styles.addAgentBtn}
						onClick={() => setShowAddAgent(true)}
						title="Добавить нового агента"
					>
						+ Новый агент
					</button>
					<input
						className={styles.searchInput}
						type="text"
						placeholder="Поиск по названию..."
						value={search}
						onChange={(e) => setSearch(e.target.value)}
					/>
					<div
						className={styles.statusFilters}
						aria-label="Фильтр инструментов"
					>
						<button
							className={`${styles.statusFilter} ${statusFilter === "all" ? styles.statusFilterActive : ""}`}
							onClick={() => setStatusFilter("all")}
						>
							Все <span>{toolStats.total}</span>
						</button>
						<button
							className={`${styles.statusFilter} ${statusFilter === "enabled" ? styles.statusFilterActive : ""}`}
							onClick={() => setStatusFilter("enabled")}
						>
							Включённые <span>{toolStats.enabled}</span>
						</button>
						<button
							className={`${styles.statusFilter} ${statusFilter === "disabled" ? styles.statusFilterActive : ""}`}
							onClick={() => setStatusFilter("disabled")}
						>
							Отключённые <span>{toolStats.disabled}</span>
						</button>
					</div>
					<div className={styles.actions}>
						<button
							className={styles.actionBtn}
							onClick={enableAll}
						>
							Включить все
						</button>
						<button
							className={styles.actionBtn}
							onClick={disableAll}
						>
							Отключить все
						</button>
					</div>
				</div>
			</div>

			<div className={styles.agentInfo}>
				<span
					className={styles.agentDot}
					style={{ background: getColor(selectedAgent) }}
				/>
				<span className={styles.agentTitle}>
					{getLabel(selectedAgent)}
				</span>
				<span className={styles.agentCount}>
					{agentTools.length} из {toolStats.total} инструментов
				</span>
				<div className={styles.modelSelect}>
					<label className={styles.label}>Модель:</label>
					<Select
						value={models[selectedAgent] || ""}
						onChange={(v) => setAgentModel(selectedAgent, v)}
						placeholder={defaultModel || "по умолчанию"}
						options={modelOptions}
					/>
				</div>
			</div>

			<div className={styles.body}>
				{isLoading ? null : agentTools.length === 0 ? (
					<div className={styles.empty}>
						Нет инструментов для этого агента
					</div>
				) : (
					<div className={styles.grid}>
						{agentTools.map((tool) => {
							const entry = getToolEntry(
								selectedAgent,
								tool.name,
							);
							const typedEntry =
								typeof entry === "object" && entry !== null
									? (entry as ToolEntry)
									: null;
							const isRequired = typedEntry?.required ?? false;
							const isEnabled =
								isRequired ||
								(entry === undefined
									? true
									: typeof entry === "string"
										? true
										: (entry as ToolEntry).enabled);
							return (
								<div
									key={tool.name}
									className={`${styles.toolCard} ${!isEnabled ? styles.toolDisabled : ""} ${isRequired ? styles.toolRequired : ""} ${!isRequired ? styles.toolClickable : ""}`}
									onClick={
										isRequired
											? undefined
											: () =>
													toggleTool(
														selectedAgent,
														tool.name,
													)
									}
								>
									<div className={styles.cardHead}>
										{isRequired ? (
											<span
												className={styles.lockIcon}
												title="Обязательный инструмент"
											>
												<svg
													width="14"
													height="14"
													viewBox="0 0 14 14"
													fill="none"
												>
													<rect
														x="2"
														y="6"
														width="10"
														height="7"
														rx="1.5"
														stroke="currentColor"
														strokeWidth="1.4"
													/>
													<path
														d="M4.5 6V4.5a2.5 2.5 0 0 1 5 0V6"
														stroke="currentColor"
														strokeWidth="1.4"
														strokeLinecap="round"
													/>
												</svg>
											</span>
										) : (
											<label
												className={styles.toggle}
												onClick={(e) =>
													e.stopPropagation()
												}
											>
												<input
													type="checkbox"
													checked={isEnabled}
													onChange={() =>
														toggleTool(
															selectedAgent,
															tool.name,
														)
													}
												/>
												<span
													className={
														styles.toggleSlider
													}
												/>
											</label>
										)}
										<span className={styles.toolName}>
											{tool.name}
										</span>
										{tool.risk_level !== undefined && (
											<span
												className={`${styles.riskBadge} ${styles[getRiskClass(tool.risk_level)]}`}
											>
												{getRiskLabel(tool.risk_level)}
											</span>
										)}
									</div>
									<div className={styles.toolDesc}>
										{tool.description}
									</div>
									{tool.args_schema &&
										Object.keys(tool.args_schema).length >
											0 && (
											<div className={styles.toolArgs}>
												{Object.entries(
													tool.args_schema,
												).map(([name, type]) => {
													const isOpt =
														String(type).includes(
															"?",
														);
													return (
														<span
															key={name}
															className={`${styles.toolArg} ${isOpt ? styles.toolArgOpt : ""}`}
														>
															{name}
															{isOpt
																? "?"
																: ""}:{" "}
															{String(
																type,
															).replace("?", "")}
														</span>
													);
												})}
											</div>
										)}
								</div>
							);
						})}
					</div>
				)}
			</div>

			{showAddAgent && (
				<div
					className={styles.modalOverlay}
					onClick={() => setShowAddAgent(false)}
				>
					<div
						className={styles.modal}
						onClick={(e) => e.stopPropagation()}
					>
						<h2 className={styles.modalTitle}>Новый агент</h2>
						<div className={styles.modalField}>
							<label className={styles.label}>
								Идентификатор (key)
							</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="my_agent"
								value={newAgentName}
								onChange={(e) =>
									setNewAgentName(e.target.value)
								}
							/>
						</div>
						<div className={styles.modalField}>
							<label className={styles.label}>
								Отображаемое имя
							</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="Мой агент"
								value={newAgentDisplay}
								onChange={(e) =>
									setNewAgentDisplay(e.target.value)
								}
							/>
						</div>
						<div className={styles.modalField}>
							<label className={styles.label}>
								Путь к промпту
							</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="prompts/agents/my_agent.txt"
								value={newAgentPrompt}
								onChange={(e) =>
									setNewAgentPrompt(e.target.value)
								}
							/>
						</div>
						<div className={styles.modalActions}>
							<button
								className={styles.actionBtn}
								onClick={() => setShowAddAgent(false)}
							>
								Отмена
							</button>
							<button
								className={styles.saveBtn}
								onClick={addAgent}
								disabled={!newAgentName.trim()}
							>
								Создать
							</button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
