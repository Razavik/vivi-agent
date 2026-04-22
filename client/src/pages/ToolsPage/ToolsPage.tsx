import styles from "./ToolsPage.module.css";
import type { Tool } from "../../types";

interface ToolsPageProps {
	tools: Tool[];
}

const AGENT_META: Record<string, { label: string; color: string }> = {
	director: { label: "Директор", color: "#10a37f" },
	file: { label: "Файловый агент", color: "#7eb0ff" },
	system: { label: "Системный агент", color: "#f6d365" },
	web: { label: "Веб-агент", color: "#6ee7c7" },
	telegram: { label: "Telegram-агент", color: "#5ba4cf" },
};

const AGENT_ORDER = ["director", "file", "system", "web", "telegram"];

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

export function ToolsPage({ tools }: ToolsPageProps) {
	const grouped = new Map<string, Tool[]>();
	for (const tool of tools) {
		const key = tool.agent ?? "other";
		if (!grouped.has(key)) grouped.set(key, []);
		grouped.get(key)!.push(tool);
	}

	const sectionKeys = [
		...AGENT_ORDER.filter((k) => grouped.has(k)),
		...[...grouped.keys()].filter((k) => !AGENT_ORDER.includes(k)),
	];

	const sections = sectionKeys.map((key) => ({
		key,
		label: AGENT_META[key]?.label ?? key,
		color: AGENT_META[key]?.color ?? "#888",
		tools: grouped.get(key) ?? [],
	}));

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<h1 className={styles.title}>Инструменты</h1>
				<p className={styles.subtitle}>
					{tools.length} инструментов в {sections.length} группах
				</p>
			</div>
			<div className={styles.body}>
				{sections.map((section) => (
					<div className={styles.agentSection} key={section.key}>
						<div className={styles.agentHeader}>
							<span
								className={styles.agentDot}
								style={{ background: section.color }}
							/>
							<span className={styles.agentTitle}>{section.label}</span>
							<span className={styles.agentCount}>{section.tools.length}</span>
						</div>
						<div className={styles.grid}>
							{section.tools.map((tool) => (
								<div className={styles.toolCard} key={tool.name}>
									<div className={styles.cardHead}>
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
							))}
						</div>
					</div>
				))}
			</div>
		</div>
	);
}
