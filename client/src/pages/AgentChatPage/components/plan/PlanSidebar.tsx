import styles from "./PlanSidebar.module.css";
import type { SubAgentPane, PlanItem } from "../../../../types";

function getPlanForPane(pane: SubAgentPane): PlanItem[] {
	if (pane.plan && pane.plan.length > 0) return pane.plan;
	const lastSession = pane.sessions?.[pane.sessions.length - 1];
	return lastSession?.plan ?? [];
}

interface PlanSidebarProps {
	pane: SubAgentPane;
}

export function PlanSidebar({ pane }: PlanSidebarProps) {
	const plan = getPlanForPane(pane);
	const total = plan.length;
	const done = plan.filter((item) => item.status === "completed").length;
	const active = plan.filter((item) => item.status === "in_progress").length;
	const pending = plan.filter((item) => item.status === "pending").length;
	const progress = total > 0 ? Math.round((done / total) * 100) : 0;

	return (
		<aside className={styles.sidebar}>
			<div className={styles.summaryCard}>
				<div className={styles.summaryTop}>
					<span className={styles.badge}>План оркестратора</span>
					<span className={styles.heroValue}>{progress}%</span>
				</div>
				<div className={styles.summaryTitle}>
					{pane.task || "План на текущий запуск"}
				</div>
				<div className={styles.summaryText}>
					{pane.status === "running"
						? "В работе сейчас, видно активный шаг и ближайшую очередь."
						: "История выполненного запуска без лишнего визуального шума."}
				</div>
				<div className={styles.miniStats}>
					<div className={styles.statCard}>
						<span className={styles.statLabel}>Всего</span>
						<span className={styles.statValue}>{total}</span>
					</div>
					<div className={styles.statCard}>
						<span className={styles.statLabel}>Готово</span>
						<span className={styles.statValue}>{done}</span>
					</div>
					<div className={styles.statCard}>
						<span className={styles.statLabel}>В работе</span>
						<span className={styles.statValue}>{active}</span>
					</div>
					<div className={styles.statCard}>
						<span className={styles.statLabel}>В очереди</span>
						<span className={styles.statValue}>{pending}</span>
					</div>
				</div>
				<div className={styles.progressTrack} aria-hidden="true">
					<div
						className={styles.progressFill}
						style={{ width: `${progress}%` }}
					/>
				</div>
			</div>
			{plan.length > 0 && (
				<div className={styles.planGraph}>
					<div className={styles.planGraphHeader}>Шаги плана</div>
					<div className={styles.planGraphList}>
						{plan.map((item, index) => (
							<div
								key={index}
								className={`${styles.planGraphItem} ${styles[item.status]}`}
							>
								<div className={styles.planGraphIcon}>
									{item.status === "completed" && "✓"}
									{item.status === "in_progress" && "⟳"}
									{item.status === "pending" && "○"}
								</div>
								<div className={styles.planGraphContent}>
									<div className={styles.planGraphText}>
										{item.content}
									</div>
									{index < plan.length - 1 && (
										<div className={styles.planGraphLine} />
									)}
								</div>
							</div>
						))}
					</div>
				</div>
			)}
			{plan.length === 0 && (
				<div className={styles.focusCard}>
					<div className={styles.emptyTitle}>
						План ещё не сформирован
					</div>
					<div className={styles.emptyText}>
						Как только появятся шаги, здесь останется только
						короткая сводка без лишнего шума.
					</div>
				</div>
			)}
		</aside>
	);
}
