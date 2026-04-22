import { useState } from "react";
import styles from "./ToolBlock.module.css";

interface ToolBlockProps {
	action: string;
	result: any;
}

export function ToolBlock({ action, result }: ToolBlockProps) {
	const [isOpen, setIsOpen] = useState(false);

	const formatJson = (value: any): string => {
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	};

	return (
		<div className={styles.toolWrap}>
			<button
				className={styles.toolToggle}
				onClick={() => setIsOpen(!isOpen)}
			>
				<span>Инструмент: {action}</span>
				<span
					className={`${styles.toolIcon} ${isOpen ? styles.open : ""}`}
				>
					<svg
						width="12"
						height="12"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<path d="M9 18l6-6-6-6" />
					</svg>
				</span>
			</button>
			<div
				className={`${styles.toolResult} ${isOpen ? "" : styles.hidden}`}
			>
				<pre>
					<code>{formatJson(result)}</code>
				</pre>
			</div>
		</div>
	);
}
