import styles from "./ChatHeader.module.css";

interface ChatHeaderProps {
	onClearHistory: () => void;
	onClearLogs: () => void;
	isBusy: boolean;
	contextTokens: number;
}

export function ChatHeader({
	onClearHistory,
	onClearLogs,
	isBusy,
	contextTokens,
}: ChatHeaderProps) {
	return (
		<div className={styles.chatHeader}>
			<div className={styles.titleSection}>
				<h2 className={styles.chatTitle}>Vivi</h2>
				{contextTokens > 0 && (
					<span className={styles.tokenCounter}>{contextTokens} токенов</span>
				)}
			</div>
			<div className={styles.headerActions}>
				<button
					className={styles.iconBtn}
					onClick={onClearHistory}
					disabled={isBusy}
					title="Очистить историю"
				>
					<svg
						width="15"
						height="15"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<polyline points="3 6 5 6 21 6" />
						<path d="M19 6l-1 14H6L5 6" />
						<path d="M10 11v6M14 11v6" />
						<path d="M9 6V4h6v2" />
					</svg>
					История
				</button>
				<button
					className={styles.iconBtn}
					onClick={onClearLogs}
					disabled={isBusy}
					title="Очистить логи"
				>
					<svg
						width="15"
						height="15"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
						<polyline points="14 2 14 8 20 8" />
						<line x1="9" y1="13" x2="15" y2="13" />
						<line x1="9" y1="17" x2="12" y2="17" />
					</svg>
					Логи
				</button>
			</div>
		</div>
	);
}
