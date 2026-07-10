import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import styles from "./CrashesPage.module.css";
import { fetchJson } from "../../utils/http";

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
	const [selected, setSelected] = useState<CrashDetail | null>(null);
	const { data } = useQuery({
		queryKey: ["crashes"],
		queryFn: () => fetchJson<{ crashes?: CrashSummary[] }>("/api/crashes", { crashes: [] }),
	});
	const reports = data?.crashes ?? [];
	const openReport = useMutation({
		mutationFn: (filename: string) =>
			fetchJson<CrashDetail | null>(`/api/crashes/${encodeURIComponent(filename)}`, null),
		onSuccess: (detail) => {
			if (detail) setSelected(detail);
		},
	});

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
								onClick={() => openReport.mutate(r.file)}
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
					{!selected && !openReport.isPending && (
						<div className={styles.detailEmpty}>
							Выберите отчёт для просмотра
						</div>
					)}
					{openReport.isPending && (
						<div className={styles.detailEmpty}>Загрузка…</div>
					)}
					{selected && !openReport.isPending && (
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

