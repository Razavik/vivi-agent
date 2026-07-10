import { useState, type RefObject } from "react";
import styles from "./ThoughtBlockInThread.module.css";

interface ThoughtBlockInThreadProps {
	thought: string;
	id: string;
	streaming?: boolean;
	textRef?: RefObject<HTMLDivElement | null>;
}

export function ThoughtBlockInThread({
	thought,
	id,
	streaming = false,
	textRef,
}: ThoughtBlockInThreadProps) {
	const [isOpen, setIsOpen] = useState(true);

	return (
		<div className={styles.messageThoughtWrap}>
			<button className={styles.nativeToggle} onClick={() => setIsOpen(!isOpen)}>
				<span>{streaming ? "Думаю..." : "Thinking"}</span>
				<span className={`${styles.thoughtIcon} ${isOpen ? styles.open : ""}`}>
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
				id={id}
				ref={textRef}
				className={`${styles.messageThought} ${isOpen ? "" : styles.hidden}`}
			>
				{thought}
			</div>
		</div>
	);
}

