import { useRef } from "react";
import {
	ImagePlus,
	SendHorizontal,
	Square,
	Trash2,
	X,
} from "lucide-react";
import styles from "./Composer.module.css";
import { LiveStatus } from "../LiveStatus/LiveStatus";
import { Select } from "../Select/Select";

interface ModelOption {
	value: string;
	label: string;
}

interface ComposerProps {
	task: string;
	images: string[];
	contextTokens: number;
	contextLimit: number;
	selectedModel: string;
	modelOptions: ModelOption[];
	onClearHistory: () => void;
	onClearLogs: () => void;
	onModelChange: (value: string) => void;
	onTaskChange: (value: string) => void;
	onImagesChange: (images: string[]) => void;
	onRun: () => void;
	onStop: () => void;
	isRunning: boolean;
	liveStatus: string;
	pcControlMode: boolean;
	onPcControlModeChange: (enabled: boolean) => void;
}

export function Composer({
	task,
	images,
	contextTokens,
	contextLimit,
	selectedModel,
	modelOptions,
	onClearHistory,
	onClearLogs,
	onModelChange,
	onTaskChange,
	onImagesChange,
	onRun,
	onStop,
	isRunning,
	liveStatus,
	pcControlMode,
	onPcControlModeChange,
}: ComposerProps) {
	const fileInputRef = useRef<HTMLInputElement>(null);
	const tokenPercent = Math.max(
		0,
		Math.min(
			100,
			Math.round((contextTokens / Math.max(contextLimit, 1)) * 100),
		),
	);
	const selectedModelLabel =
		modelOptions.find((opt) => opt.value === selectedModel)?.label ||
		selectedModel ||
		"Выбрать модель";

	const readFilesAsBase64 = (files: File[]): Promise<string[]> => {
		const imageFiles = files.filter((f) => f.type.startsWith("image/"));
		return Promise.all(
			imageFiles.map(
				(file) =>
					new Promise<string>((resolve) => {
						const reader = new FileReader();
						reader.onload = () =>
							resolve((reader.result as string).split(",")[1]);
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
		const imageItems = items.filter((item) =>
			item.type.startsWith("image/"),
		);
		if (imageItems.length === 0) return;
		e.preventDefault();
		const readers = imageItems.map(
			(item) =>
				new Promise<string>((resolve) => {
					const file = item.getAsFile();
					if (!file) return resolve("");
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
									<X size={12} />
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
					<div className={styles.textareaWrapper}>
						<textarea
							value={task}
							onChange={(e) => onTaskChange(e.target.value)}
							placeholder="Введите запрос..."
							onKeyDown={(e) => {
								if (
									e.key === "Enter" &&
									!e.shiftKey &&
									!isRunning
								) {
									e.preventDefault();
									onRun();
								}
							}}
							onPaste={handlePaste}
						/>
					</div>
					<div className={styles.buttonsWrapper}>
						<div className={styles.controlStrip}>
							<div className={styles.actionGroup}>
								<button
									className={`${styles.actionBtn} ${styles.clearButton}`}
									onClick={() => {
										onClearHistory();
										onClearLogs();
									}}
									disabled={isRunning}
									title="Очистить историю и логи"
								>
									<Trash2 size={15} />
									Очистить всё
								</button>
								<label
									className={styles.pcModeToggle}
									title="Режим управления ПК"
								>
									<input
										type="checkbox"
										checked={pcControlMode}
										onChange={(e) =>
											onPcControlModeChange(
												e.target.checked,
											)
										}
									/>
									<span className={styles.pcModeTextGroup}>
										<span className={styles.pcModeLabel}>
											ПК
										</span>
									</span>
									<span className={styles.pcModeSwitch}>
										<span className={styles.pcModeThumb} />
									</span>
								</label>
								<div className={styles.modelMenuWrap}>
									<Select
										value={selectedModel}
										onChange={onModelChange}
										options={modelOptions}
										placeholder={selectedModelLabel}
										className={styles.modelSelect}
										style={{
											width: "156px",
											minWidth: "156px",
											maxWidth: "156px",
										}}
									/>
								</div>
							</div>
						</div>
						<div className={styles.rightControls}>
							<button
								className={styles.attachCircleBtn}
								onClick={() => fileInputRef.current?.click()}
								title="Прикрепить изображение"
								disabled={isRunning}
							>
								<ImagePlus size={20} />
							</button>
							<div className={styles.contextOrbGroup}>
								<button
									type="button"
									className={styles.contextOrb}
									style={{
										["--context-fill" as string]: `${tokenPercent}%`,
									}}
									aria-label={`Контекстное окно ${tokenPercent} процентов`}
									title="Контекстное окно"
								>
									<span className={styles.contextOrbInner}>
										<span
											className={styles.contextOrbValue}
										>
										</span>
									</span>
								</button>
								<div
									className={styles.contextTooltip}
									role="status"
									aria-live="polite"
								>
									<div className={styles.contextTooltipTitle}>
										Контекстное окно
									</div>
									<div
										className={styles.contextTooltipPercent}
									>
										{tokenPercent}% заполнено
									</div>
									<div className={styles.contextTooltipScale}>
										<div
											className={
												styles.contextTooltipScaleFill
											}
											style={{
												width: `${tokenPercent}%`,
											}}
										/>
									</div>
									<div
										className={styles.contextTooltipTokens}
									>
										{contextTokens > 0 &&
											`Использовано ${contextTokens.toLocaleString()} токенов`}
									</div>
								</div>
							</div>
							<button
								className={styles.sendBtn}
								onClick={isRunning ? onStop : onRun}
							>
								{isRunning ? (
									<Square size={16} fill="currentColor" />
								) : (
									<SendHorizontal size={16} />
								)}
							</button>
						</div>
					</div>
				</div>
			</div>
			<div className={styles.hint}>
				Agent 1 может допускать ошибки. Проверяй важную информацию.
			</div>
		</div>
	);
}
