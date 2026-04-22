import styles from "./ConfirmationPrompt.module.css";
import type { ConfirmationRequest } from "../../types";

interface ConfirmationPromptProps {
	request: ConfirmationRequest;
	onApprove: () => void;
	onReject: () => void;
}

export function ConfirmationPrompt({
	request,
	onApprove,
	onReject,
}: ConfirmationPromptProps) {
	return (
		<div className={styles.overlay} role="presentation">
			<div className={styles.backdrop} onClick={onReject} />
			<div
				className={styles.prompt}
				role="dialog"
				aria-modal="true"
				aria-labelledby="confirmation-title"
			>
				<div id="confirmation-title" className={styles.title}>
					Требуется подтверждение
				</div>
				<div className={styles.message}>{request.message}</div>
				{request.tool && (
					<div className={styles.meta}>
						<span>Инструмент: {request.tool}</span>
						{typeof request.step === "number" && (
							<span>Шаг: {request.step}</span>
						)}
					</div>
				)}
				<div className={styles.actions}>
					<button className={styles.rejectBtn} onClick={onReject}>
						Отклонить
					</button>
					<button className={styles.approveBtn} onClick={onApprove}>
						Подтвердить
					</button>
				</div>
			</div>
		</div>
	);
}
