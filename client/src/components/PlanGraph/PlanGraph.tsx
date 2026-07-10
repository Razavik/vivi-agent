import { Check, Circle, Loader2 } from "lucide-react";
import type { PlanItem } from "../../types";
import styles from "./PlanGraph.module.css";

interface PlanGraphProps {
	plan: PlanItem[];
	title?: string;
	compact?: boolean;
}

const STATUS_META: Record<
	PlanItem["status"],
	{ label: string; detail: string; Icon: typeof Circle }
> = {
	pending: { label: "Pending", detail: "Ожидает выполнения", Icon: Circle },
	in_progress: { label: "Active", detail: "В работе", Icon: Loader2 },
	completed: { label: "Done", detail: "Завершено", Icon: Check },
};

export function PlanGraph({ plan, title = "План", compact = false }: PlanGraphProps) {
	if (!plan.length) return null;

	const done = plan.filter((item) => item.status === "completed").length;
	const activeIndex = plan.findIndex((item) => item.status === "in_progress");
	const progress = Math.round((done / plan.length) * 100);

	return (
		<section className={`${styles.planBlock} ${compact ? styles.compact : ""}`}>
			<div className={styles.panelGlow} />
			<div className={styles.planHeader}>
				<div>
					<div className={styles.planLabel}>{title}</div>
					<div className={styles.planSubtitle}>
						{done} / {plan.length} выполнено
					</div>
				</div>
				<div
					className={styles.planMeter}
					aria-label={`${done} из ${plan.length} выполнено`}
				>
					<span>{progress}%</span>
				</div>
			</div>
			<div className={styles.progressTrack} aria-hidden="true">
				<div className={styles.progressFill} style={{ width: `${progress}%` }} />
			</div>

			<div className={styles.graph}>
				{plan.map((item, index) => {
					const meta = STATUS_META[item.status];
					const Icon = meta.Icon;
					const isLast = index === plan.length - 1;
					const isPastActive =
						activeIndex !== -1 && index < activeIndex && item.status !== "completed";
					return (
						<div
							key={item.id}
							className={`${styles.graphRow} ${styles[item.status]}`}
							style={{ animationDelay: `${index * 55}ms` }}
						>
							<div className={styles.rail}>
								<div className={`${styles.nodeDot} ${styles[item.status]}`}>
									<Icon size={compact ? 10 : 12} />
								</div>
								{!isLast && (
									<div
										className={`${styles.nodeLine} ${
											item.status === "completed" || isPastActive
												? styles.completedLine
												: ""
										}`}
									/>
								)}
							</div>
							<div className={`${styles.nodeCard} ${styles[item.status]}`}>
								<div className={styles.nodeTop}>
									<div className={styles.nodeTitle}>{item.content}</div>
									<span className={`${styles.statusPill} ${styles[item.status]}`}>
										{meta.label}
									</span>
								</div>
								<div className={styles.nodeFooter}>
									<span className={styles.nodeId}>{item.id || index + 1}</span>
									<span className={styles.nodeDetail}>{meta.detail}</span>
								</div>
							</div>
						</div>
					);
				})}
			</div>
		</section>
	);
}
