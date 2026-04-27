import { useRef } from "react";
import styles from "./Composer.module.css";
import { LiveStatus } from "../LiveStatus/LiveStatus";

interface ComposerProps {
	task: string;
	images: string[];
	onTaskChange: (value: string) => void;
	onImagesChange: (images: string[]) => void;
	onRun: () => void;
	onStop: () => void;
	isRunning: boolean;
	liveStatus: string;
}

export function Composer({
	task,
	images,
	onTaskChange,
	onImagesChange,
	onRun,
	onStop,
	isRunning,
	liveStatus,
}: ComposerProps) {
	const fileInputRef = useRef<HTMLInputElement>(null);

	const readFilesAsBase64 = (files: File[]): Promise<string[]> => {
		const imageFiles = files.filter((f) => f.type.startsWith("image/"));
		return Promise.all(
			imageFiles.map(
				(file) =>
					new Promise<string>((resolve) => {
						const reader = new FileReader();
						reader.onload = () => resolve((reader.result as string).split(",")[1]);
						reader.readAsDataURL(file);
					}),
			),
		);
	};

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = Array.from(e.target.files || []);
		e.target.value = "";
		if (!files.length) return;
		readFilesAsBase64(files).then((b64s) => {
			if (b64s.length > 0) onImagesChange([...images, ...b64s]);
		});
	};

	const removeImage = (idx: number) => {
		onImagesChange(images.filter((_, i) => i !== idx));
	};

	const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
		const items = Array.from(e.clipboardData.items);
		const imageItems = items.filter((item) => item.type.startsWith("image/"));
		if (imageItems.length === 0) return;
		e.preventDefault();
		const readers = imageItems.map(
			(item) =>
				new Promise<string>((resolve) => {
					const file = item.getAsFile();
					if (!file) return;
					const reader = new FileReader();
					reader.onload = () => {
						const result = reader.result as string;
						resolve(result.split(",")[1]);
					};
					reader.readAsDataURL(file);
				}),
		);
		Promise.all(readers).then((b64s) => {
			onImagesChange([...images, ...b64s.filter(Boolean)]);
		});
	};

	return (
		<div className={styles.composer}>
			{isRunning && <LiveStatus status={liveStatus} />}
			<div className={styles.composerRow}>
				{images.length > 0 && (
					<div className={styles.imagePreviewRow}>
						{images.map((b64, idx) => (
							<div key={idx} className={styles.imagePreviewItem}>
								<img
									src={`data:image/png;base64,${b64}`}
									className={styles.imagePreviewThumb}
									alt={`attachment-${idx}`}
								/>
								<button
									className={styles.imageRemoveBtn}
									onClick={() => removeImage(idx)}
									title="Удалить"
								>
									×
								</button>
							</div>
						))}
					</div>
				)}
				<div className={styles.inputRow}>
					<input
						ref={fileInputRef}
						type="file"
						accept="image/*"
						multiple
						style={{ display: "none" }}
						onChange={handleFileChange}
					/>
					<textarea
						value={task}
						onChange={(e) => onTaskChange(e.target.value)}
						placeholder="Введите запрос..."
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey && !isRunning) {
								e.preventDefault();
								onRun();
							}
						}}
						onPaste={handlePaste}
					/>
					<button
						className={styles.attachBtn}
						onClick={() => fileInputRef.current?.click()}
						title="Прикрепить изображение"
						disabled={isRunning}
					>
						<svg
							width="18"
							height="18"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2"
							strokeLinecap="round"
							strokeLinejoin="round"
						>
							<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
							<circle cx="8.5" cy="8.5" r="1.5" />
							<polyline points="21 15 16 10 5 21" />
						</svg>
					</button>
					<button className={styles.sendBtn} onClick={isRunning ? onStop : onRun}>
						{isRunning ? (
							<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
								<rect x="6" y="6" width="12" height="12" />
							</svg>
						) : (
							<svg
								width="16"
								height="16"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="3"
								strokeLinecap="round"
								strokeLinejoin="round"
							>
								<path d="M5 12h14M12 5l7 7-7 7" />
							</svg>
						)}
					</button>
				</div>
			</div>
			<div className={styles.hint}>
				Agent 1 может допускать ошибки. Проверяйте важную информацию.
			</div>
		</div>
	);
}
