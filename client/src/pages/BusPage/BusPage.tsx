import { useState, useEffect, useCallback, useRef } from "react";
import styles from "./BusPage.module.css";

interface BusMessage {
	msg_id: string;
	msg_type: string;
	sender: string;
	run_id: string | null;
	payload: Record<string, unknown>;
	published_at: number;
}

const TYPE_COLORS: Record<string, string> = {
	run_started: "#10a37f",
	run_finished: "#33d17a",
	progress_update: "#7eb0ff",
	question_to_director: "#f6d365",
	outbox_message: "#a78bfa",
	dependency_ready: "#34d399",
	sub_agent_error: "#ef4444",
	system_event: "#94a3b8",
};

function fmtTime(ts: number): string {
	return new Date(ts * 1000).toLocaleTimeString("ru-RU", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	});
}

function fmtPayload(payload: Record<string, unknown>): string {
	try {
		return JSON.stringify(payload, null, 2);
	} catch {
		return String(payload);
	}
}

export function BusPage() {
	const [messages, setMessages] = useState<BusMessage[]>([]);
	const [filterType, setFilterType] = useState("");
	const [filterRun, setFilterRun] = useState("");
	const [selected, setSelected] = useState<BusMessage | null>(null);
	const [autoScroll, setAutoScroll] = useState(true);
	const bottomRef = useRef<HTMLDivElement>(null);

	const reload = useCallback(async () => {
		try {
			const res = await fetch("/api/bus");
			const data = await res.json();
			setMessages((data.messages ?? []).slice().reverse());
		} catch {
			// ignore
		}
	}, []);

	useEffect(() => {
		void reload();
		const timer = setInterval(() => void reload(), 2000);
		return () => clearInterval(timer);
	}, [reload]);

	useEffect(() => {
		if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages, autoScroll]);

	const msgTypes = Array.from(new Set(messages.map((m) => m.msg_type))).sort();
	const runIds = Array.from(new Set(messages.map((m) => m.run_id).filter(Boolean))).sort();

	const filtered = messages.filter((m) => {
		if (filterType && m.msg_type !== filterType) return false;
		if (filterRun && m.run_id !== filterRun) return false;
		return true;
	});

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<span className={styles.title}>MessageBus</span>
				<span className={styles.count}>{filtered.length} сообщений</span>

				<select
					className={styles.filterSelect}
					value={filterType}
					onChange={(e) => setFilterType(e.target.value)}
				>
					<option value="">Все типы</option>
					{msgTypes.map((t) => (
						<option key={t} value={t}>{t}</option>
					))}
				</select>

				<select
					className={styles.filterSelect}
					value={filterRun}
					onChange={(e) => setFilterRun(e.target.value)}
				>
					<option value="">Все run</option>
					{runIds.map((id) => (
						<option key={id as string} value={id as string}>{(id as string).slice(0, 12)}…</option>
					))}
				</select>

				<label className={styles.autoScrollLabel}>
					<input
						type="checkbox"
						checked={autoScroll}
						onChange={(e) => setAutoScroll(e.target.checked)}
						className={styles.autoScrollCheck}
					/>
					Автоскролл
				</label>
			</div>

			<div className={styles.content}>
				<div className={styles.feed}>
					{filtered.length === 0 ? (
						<div className={styles.empty}>Нет сообщений</div>
					) : (
						filtered.map((msg) => (
							<div
								key={msg.msg_id}
								className={`${styles.msgRow} ${selected?.msg_id === msg.msg_id ? styles.msgRowSelected : ""}`}
								onClick={() => setSelected(selected?.msg_id === msg.msg_id ? null : msg)}
							>
								<span className={styles.msgTime}>{fmtTime(msg.published_at)}</span>
								<span
									className={styles.msgType}
									style={{ color: TYPE_COLORS[msg.msg_type] ?? "#94a3b8" }}
								>
									{msg.msg_type}
								</span>
								<span className={styles.msgSender}>{msg.sender || "—"}</span>
								{msg.run_id && (
									<span className={styles.msgRunId}>{msg.run_id.slice(0, 8)}</span>
								)}
							</div>
						))
					)}
					<div ref={bottomRef} />
				</div>

				{selected && (
					<div className={styles.detail}>
						<div className={styles.detailHeader}>
							<span
								className={styles.detailType}
								style={{ color: TYPE_COLORS[selected.msg_type] ?? "#94a3b8" }}
							>
								{selected.msg_type}
							</span>
							<button className={styles.closeBtn} onClick={() => setSelected(null)}>✕</button>
						</div>
						<div className={styles.detailBody}>
							<div className={styles.detailRow}>
								<span className={styles.lbl}>ID</span>
								<span className={styles.mono}>{selected.msg_id}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.lbl}>Sender</span>
								<span className={styles.val}>{selected.sender || "—"}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.lbl}>Run ID</span>
								<span className={styles.mono}>{selected.run_id ?? "—"}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.lbl}>Время</span>
								<span className={styles.val}>{fmtTime(selected.published_at)}</span>
							</div>
							<div className={styles.detailRow}>
								<span className={styles.lbl}>Payload</span>
								<pre className={styles.payloadPre}>{fmtPayload(selected.payload)}</pre>
							</div>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
