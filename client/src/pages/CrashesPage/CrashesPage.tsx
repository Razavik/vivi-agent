import { useState, useEffect, useCallback } from "react";
import styles from "./CrashesPage.module.css";

interface CrashSummary {
	file: string;
	timestamp: number;
	exception_type: string;
	exception_message: string;
}

interface CrashDetail extends CrashSummary {
	traceback: string;
	python_version: string;
	context: Record<string, unknown>;
}

function fmtTime(ts: number): string {
	return new Date(ts * 1000).toLocaleString("ru-RU");
}

export function CrashesPage() {
	const [reports, setReports] = useState<CrashSummary[]>([]);
	const [selected, setSelected] = useState<CrashDetail | null>(null);
	const [loading, setLoading] = useState(false);

	const reload = useCallback(async () => {
		try {
			const res = await fetch("/api/crashes");
			const data = await res.json();
			setReports(data.crashes ?? []);
		} catch {
			// ignore
		}
	}, []);

	useEffect(() => {
		void reload();
	}, [reload]);

	const openReport = async (filename: string) => {
		setLoading(true);
		try {
			const res = await fetch(`/api/crashes/${encodeURIComponent(filename)}`);
			const data = await res.json();
			setSelected(data);
		} catch {
			// ignore
		} finally {
			setLoading(false);
		}
	};

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<span className={styles.title}>Crash Reports</span>
				{reports.length > 0 && (
					<span className={styles.count}>{reports.length} отчётов</span>
				)}
			</div>

			<div className={styles.content}>
				<div className={styles.list}>
					{reports.length === 0 ? (
						<div className={styles.empty}>
							<div className={styles.emptyIcon}>✓</div>
							<div>Crash-отчётов нет</div>
						</div>
					) : (
						reports.map((r) => (
							<div
								key={r.file}
								className={`${styles.reportCard} ${selected?.file === r.file ? styles.reportCardSelected : ""}`}
								onClick={() => void openReport(r.file)}
							>
								<div className={styles.reportHeader}>
									<span className={styles.exType}>{r.exception_type}</span>
									<span className={styles.reportTime}>{fmtTime(r.timestamp)}</span>
								</div>
								<div className={styles.reportMsg}>{r.exception_message}</div>
								<div className={styles.reportFile}>{r.file}</div>
							</div>
						))
					)}
				</div>

				<div className={styles.detail}>
					{!selected && !loading && (
						<div className={styles.detailEmpty}>
							Выберите отчёт для просмотра
						</div>
					)}
					{loading && (
						<div className={styles.detailEmpty}>Загрузка…</div>
					)}
					{selected && !loading && (
						<>
							<div className={styles.detailHeader}>
								<span className={styles.detailType}>{selected.exception_type}</span>
								<span className={styles.detailTime}>{fmtTime(selected.timestamp)}</span>
								<button className={styles.closeBtn} onClick={() => setSelected(null)}>✕</button>
							</div>
							<div className={styles.detailBody}>
								<div className={styles.section}>
									<div className={styles.sectionLabel}>Сообщение</div>
									<div className={styles.sectionValue}>{selected.exception_message}</div>
								</div>

								{Object.keys(selected.context ?? {}).length > 0 && (
									<div className={styles.section}>
										<div className={styles.sectionLabel}>Контекст</div>
										<pre className={styles.ctxPre}>
											{JSON.stringify(selected.context, null, 2)}
										</pre>
									</div>
								)}

								<div className={styles.section}>
									<div className={styles.sectionLabel}>Traceback</div>
									<pre className={styles.tbPre}>{selected.traceback}</pre>
								</div>

								<div className={styles.section}>
									<div className={styles.sectionLabel}>Python</div>
									<div className={styles.sectionValue + " " + styles.mono}>
										{selected.python_version.split(" ")[0]}
									</div>
								</div>
							</div>
						</>
					)}
				</div>
			</div>
		</div>
	);
}
