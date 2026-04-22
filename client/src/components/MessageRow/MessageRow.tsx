import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./MessageRow.module.css";
import type { ChatEvent } from "../../types";

interface MessageRowProps {
	message: ChatEvent;
}

export function MessageRow({ message }: MessageRowProps) {
	const [lightbox, setLightbox] = useState<string | null>(null);

	const markdownComponents = {
		pre({ children }: any) {
			return <pre className={styles.codeBlock}>{children}</pre>;
		},
		code({ children, ...props }: any) {
			return (
				<code className={styles.inlineCode} {...props}>
					{children}
				</code>
			);
		},
	};

	return (
		<div
			className={`${styles.eventRow} ${message.role === "user" ? styles.userMessage : styles.answerBlock}`}
		>
			<div className={styles.eventContent}>
				{message.role === "user" && <div className={styles.eventLabel}>Вы</div>}
				{message.images && message.images.length > 0 && (
					<div className={styles.imageGrid}>
						{message.images.map((b64, idx) => (
							<img
								key={idx}
								src={`data:image/png;base64,${b64}`}
								className={styles.messageImage}
								alt={`image-${idx}`}
								onClick={() => setLightbox(`data:image/png;base64,${b64}`)}
							/>
						))}
					</div>
				)}
				{lightbox && (
					<div className={styles.lightboxOverlay} onClick={() => setLightbox(null)}>
						<img
							src={lightbox}
							className={styles.lightboxImage}
							alt="full"
							onClick={(e) => e.stopPropagation()}
						/>
						<button className={styles.lightboxClose} onClick={() => setLightbox(null)}>
							×
						</button>
					</div>
				)}
				<div className={styles.eventText}>
					{message.role === "assistant" ? (
						<ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
							{message.content || ""}
						</ReactMarkdown>
					) : (
						message.content || ""
					)}
				</div>
			</div>
		</div>
	);
}
