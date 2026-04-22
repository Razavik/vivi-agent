import styles from "./AgentsSidebar.module.css";
import { AgentPanel } from "../AgentPanel/AgentPanel";
import type { SubAgentPane } from "../../types";

interface AgentsSidebarProps {
	panes: SubAgentPane[];
}

export function AgentsSidebar({ panes }: AgentsSidebarProps) {
	return (
		<aside className={styles.sidebar}>
			<div className={styles.sidebarHeader}>Агенты</div>
			<div className={styles.list}>
				{panes.length === 0 ? (
					<div className={styles.empty}>
						Активных агентов нет.
						<br />
						Они появятся здесь во время выполнения задач.
					</div>
				) : (
					panes.map((pane) => (
						<AgentPanel key={pane.id} pane={pane} />
					))
				)}
			</div>
		</aside>
	);
}
