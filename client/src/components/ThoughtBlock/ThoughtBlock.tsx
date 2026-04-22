import { useState } from "react";
import styles from "./ThoughtBlock.module.css";

interface ThoughtBlockProps {
	thought: string;
	id: string;
}

export function ThoughtBlock({ thought, id }: ThoughtBlockProps) {
	const [isOpen, setIsOpen] = useState(false);

	return (
		<div className={styles.messageThoughtWrap}>
			<button className={styles.messageThoughtToggle} onClick={() => setIsOpen(!isOpen)}>
				<span>Размышление</span>
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
			<div id={id} className={`${styles.messageThought} ${isOpen ? "" : styles.hidden}`}>
				{thought}
			</div>
		</div>
	);
}
