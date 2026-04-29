import styles from "./NavBar.module.css";

export type NavPage = "chat" | "agents" | "tools" | "settings" | "runs" | "bus" | "crashes" | "diagnostics" | "ops";

interface NavBarProps {
	activePage: NavPage;
	onNavigate: (page: NavPage) => void;
	hasActiveAgents: boolean;
	alertCount?: number;
}

export function NavBar({ activePage, onNavigate, hasActiveAgents, alertCount = 0 }: NavBarProps) {
	return (
		<nav className={styles.navbar}>
			<div className={styles.logo}>V</div>

			<button
				className={`${styles.navBtn} ${activePage === "runs" ? styles.active : ""}`}
				onClick={() => onNavigate("runs")}
				title="Runs Dashboard"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<rect x="3" y="3" width="18" height="18" rx="2" />
					<line x1="3" y1="9" x2="21" y2="9" />
					<line x1="3" y1="15" x2="21" y2="15" />
					<line x1="9" y1="9" x2="9" y2="21" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "chat" ? styles.active : ""}`}
				onClick={() => onNavigate("chat")}
				title="Чат"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "agents" ? styles.active : ""}`}
				onClick={() => onNavigate("agents")}
				title="Агенты"
			>
				{hasActiveAgents && <span className={styles.badge} />}
				{alertCount > 0 && (
					<span className={styles.alertBadge}>{alertCount > 9 ? "9+" : alertCount}</span>
				)}
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<circle cx="12" cy="8" r="4" />
					<path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "tools" ? styles.active : ""}`}
				onClick={() => onNavigate("tools")}
				title="Инструменты"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "bus" ? styles.active : ""}`}
				onClick={() => onNavigate("bus")}
				title="MessageBus"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "crashes" ? styles.active : ""}`}
				onClick={() => onNavigate("crashes")}
				title="Crash Reports"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
					<line x1="12" y1="9" x2="12" y2="13" />
					<line x1="12" y1="17" x2="12.01" y2="17" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "diagnostics" ? styles.active : ""}`}
				onClick={() => onNavigate("diagnostics")}
				title="Diagnostics"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<path d="M22 12h-4l-3 8L9 4l-3 8H2" />
					<circle cx="12" cy="12" r="10" opacity="0.25" />
				</svg>
			</button>

			<button
				className={`${styles.navBtn} ${activePage === "ops" ? styles.active : ""}`}
				onClick={() => onNavigate("ops")}
				title="Agent Ops"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<path d="M12 2v4" />
					<path d="M12 18v4" />
					<path d="m4.93 4.93 2.83 2.83" />
					<path d="m16.24 16.24 2.83 2.83" />
					<path d="M2 12h4" />
					<path d="M18 12h4" />
					<circle cx="12" cy="12" r="4" />
				</svg>
			</button>

			<div className={styles.spacer} />

			<button
				className={`${styles.navBtn} ${activePage === "settings" ? styles.active : ""}`}
				onClick={() => onNavigate("settings")}
				title="Настройки моделей"
			>
				<svg
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					strokeWidth="2"
					strokeLinecap="round"
					strokeLinejoin="round"
				>
					<circle cx="12" cy="12" r="3" />
					<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
				</svg>
			</button>
		</nav>
	);
}
