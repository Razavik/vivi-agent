import { useState, useEffect, useCallback } from "react";
import styles from "./RunsDashboardPage.module.css";

interface AgentRun {
	run_id: string;
	agent_name: string;
	task: string;
	status: string;
	step: number | null;
	retries: number;
	interrupt_count: number;
	created_at: number | null;
	updated_at: number | null;
	result: string | null;
	error: string | null;
	metadata: Record<string, unknown>;
}

const STATUS_LABELS: Record<string, string> = {
	running: "Работает",
	paused: "Пауза",
	waiting_input: "Ждёт ввода",
	queued: "В очереди",
	cancelling: "Отмена…",
	finished: "Готово",
	cancelled: "Отменён",
	error: "Ошибка",
	interrupted: "Прерван",
};

function fmtTime(ts: number | null): string {
	if (!ts) return "—";
	return new Date(ts * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDuration(start: number | null, end: number | null): string {
	if (!start) return "—";
	const sec = Math.round((end ?? Date.now() / 1000) - start);
	if (sec < 60) return `${sec}с`;
	return `${Math.floor(sec / 60)}м ${sec % 60}с`;
}

function StatusBadge({ status }: { status: string }) {
	return (
		<span className={`${styles.badge} ${styles["badge_" + status] ?? styles.badge_default}`}>
			{STATUS_LABELS[status] ?? status}
		</span>
	);
}

type FilterTab = "all" | "active" | "done";

export function RunsDashboardPage() {
	const [runs, setRuns] = useState<AgentRun[]>([]);
	const [filter, setFilter] = useState<FilterTab>("all");
	const [selected, setSelected] = useState<AgentRun | null>(null);
	const [now, setNow] = useState(() => Date.now() / 1000);

	const reload = useCallback(async () => {
		try {
			const res = await fetch("/api/runs");
			const data = await res.json();
			setRuns(data.runs ?? []);
		} catch {
			// ignore
		}
	}, []);

	useEffect(() => {
		void reload();
		const timer = setInterval(() => {
			void reload();
			setNow(Date.now() / 1000);
		}, 2000);
		return () => clearInterval(timer);
	}, [reload]);

	const activeStatuses = new Set(["queued", "running", "waiting_input", "paused", "cancelling"]);
	const doneStatuses = new Set(["finished", "cancelled", "error", "interrupted"]);

	const filtered = runs.filter((r) => {
		if (filter === "active") return activeStatuses.has(r.status);
		if (filter === "done") return doneStatuses.has(r.status);
		return true;
	});

	const activeCount = runs.filter((r) => activeStatuses.has(r.status)).length;

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<span className={styles.title}>Runs</span>
				<div className={styles.stats}>
					<span className={styles.statItem}>
						<span className={styles.statDot + " " + styles.dotActive} />
						{activeCount} активных
					</span>
					<span className={styles.statItem}>{runs.length} всего</span>
				</div>
				<div className={styles.filterTabs}>
					{(["all", "active", "done"] as FilterTab[]).map((f) => (
						<button
							key={f}
							className={`${styles.filterTab} ${filter === f ? styles.filterTabActive : ""}`}
							onClick={() => setFilter(f)}
						>
							{f === "all" ? "Все" : f === "active" ? "Активные" : "Завершённые"}
						</button>
					))}
				</div>
			</div>

			<div className={styles.content}>
				<div className={styles.tableWrap}>
					{filtered.length === 0 ? (
						<div className={styles.empty}>Нет запусков</div>
					) : (
						<table className={styles.table}>
							<thead>
								<tr>
									<th>Run ID</th>
									<th>Агент</th>
									<th>Задача</th>
									<th>Статус</th>
									<th>Шаг</th>
									<th>Retries</th>
									<th>Прерывания</th>
									<th>Время</th>
									<th>Длит.</th>
								</tr>
							</thead>
							<tbody>
								{filtered.map((run) => (
									<tr
										key={run.run_id}
										className={`${styles.row} ${selected?.run_id === run.run_id ? styles.rowSelected : ""}`}
										onClick={() => setSelected(selected?.run_id === run.run_id ? null : run)}
									>
										<td className={styles.cellId}>{run.run_id.slice(0, 8)}…</td>
										<td className={styles.cellAgent}>{run.agent_name}</td>
										<td className={styles.cellTask} title={run.task}>{run.task}</td>
										<td><StatusBadge status={run.status} /></td>
										<td className={styles.cellNum}>{run.step ?? "—"}</td>
										<td className={styles.cellNum}>
											{run.retries > 0 ? <span className={styles.retryBadge}>{run.retries}</span> : "0"}
										</td>
										<td className={styles.cellNum}>
											{run.interrupt_count > 0 ? <span className={styles.interruptBadge}>{run.interrupt_count}</span> : "0"}
										</td>
										<td className={styles.cellTime}>{fmtTime(run.created_at)}</td>
										<td className={styles.cellTime}>
											{activeStatuses.has(run.status)
												? <span className={styles.liveDuration}>{fmtDuration(run.created_at, now)}</span>
												: fmtDuration(run.created_at, run.updated_at)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					)}
				</div>

				{selected && (
					<div className={styles.detail}>
						<div className={styles.detailHeader}>
							<span className={styles.detailTitle}>Детали</span>
							<button className={styles.closeBtn} onClick={() => setSelected(null)}>✕</button>
						</div>
						<div className={styles.detailBody}>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Run ID</span>
								<span className={styles.detailValue + " " + styles.mono}>{selected.run_id}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Агент</span>
								<span className={styles.detailValue}>{selected.agent_name}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Статус</span>
								<StatusBadge status={selected.status} />
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Задача</span>
								<span className={styles.detailValue}>{selected.task}</span>
							</div>
							{selected.result && (
								<div className={styles.detailRow}>
									<span className={styles.detailLabel}>Результат</span>
									<span className={styles.detailValue}>{selected.result}</span>
								</div>
							)}
							{selected.error && (
								<div className={styles.detailRow}>
									<span className={styles.detailLabel}>Ошибка</span>
									<span className={styles.detailValue + " " + styles.errText}>{selected.error}</span>
								</div>
							)}
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Шаг</span>
								<span className={styles.detailValue}>{selected.step ?? "—"}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Retries</span>
								<span className={styles.detailValue}>{selected.retries}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Прерывания</span>
								<span className={styles.detailValue}>{selected.interrupt_count}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Приоритет</span>
								<span className={styles.detailValue}>
									{(selected.metadata?.priority as number | undefined) ?? 5}
								</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Запущен</span>
								<span className={styles.detailValue}>{fmtTime(selected.created_at)}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Обновлён</span>
								<span className={styles.detailValue}>{fmtTime(selected.updated_at)}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.detailLabel}>Длит.</span>
								<span className={styles.detailValue}>
									{activeStatuses.has(selected.status)
										? fmtDuration(selected.created_at, now)
										: fmtDuration(selected.created_at, selected.updated_at)}
								</span>
							</div>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
