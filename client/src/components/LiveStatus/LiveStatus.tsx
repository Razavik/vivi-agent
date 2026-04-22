import styles from "./LiveStatus.module.css";

interface LiveStatusProps {
	status: string;
}

export function LiveStatus({ status }: LiveStatusProps) {
	return (
		<div className={styles.liveStatus}>
			<span className={styles.liveStatusDot}></span>
			<span>{status || "Агент думает..."}</span>
		</div>
	);
}
