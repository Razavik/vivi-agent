import styles from "./ToolsDrawer.module.css";
import type { Tool } from "../../types";

interface ToolsDrawerProps {
	tools: Tool[];
	isOpen: boolean;
	onClose: () => void;
}

function getToolGroup(toolName: string): string {
	if (
		toolName.includes("file") ||
		toolName === "list_directory" ||
		toolName === "create_directory"
	)
		return "Файлы";
	if (toolName.includes("app") || toolName.includes("process"))
		return "Процессы и приложения";
	if (toolName.includes("powershell") || toolName.includes("system"))
		return "Система";
	if (toolName.includes("confirmation") || toolName.includes("finish"))
		return "Диалог";
	return "Прочее";
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

export function ToolsDrawer({ tools, isOpen, onClose }: ToolsDrawerProps) {
	if (!isOpen) return null;

	// Группируем инструменты по категориям
	const grouped = new Map<string, Tool[]>();
	for (const tool of tools) {
		const group = getToolGroup(tool.name);
		if (!grouped.has(group)) {
			grouped.set(group, []);
		}
		grouped.get(group)!.push(tool);
	}

	const groups = Array.from(grouped.entries());

	return (
		<div
			className={`${styles.toolsDrawer} ${!isOpen ? styles.hidden : ""}`}
		>
			<div className={styles.drawerHeader}>
				<h3>Доступные инструменты</h3>
				<button className={styles.closeBtn} onClick={onClose}>
					&times;
				</button>
			</div>
			<div className={styles.toolsList}>
				{groups.map(([group, groupTools], idx) => (
					<div
						key={group}
						className={`${styles.toolGroup} ${idx === groups.length - 1 ? styles.lastGroup : ""}`}
					>
						<h4 className={styles.toolGroupTitle}>{group}</h4>
						{groupTools.map((tool, idx) => (
							<div key={idx} className={styles.toolItem}>
								<div className={styles.toolCardHead}>
									<div className={styles.toolName}>
										{tool.name}
									</div>
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
											).map(([name, type]) => (
												<span
													key={name}
													className={styles.toolArg}
												>
													<strong>{name}</strong>:{" "}
													{String(type)}
												</span>
											))}
										</div>
									)}
							</div>
						))}
					</div>
				))}
			</div>
		</div>
	);
}
