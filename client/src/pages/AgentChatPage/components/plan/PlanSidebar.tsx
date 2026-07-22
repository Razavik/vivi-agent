import styles from "./PlanSidebar.module.css";
import type { SubAgentPane, PlanItem } from "../../../../types";

function getPlanForPane(pane: SubAgentPane): PlanItem[] {
	if (pane.plan && pane.plan.length > 0) return pane.plan;
	const lastSession = pane.sessions?.[pane.sessions.length - 1];
	return lastSession?.plan ?? [];
}

export interface TelegramStyleProps {
	draft: string;
	current: string | null;
	saving: boolean;
	error: string | null;
	open: boolean;
	onToggleOpen: () => void;
	onDraftChange: (value: string) => void;
	onSave: () => void;
}

interface PlanSidebarProps {
	pane: SubAgentPane;
	width: number;
	telegramStyle?: TelegramStyleProps;
}

export function PlanSidebar({ pane, width, telegramStyle }: PlanSidebarProps) {
	const plan = getPlanForPane(pane);

	return (
		<aside className={styles.sidebar} style={{ width }}>
			{pane.name === "telegram" && telegramStyle && (
				<div className={styles.styleSection}>
					<button
						className={styles.styleToggleBtn}
						onClick={telegramStyle.onToggleOpen}
					>
						Стиль общения {telegramStyle.open ? "▾" : "▸"}
					</button>
					{telegramStyle.open && (
						<div className={styles.stylePanel}>
							<p>
								Агент подстраивает переписку под этот текст (тон,
								длина фраз, эмодзи). Можно изменить вручную или
								попросить агента выучить стиль заново по своим
								сообщениям — оба способа пишут в один и тот же
								файл. Доступно в любой момент, вне зависимости от
								того, запущен агент сейчас или нет.
							</p>
							<textarea
								className={styles.styleTextarea}
								value={telegramStyle.draft}
								onChange={(e) =>
									telegramStyle.onDraftChange(e.target.value)
								}
								placeholder="Не определён — агент выучит стиль сам при первой переписке, либо впиши описание вручную (тон, длина, эмодзи, обращения)."
								maxLength={2000}
							/>
							<div className={styles.styleFooter}>
								<button
									className={styles.styleSaveBtn}
									disabled={
										telegramStyle.saving ||
										telegramStyle.draft ===
											(telegramStyle.current ?? "")
									}
									onClick={telegramStyle.onSave}
								>
									{telegramStyle.saving ? "Сохраняю…" : "Сохранить"}
								</button>
								{telegramStyle.error ? (
									<span className={styles.styleError}>
										{telegramStyle.error}
									</span>
								) : (
									<span className={styles.styleHint}>
										{telegramStyle.draft.length}/2000
									</span>
								)}
							</div>
						</div>
					)}
				</div>
			)}
			{plan.length > 0 && (
				<div className={styles.planGraph}>
					<div className={styles.planGraphHeader}>Шаги плана</div>
					<div className={styles.planGraphList}>
						{plan.map((item, index) => (
							<div
								key={index}
								className={`${styles.planGraphItem} ${styles[item.status]}`}
							>
								<div className={styles.planGraphIcon}>
									{item.status === "completed" && "✓"}
									{item.status === "in_progress" && "⟳"}
									{item.status === "pending" && "○"}
								</div>
								<div className={styles.planGraphContent}>
									<div className={styles.planGraphText}>
										{item.content}
									</div>
									{index < plan.length - 1 && (
										<div className={styles.planGraphLine} />
									)}
								</div>
							</div>
						))}
					</div>
				</div>
			)}
			{plan.length === 0 && (
				<div className={styles.focusCard}>
					<div className={styles.emptyTitle}>
						План ещё не сформирован
					</div>
					<div className={styles.emptyText}>
						Как только появятся шаги, здесь останется только
						короткая сводка без лишнего шума.
					</div>
				</div>
			)}
		</aside>
	);
}
