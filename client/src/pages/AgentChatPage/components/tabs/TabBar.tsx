import styles from "./TabBar.module.css";

type ChatTab = "log" | "artifacts" | "timeline";

interface TabBarProps {
	activeTab: ChatTab;
	onTabChange: (tab: ChatTab) => void;
	developerMode: boolean;
}

export function TabBar({ activeTab, onTabChange, developerMode }: TabBarProps) {
	return (
		<div className={styles.bar}>
			<button
				className={`${styles.btn} ${activeTab === "log" ? styles.active : ""}`}
				onClick={() => onTabChange("log")}
			>
				Лог
			</button>
			{developerMode && (
				<>
					<button
						className={`${styles.btn} ${activeTab === "artifacts" ? styles.active : ""}`}
						onClick={() => onTabChange("artifacts")}
					>
						Артефакты
					</button>
					<button
						className={`${styles.btn} ${activeTab === "timeline" ? styles.active : ""}`}
						onClick={() => onTabChange("timeline")}
					>
						Timeline
					</button>
				</>
			)}
		</div>
	);
}
