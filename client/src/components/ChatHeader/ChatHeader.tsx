import styles from "./ChatHeader.module.css";

interface ChatHeaderProps {}

export function ChatHeader(_props: ChatHeaderProps) {
	return (
		<div className={styles.chatHeader}>
			<div className={styles.titleSection}>
				<h2 className={styles.chatTitle}>Vivi</h2>
			</div>
		</div>
	);
}
