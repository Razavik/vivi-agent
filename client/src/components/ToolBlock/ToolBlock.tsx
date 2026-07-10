import { useState } from "react";
import styles from "./ToolBlock.module.css";

interface ToolBlockProps {
	action: string;
	result: unknown;
}

export function ToolBlock({ action, result }: ToolBlockProps) {
	const [isOpen, setIsOpen] = useState(false);

	const formatJson = (value: unknown): string => {
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	};

	const resolveImageDataUrl = (value: unknown): string | null => {
		if (!value || typeof value !== "object") return null;
		const record = value as Record<string, unknown>;
		const webPath = record.web_path;
		if (typeof webPath === "string" && webPath.trim()) return webPath;
		const imageRaw = record.image ?? record.screenshot;
		if (typeof imageRaw !== "string" || !imageRaw.trim()) return null;
		if (imageRaw.startsWith("data:image/")) return imageRaw;
		const formatRaw = record.format;
		const mime =
			typeof formatRaw === "string" && formatRaw.startsWith("image/")
				? formatRaw
				: "image/png";
		return `data:${mime};base64,${imageRaw}`;
	};

	const imageUrl = resolveImageDataUrl(result);
	const hasImagePreview =
		action === "take_screenshot" || action === "read_image" || Boolean(imageUrl);

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
					{hasImagePreview && imageUrl && (
						<div className={styles.previewWrap}>
							<div className={styles.previewLabel}>Что видит агент</div>
							<img
								className={styles.previewImage}
								src={imageUrl}
								alt="Скриншот агента"
								loading="lazy"
							/>
						</div>
					)}
					<pre>
						<code>{formatJson(result)}</code>
					</pre>
				</div>
		</div>
	);
}

