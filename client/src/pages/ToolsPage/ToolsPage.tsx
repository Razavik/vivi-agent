import { useState, useMemo, useEffect } from "react";
import styles from "./ToolsPage.module.css";
import type { Tool } from "../../types";
import { Select } from "../../components/Select/Select";

interface ToolsPageProps {
	tools: Tool[];
}

const AGENT_COLORS: Record<string, string> = {
	director: "#10a37f",
	file: "#7eb0ff",
	system: "#f6d365",
	web: "#6ee7c7",
	telegram: "#5ba4cf",
};

const COLOR_PALETTE = ["#a78bfa", "#f87171", "#fb923c", "#34d399", "#60a5fa", "#f472b6", "#facc15"];

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

// Тип для конфигурации агентов из agents.json
type AgentsConfig = Record<string, AgentCfg>;

interface ToolEntry {
	name: string;
	enabled: boolean;
	required?: boolean;
}

export function ToolsPage({ tools }: ToolsPageProps) {
	const [search, setSearch] = useState("");
	const [selectedAgent, setSelectedAgent] = useState<string>("director");
	const [agentsConfig, setAgentsConfig] = useState<AgentsConfig>({});
	const [loaded, setLoaded] = useState(false);
	const [models, setModels] = useState<Record<string, string>>({});
	const [defaultModel, setDefaultModel] = useState("");
	const [ollamaModels, setOllamaModels] = useState<string[]>([]);
	const [showAddAgent, setShowAddAgent] = useState(false);
	const [newAgentName, setNewAgentName] = useState("");
	const [newAgentDisplay, setNewAgentDisplay] = useState("");
	const [newAgentPrompt, setNewAgentPrompt] = useState("");

	// Загрузка конфигурации агентов, моделей и списка Ollama
	useEffect(() => {
		const load = async () => {
			try {
				const [agentsRes, modelsRes, ollamaRes] = await Promise.all([
					fetch("/api/agents-config"),
					fetch("/api/models"),
					fetch("/api/available-models"),
				]);
				const agentsData = await agentsRes.json();
				const modelsData = await modelsRes.json();
				const ollamaData = await ollamaRes.json();
				if (agentsData.config) {
					setAgentsConfig(agentsData.config);
					const first = Object.keys(agentsData.config)[0];
					if (first) setSelectedAgent(first);
				}
				if (modelsData.models) setModels(modelsData.models);
				if (modelsData.default) setDefaultModel(modelsData.default);
				if (ollamaData.models) setOllamaModels(ollamaData.models);
			} catch (e) {
				console.error("Ошибка загрузки:", e);
			} finally {
				setLoaded(true);
			}
		};
		load();
	}, []);

	// Отправка конфига на сервер (тихая, без состояния)
	const saveToServer = (config: AgentsConfig) => {
		fetch("/api/agents-config", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ config }),
		}).catch((e) => console.error("Ошибка сохранения:", e));
	};

	// Сменить модель агента
	const setAgentModel = (agent: string, model: string) => {
		const updated = { ...models, [agent]: model };
		setModels(updated);
		fetch("/api/models", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ models: updated }),
		}).catch((e) => console.error("Ошибка сохранения модели:", e));
	};

	// Добавить нового агента в agents.json
	const addAgent = async () => {
		const key = newAgentName.trim().toLowerCase().replace(/\s+/g, "_");
		if (!key) return;
		const updated: AgentsConfig = {
			...agentsConfig,
			[key]: {
				display_name: newAgentDisplay.trim() || key,
				prompt_path: newAgentPrompt.trim() || `prompts/agents/${key}.txt`,
				tools: [],
			},
		};
		try {
			await fetch("/api/agents-config", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ config: updated }),
			});
			setAgentsConfig(updated);
			setSelectedAgent(key);
			setShowAddAgent(false);
			setNewAgentName("");
			setNewAgentDisplay("");
			setNewAgentPrompt("");
		} catch (e) {
			console.error("Ошибка добавления агента:", e);
		}
	};

	// Переключение инструмента — меняем enabled и сразу сохраняем
	const toggleTool = (agent: string, toolName: string) => {
		setAgentsConfig((prev) => {
			const cfg = prev[agent] || {};
			const tools: ToolEntry[] = (cfg.tools || []).map((t) =>
				typeof t === "string" ? { name: t, enabled: true } : (t as ToolEntry),
			);
			const updated = tools.map((t) =>
				t.name === toolName ? { ...t, enabled: !t.enabled } : t,
			);
			const next = { ...prev, [agent]: { ...cfg, tools: updated } };
			saveToServer(next);
			return next;
		});
	};

	// Список агентов из agentsConfig + из tools
	const availableAgents = useMemo(() => {
		const fromConfig = Object.keys(agentsConfig);
		const fromTools = tools.map((t) => t.agent).filter(Boolean) as string[];
		const merged = [...new Set([...fromConfig, ...fromTools])];
		return merged;
	}, [agentsConfig, tools]);

	// Отображаемое имя агента
	const getLabel = (key: string) => agentsConfig[key]?.display_name || key;
	const getColor = (key: string) => getAgentColor(key, availableAgents.indexOf(key));

	// Фильтрация инструментов для выбранного агента
	const agentTools = useMemo(() => {
		const q = search.toLowerCase();
		return tools.filter((t) => {
			if (t.agent !== selectedAgent) return false;
			if (q && !t.name.toLowerCase().includes(q) && !t.description.toLowerCase().includes(q))
				return false;
			return true;
		});
	}, [tools, selectedAgent, search]);

	// Включить все инструменты
	const enableAll = () => {
		setAgentsConfig((prev) => {
			const cfg = prev[selectedAgent] || {};
			const tools: ToolEntry[] = (cfg.tools || []).map((t) =>
				typeof t === "string"
					? { name: t, enabled: true }
					: { ...(t as ToolEntry), enabled: true },
			);
			const next = { ...prev, [selectedAgent]: { ...cfg, tools } };
			saveToServer(next);
			return next;
		});
	};

	// Отключить все инструменты
	const disableAll = () => {
		setAgentsConfig((prev) => {
			const cfg = prev[selectedAgent] || {};
			const tools: ToolEntry[] = (cfg.tools || []).map((t) =>
				typeof t === "string"
					? { name: t, enabled: false }
					: { ...(t as ToolEntry), enabled: false },
			);
			const next = { ...prev, [selectedAgent]: { ...cfg, tools } };
			saveToServer(next);
			return next;
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
					<div className={styles.actions}>
						<button className={styles.actionBtn} onClick={enableAll}>
							Включить все
						</button>
						<button className={styles.actionBtn} onClick={disableAll}>
							Отключить все
						</button>
					</div>
				</div>
			</div>

			<div className={styles.agentInfo}>
				<span className={styles.agentDot} style={{ background: getColor(selectedAgent) }} />
				<span className={styles.agentTitle}>{getLabel(selectedAgent)}</span>
				<span className={styles.agentCount}>{agentTools.length} инструментов</span>
				<div className={styles.modelSelect}>
					<label className={styles.label}>Модель:</label>
					<Select
						value={models[selectedAgent] || ""}
						onChange={(v) => setAgentModel(selectedAgent, v)}
						placeholder={defaultModel || "по умолчанию"}
						options={[
							{ value: "", label: `по умолчанию (${defaultModel})` },
							...ollamaModels.map((m) => ({ value: m, label: m })),
						]}
					/>
				</div>
			</div>

			<div className={styles.body}>
				{!loaded ? null : agentTools.length === 0 ? (
					<div className={styles.empty}>Нет инструментов для этого агента</div>
				) : (
					<div className={styles.grid}>
						{agentTools.map((tool) => {
							const toolsList = agentsConfig[selectedAgent]?.tools || [];
							const entry = toolsList.find((t) =>
								typeof t === "string"
									? t === tool.name
									: (t as ToolEntry).name === tool.name,
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
											: () => toggleTool(selectedAgent, tool.name)
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
												onClick={(e) => e.stopPropagation()}
											>
												<input
													type="checkbox"
													checked={isEnabled}
													onChange={() =>
														toggleTool(selectedAgent, tool.name)
													}
												/>
												<span className={styles.toggleSlider} />
											</label>
										)}
										<span className={styles.toolName}>{tool.name}</span>
										{tool.risk_level !== undefined && (
											<span
												className={`${styles.riskBadge} ${styles[getRiskClass(tool.risk_level)]}`}
											>
												{getRiskLabel(tool.risk_level)}
											</span>
										)}
									</div>
									<div className={styles.toolDesc}>{tool.description}</div>
									{tool.args_schema &&
										Object.keys(tool.args_schema).length > 0 && (
											<div className={styles.toolArgs}>
												{Object.entries(tool.args_schema).map(
													([name, type]) => {
														const isOpt = String(type).includes("?");
														return (
															<span
																key={name}
																className={`${styles.toolArg} ${isOpt ? styles.toolArgOpt : ""}`}
															>
																{name}
																{isOpt ? "?" : ""}:{" "}
																{String(type).replace("?", "")}
															</span>
														);
													},
												)}
											</div>
										)}
								</div>
							);
						})}
					</div>
				)}
			</div>

			{/* Модальное окно добавления агента */}
			{showAddAgent && (
				<div className={styles.modalOverlay} onClick={() => setShowAddAgent(false)}>
					<div className={styles.modal} onClick={(e) => e.stopPropagation()}>
						<h2 className={styles.modalTitle}>Новый агент</h2>
						<div className={styles.modalField}>
							<label className={styles.label}>Идентификатор (key)</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="my_agent"
								value={newAgentName}
								onChange={(e) => setNewAgentName(e.target.value)}
							/>
						</div>
						<div className={styles.modalField}>
							<label className={styles.label}>Отображаемое имя</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="Мой агент"
								value={newAgentDisplay}
								onChange={(e) => setNewAgentDisplay(e.target.value)}
							/>
						</div>
						<div className={styles.modalField}>
							<label className={styles.label}>Путь к промпту</label>
							<input
								className={styles.modalInput}
								type="text"
								placeholder="prompts/agents/my_agent.txt"
								value={newAgentPrompt}
								onChange={(e) => setNewAgentPrompt(e.target.value)}
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
