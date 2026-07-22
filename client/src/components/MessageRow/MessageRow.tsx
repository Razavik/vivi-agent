import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./MessageRow.module.css";
import type { ChatEvent } from "../../types";
import { ImageThumbGrid } from "../ImageThumbGrid/ImageThumbGrid";
import { isWindowsPath, openPath } from "../../utils/openPath";
import { extractMarkdownImages, normalizeAssistantText } from "../../utils/renderText";

interface MessageRowProps {
	message: ChatEvent;
}

const markdownComponents: Components = {
	pre({ children }) {
		return <pre className={styles.codeBlock}>{children}</pre>;
	},
	code({ children, ...props }) {
		const text = typeof children === "string" ? children : String(children ?? "");
		if (isWindowsPath(text)) {
			return (
				<code
					className={`${styles.inlineCode} ${styles.pathLink}`}
					title="Открыть в проводнике"
					onClick={() => void openPath(text.trim())}
					{...props}
				>
					{text}
				</code>
			);
		}
		return (
			<code className={styles.inlineCode} {...props}>
				{children}
			</code>
		);
	},
};

export function MessageRow({ message }: MessageRowProps) {
	const isAssistant = message.role === "assistant";
	// Картинки, встроенные оператором/саб-агентом в текст (finish_task(attach_images=true)
	// — URL артефакта /api/artifact-image/...), вырезаются из markdown и рисуются
	// отдельной сеткой маленьких превью — как и вложения пользователя, одним и тем же
	// компонентом с общим lightbox, а не полноразмерными блоками прямо в тексте.
	const { text: displayText, images: markdownImages } = isAssistant
		? extractMarkdownImages(normalizeAssistantText(message.content || ""))
		: { text: message.content || "", images: [] as string[] };

	const uploadedImages = (message.images ?? []).map(
		(b64) => `data:image/png;base64,${b64}`,
	);
	const allImages = [...uploadedImages, ...markdownImages];

	return (
		<div
			className={`${styles.eventRow} ${message.role === "user" ? styles.userMessage : styles.answerBlock}`}
		>
			<div className={styles.eventContent}>
				{message.role === "user" && <div className={styles.eventLabel}>Вы</div>}
				<ImageThumbGrid images={allImages} />
				<div className={styles.eventText}>
					{isAssistant ? (
						<ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
							{displayText}
						</ReactMarkdown>
					) : (
						message.content || ""
					)}
				</div>
			</div>
		</div>
	);
}
