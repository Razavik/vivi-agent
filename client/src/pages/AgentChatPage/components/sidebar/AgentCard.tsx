import styles from "./AgentCard.module.css";

interface AgentCardProps {
	displayName: string;
	task: string;
	status: string;
	selected: boolean;
	onClick: () => void;
	onClear?: () => void;
}

export function AgentCard({
	displayName,
	task,
	status,
	selected,
	onClick,
	onClear,
}: AgentCardProps) {
	// Раньше проверялось id.startsWith("history:") — но после слияния живой (SSE)
	// панели с исторической id почти всегда оказывается реальным run_id, а не
	// синтетическим "history:...", поэтому кнопка очистки практически никогда не
	// показывалась. Видимость должна зависеть только от статуса, не от id.
	const showClearButton = status === "done" || status === "error";

	return (
		<div
			className={`${styles.card} ${selected ? styles.selected : ""}`}
			onClick={onClick}
		>
			<span className={`${styles.dot} ${styles[status]}`} />
			<div className={styles.info}>
				<div className={styles.name}>{displayName}</div>
				<div className={styles.task}>{task || "Ещё не запускался"}</div>
			</div>
			<div className={styles.actions}>
				{showClearButton && (
					<button
						className={styles.clearBtn}
						title="Очистить память агента"
						onClick={(e) => {
							e.stopPropagation();
							onClear?.();
						}}
					>
						✕
					</button>
				)}
			</div>
		</div>
	);
}
