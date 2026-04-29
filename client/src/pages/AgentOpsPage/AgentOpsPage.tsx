import { useCallback, useEffect, useMemo, useState } from "react";
import type {
	AgentScorecardItem,
	MemoryInspectionItem,
	PostRunReview,
	PreflightReport,
	TaskTemplate,
} from "../../types";
import styles from "./AgentOpsPage.module.css";

type OpsTab = "preflight" | "reviews" | "scorecard" | "memory" | "templates" | "replay" | "command" | "maintenance";

function fmtTime(ts?: number | string): string {
	if (!ts) return "нет данных";
	const date = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
	return Number.isNaN(date.getTime()) ? "нет данных" : date.toLocaleString("ru-RU");
}

function Badge({ tone, children }: { tone: "ok" | "warn" | "err" | "muted"; children: React.ReactNode }) {
	return <span className={`${styles.badge} ${styles[`badge_${tone}`]}`}>{children}</span>;
}

export function AgentOpsPage() {
	const [activeTab, setActiveTab] = useState<OpsTab>("preflight");
	const [preflight, setPreflight] = useState<PreflightReport | null>(null);
	const [reviews, setReviews] = useState<PostRunReview[]>([]);
	const [scorecard, setScorecard] = useState<AgentScorecardItem[]>([]);
	const [memory, setMemory] = useState<MemoryInspectionItem[]>([]);
	const [templates, setTemplates] = useState<TaskTemplate[]>([]);
	const [replays, setReplays] = useState<any[]>([]);
	const [command, setCommand] = useState("Remove-Item .\\logs -Recurse");
	const [commandPreview, setCommandPreview] = useState<any>(null);
	const [maintenance, setMaintenance] = useState<any>(null);
	const [loading, setLoading] = useState(false);

	const reload = useCallback(async () => {
		setLoading(true);
		try {
			const [preflightRes, reviewsRes, scoreRes, memoryRes, templatesRes, replayRes] = await Promise.all([
				fetch("/api/preflight"),
				fetch("/api/post-run-reviews"),
				fetch("/api/agent-scorecard"),
				fetch("/api/memory-inspector"),
				fetch("/api/task-templates"),
				fetch("/api/run-replays"),
			]);
			setPreflight(await preflightRes.json());
			setReviews(((await reviewsRes.json()).reviews ?? []) as PostRunReview[]);
			setScorecard(((await scoreRes.json()).agents ?? []) as AgentScorecardItem[]);
			setMemory(((await memoryRes.json()).agents ?? []) as MemoryInspectionItem[]);
			setTemplates(((await templatesRes.json()).templates ?? []) as TaskTemplate[]);
			setReplays(((await replayRes.json()).sessions ?? []) as any[]);
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		void reload();
	}, [reload]);

	const runMaintenance = async () => {
		setLoading(true);
		try {
			const res = await fetch("/api/maintenance/run", { method: "POST" });
			setMaintenance(await res.json());
			await reload();
		} finally {
			setLoading(false);
		}
	};

	const previewCommand = async () => {
		const res = await fetch("/api/command-preview", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command }),
		});
		setCommandPreview(await res.json());
	};

	const totals = useMemo(() => {
		return scorecard.reduce(
			(acc, item) => {
				acc.runs += item.total;
				acc.failures += item.failed + item.blocked;
				acc.retries += item.retries;
				return acc;
			},
			{ runs: 0, failures: 0, retries: 0 },
		);
	}, [scorecard]);

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<div>
					<div className={styles.eyebrow}>Agent Ops</div>
					<div className={styles.title}>Контур самопроверки агента</div>
				</div>
				<div className={styles.actions}>
					<button className={styles.btn} onClick={() => void reload()} disabled={loading}>
						{loading ? "Проверка..." : "Обновить"}
					</button>
					<button className={styles.primaryBtn} onClick={() => void runMaintenance()} disabled={loading}>
						Maintenance
					</button>
				</div>
			</div>

			<div className={styles.summaryRow}>
				<div className={styles.summaryItem}>
					<span>Preflight</span>
					<strong>{preflight?.allowed ? "passed" : "blocked"}</strong>
				</div>
				<div className={styles.summaryItem}>
					<span>Health</span>
					<strong>{preflight?.report?.score ?? "--"}/100</strong>
				</div>
				<div className={styles.summaryItem}>
					<span>Runs</span>
					<strong>{totals.runs}</strong>
				</div>
				<div className={styles.summaryItem}>
					<span>Retries</span>
					<strong>{totals.retries}</strong>
				</div>
			</div>

			<div className={styles.tabs}>
				{([
					["preflight", "Preflight"],
					["reviews", "Post-run"],
					["scorecard", "Scorecard"],
					["memory", "Memory"],
					["templates", "Templates"],
					["replay", "Replay"],
					["command", "Command"],
					["maintenance", "Maintenance"],
				] as [OpsTab, string][]).map(([id, label]) => (
					<button
						key={id}
						className={`${styles.tab} ${activeTab === id ? styles.tabActive : ""}`}
						onClick={() => setActiveTab(id)}
					>
						{label}
					</button>
				))}
			</div>

			<div className={styles.content}>
				{activeTab === "preflight" && (
					<div className={styles.panel}>
						<div className={styles.panelHeader}>
							<Badge tone={preflight?.allowed ? "ok" : "err"}>{preflight?.status ?? "unknown"}</Badge>
							<span>{preflight?.summary}</span>
						</div>
						<div className={styles.grid2}>
							<div className={styles.block}>
								<div className={styles.blockTitle}>Блокеры</div>
								{preflight?.blocking.length ? (
									preflight.blocking.map((check) => (
										<div key={check.id} className={styles.issue}>
											<strong>{check.title}</strong>
											<span>{check.summary}</span>
										</div>
									))
								) : (
									<div className={styles.empty}>Критичных блокеров нет</div>
								)}
							</div>
							<div className={styles.block}>
								<div className={styles.blockTitle}>Предупреждения</div>
								{preflight?.warnings.length ? (
									preflight.warnings.map((check) => (
										<div key={check.id} className={styles.issue}>
											<strong>{check.title}</strong>
											<span>{check.action || check.summary}</span>
										</div>
									))
								) : (
									<div className={styles.empty}>Предупреждений нет</div>
								)}
							</div>
						</div>
					</div>
				)}

				{activeTab === "reviews" && (
					<div className={styles.list}>
						{reviews.length === 0 ? (
							<div className={styles.empty}>Post-run reviews ещё не создавались</div>
						) : (
							reviews.map((review) => (
								<div key={review.id} className={styles.card}>
									<div className={styles.cardTop}>
										<Badge tone={review.status === "clean" ? "ok" : "warn"}>{review.status}</Badge>
										<span>{fmtTime(review.created_at)}</span>
									</div>
									<div className={styles.cardTitle}>{review.summary}</div>
									<div className={styles.cardText}>{review.task}</div>
									<div className={styles.metaLine}>
										score {review.diagnostics_score ?? "--"} · failed {review.failed_checks.length} · warnings {review.warning_checks.length}
									</div>
								</div>
							))
						)}
					</div>
				)}

				{activeTab === "scorecard" && (
					<div className={styles.tableWrap}>
						<table className={styles.table}>
							<thead>
								<tr>
									<th>Agent</th>
									<th>Total</th>
									<th>Success</th>
									<th>Failed</th>
									<th>Blocked</th>
									<th>Retries</th>
									<th>Avg steps</th>
								</tr>
							</thead>
							<tbody>
								{scorecard.map((item) => (
									<tr key={item.agent}>
										<td>{item.agent}</td>
										<td>{item.total}</td>
										<td>{item.success_rate}%</td>
										<td>{item.failed}</td>
										<td>{item.blocked}</td>
										<td>{item.retries}</td>
										<td>{item.avg_steps}</td>
									</tr>
								))}
							</tbody>
						</table>
						{scorecard.length === 0 && <div className={styles.empty}>Run статистики пока нет</div>}
					</div>
				)}

				{activeTab === "memory" && (
					<div className={styles.list}>
						{memory.map((item) => (
							<div key={item.agent} className={styles.card}>
								<div className={styles.cardTop}>
									<strong>{item.display_name}</strong>
									<Badge tone={item.stale ? "warn" : "ok"}>{item.stale ? "stale" : "fresh"}</Badge>
								</div>
								<div className={styles.metaLine}>
									messages {item.messages} · actions {item.actions} · updated {fmtTime(item.updated_at)}
								</div>
								{item.facts.length > 0 && (
									<div className={styles.facts}>
										{item.facts.map((fact, idx) => (
											<div key={idx}>{fact}</div>
										))}
									</div>
								)}
							</div>
						))}
					</div>
				)}

				{activeTab === "templates" && (
					<div className={styles.list}>
						{templates.map((tpl) => (
							<div key={tpl.id} className={styles.card}>
								<div className={styles.cardTitle}>{tpl.title}</div>
								<div className={styles.cardText}>{tpl.prompt}</div>
								<div className={styles.gates}>
									{tpl.quality_gates.map((gate) => (
										<span key={gate}>{gate}</span>
									))}
								</div>
							</div>
						))}
					</div>
				)}

				{activeTab === "replay" && (
					<div className={styles.list}>
						{replays.length === 0 ? (
							<div className={styles.empty}>Логов replay пока нет</div>
						) : (
							replays.map((session) => (
								<div key={session.id} className={styles.card}>
									<div className={styles.cardTop}>
										<strong>{session.id}</strong>
										<Badge tone={session.errors?.length ? "err" : "ok"}>
											{session.errors?.length ? "errors" : "clean"}
										</Badge>
									</div>
									<div className={styles.metaLine}>
										events {session.events} · tool calls {session.tool_calls} · {fmtTime(session.updated_at)}
									</div>
									<div className={styles.facts}>
										{(session.timeline ?? []).slice(-4).map((event: any, idx: number) => (
											<div key={idx}>
												{event.event}: {JSON.stringify(event.payload).slice(0, 180)}
											</div>
										))}
									</div>
								</div>
							))
						)}
					</div>
				)}

				{activeTab === "command" && (
					<div className={styles.panel}>
						<div className={styles.commandBox}>
							<textarea
								value={command}
								onChange={(e) => setCommand(e.target.value)}
								className={styles.commandInput}
							/>
							<button className={styles.primaryBtn} onClick={() => void previewCommand()}>
								Preview
							</button>
						</div>
						{commandPreview && (
							<div className={styles.preview}>
								<div className={styles.panelHeader}>
									<Badge
										tone={
											commandPreview.risk === "high"
												? "err"
												: commandPreview.risk === "medium"
													? "warn"
													: "ok"
										}
									>
										{commandPreview.risk}
									</Badge>
									<span>{commandPreview.recommendation}</span>
								</div>
								<div className={styles.grid2}>
									<div className={styles.block}>
										<div className={styles.blockTitle}>Причины</div>
										{commandPreview.reasons.map((reason: string) => (
											<div key={reason} className={styles.issue}>
												<span>{reason}</span>
											</div>
										))}
									</div>
									<div className={styles.block}>
										<div className={styles.blockTitle}>Пути</div>
										{commandPreview.touched_paths.length ? (
											commandPreview.touched_paths.map((path: string) => (
												<div key={path} className={styles.issue}>
													<span>{path}</span>
												</div>
											))
										) : (
											<div className={styles.empty}>Явных путей не найдено</div>
										)}
									</div>
								</div>
							</div>
						)}
					</div>
				)}

				{activeTab === "maintenance" && (
					<div className={styles.panel}>
						<div className={styles.panelHeader}>
							<Badge tone={maintenance?.status === "blocked" ? "err" : "ok"}>
								{maintenance?.status ?? "not run"}
							</Badge>
							<span>Maintenance запускает preflight, scorecard и собирает рекомендации.</span>
						</div>
						<div className={styles.block}>
							<div className={styles.blockTitle}>Рекомендации</div>
							{maintenance?.recommendations?.length ? (
								maintenance.recommendations.map((item: any) => (
									<div key={item.check_id} className={styles.issue}>
										<strong>{item.title}</strong>
										<span>{item.fix?.steps?.join(" → ")}</span>
									</div>
								))
							) : (
								<div className={styles.empty}>Нажми Maintenance, чтобы собрать рекомендации</div>
							)}
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
