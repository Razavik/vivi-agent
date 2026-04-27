import type { SupervisorAlert } from "../../types";
import styles from "./SupervisorAlerts.module.css";

const ALERT_LABELS: Record<string, string> = {
	hang_detected: "Зависание",
	stale_paused: "Долгая пауза",
	waiting_timeout: "Ожидание ввода",
	deadlock_detected: "Deadlock",
};

interface Props {
	alerts: SupervisorAlert[];
	onDismiss: (timestamp: number) => void;
	onDismissAll: () => void;
}

export function SupervisorAlerts({ alerts, onDismiss, onDismissAll }: Props) {
	if (alerts.length === 0) return null;

	return (
		<div className={styles.container}>
			<div className={styles.header}>
				<span className={styles.title}>Supervisor-алерты</span>
				<button className={styles.dismissAll} onClick={onDismissAll}>
					Скрыть все
				</button>
			</div>
			{alerts.map((alert) => {
				const idleSeconds =
					typeof alert.payload.idle_seconds === "number"
						? `${Math.round(alert.payload.idle_seconds)}с`
						: "";
				return (
				<div key={alert.timestamp} className={`${styles.alert} ${styles[alert.payload.type] ?? ""}`}>
					<div className={styles.alertTop}>
						<span className={styles.alertType}>
							{ALERT_LABELS[alert.payload.type] ?? alert.payload.type}
						</span>
						{alert.payload.agent_name && (
							<span className={styles.alertAgent}>{alert.payload.agent_name}</span>
						)}
						{idleSeconds && <span className={styles.alertIdle}>{idleSeconds}</span>}
						<button className={styles.close} onClick={() => onDismiss(alert.timestamp)}>
							✕
						</button>
					</div>
					<div className={styles.alertMessage}>{alert.payload.message}</div>
					{alert.payload.task && (
						<div className={styles.alertTask} title={alert.payload.task}>
							{alert.payload.task}
						</div>
					)}
				</div>
				);
			})}
		</div>
	);
}
