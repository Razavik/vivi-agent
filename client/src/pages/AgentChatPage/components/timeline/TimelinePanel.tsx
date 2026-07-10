import styles from "./TimelinePanel.module.css";
import type { SubAgentPane } from "../../../../types";

interface TimelineEvent {
	time: string;
	kind: string;
	label: string;
	detail?: string;
}

function buildTimeline(pane: SubAgentPane): TimelineEvent[] {
	const events: TimelineEvent[] = [];
	const fmt = (ts: number) =>
		new Date(ts).toLocaleTimeString("ru-RU", {
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});

	if (pane.startedAt) {
		events.push({
			time: fmt(pane.startedAt),
			kind: "start",
			label: "Запущен",
			detail: pane.task,
		});
	}

	const allSessions = pane.sessions ?? [];
	for (const session of allSessions) {
		for (const step of session.steps) {
			if (step.action === "ask_operator") {
				events.push({
					time: "",
					kind: "question",
					label: "Вопрос оператору",
					detail: step.args ? JSON.stringify(step.args) : "",
				});
			} else if (step.action === "finish_task") {
				events.push({
					time: "",
					kind: "finish",
					label: "Завершён",
					detail: String(step.args?.summary ?? ""),
				});
			} else if (step.action) {
				events.push({
					time: "",
					kind: step.success === false ? "fail" : "step",
					label: step.action,
					detail: step.thought,
				});
			}
		}
	}

	const liveSteps = pane.steps.filter(
		(s) => !allSessions.flatMap((ss) => ss.steps).includes(s),
	);
	for (const step of liveSteps) {
		events.push({
			time: "",
			kind:
				step.success === false
					? "fail"
					: step.result !== undefined
						? "step"
						: "pending",
			label: step.action ?? "…",
			detail: step.thought,
		});
	}

	if (pane.question) {
		events.push({
			time: "",
			kind: "question",
			label: "Вопрос оператору",
			detail: pane.question,
		});
	}
	if (pane.status === "paused") {
		events.push({ time: "", kind: "pause", label: "На паузе" });
	}
	if (pane.result && pane.status === "done") {
		events.push({
			time: "",
			kind: "finish",
			label: "Готово",
			detail: pane.result.slice(0, 120),
		});
	}
	if (pane.status === "error") {
		events.push({
			time: "",
			kind: "error",
			label: "Ошибка",
			detail: pane.errorMessage,
		});
	}

	return events;
}

const TL_COLORS: Record<string, string> = {
	start: "var(--accent)",
	step: "rgba(255,255,255,0.2)",
	fail: "var(--err)",
	finish: "var(--ok)",
	question: "var(--warn)",
	pause: "var(--warn)",
	error: "var(--err)",
	pending: "#7eb0ff",
};

interface TimelinePanelProps {
	pane: SubAgentPane;
}

export function TimelinePanel({ pane }: TimelinePanelProps) {
	const events = buildTimeline(pane);
	if (!events.length) {
		return (
			<div className={styles.empty}>
				<div>Нет событий</div>
			</div>
		);
	}
	return (
		<div className={styles.timeline}>
			{events.map((ev, i) => (
				<div key={i} className={styles.row}>
					<div className={styles.left}>
						{ev.time && (
							<span className={styles.time}>{ev.time}</span>
						)}
						<span
							className={styles.dot}
							style={{
								background:
									TL_COLORS[ev.kind] ?? "var(--border)",
							}}
						/>
						{i < events.length - 1 && (
							<span className={styles.line} />
						)}
					</div>
					<div className={styles.content}>
						<span
							className={styles.label}
							style={{
								color:
									TL_COLORS[ev.kind] ?? "var(--text-muted)",
							}}
						>
							{ev.label}
						</span>
						{ev.detail && (
							<span className={styles.detail}>{ev.detail}</span>
						)}
					</div>
				</div>
			))}
		</div>
	);
}
