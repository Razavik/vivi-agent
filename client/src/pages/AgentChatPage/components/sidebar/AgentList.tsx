import styles from "./AgentList.module.css";
import { AgentCard } from "./AgentCard";
import type { SubAgentPane } from "../../../../types";

interface AgentListProps {
	panes: SubAgentPane[];
	selectedId: string;
	onSelect: (id: string) => void;
	onClearAgent: (name: string) => void;
	onClearAll: () => void;
}

export function AgentList({
	panes,
	selectedId,
	onSelect,
	onClearAgent,
	onClearAll,
}: AgentListProps) {
	return (
		<aside className={styles.sidebar}>
			<div className={styles.header}>
				<span>Агенты</span>
				<button
					className={styles.clearAllBtn}
					onClick={onClearAll}
					title="Очистить память всех агентов"
				>
					Очистить все
				</button>
			</div>
			<div className={styles.list}>
				{panes.map((pane) => (
					<AgentCard
						key={pane.id}
						displayName={pane.displayName}
						task={pane.task}
						status={pane.status}
						selected={selectedId === pane.id}
						onClick={() => onSelect(pane.id)}
						onClear={() => onClearAgent(pane.name)}
					/>
				))}
			</div>
		</aside>
	);
}
