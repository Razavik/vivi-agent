import { useCallback, useEffect, useMemo, useState } from "react";
import type { DiagnosticCheck, DiagnosticStatus, DiagnosticsReport } from "../../types";
import styles from "./DiagnosticsPage.module.css";

const STATUS_LABEL: Record<DiagnosticStatus, string> = {
	pass: "OK",
	warn: "WARN",
	fail: "FAIL",
	skip: "SKIP",
};

const STATUS_ORDER: Record<DiagnosticStatus, number> = {
	fail: 0,
	warn: 1,
	skip: 2,
	pass: 3,
};

function fmtTime(ts?: number): string {
	if (!ts) return "нет данных";
	return new Date(ts * 1000).toLocaleString("ru-RU");
}

function statusClass(status: DiagnosticStatus): string {
	if (status === "fail") return styles.statusFail;
	if (status === "warn") return styles.statusWarn;
	if (status === "pass") return styles.statusPass;
	return styles.statusSkip;
}

function scoreClass(report: DiagnosticsReport): string {
	if (report.status === "critical") return styles.scoreCritical;
	if (report.status === "attention") return styles.scoreAttention;
	return styles.scoreHealthy;
}

function renderDetails(details: Record<string, unknown> | undefined): string {
	if (!details || Object.keys(details).length === 0) return "";
	return JSON.stringify(details, null, 2);
}

export function DiagnosticsPage() {
	const [report, setReport] = useState<DiagnosticsReport | null>(null);
	const [selectedId, setSelectedId] = useState<string>("");
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState("");
	const [filter, setFilter] = useState<DiagnosticStatus | "all">("all");

	const reload = useCallback(async () => {
		setLoading(true);
		setError("");
		try {
			const res = await fetch("/api/diagnostics");
			const data = await res.json();
			setReport(data);
			setSelectedId((current) => current || data.checks?.[0]?.id || "");
		} catch (e) {
			setError(e instanceof Error ? e.message : "Не удалось загрузить диагностику");
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		void reload();
	}, [reload]);

	const checks = useMemo(() => {
		const list = [...(report?.checks ?? [])].sort(
			(a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status],
		);
		if (filter === "all") return list;
		return list.filter((check) => check.status === filter);
	}, [filter, report]);

	const selected = useMemo<DiagnosticCheck | undefined>(() => {
		return report?.checks.find((check) => check.id === selectedId) ?? checks[0];
	}, [checks, report, selectedId]);

	const topProblems = useMemo(() => {
		return (report?.checks ?? []).filter((check) => check.status === "fail" || check.status === "warn").slice(0, 4);
	}, [report]);

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<div>
					<div className={styles.eyebrow}>System Diagnostics</div>
					<div className={styles.title}>Панель здоровья агента</div>
				</div>
				<div className={styles.headerActions}>
					<div className={styles.generated}>Обновлено: {fmtTime(report?.generated_at)}</div>
					<button className={styles.refreshBtn} onClick={() => void reload()} disabled={loading}>
						{loading ? "Проверка..." : "Обновить"}
					</button>
				</div>
			</div>

			{error && <div className={styles.errorBanner}>{error}</div>}

			<div className={styles.body}>
				<div className={styles.left}>
					<div className={styles.scorePanel}>
						<div className={`${styles.scoreRing} ${report ? scoreClass(report) : ""}`}>
							<span>{report?.score ?? "--"}</span>
							<small>/100</small>
						</div>
						<div className={styles.scoreText}>
							<div className={styles.scoreTitle}>
								{report?.status === "critical"
									? "Нужен разбор"
									: report?.status === "attention"
										? "Есть предупреждения"
										: "Система стабильна"}
							</div>
							<div className={styles.scoreSummary}>
								{report?.summary ?? "Диагностика ещё не загружена"}
							</div>
						</div>
					</div>

					<div className={styles.kpis}>
						<div className={styles.kpi}>
							<span className={styles.kpiValue}>{report?.counts.fail ?? 0}</span>
							<span className={styles.kpiLabel}>critical</span>
						</div>
						<div className={styles.kpi}>
							<span className={styles.kpiValue}>{report?.counts.warn ?? 0}</span>
							<span className={styles.kpiLabel}>warnings</span>
						</div>
						<div className={styles.kpi}>
							<span className={styles.kpiValue}>{report?.counts.pass ?? 0}</span>
							<span className={styles.kpiLabel}>passed</span>
						</div>
					</div>

					<div className={styles.section}>
						<div className={styles.sectionTitle}>Приоритеты</div>
						{topProblems.length === 0 ? (
							<div className={styles.emptySmall}>Срочных проблем нет</div>
						) : (
							topProblems.map((check) => (
								<button
									key={check.id}
									className={styles.priorityItem}
									onClick={() => setSelectedId(check.id)}
								>
									<span className={`${styles.statusDot} ${statusClass(check.status)}`} />
									<span>{check.title}</span>
								</button>
							))
						)}
					</div>

					<div className={styles.section}>
						<div className={styles.sectionTitle}>Факты окружения</div>
						<div className={styles.facts}>
							{Object.entries(report?.facts ?? {}).map(([key, value]) => (
								<div key={key} className={styles.factRow}>
									<span>{key}</span>
									<code>{Array.isArray(value) ? `${value.length} items` : String(value)}</code>
								</div>
							))}
						</div>
					</div>
				</div>

				<div className={styles.center}>
					<div className={styles.tabs}>
						{(["all", "fail", "warn", "pass", "skip"] as const).map((item) => (
							<button
								key={item}
								className={`${styles.tab} ${filter === item ? styles.tabActive : ""}`}
								onClick={() => setFilter(item)}
							>
								{item === "all" ? "Все" : STATUS_LABEL[item]}
							</button>
						))}
					</div>

					<div className={styles.checkList}>
						{checks.map((check) => (
							<button
								key={check.id}
								className={`${styles.checkCard} ${selected?.id === check.id ? styles.checkCardActive : ""}`}
								onClick={() => setSelectedId(check.id)}
							>
								<div className={styles.checkTop}>
									<span className={`${styles.statusBadge} ${statusClass(check.status)}`}>
										{STATUS_LABEL[check.status]}
									</span>
									<span className={styles.severity}>{check.severity}</span>
								</div>
								<div className={styles.checkTitle}>{check.title}</div>
								<div className={styles.checkSummary}>{check.summary}</div>
							</button>
						))}
						{checks.length === 0 && <div className={styles.empty}>Нет проверок для выбранного фильтра</div>}
					</div>
				</div>

				<div className={styles.detail}>
					{selected ? (
						<>
							<div className={styles.detailHeader}>
								<span className={`${styles.statusBadge} ${statusClass(selected.status)}`}>
									{STATUS_LABEL[selected.status]}
								</span>
								<span className={styles.detailTitle}>{selected.title}</span>
							</div>
							<div className={styles.detailBody}>
								<div className={styles.detailBlock}>
									<div className={styles.detailLabel}>Сводка</div>
									<div className={styles.detailText}>{selected.summary}</div>
								</div>
								{selected.action && (
									<div className={styles.detailBlock}>
										<div className={styles.detailLabel}>Что сделать</div>
										<div className={styles.actionText}>{selected.action}</div>
									</div>
								)}
								{renderDetails(selected.details) && (
									<div className={styles.detailBlock}>
										<div className={styles.detailLabel}>Details</div>
										<pre className={styles.detailsPre}>{renderDetails(selected.details)}</pre>
									</div>
								)}
							</div>
						</>
					) : (
						<div className={styles.empty}>Выберите проверку</div>
					)}
				</div>
			</div>
		</div>
	);
}
