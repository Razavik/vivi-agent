import {
	Bot,
	BookOpen,
	Cpu,
	MessageSquare,
	Settings,
	Wrench,
} from "lucide-react";
import styles from "./NavBar.module.css";

export type NavPage =
	| "chat"
	| "agents"
	| "tools"
	| "models"
	| "skills"
	| "settings";

interface NavBarProps {
	activePage: NavPage;
	onNavigate: (page: NavPage) => void;
	hasActiveAgents: boolean;
	alertCount?: number;
	pcControlMode: boolean;
}

const ICON_SIZE = 20;

export function NavBar({
	activePage,
	onNavigate,
	hasActiveAgents,
	alertCount = 0,
	pcControlMode,
}: NavBarProps) {
	return (
		<nav className={styles.navbar}>
			<button className={styles.logo} onClick={() => onNavigate("chat")} title="Чат">
				V
			</button>
			<button className={`${styles.navBtn} ${activePage === "chat" ? styles.active : ""}`} onClick={() => onNavigate("chat")} title="Чат">
				<MessageSquare size={ICON_SIZE} />
			</button>
			{!pcControlMode && (
				<button className={`${styles.navBtn} ${activePage === "agents" ? styles.active : ""}`} onClick={() => onNavigate("agents")} title="Агенты">
					{hasActiveAgents && <span className={styles.badge} />}
					{alertCount > 0 && <span className={styles.alertBadge}>{alertCount > 9 ? "9+" : alertCount}</span>}
					<Bot size={ICON_SIZE} />
				</button>
			)}
			{!pcControlMode && (
				<button className={`${styles.navBtn} ${activePage === "tools" ? styles.active : ""}`} onClick={() => onNavigate("tools")} title="Инструменты">
					<Wrench size={ICON_SIZE} />
				</button>
			)}
			<button className={`${styles.navBtn} ${activePage === "models" ? styles.active : ""}`} onClick={() => onNavigate("models")} title="Модели">
				<Cpu size={ICON_SIZE} />
			</button>
			<button className={`${styles.navBtn} ${activePage === "skills" ? styles.active : ""}`} onClick={() => onNavigate("skills")} title="Скиллы">
				<BookOpen size={ICON_SIZE} />
			</button>
			<div className={styles.spacer} />
			<button className={`${styles.navBtn} ${activePage === "settings" ? styles.active : ""}`} onClick={() => onNavigate("settings")} title="Настройки">
				<Settings size={ICON_SIZE} />
			</button>
		</nav>
	);
}
