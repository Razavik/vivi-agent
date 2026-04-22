import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./AgentPanel.module.css";
import type { SubAgentPane } from "../../types";

interface AgentPanelProps {
	pane: SubAgentPane;
}

export function AgentPanel({ pane }: AgentPanelProps) {
	const [expanded, setExpanded] = useState(true);

	const dotClass = `${styles.dot} ${styles[pane.status]}`;
	const panelClass = `${styles.panel} ${styles[pane.status]}`;

	return (
		<div className={panelClass}>
			<div className={styles.header} onClick={() => setExpanded((v) => !v)}>
				<span className={dotClass} />
				<span className={styles.agentName}>{pane.displayName}</span>
				{pane.steps.length > 0 && (
					<span className={styles.stepCount}>{pane.steps.length}</span>
				)}
				<span className={`${styles.chevron} ${expanded ? styles.open : ""}`}>▼</span>
			</div>

			{expanded && (
				<>
					<div className={styles.task} title={pane.task}>
						{pane.task}
					</div>

					{pane.steps.length > 0 && (
						<div className={styles.body}>
							{pane.steps.map((s, i) => {
								const hasResult = s.result !== undefined;
								const actionClass = hasResult
									? s.success
										? styles.success
										: styles.fail
									: styles.pending;
								return (
									<div className={styles.stepRow} key={i}>
										<span className={styles.stepNum}>{s.step}</span>
										<div style={{ flex: 1, minWidth: 0 }}>
											{s.action && (
												<div
													className={`${styles.stepAction} ${actionClass}`}
												>
													{s.action}
												</div>
											)}
											{s.thought && (
												<div className={styles.stepThought}>
													{s.thought}
												</div>
											)}
										</div>
									</div>
								);
							})}
						</div>
					)}

					{pane.question && (
						<div className={styles.question}>
							<div className={styles.questionLabel}>Вопрос директору:</div>
							<div>{pane.question}</div>
						</div>
					)}

					{pane.answer && (
						<div className={styles.answer}>
							<div className={styles.answerLabel}>Ответ:</div>
							<div>{pane.answer}</div>
						</div>
					)}

					{pane.result && (
						<div className={styles.result}>
							<ReactMarkdown remarkPlugins={[remarkGfm]}>{pane.result}</ReactMarkdown>
						</div>
					)}
				</>
			)}
		</div>
	);
}
