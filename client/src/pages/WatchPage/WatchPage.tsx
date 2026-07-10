import { useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CircleStop, Loader2 } from "lucide-react";
import { fetchJson } from "../../utils/http";
import styles from "./WatchPage.module.css";

interface MonitorAction {
	action?: string;
	thought?: string;
	success?: boolean;
}

interface MonitorState {
	running: boolean;
	goal: string;
	last_action?: MonitorAction | null;
	pending_confirmation: boolean;
	updated_at: number;
}

interface HistoryMessage {
	role?: string;
	content?: string;
}

interface HistoryPayload {
	chat_history?: HistoryMessage[];
}

function shortText(value: string, max = 900): string {
	const normalized = value.replace(/\s+/g, " ").trim();
	if (normalized.length <= max) return normalized;
	return `${normalized.slice(0, max - 1)}…`;
}

export function WatchPage() {
	useEffect(() => {
		const previousTitle = document.title;
		document.title = "Vivi Monitor";
		return () => {
			document.title = previousTitle;
		};
	}, []);

	const stateQuery = useQuery({
		queryKey: ["monitor-state"],
		queryFn: () =>
			fetchJson<MonitorState>("/api/monitor/state", {
				running: false,
				goal: "",
				pending_confirmation: false,
				updated_at: Date.now() / 1000,
			}),
		refetchInterval: 1000,
	});

	const historyQuery = useQuery({
		queryKey: ["monitor-history"],
		queryFn: () => fetchJson<HistoryPayload>("/api/history", {}),
		refetchInterval: 1500,
	});

	const cancelMutation = useMutation({
		mutationFn: async () => {
			await fetch("/api/cancel", { method: "POST" });
		},
		onSuccess: () => stateQuery.refetch(),
	});

	const state = stateQuery.data;
	const messages = (historyQuery.data?.chat_history ?? [])
		.filter((item) => item.content && item.role)
		.slice(-4);
	const lastAction = state?.last_action;

	return (
		<section className={styles.watchShell}>
			<header className={styles.header}>
				<div className={styles.titleBlock}>
					<h1>
						<span
							className={`${styles.statusDot} ${state?.running ? styles.running : ""}`}
						/>
						{state?.running ? "Агент работает" : "Ожидание"}
					</h1>
				</div>
				<button
					type="button"
					className={styles.stopButton}
					onClick={() => cancelMutation.mutate()}
					disabled={!state?.running || cancelMutation.isPending}
					title="Остановить агента"
				>
					<CircleStop size={17} />
				</button>
			</header>

			{state?.pending_confirmation && (
				<div className={styles.warning}>
					<AlertTriangle size={15} />
					Требуется подтверждение
				</div>
			)}

			<div className={styles.currentCard}>
				<span>Задача</span>
				<p>{state?.goal ? shortText(state.goal, 150) : "Активной задачи нет"}</p>
			</div>

			<div className={styles.actionCard}>
				<span>Сейчас</span>
				<strong>{lastAction?.action || "Думает"}</strong>
				{lastAction?.thought && <p>{shortText(lastAction.thought, 130)}</p>}
			</div>

			<div className={styles.chatPanel}>
				{messages.length === 0 ? (
					<div className={styles.empty}>
						<span>Сообщений пока нет</span>
					</div>
				) : (
					messages.map((message, index) => (
						<div
							key={`${message.role}-${index}`}
							className={`${styles.bubble} ${
								message.role === "user" ? styles.user : styles.assistant
							}`}
						>
							<strong>{message.role === "user" ? "Вы" : "Агент"}</strong>
							<p>{shortText(message.content || "", 260)}</p>
						</div>
					))
				)}
			</div>

			<div className={styles.actionBar}>
				<span>{state?.pending_confirmation ? "Нужно действие пользователя" : "Наблюдение активно"}</span>
				{state?.running && <Loader2 className={styles.spin} size={18} />}
			</div>
		</section>
	);
}
